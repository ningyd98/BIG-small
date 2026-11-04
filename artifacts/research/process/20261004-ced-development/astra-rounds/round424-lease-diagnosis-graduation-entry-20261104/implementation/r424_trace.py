"""Record actual caller/transaction state without replacing any target function."""

import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
REPOSITORY = str(ROOT / 'src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py')
TEST = str(ROOT / 'tests/test_rgbd_lease_handoff.py')
NAMES = {'_writer_call', '_legacy_write_transaction', '_register_writer',
         '_unregister_writer', 'expire_leases', '_request_cancel_unlocked',
         '_retry_job_unlocked', '_handoff', 'race', 'refresh_before_cas'}
_previous = None
_stream = None


def trace(frame, event, arg):
    if frame.f_code.co_filename not in {REPOSITORY, TEST} or frame.f_code.co_name not in NAMES:
        return None
    if event not in {'call', 'exception', 'return'}:
        return trace
    local = frame.f_locals
    repo = local.get('self', local.get('repo'))
    transactions = getattr(repo, '_transactions', None)
    connection = getattr(transactions, 'connection', None)
    owner = getattr(transactions, 'writer_owner', None)
    caller = frame.f_back
    chain = []
    parent = caller
    for _ in range(3):
        if parent is None:
            break
        chain.append({'file': parent.f_code.co_filename, 'function': parent.f_code.co_name,
                      'line': parent.f_lineno})
        parent = parent.f_back
    row = {'event': event, 'monotonic_ns': time.monotonic_ns(), 'pid': os.getpid(),
           'thread_id': threading.get_ident(), 'function': frame.f_code.co_name,
           'file': frame.f_code.co_filename, 'line': frame.f_lineno,
           'connection_present': connection is not None,
           'in_transaction': None if connection is None else connection.in_transaction,
           'owner_operation': getattr(owner, 'operation', None),
           'caller_chain': chain,
           'repository_database_path': str(getattr(repo, 'database_path', '')),
           'caller': None if caller is None else {
               'file': caller.f_code.co_filename, 'function': caller.f_code.co_name,
               'line': caller.f_lineno}}
    if frame.f_code.co_name == '_writer_call':
        row['requested_writer'] = getattr(local.get('function'), '__name__', None)
    if event == 'exception':
        row['exception'] = {'type': arg[0].__name__, 'message': str(arg[1])}
        second = local.get('connection')
        if frame.f_code.co_name == 'refresh_before_cas' and second is not None:
            row['second_connection_is_distinct'] = second is not connection
            row['second_connection_in_transaction'] = second.in_transaction
    _stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    _stream.flush()
    return trace


def pytest_sessionstart(session):
    global _previous, _stream
    _previous = sys.gettrace()
    assert _previous is None, 'record-only observer requires an unused trace channel'
    _stream = Path(os.environ['R424_TRACE_PATH']).open('x', encoding='utf-8')
    sys.settrace(trace)


def pytest_sessionfinish(session, exitstatus):
    sys.settrace(_previous)
    if _stream is not None:
        _stream.close()
