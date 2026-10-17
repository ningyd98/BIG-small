"""R234 passive exception trace plugin; never grants product authority."""
from pathlib import Path
import hashlib
import json
import os
import queue
import sys
import threading

import pytest

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
FILE = 'tests/test_local_public_writer_binding_race.py::'
NODES = (
    FILE + 'test_late_binding_rejects_public_writer[memory]',
    FILE + 'test_late_binding_rejects_public_writer[sqlite]',
    FILE + 'test_late_binding_rejects_public_writer_second_connection',
)
# All path resolution occurs before any callback is installed.
LEASE = str((ROOT / 'src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py').resolve())
WORKER = str((ROOT / 'src/cloud_edge_robot_arm/simulation_runtime/worker.py').resolve())
RUNTIME = str((ROOT / 'src/cloud_edge_robot_arm/vision/worker_runtime.py').resolve())
TARGETS = {
    (WORKER, 'SimulationWorker._execute', 242): (),
    (LEASE, 'OperationalLeaseSession.__init__', 417): (),
    (LEASE, 'OperationalLeaseSession._serve', 654): (657, 658, 660, 678, 681, 683),
    (RUNTIME, 'VisualWorkerRuntime._initialize_local', 420): (),
}
INIT = (LEASE, 'OperationalLeaseSession.__init__', 417)
SERVE = (LEASE, 'OperationalLeaseSession._serve', 654)
MAX_BYTES = 1048576


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode()


def callback_identity(callback):
    return None if callback is None else {'id': id(callback), 'type': type(callback).__name__}


