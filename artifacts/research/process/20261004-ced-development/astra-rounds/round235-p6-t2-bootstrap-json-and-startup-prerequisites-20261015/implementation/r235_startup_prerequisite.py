"""R235: once-only import scheduling prerequisite, never a clock/worker warmup."""
from pathlib import Path
import hashlib
import importlib
import json
import os
import sys
import threading
import time
import traceback

MODULE = 'tests.test_operational_time_v1'
EXPECTED = {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_time_v1.py',
            'bytes': 24211, 'sha256': 'ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f'}
_CONFIGURED = False


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def hooks():
    return (sys.getprofile(), threading.getprofile(), sys.gettrace(), threading.gettrace())


def hook_record(values):
    return [None if value is None else {'id': id(value), 'type': type(value).__name__}
            for value in values]


def pytest_configure(config):
    global _CONFIGURED
    if _CONFIGURED:
        raise RuntimeError('R235 prerequisite invoked more than once')
    _CONFIGURED = True
    path = Path(os.environ['BIGSMALL_R235_PREREQUISITE_RECORD'])
    previous = hooks()
    before = sys.modules.get(MODULE)
    record = {
        'schema_version': 'bigsmall.r235.startup-prerequisite.v1',
        'module_name': MODULE, 'expected_pin': EXPECTED, 'actual_file_pin': None,
        'pid': os.getpid(), 'already_loaded_before': MODULE in sys.modules,
        'module_id_before': None if before is None else id(before),
        'module_id_returned': None, 'module_id_after': None,
        'same_sys_modules_object_after': False,
        'same_previously_loaded_object': None,
        'modules_before': sorted(sys.modules), 'modules_after': None,
        'import_started_perf_counter_ns': None, 'import_finished_perf_counter_ns': None,
        'elapsed_ns': None, 'time_basis': 'host perf_counter_ns diagnostic-only',
        'profile_trace_before': hook_record(previous), 'profile_trace_after': None,
        'profile_trace_before_after_equal': False, 'pre_import_hooks_empty': False,
        'plugin_direct_factory_calls_prohibited_by_source_review': True,
        'pre_observer_resource_measurement': None,
        'exception': None, 'accepted_prerequisite': False,
        'legal_RED': False, 'GREEN': False, 'product_acceptance': False,
    }
    try:
        if any(value is not None for value in previous):
            raise RuntimeError('R235 requires empty profile/trace channels before import')
        record['pre_import_hooks_empty'] = True
        expected_path = Path(EXPECTED['path'])
        if expected_path.is_symlink() or pin(expected_path) != EXPECTED:
            raise ValueError('R235 prerequisite source path/hash differs')
        record['import_started_perf_counter_ns'] = time.perf_counter_ns()
        module = importlib.import_module(MODULE)
        record['import_finished_perf_counter_ns'] = time.perf_counter_ns()
        record['elapsed_ns'] = (record['import_finished_perf_counter_ns']
                                - record['import_started_perf_counter_ns'])
        actual_path = Path(module.__file__).resolve()
        record['actual_file_pin'] = pin(actual_path)
        record['module_id_returned'] = id(module)
        record['module_id_after'] = id(sys.modules[MODULE])
        record['same_sys_modules_object_after'] = sys.modules[MODULE] is module
        if record['already_loaded_before']:
            record['same_previously_loaded_object'] = module is before
        if (record['actual_file_pin'] != EXPECTED or sys.modules[MODULE] is not module
                or (record['already_loaded_before'] and module is not before)):
            raise ValueError('R235 imported module identity/path/hash differs')
        after = hooks()
        if any(a is not b for a, b in zip(previous, after)):
            raise RuntimeError('R235 prerequisite changed profile/trace channels')
        record['accepted_prerequisite'] = True
    except BaseException as error:
        if record['import_started_perf_counter_ns'] is not None and record['import_finished_perf_counter_ns'] is None:
            record['import_finished_perf_counter_ns'] = time.perf_counter_ns()
            record['elapsed_ns'] = (record['import_finished_perf_counter_ns']
                                    - record['import_started_perf_counter_ns'])
        record['exception'] = {'type': type(error).__name__, 'module': type(error).__module__,
                               'message': str(error), 'traceback': traceback.format_exc()}
        raise
    finally:
        after = hooks()
        record['modules_after'] = sorted(sys.modules)
        record['profile_trace_after'] = hook_record(after)
        record['profile_trace_before_after_equal'] = all(a is b for a, b in zip(previous, after))
        raw = (json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
        with path.open('xb') as handle:
            if handle.write(raw) != len(raw):
                raise OSError('partial R235 prerequisite evidence write')
