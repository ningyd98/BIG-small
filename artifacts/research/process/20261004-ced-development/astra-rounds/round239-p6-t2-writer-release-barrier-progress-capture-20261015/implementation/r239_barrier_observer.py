"""R239 read-only bystander sampling; never changes product barriers or hooks."""
from pathlib import Path
import hashlib
import json
import os
import sys
import threading
import time
import pytest

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round239-p6-t2-writer-release-barrier-progress-capture-20261015'
FIXTURE = str(ROOT / 'tests/test_local_public_writer_binding_race.py')
EVENT_TYPE = threading.Event
CODES = {
    '_r223_run': 89,
    '_r223_run.<locals>.writer_body': 116,
    '_r223_run.<locals>.observe_entry': 139,
    '_r223_run.<locals>.during_episode': 168,
}
NODES = {
    'tests/test_local_public_writer_binding_race.py::test_late_binding_rejects_public_writer[memory]': 'memory.json',
    'tests/test_local_public_writer_binding_race.py::test_late_binding_rejects_public_writer[sqlite]': 'sqlite.json',
    'tests/test_local_public_writer_binding_race.py::test_late_binding_rejects_public_writer_second_connection': 'sqlite-second-connection.json',
}
PINS = [
    {'path': FIXTURE, 'bytes': 16529, 'sha256': '84e771641c669c5d67d8c19fa51e8df759e32fd480c6c0762c2a98bcb8de2093'},
    {'path': str(ROOT / 'tests/test_operational_runtime_closure.py'), 'bytes': 254018,
     'sha256': 'ed602dc9ba5c0b15af20fbe8ca4d9b58d2e4e45fac621dc6f5e5e2cd4a94e7d3'},
]
TOTAL_TICKS = 0
PLUGIN_ERRORS = []


def hook_identity(value):
    return None if value is None else {'id': id(value), 'type': type(value).__name__}


def hooks():
    return {'sys_profile': hook_identity(sys.getprofile()), 'sys_trace': hook_identity(sys.gettrace()),
            'threading_profile': hook_identity(threading.getprofile()),
            'threading_trace': hook_identity(threading.gettrace())}


def code_matches(frame):
    code = frame.f_code
    return code.co_filename == FIXTURE and CODES.get(code.co_qualname) == code.co_firstlineno


def stack(head):
    output, frame = [], head
    try:
        for _ in range(12):
            if frame is None:
                break
            code = frame.f_code
            output.append({'filename': code.co_filename[:512], 'qualname': code.co_qualname[:256],
                           'lineno': frame.f_lineno,
                           'filename_truncated': len(code.co_filename) > 512,
                           'qualname_truncated': len(code.co_qualname) > 256})
            frame = frame.f_back
        return output, frame is not None
    finally:
        frame = None


def event_flag(value, label, flags, unavailable):
    if type(value) is EVENT_TYPE:
        flag = value.__dict__.get('_flag')
        if type(flag) is bool:
            flags[label] = flag
        else:
            unavailable.append({'field': label, 'reason': 'native flag unavailable', 'type': type(flag).__name__})
    else:
        unavailable.append({'field': label, 'reason': 'exact original Event unavailable', 'type': type(value).__name__})


def primitives(frame, output, flags, unavailable):
    local = frame.f_locals
    label = frame.f_code.co_qualname
    state = {'frame': label}
    try:
        case = local.get('case')
        if type(case) is dict:
            for key in ('bootstrap_complete', 'writer_attempted', 'writer_returned', 'writer_joined'):
                value = case.get(key)
                if type(value) is bool:
                    state[key] = value
            writer = case.get('writer')
            if type(writer) is dict:
                for key in ('attempted', 'returned', 'joined'):
                    if type(writer.get(key)) is bool:
                        state['writer_' + key] = writer[key]
                error = writer.get('exception')
                if error is None:
                    state['writer_exception'] = None
                elif type(error) is dict:
                    state['writer_exception'] = {
                        key: error[key][:512] if type(error.get(key)) is str else None
                        for key in ('type', 'message')}
            order = case.get('order')
            if type(order) is list:
                state['order_length'] = len(order)
                state['order_last8'] = []
                for item in order[-8:]:
                    if type(item) is dict:
                        state['order_last8'].append({
                            'sequence': item.get('sequence') if type(item.get('sequence')) is int else None,
                            'kind': item.get('kind')[:256] if type(item.get('kind')) is str else None})
        else:
            unavailable.append({'field': label + '.case', 'reason': 'exact dict unavailable'})
        for key in ('release', 'entered', 'ready'):
            if key in local:
                event_flag(local[key], label + '.' + key, flags, unavailable)
        data = local.get('data')
        if type(data) is dict:
            for key in ('start', 'finished'):
                if key in data:
                    event_flag(data[key], label + '.data.' + key, flags, unavailable)
        output.append(state)
    finally:
        local = case = writer = error = order = data = None