class Capture:
    def __init__(self, nodeid):
        self.nodeid = nodeid
        self.pid = os.getpid()
        self.main_ident = threading.get_ident()
        self.guard = threading.Lock()
        self.events = []
        self.reasons = []
        self.dropped_events = 0
        self.buffer_bytes = 0
        self.sequence = 0
        self.thread_sequences = {}
        self.threads = {}
        self.frames = {}
        self.next_frame = 0
        self.exception_frames = set()
        self.milestones = set()
        self.startup_sampled = set()
        self.broker_idents = set()
        self.idle = {'count': 0, 'first': None, 'last': None}
        self.restoration = None

    def incomplete(self, reason):
        if reason not in self.reasons and len(self.reasons) < 32:
            self.reasons.append(reason)

    def message(self, error):
        raw = str(error).encode('utf-8', errors='replace')
        if len(raw) > 8192:
            self.incomplete('exception message exceeds 8192 UTF8 bytes')
            return raw[:8192].decode('utf-8', errors='ignore')
        return raw.decode('utf-8')

    def frame_descriptor(self, frame, lineno=None):
        code = frame.f_code
        return {'filename': code.co_filename, 'qualname': code.co_qualname,
                'first_line': code.co_firstlineno,
                'line': frame.f_lineno if lineno is None else lineno}

    def exception(self, error, tb=None, depth=0, seen=None):
        if seen is None:
            seen = set()
        if id(error) in seen:
            return {'cycle': True, 'exception_id': id(error)}
        if depth >= 3:
            self.incomplete('exception cause/context depth exceeds 3')
            return {'depth_exceeded': True}
        seen = seen | {id(error)}
        frames = []
        trace = error.__traceback__ if tb is None else tb
        while trace is not None and len(frames) < 32:
            frames.append(self.frame_descriptor(trace.tb_frame, trace.tb_lineno))
            trace = trace.tb_next
        if trace is not None:
            self.incomplete('exception traceback exceeds 32 frames')
        cause, context = error.__cause__, error.__context__
        result = {'exception_id': id(error), 'type': type(error).__qualname__,
                  'module': type(error).__module__, 'message': self.message(error),
                  'traceback': frames, 'suppress_context': bool(error.__suppress_context__),
                  'cause': None, 'context': None}
        if cause is not None:
            result['cause'] = self.exception(cause, depth=depth + 1, seen=seen)
        if context is not None:
            result['context'] = self.exception(context, depth=depth + 1, seen=seen)
        return result

    def startup(self, frame):
        # One non-atomic sample only; no waits, joins, clock or product calls.
        obj = frame.f_locals.get('self')
        sample = {'non_atomic': True, 'self_id': None if obj is None else id(obj),
                  'startup_error': None, 'ready_is_set': None, 'broker_ident': None,
                  'broker_native_id': None, 'broker_stack': None, 'unknown_reasons': []}
        if obj is None:
            sample['unknown_reasons'].append('self unavailable')
            return sample
        fields = obj.__dict__
        error = fields.get('_startup_error')
        if isinstance(error, BaseException):
            sample['startup_error'] = self.exception(error)
        elif error is None:
            sample['unknown_reasons'].append('no existing startup exception')
        else:
            sample['unknown_reasons'].append('startup error is not an exception')
        ready = fields.get('_ready')
        if type(ready) is threading.Event:
            sample['ready_is_set'] = ready.is_set()
        else:
            sample['unknown_reasons'].append('existing ready event unavailable')
        broker = fields.get('_broker')
        if isinstance(broker, threading.Thread):
            sample['broker_ident'] = broker.ident
            sample['broker_native_id'] = broker.native_id
        else:
            sample['unknown_reasons'].append('existing broker unavailable')
        ident = sample['broker_ident']
        if ident is not None:
            self.broker_idents.add(ident)
            all_frames = sys._current_frames()
            current = all_frames.get(ident)
            del all_frames
            if current is not None:
                stack = []
                for _ in range(16):
                    if current is None:
                        break
                    stack.append(self.frame_descriptor(current))
                    current = current.f_back
                sample['broker_stack'] = {'frames': stack, 'truncated': current is not None}
                del current
            else:
                sample['unknown_reasons'].append('broker frame unavailable at sample')
        return sample

    def trace(self, frame, event, arg):
        code = frame.f_code
        identity = (code.co_filename, code.co_qualname, code.co_firstlineno)
        if identity not in TARGETS:
            return None
        if event not in {'call', 'exception', 'return', 'line'}:
            return self.trace
        frame_id = id(frame)
        if event == 'line':
            if frame.f_lineno not in TARGETS[identity] or (frame_id, frame.f_lineno) in self.milestones:
                return self.trace
        if not self.guard.acquire(blocking=False):
            self.incomplete('observer bookkeeping contention; selected event lost')
            self.dropped_events += 1
            return self.trace
        try:
            if event == 'line':
                self.milestones.add((frame_id, frame.f_lineno))
            ident, native = threading.get_ident(), threading.get_native_id()
            self.sequence += 1
            self.thread_sequences[ident] = self.thread_sequences.get(ident, 0) + 1
            self.threads[ident] = native
            basic = {'nodeid': self.nodeid, 'pid': self.pid, 'thread_id': ident,
                     'native_thread_id': native, 'sequence': self.sequence,
                     'thread_sequence': self.thread_sequences[ident], 'event': event,
                     'frame_id': frame_id, 'code': {'filename': identity[0],
                     'qualname': identity[1], 'first_line': identity[2]}, 'line': frame.f_lineno}
            if event == 'exception' and identity == SERVE and frame.f_lineno == 662 and type(arg[1]) is queue.Empty:
                self.idle['count'] += 1
                if self.idle['first'] is None:
                    self.idle['first'] = basic
                self.idle['last'] = basic
                return self.trace
            if len(self.events) >= 512 or self.buffer_bytes >= MAX_BYTES - 65536:
                self.incomplete('selected trace event/byte cap reached')
                self.dropped_events += 1
                return self.trace
            if event == 'call':
                self.next_frame += 1
                self.frames[frame_id] = self.next_frame
            basic['frame_sequence'] = self.frames.get(frame_id)
            obj = frame.f_locals.get('self')
            basic['self_id'] = None if obj is None else id(obj)
            if event == 'exception':
                self.exception_frames.add(frame_id)
                basic['exception'] = self.exception(arg[1], tb=arg[2])
                if identity == INIT and frame_id not in self.startup_sampled:
                    self.startup_sampled.add(frame_id)
                    basic['startup_observation'] = self.startup(frame)
            elif event == 'return':
                basic['return_is_not_success_claim'] = True
                basic['exception_observed_in_frame'] = frame_id in self.exception_frames
                self.frames.pop(frame_id, None)
                self.exception_frames.discard(frame_id)
                self.startup_sampled.discard(frame_id)
                self.milestones.difference_update((frame_id, line) for line in TARGETS[identity])
            size = len(encoded(basic))
            if self.buffer_bytes + size > MAX_BYTES - 65536:
                self.incomplete('serialized trace byte cap reached')
                self.dropped_events += 1
            else:
                self.events.append(basic)
                self.buffer_bytes += size
        except BaseException as error:
            self.incomplete('observer callback error: ' + type(error).__name__)
        finally:
            self.guard.release()
        return self.trace

    def finish(self, previous_sys, previous_thread, previous_profile, previous_thread_profile):
        self.restoration = {
            'sys_trace': sys.gettrace() is previous_sys,
            'threading_trace': threading.gettrace() is previous_thread,
            'sys_profile': sys.getprofile() is previous_profile,
            'threading_profile': threading.getprofile() is previous_thread_profile,
            'previous_sys_trace': callback_identity(previous_sys),
            'previous_threading_trace': callback_identity(previous_thread),
        }
        if not all(self.restoration[key] for key in ('sys_trace', 'threading_trace', 'sys_profile', 'threading_profile')):
            self.incomplete('trace/profile restoration mismatch')
        live = {thread.ident: thread for thread in threading.enumerate()}
        threads = []
        for ident in sorted(set(self.threads) | self.broker_idents):
            is_main = ident == self.main_ident
            thread = live.get(ident)
            alive = thread is not None and thread.is_alive()
            if alive and not is_main:
                self.incomplete('observed supplemental thread still alive after teardown')
            threads.append({'thread_id': ident, 'native_thread_id': self.threads.get(ident),
                            'main_protocol_thread': is_main, 'alive_after_teardown': alive,
                            'per_thread_trace_restored': self.restoration['sys_trace'] if is_main else None,
                            'termination_observed': not alive if not is_main else None})
        result = {'schema_version': 'bigsmall.r234.exception-trace.v1',
                  'nodeid': self.nodeid, 'pid': self.pid, 'events': self.events,
                  'idle_queue_empty': self.idle, 'event_count': len(self.events),
                  'dropped_events': self.dropped_events, 'incomplete_reasons': self.reasons,
                  'restoration': self.restoration, 'threads': threads,
                  'limits': {'events': 512, 'traceback_frames': 32, 'cause_depth': 3,
                             'message_utf8': 8192, 'trace_json_utf8': MAX_BYTES},
                  'diagnostic_only': True, 'atomic_snapshot': False,
                  'unobserved': {'OS_handles': None, 'GPU_native': None, 'network_calls': None}}
        result['capture_complete'] = not self.reasons
        raw = encoded(result)
        if len(raw) > MAX_BYTES:
            self.incomplete('final trace serialization exceeds byte cap')
            result['capture_complete'] = False
            while len(raw) > MAX_BYTES and result['events']:
                result['events'].pop()
                result['dropped_events'] += 1
                result['event_count'] = len(result['events'])
                raw = encoded(result)
        directory = Path(os.environ['BIGSMALL_R234_TRACE_ROOT'])
        path = directory / (hashlib.sha256(self.nodeid.encode()).hexdigest() + '.json')
        with path.open('xb') as handle:
            if handle.write(raw) != len(raw):
                raise OSError('partial R234 trace write')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    capture = Capture(item.nodeid)
    previous_sys, previous_thread = sys.gettrace(), threading.gettrace()
    previous_profile, previous_thread_profile = sys.getprofile(), threading.getprofile()
    installed = False
    try:
        if item.nodeid not in NODES:
            capture.incomplete('unexpected node before fixture allocation')
            raise pytest.UsageError('R234 accepts only the exact three nodes')
        if previous_sys is not None or previous_thread is not None:
            capture.incomplete('existing trace detected before fixture allocation')
            raise pytest.UsageError('R234 refuses to compose an existing trace')
        threading.settrace(capture.trace)
        sys.settrace(capture.trace)
        installed = True
        yield
    finally:
        # Only this plugin's independent trace channel is restored.
        if installed:
            sys.settrace(previous_sys)
            threading.settrace(previous_thread)
        capture.finish(previous_sys, previous_thread, previous_profile, previous_thread_profile)
