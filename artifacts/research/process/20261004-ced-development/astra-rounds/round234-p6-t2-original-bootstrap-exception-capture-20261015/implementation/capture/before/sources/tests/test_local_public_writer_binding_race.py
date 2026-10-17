"""R223 real public precheck/inner-lock races; no synthetic binding authority."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading

import pytest

from tests import test_operational_runtime_closure as _frozen


def _r223_plain(value):
    return _frozen._b_t2_plain(value)


def _r223_save(root, nodeid, value):
    directory = Path(root)
    assert directory.is_dir() and not directory.is_symlink()
    path = directory / (hashlib.sha256(nodeid.encode()).hexdigest() + '.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(_r223_plain(value), stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


@contextmanager
def _r223_observe(monkeypatch, request):
    value = {
        'schema_version': 'bigsmall.r158-t2-resource.v1', 'round': 'R223',
        'command_id': 'R223', 'nodeid': request.node.nodeid, 'pid': os.getpid(),
        'scenario': request.node.name, 'entered_contract_guard': True, 'entered_behavior': True,
        'allocation_attempts': 0, 'resources': [], 'worker_lifecycles': [], 'cleanup_errors': [],
        'observations': {'assertions_completed': False, 'observers_restored': False, 'scenarios': []},
        'unobserved': {'OS_handles': None, 'external_models': None, 'GPU_native': None, 'network_calls': None},
    }
    try:
        with _frozen._b_t2_observe(monkeypatch, value) as observed:
            yield observed
            value['observations']['assertions_completed'] = True
    finally:
        error_type, error, _ = sys.exc_info()
        value['observations']['exit_exception'] = None if error_type is None else {
            'type': error_type.__name__, 'message': str(error)}
        value['allocation_attempts'] = len(value['resources'])
        _r223_save(os.environ['BIGSMALL_R223_RESOURCE_ROOT'], request.node.nodeid, value)


def _r223_legacy_state(events, task):
    from cloud_edge_robot_arm.repositories.event_autonomy import InMemoryEventAutonomyRepository

    lock = events._lock if type(events) is InMemoryEventAutonomyRepository else events._write_lock
    with lock:
        if type(events) is InMemoryEventAutonomyRepository:
            return {'present': task in events._states, 'value': events._states.get(task)}
        return [dict(row) for row in events._conn.execute(
            'SELECT * FROM event_mode_states WHERE task_id=? ORDER BY task_id', (task,))]


def _r223_bound(events, task):
    from cloud_edge_robot_arm.repositories.event_autonomy import InMemoryEventAutonomyRepository
    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import local_get_unlocked

    lock = events._lock if type(events) is InMemoryEventAutonomyRepository else events._write_lock
    with lock:
        return local_get_unlocked(events, 'binding', task)


def _r223_operation_rows(events, reads, operation_id):
    from cloud_edge_robot_arm.repositories.event_autonomy import (
        InMemoryEventAutonomyRepository, SQLiteEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import local_receipt_read_unlocked

    if type(events) is SQLiteEventAutonomyRepository:
        return _frozen._b_t2_operation_rows(reads, operation_id)
    if type(events) is not InMemoryEventAutonomyRepository:
        raise TypeError('R223 requires an exact Memory or SQLite event repository')
    with events._lock:
        receipt = local_receipt_read_unlocked(events, operation_id)
    job_rows = [dict(row) for row in reads['job'].execute(
        'SELECT * FROM simulation_local_publications_v1 WHERE operation_id=?', (operation_id,))]
    return {'event': [] if receipt is None else [receipt], 'job': job_rows}


def _r223_run(monkeypatch, directory, backend, observed, *, mode, second=False):
    from cloud_edge_robot_arm.repositories.event_autonomy import (
        InMemoryEventAutonomyRepository, SQLiteEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime
    from tests.test_visual_worker_factory import software_factory

    directory.mkdir(parents=True, exist_ok=False)
    ready, entered, release = threading.Event(), threading.Event(), threading.Event()
    observed.release_events.append(release)
    writer = None
    events = None
    reads = {}
    data = {}
    case = {'mode': mode, 'backend': backend, 'second_connection': second, 'order': [],
            'writer': {'attempted': False, 'returned': False, 'exception': None},
            'bootstrap_complete': False, 'binding': None, 'before': None, 'after': None}
    observed.value['observations']['r223'] = case
    observed.value['observations']['scenarios'].append(case)
    order_lock = threading.Lock()

    def record(kind, **details):
        with order_lock:
            case['order'].append({'sequence': len(case['order']) + 1, 'kind': kind,
                                  'pid': os.getpid(), 'thread': threading.get_ident(),
                                  'native_thread': threading.get_native_id(), **details})

    def writer_body():
        target = None
        try:
            target = SQLiteEventAutonomyRepository(events.path) if second else events
            data['writer_repository'] = target
            data['writer_code'] = type(target).save_state.__wrapped__.__code__
            record('WRITER_READY', repository=id(target), connection=None if backend == 'memory' else id(target._conn))
            ready.set()
            assert data['start'].wait(10), 'R223 writer start barrier timed out'
            case['writer']['attempted'] = True
            target.save_state(data['task'], 'RUNNING', 'R223 positive public writer')
            case['writer']['returned'] = True
            record('WRITER_RETURNED')
        except BaseException as error:
            case['writer']['exception'] = {'type': type(error).__name__, 'message': str(error)}
            data['writer_error'] = error
            record('WRITER_RAISED', exception=case['writer']['exception'])
        finally:
            if second and target is not None:
                target.close()
            ready.set()
            data['finished'].set()

    def observe_entry(frame, event, arg):
        if event != 'call':
            return
        if (frame.f_code is VisualWorkerRuntime._initialize_local.__code__
                and frame.f_locals.get('self').source.event_repository is events):
            runtime = frame.f_locals['self']
            data['task'] = frame.f_locals['episode_id']
            case['task_id'] = data['task']
            case['legacy_before'] = _r223_legacy_state(events, data['task'])
            assert _r223_bound(events, data['task']) is None, 'R223 target was already bound before public precheck'
            record('PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK', runtime=id(runtime), repository=id(events))
            if mode in {'race', 'before'}:
                data['start'].set()
                assert entered.wait(10), 'R223 original writer entry barrier timed out'
                if mode == 'before':
                    release.set()
                    assert data['finished'].wait(10), 'R223 writer-before-binding did not finish'
                    assert case['writer']['returned'] and data.get('writer_error') is None
                    record('LEGACY_WRITER_FINISHED_BEFORE_BINDING')
        elif (frame.f_code is data.get('writer_code')
                and frame.f_locals.get('self') is data.get('writer_repository')
                and frame.f_locals.get('task_id') == data.get('task')):
            record('ORIGINAL_SAVE_STATE_AFTER_PUBLIC_PRECHECK_BEFORE_INNER_LOCK',
                   code_name=frame.f_code.co_qualname, repository=id(frame.f_locals['self']),
                   lock=id(events._lock if backend == 'memory' else frame.f_locals['self']._write_lock))
            entered.set()
            assert release.wait(10), 'R223 original writer release timed out'
            record('ORIGINAL_WRITER_RELEASED_TOWARD_REAL_INNER_LOCK')

    def during_episode(worker, repo, job, source_root):
        runtime = received[0][3].worker_runtime
        task = runtime.bootstrap.definition.episode_id
        assert task == data['task']
        raw = runtime.bootstrap.to_payload()
        rows = _r223_operation_rows(events, reads, 'bootstrap-init:' + runtime._bootstrap_id)
        assert raw['transaction']['phase'] == 'COMPLETE'
        assert all(any(row['phase'] == 'COMPLETE' for row in group) for group in rows.values())
        binding = _r223_bound(events, task)
        assert binding == raw['original_time']
        case.update(bootstrap_complete=True, bootstrap=raw, binding=binding,
                    complete_receipts=rows, before=_frozen._b_t2_snapshot(events, reads))
        record('DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE', runtime=id(runtime))
        if mode == 'race':
            assert entered.is_set() and not data['finished'].is_set()
            release.set()
            assert data['finished'].wait(10), 'R223 late writer did not finish after binding'
        elif mode == 'negative':
            before_budget = raw['payload']['state']
            events.save_state(task, 'CANCELLED', 'R223 exact negative positional route')
            assert events.get_state(task) == 'CANCELLED'
            assert runtime.bootstrap.to_payload()['payload']['state'] == before_budget
            case['negative_state'] = events.get_state(task)
            case['unchanged_budget'] = before_budget
            record('BOUND_EXACT_NEGATIVE_CANCELLATION')
        case['legacy_after'] = _r223_legacy_state(events, task)
        case['after'] = _frozen._b_t2_snapshot(events, reads)
        record('DURING_EPISODE_AFTER_WRITER_READBACK')

    try:
        with monkeypatch.context() as scoped:
            repo, job, worker, calls, received, _, initial_events = software_factory(
                scoped, directory, during_episode=during_episode)
            events = initial_events
            if backend == 'memory':
                initial_events.close()
                events = InMemoryEventAutonomyRepository()
                worker.visual_event_repository = events
            worker.operational_time_mode = 'LOCAL_TEMPORAL_PUBLICATION_V1'
            reads['job'] = sqlite3.connect(repo.database_path)
            reads['job'].row_factory = sqlite3.Row
            if backend == 'sqlite':
                reads['event'] = sqlite3.connect(events.path)
                reads['event'].row_factory = sqlite3.Row
            data.update(start=threading.Event(), finished=threading.Event())
            if mode in {'race', 'before'}:
                writer = threading.Thread(target=writer_body, name='R223-public-save-state')
                observed.add(writer, 'helper_thread')['initialized'] = True
                writer.start()
                assert ready.wait(10), 'R223 writer repository initialization timed out'
                assert data.get('writer_error') is None, 'R223 second repository initialization failed'
            observed.wait_observer = observe_entry
            assert worker.poll_once()
            assert calls.count('episode') == 1, repo.get_job(job.job_id).error_message
            assert case['bootstrap_complete'], 'R223 genuine private bootstrap did not finish'
    finally:
        observed.wait_observer = None
        release.set()
        if 'start' in data:
            data['start'].set()
        if writer is not None:
            writer.join(timeout=10)
            case['writer_joined'] = not writer.is_alive()
        if events is not None:
            events.close()
        for connection in reads.values():
            connection.close()
        case['exit_exception'] = None if sys.exc_info()[0] is None else {
            'type': sys.exc_info()[0].__name__, 'message': str(sys.exc_info()[1])}
    return case


def _r223_case(monkeypatch, tmp_path, request, backend, observed, *, mode, second=False):
    try:
        return _r223_run(monkeypatch, tmp_path / 'real-factory', backend, observed, mode=mode, second=second)
    finally:
        value = observed.value['observations'].get('r223')
        if value is not None:
            _r223_save(os.environ['BIGSMALL_R223_CASE_ROOT'], request.node.nodeid, value)


@pytest.mark.parametrize('backend', ['memory', 'sqlite'])
def test_late_binding_rejects_public_writer(monkeypatch, tmp_path, request, backend):
    with _r223_observe(monkeypatch, request) as observed:
        case = _r223_case(monkeypatch, tmp_path, request, backend, observed, mode='race')
        assert case['writer_joined'] and case['writer']['attempted'] and case['bootstrap_complete']
        error = case['writer']['exception']
        assert error is not None and error['type'] == 'ValueError' and re.search(
            'private|operational|scope', error['message']), 'R223 late local binding was not rejected'
        assert case['legacy_after'] == case['legacy_before']


def test_late_binding_rejects_public_writer_second_connection(monkeypatch, tmp_path, request):
    with _r223_observe(monkeypatch, request) as observed:
        case = _r223_case(monkeypatch, tmp_path, request, 'sqlite', observed, mode='race', second=True)
        assert case['writer_joined'] and case['writer']['attempted'] and case['bootstrap_complete']
        error = case['writer']['exception']
        assert error is not None and error['type'] == 'ValueError' and re.search(
            'private|operational|scope', error['message']), 'R223 late local binding was not rejected'
        assert case['legacy_after'] == case['legacy_before']


@pytest.mark.parametrize('backend', ['memory', 'sqlite'])
def test_writer_committed_before_binding_is_legacy(monkeypatch, tmp_path, request, backend):
    with _r223_observe(monkeypatch, request) as observed:
        case = _r223_case(monkeypatch, tmp_path, request, backend, observed, mode='before')
        assert case['writer_joined'] and case['writer']['returned'] and case['writer']['exception'] is None
        assert case['bootstrap_complete'] and case['legacy_after'] != case['legacy_before']
        kinds = [item['kind'] for item in case['order']]
        assert kinds.index('LEGACY_WRITER_FINISHED_BEFORE_BINDING') < kinds.index('DURING_EPISODE_GENUINE_BINDING_AND_BOTH_COMPLETE')


@pytest.mark.parametrize('backend', ['memory', 'sqlite'])
def test_bound_negative_cancellation_remains_supported(monkeypatch, tmp_path, request, backend):
    with _r223_observe(monkeypatch, request) as observed:
        case = _r223_case(monkeypatch, tmp_path, request, backend, observed, mode='negative')
        assert case['bootstrap_complete'] and case['negative_state'] == 'CANCELLED'
        assert case['legacy_before'] == case['legacy_after']


@pytest.mark.parametrize('backend', ['memory', 'sqlite'])
def test_unbound_legacy_writer_roundtrip(monkeypatch, tmp_path, request, backend):
    from cloud_edge_robot_arm.repositories.event_autonomy import InMemoryEventAutonomyRepository
    from tests.test_visual_worker_factory import software_factory

    with _r223_observe(monkeypatch, request) as observed:
        with monkeypatch.context() as scoped:
            repo, job, worker, calls, received, _, initial = software_factory(scoped, tmp_path)
            events = initial
            try:
                if backend == 'memory':
                    initial.close()
                    events = InMemoryEventAutonomyRepository()
                task = 'R223-unbound-legacy-task'
                assert _r223_bound(events, task) is None
                before = _r223_legacy_state(events, task)
                events.save_state(task, 'RUNNING', 'R223 ordinary legacy roundtrip')
                assert events.get_state(task) == 'RUNNING'
                first = _r223_legacy_state(events, task)
                events.save_state(task, 'PAUSED', 'R223 subsequent real transaction remains usable')
                assert events.get_state(task) == 'PAUSED'
                value = {'backend': backend, 'mode': 'unbound', 'before': before, 'first': first,
                         'after': _r223_legacy_state(events, task), 'binding': _r223_bound(events, task),
                         'polled': False, 'worker_active_job_id': worker.active_job_id}
                observed.value['observations']['scenarios'].append(value)
                _r223_save(os.environ['BIGSMALL_R223_CASE_ROOT'], request.node.nodeid, value)
            finally:
                events.close()