def locate_writer(frames, main_id):
    candidate = None
    for ident, head in frames.items():
        if ident == main_id:
            continue
        frame = head
        try:
            for _ in range(64):
                if frame is None:
                    break
                if (code_matches(frame)
                        and frame.f_code.co_qualname == '_r223_run.<locals>.writer_body'):
                    if candidate is not None:
                        return None, 'multiple original writer frames'
                    candidate = ident
                    break
                frame = frame.f_back
        finally:
            frame = head = None
    return candidate, None


def sample(main_id, started, ordinal):
    frames = sys._current_frames()
    head = frame = None
    try:
        writer_id, writer_problem = locate_writer(frames, main_id)
        result = {'ordinal': ordinal, 'host_offset_ns': time.perf_counter_ns() - started,
                  'main_stack': [], 'writer_stack': [], 'primitive_state': [], 'barrier_flags': {},
                  'unavailable': [], 'truncation': {}, 'writer_ident': writer_id,
                  'writer_native_id': None, 'non_atomic': True}
        if writer_problem:
            result['unavailable'].append({'field': 'writer', 'reason': writer_problem})
        for label, ident in (('main', main_id), ('writer', writer_id)):
            head = frames.get(ident) if ident is not None else None
            if head is None:
                result['unavailable'].append({'field': label + '_stack', 'reason': 'frame missing'})
                continue
            result[label + '_stack'], truncated = stack(head)
            result['truncation'][label + '_stack'] = truncated
            frame = head
            for _ in range(64):
                if frame is None:
                    break
                if code_matches(frame):
                    primitives(frame, result['primitive_state'], result['barrier_flags'], result['unavailable'])
                frame = frame.f_back
            if frame is not None:
                result['unavailable'].append({'field': label + '_fixture_lookup', 'reason': '64 frame search bound'})
            frame = head = None
        return result
    finally:
        frame = head = None
        frames.clear()
        frames = None


