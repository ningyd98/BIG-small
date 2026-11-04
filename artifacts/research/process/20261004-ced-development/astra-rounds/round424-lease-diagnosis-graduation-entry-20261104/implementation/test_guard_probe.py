"""SOFTWARE_ONLY independent guard probe, never a replacement for the old test."""

import json
import multiprocessing
import os
from pathlib import Path
from queue import Empty
import sys
import time

import pytest

from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from tests.test_rgbd_lease_handoff import _competing_guard_process

REPOSITORY = str(Path('/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py'))


def record(path, event, **values):
    row = {'event': event, 'pid': os.getpid(), 'monotonic_ns': time.monotonic_ns(), **values}
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def child(database, queue, command, log, preinitialize):
    def observe(frame, event, arg):
        if frame.f_code.co_filename != REPOSITORY:
            return None
        if frame.f_code.co_name not in {'__init__', '_initialize', 'publication_guard'}:
            return None
        if event in {'call', 'return', 'exception'} or (
            event == 'line' and frame.f_code.co_name == 'publication_guard'
            and frame.f_lineno in {504, 505}
        ):
            record(log, 'child_trace', function=frame.f_code.co_name, kind=event,
                   line=frame.f_lineno)
        return observe

    sys.settrace(observe)
    record(log, 'before_constructor', preinitialize=preinitialize)
    try:
        if not preinitialize:
            # Calls the frozen original helper, including its original constructor and messages.
            _competing_guard_process(Path(database), queue)
        else:
            repo = SQLiteSimulationJobRepository(Path(database))
            record(log, 'after_constructor')
            queue.put('ready')
            assert command.get(timeout=5) == 'enter_guard'
            with repo.publication_guard():
                queue.put('acquired')
        record(log, 'child_completed')
    finally:
        sys.settrace(None)


def wait_for_flock(path):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        if any(row.get('event') == 'child_trace' and row.get('kind') == 'line'
               and row.get('line') == 504 for row in rows):
            return rows
        time.sleep(0.01)
    raise AssertionError('child never reached the real flock call')


def test_guard_initialization_handshake(tmp_path):
    evidence = Path(os.environ['R424_GUARD_EVIDENCE'])
    evidence.mkdir(exist_ok=False)
    context = multiprocessing.get_context('spawn')
    summary = []
    for preinitialize in (False, True):
        label = 'original_constructor_inside_parent_guard' if not preinitialize else 'preinitialized_control'
        log = evidence / (label + '.jsonl')
        database = tmp_path / (label + '.db')
        first = SQLiteSimulationJobRepository(database)
        second = SQLiteSimulationJobRepository(database)
        messages, command = context.Queue(), context.Queue()
        process = context.Process(target=child, args=(str(database), messages, command, str(log), preinitialize))
        try:
            if preinitialize:
                process.start()
                assert messages.get(timeout=5) == 'ready'
                # A fresh segment makes the observed flock the guard requested after ready.
                initial_lines = len(log.read_text().splitlines())
            else:
                initial_lines = 0
            with first.publication_guard(), second.publication_guard():
                record(log, 'parent_guard_held')
                if not preinitialize:
                    process.start()
                else:
                    command.put('enter_guard')
                deadline = time.monotonic() + 5
                while True:
                    rows = wait_for_flock(log)
                    segment = rows[initial_lines:]
                    if any(row.get('event') == 'child_trace' and row.get('kind') == 'line'
                           and row.get('line') == 504 for row in segment):
                        break
                    assert time.monotonic() < deadline, 'control did not request its guard'
                    time.sleep(0.01)
                with pytest.raises(Empty):
                    messages.get(timeout=0.1)
                assert process.is_alive()
                rows = [json.loads(line) for line in log.read_text().splitlines()]
                segment = rows[initial_lines:]
                assert not any(row.get('event') == 'child_trace' and row.get('kind') == 'line'
                               and row.get('line') == 505 for row in segment)
                record(log, 'parent_before_release_child_at_flock', preinitialize=preinitialize)
            record(log, 'parent_guard_released')
            received = [messages.get(timeout=5)]
            if not preinitialize:
                assert received == ['waiting']
                received.append(messages.get(timeout=5))
            assert received[-1] == 'acquired'
            process.join(timeout=5)
            assert process.exitcode == 0
            summary.append({'case': label, 'messages_after_release': received,
                            'child_pid': process.pid, 'child_exitcode': process.exitcode,
                            'same_thread_two_repositories_reentrant': True})
        finally:
            if process.pid is not None and process.is_alive():
                process.terminate()
                process.join(timeout=5)
            messages.close()
            messages.join_thread()
            command.close()
            command.join_thread()
    with (evidence / 'summary.json').open('x') as stream:
        json.dump({'scope': 'SOFTWARE_ONLY_DIAGNOSIS', 'cases': summary}, stream, indent=2)
        stream.write('\n')