def observe(stop, value, main_id, started, initial_hooks):
    global TOTAL_TICKS
    resource = value['sampler_resources']
    resource['thread']['target_entered'] = True
    resource['thread']['ident'] = threading.get_ident()
    resource['thread']['native_id'] = threading.get_native_id()
    value['inherited_hooks']['sampler_start'] = hooks()
    value['inherited_hooks']['sys_hooks_match_original_thread_hooks'] = {
        'profile': hook_identity(sys.getprofile()) == initial_hooks['threading_profile'],
        'trace': hook_identity(sys.gettrace()) == initial_hooks['threading_trace']}
    previous, last_kept, used = None, -1000000000, 0
    last = None
    try:
        while not stop.is_set():
            if TOTAL_TICKS >= 2401:
                value['observation_errors'].append({'type': 'GlobalTickCap', 'message': '2401 total ticks exhausted'})
                value['counters']['bound_reached'] = True
                break
            TOTAL_TICKS += 1
            value['counters']['ticks'] += 1
            current = sample(main_id, started, value['counters']['ticks'])
            last = current
            signature = json.dumps({k: v for k, v in current.items() if k not in {'ordinal', 'host_offset_ns'}},
                                   sort_keys=True, ensure_ascii=False, allow_nan=False)
            changed = signature != previous
            periodic = current['host_offset_ns'] - last_kept >= 1000000000
            if changed or periodic:
                raw_size = len(json.dumps(current, ensure_ascii=False, allow_nan=False).encode())
                if len(value['samples']) < 1023 and used + raw_size < 8 * 1024 * 1024 - 65536:
                    value['samples'].append(current)
                    used += raw_size
                    last_kept = current['host_offset_ns']
                    previous = signature
                else:
                    value['counters']['dropped'] += 1
                    value['counters']['bound_reached'] = True
            stop.wait(0.25)
    except BaseException as error:
        value['observation_errors'].append({'type': type(error).__name__, 'message': str(error)[:512]})
    finally:
        if last is not None and (not value['samples'] or value['samples'][-1]['ordinal'] != last['ordinal']):
            if len(value['samples']) < 1024 and used + len(json.dumps(last, ensure_ascii=False).encode()) < 8 * 1024 * 1024 - 65536:
                value['samples'].append(last)
            else:
                value['counters']['dropped'] += 1
                value['counters']['bound_reached'] = True
        value['counters']['records'] = len(value['samples'])
        value['counters']['total_ticks_after_node'] = TOTAL_TICKS
        resource['thread']['target_finally_reached'] = True
        value['inherited_hooks']['sampler_end'] = hooks()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    if item.nodeid not in NODES:
        yield
        return
    started = time.perf_counter_ns()
    main_id = threading.get_ident()
    initial_hooks = hooks()
    value = {'schema_version': 'bigsmall.r239.barrier-progress.v1', 'exact_nodeid': item.nodeid,
             'pinned_sources': PINS, 'host_start_ns': started, 'host_end_ns': None,
             'main_thread': {'ident': main_id, 'native_id': threading.get_native_id()},
             'inherited_hooks': {'main_before_setup': initial_hooks},
             'samples': [], 'counters': {'ticks': 0, 'records': 0, 'dropped': 0, 'bound_reached': False},
             'bounds': {'global_ticks': 2401, 'node_records': 1024, 'node_bytes': 8 * 1024 * 1024,
                        'stack_frames_each': 12, 'lookup_frames_each': 64, 'interval_seconds': 0.25},
             'observation_errors': [], 'sampler_resources': {
                 'event': {'constructor_attempted': False, 'initialized': False, 'id': None,
                           'stop_requested': False, 'exception': None},
                 'thread': {'constructor_attempted': False, 'initialized': False, 'id': None,
                            'start_attempted': False, 'started': False, 'target_entered': False,
                            'ident': None, 'native_id': None, 'target_finally_reached': False,
                            'join_attempted': False, 'joined': False, 'alive_after_join': None,
                            'join_elapsed_ns': None, 'exception': None}},
             'final_hook_comparison': None, 'complete': False,
             'diagnostic_limits': 'Non-atomic samples may miss transitions and perturb scheduling; no OC1 time or root-cause proof.'}
    stop = thread = None
    stage = 'source pins'
    try:
        for pin in PINS:
            path = Path(pin['path'])
            raw = path.read_bytes()
            if path.is_symlink() or len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
                raise ValueError('pinned original fixture source differs')
        stage = 'event constructor'
        value['sampler_resources']['event']['constructor_attempted'] = True
        stop = EVENT_TYPE()
        value['sampler_resources']['event'].update(initialized=True, id=id(stop))
        stage = 'thread constructor'
        value['sampler_resources']['thread']['constructor_attempted'] = True
        thread = threading.Thread(target=observe, args=(stop, value, main_id, started, initial_hooks),
                                  name='R239-bystander-' + NODES[item.nodeid], daemon=False)
        value['sampler_resources']['thread'].update(initialized=True, id=id(thread), start_attempted=True)
        stage = 'thread start'
        thread.start()
        value['sampler_resources']['thread']['started'] = True
    except BaseException as error:
        detail = {'stage': stage, 'type': type(error).__name__, 'message': str(error)[:512]}
        value['observation_errors'].append(detail)
        resource = 'event' if stage == 'event constructor' else 'thread'
        value['sampler_resources'][resource]['exception'] = detail
    try:
        yield
    finally:
        try:
            if stop is not None:
                value['sampler_resources']['event']['stop_requested'] = True
                stop.set()
            if thread is not None and thread.ident is not None:
                began = time.perf_counter_ns()
                value['sampler_resources']['thread']['join_attempted'] = True
                thread.join(timeout=2.0)
                alive = thread.is_alive()
                value['sampler_resources']['thread'].update(joined=not alive, alive_after_join=alive,
                                                          join_elapsed_ns=time.perf_counter_ns() - began)
        except BaseException as error:
            detail = {'stage': 'sampler cleanup', 'type': type(error).__name__, 'message': str(error)[:512]}
            value['observation_errors'].append(detail)
            value['sampler_resources']['thread']['exception'] = detail
        value['host_end_ns'] = time.perf_counter_ns()
        value['host_elapsed_ns'] = value['host_end_ns'] - started
        final_hooks = hooks()
        value['inherited_hooks']['main_after_teardown'] = final_hooks
        value['final_hook_comparison'] = {'main_before_equals_after': initial_hooks == final_hooks,
                                         'hooks_modified_by_plugin': False}
        resource = value['sampler_resources']
        value['complete'] = bool(not value['observation_errors'] and not value['counters']['bound_reached']
                                 and value['samples'] and resource['event']['initialized']
                                 and resource['event']['stop_requested'] and resource['thread']['started']
                                 and resource['thread']['target_entered'] and resource['thread']['target_finally_reached']
                                 and resource['thread']['joined'] and resource['thread']['alive_after_join'] is False
                                 and initial_hooks == final_hooks)
        waits = [row for row in value['samples'] if any(
            name.endswith('.release') and flag is False for name, flag in row['barrier_flags'].items())]
        value['decision_output'] = {'first_main_while_release_false': waits[0]['main_stack'] if waits else None,
            'last_main_while_release_false': waits[-1]['main_stack'] if waits else None,
            'first_sampled_wait_offset_ns': waits[0]['host_offset_ns'] if waits else None,
            'last_sampled_wait_offset_ns': waits[-1]['host_offset_ns'] if waits else None,
            'sampled_wait_span_ns': waits[-1]['host_offset_ns'] - waits[0]['host_offset_ns'] if waits else None,
            'dominant_phase': 'unknown', 'missing_intervals': 'all between samples and unavailable frame intervals'}
        try:
            directory = Path(os.environ['BIGSMALL_R239_PROGRESS_ROOT'])
            if directory != D / 'implementation/capture/progress':
                raise ValueError('exact diagnostic output directory required')
            raw = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode()
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('progress JSON byte cap exceeded')
            with (directory / NODES[item.nodeid]).open('xb') as handle:
                if handle.write(raw) != len(raw):
                    raise OSError('partial progress sidecar write')
        except BaseException as error:
            PLUGIN_ERRORS.append({'nodeid': item.nodeid, 'type': type(error).__name__, 'message': str(error)[:512]})
        stop = thread = None
