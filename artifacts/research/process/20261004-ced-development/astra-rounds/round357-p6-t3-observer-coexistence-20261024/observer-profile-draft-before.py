"""R354 source-preparation fragment: bounded profile observations only.

NOT RUNNABLE AS THE FINAL PLUGIN: lifecycle/gate/native-signal ownership work
is pending actual Astra R356. No hook installs itself at import. This fragment
does not register a signal, import product code, or wrap any product function.
"""

import json
import os
from pathlib import Path
import stat
import sys
import threading
import time


ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round354-p6-t3-live-noncompletion-evidence-20261024'
COMMAND = 'R354:live_utc_01'
NODE = 'tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]'
DIRECTORY = ROUND / 'implementation/live_utc_01/diagnostic'

# Fixed AST lexical coordinates, including the decorator-first-line convention.
# No target is imported/discovered dynamically or resolved through an object.
TARGETS = (
    ('stage', 'tests/test_operational_runtime_closure.py', '_b_t2_exercise', 4082),
    ('stage', 'tests/test_operational_runtime_closure.py', '_b_t3_ground_and_route', 5214),
    ('stage', 'tests/test_operational_runtime_closure.py', '_b_t3_supervision', 5266),
    ('stage', 'tests/test_operational_runtime_closure.py', '_b_t3_external_utc', 5599),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime.initialize_supervision', 1750),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime.reserve_supervision_capture', 1887),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime.complete_supervision_capture', 1902),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime.reserve_supervision_plan', 1939),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime.complete_supervision_plan', 2026),
    ('stage', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime._local_supervision_transition', 1263),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_copy', 48),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_object', 72),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_canonical', 112),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_hash', 116),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_history', 1361),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_semantic', 1448),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', '_validate_nested_local', 434),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/local_temporal.py', 'LocalEnvelope.from_payload', 1863),
    ('hotspot', 'src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py', 'derive_local_supervision', 888),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', '_local_read_record', 149),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime._read_lease', 1338),
    ('hotspot', 'src/cloud_edge_robot_arm/vision/worker_runtime.py', 'VisualWorkerRuntime._local_mutate', 707),
    ('hotspot', 'src/cloud_edge_robot_arm/simulation_runtime/worker.py', 'SimulationWorker.poll_once', 146),
)

MAX_COARSE = 512
MAX_HOTSPOT_EVENTS = 1_000_000
MAX_CALLBACKS = 50_000_000
MAX_ACTIVE_PER_THREAD = 256
MAX_THREADS = 64
MAX_SIZE_SAMPLES = 64
MAX_CPU_NS = 30_000_000_000
MAX_JSONL_BYTES = 16 * 1024 * 1024
MARKER_HEADROOM = 16 * 1024
CHECKPOINT_NS = 5_000_000_000


def _identity(value):
    return {'device': value.st_dev, 'inode': value.st_ino}


def _write_all(fd, raw):
    """Append a whole line or preserve the genuine short/torn prefix on error."""
    position = 0
    while position < len(raw):
        count = os.write(fd, raw[position:])
        if count <= 0:
            raise OSError('nonpositive observer write')
        position += count


def _stderr_fault(stage, error_type):
    """Best effort bounded, direct error channel; never throw into application."""
    try:
        raw = ('R354 observation invalid: ' + stage[:96] + ' / ' + error_type[:96] + '\n').encode('ascii', 'replace')
        _write_all(2, raw)
    except BaseException:
        pass


class _Profiler:
    """No frame/payload reference survives a callback; all costs are inclusive.

    The future lifecycle must validate the exact gate/output identity before
    construction, then explicitly install this instance's stable callback.
    SIGUSR2 and pytest lifecycle are intentionally absent pending R356.
    """

    def __init__(self, directory, directory_identity):
        if directory != DIRECTORY:
            raise ValueError('R354 exact diagnostic directory required')
        before = os.lstat(directory)
        if not stat.S_ISDIR(before.st_mode) or _identity(before) != directory_identity:
            raise ValueError('R354 diagnostic directory identity mismatch')
        self.directory = directory
        self.directory_identity = directory_identity
        self.fd = os.open(directory / 'observer-profile.jsonl',
                          os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.file_identity = _identity(os.fstat(self.fd))
        self.callback = self.profile
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.enabled = False
        self.closed = False
        self.invalid = False
        self.saturation = None
        self.faults = []
        self.seq = 0
        self.callbacks = 0
        self.hotspot_events = 0
        self.coarse_events = 0
        self.observer_cpu_ns = 0
        self.observer_callback_max_cpu_ns = 0
        self.last_checkpoint_ns = time.monotonic_ns()
        self.seen_threads = {}
        self.active = {}
        self.sizes = {}
        self.previous_sys_profile = None
        self.previous_thread_profile = None
        self.targets = {}
        self.aggregates = {}
        for index, (category, path, qualname, line) in enumerate(TARGETS):
            target = {'id': index, 'category': category, 'path': path,
                      'qualname': qualname, 'first_line': line}
            self.targets[(str(ROOT / path), qualname, line)] = target
            self.targets[(path, qualname, line)] = target
            self.aggregates[index] = {
                'calls': 0, 'observed_return_events': 0, 'unmatched_return_events': 0,
                'inclusive_wall_ns': 0, 'inclusive_thread_cpu_ns': 0,
                'max_inclusive_wall_ns': 0, 'max_inclusive_thread_cpu_ns': 0,
            }

    def _combined_jsonl_bytes(self):
        current = os.lstat(self.directory)
        if not stat.S_ISDIR(current.st_mode) or _identity(current) != self.directory_identity:
            raise ValueError('observer live directory changed')
        total = 0
        count = 0
        with os.scandir(self.directory) as entries:
            for entry in entries:
                count += 1
                if count > 64:
                    raise ValueError('observer diagnostic entry bound')
                if not entry.name.endswith('.jsonl'):
                    continue
                value = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(value.st_mode):
                    raise ValueError('observer JSONL must be regular nofollow file')
                total += value.st_size
        return total

    def _append(self, kind, data, *, emergency=False):
        self.seq += 1
        raw = (json.dumps({'schema': 'bigsmall.r354.profile.v1', 'sequence': self.seq,
                           'command_id': COMMAND, 'kind': kind, **data},
                          ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
        if len(raw) > 65536:
            raise ValueError('observer individual record bound')
        if not emergency and self._combined_jsonl_bytes() + len(raw) > MAX_JSONL_BYTES - MARKER_HEADROOM:
            self._stop('diagnostic_jsonl_saturation')
            return False
        self.write_lock.acquire()
        try:
            _write_all(self.fd, raw)
        finally:
            self.write_lock.release()
        return True

    def _fault(self, stage, error):
        self.invalid = True
        self.enabled = False
        if len(self.faults) < 16:
            self.faults.append({'stage': stage, 'error_type': type(error).__name__})
        _stderr_fault(stage, type(error).__name__)
        self._disable_current_and_future()

    def _disable_current_and_future(self):
        # Other already-profiled threads detach themselves on their next event.
        # Threads without a later callback have no observed restore receipt.
        try:
            if sys.getprofile() is self.callback:
                sys.setprofile(self.previous_sys_profile)
            if threading.getprofile() is self.callback:
                threading.setprofile(self.previous_thread_profile)
        except BaseException as error:
            self.invalid = True
            _stderr_fault('profile_disable', type(error).__name__)

    def _stop(self, reason):
        if self.saturation is not None:
            return
        self.saturation = reason
        self.enabled = False
        try:
            self._append('saturation', {
                'reason': reason, 'monotonic_ns': time.monotonic_ns(),
                'callbacks': self.callbacks, 'hotspot_events': self.hotspot_events,
                'coarse_events': self.coarse_events,
                'measured_observer_thread_cpu_ns': self.observer_cpu_ns,
                'coverage_after_disable': 'UNKNOWN',
                'native_stack_and_parent_OS_monitoring': 'NOT_DISABLED_BY_PROFILER',
            }, emergency=True)
        except BaseException as error:
            self._fault('saturation_write', error)
        self._disable_current_and_future()

    def _size_sample(self, target, frame, event, returned, common):
        name = target['qualname']
        if self.sizes.get(target['id'], 0) >= MAX_SIZE_SAMPLES:
            return
        value = None
        unit = None
        if name == 'LocalEnvelope.from_payload' and event == 'return':
            value = frame.f_locals.get('text')
            if type(value) is str:
                unit = 'existing_text_characters'
        elif name == '_canonical' and event == 'return' and type(returned) is str:
            value = returned
            unit = 'returned_text_characters'
        elif name == '_history' and event == 'call':
            value = frame.f_locals.get('value')
            if type(value) is list:
                unit = 'existing_list_items'
        if unit is None:
            return
        self.sizes[target['id']] = self.sizes.get(target['id'], 0) + 1
        self._append('size', {**common, 'sample_ordinal': self.sizes[target['id']],
                              'length': len(value), 'unit': unit,
                              'return_event_success_inferred': False})

    def _transition_metadata(self, frame):
        # Exact built-ins only; no property, repr, payload traversal or digest.
        values = frame.f_locals
        result = {}
        kind = values.get('kind')
        cursor = values.get('cursor')
        body = values.get('body')
        if type(kind) is str and len(kind) <= 256:
            result['kind'] = kind
        if type(cursor) is int and -(2 ** 63) <= cursor < 2 ** 63:
            result['cursor'] = cursor
        if type(body) is dict:
            key = body.get('event_key')
            if type(key) is str and len(key) <= 256:
                result['existing_event_key'] = key
        return result

    def _checkpoint(self, now, *, final=False):
        active_counts = {index: 0 for index in self.aggregates}
        active_threads = []
        for identity, entries in self.active.items():
            active_threads.append({'thread_id': identity[0], 'native_thread_id': identity[1],
                                   'active_matched_frames': len(entries)})
            for entry in entries.values():
                active_counts[entry['target_id']] += 1
        aggregates = []
        for index, values in self.aggregates.items():
            aggregates.append({'target_id': index, **values,
                               'active_unfinished_calls': active_counts[index]})
        self._append('checkpoint', {
            'final': final, 'monotonic_ns': now,
            'process_time_ns': time.process_time_ns(),
            'observer_thread_cpu_ns_lower_bound': self.observer_cpu_ns,
            'observer_callback_max_thread_cpu_ns': self.observer_callback_max_cpu_ns,
            'callbacks': self.callbacks, 'hotspot_events': self.hotspot_events,
            'coarse_events': self.coarse_events, 'profiled_threads': len(self.seen_threads),
            'active_threads': active_threads, 'aggregates': aggregates,
            'inclusive_times_overlap': True, 'return_events_prove_success': False,
            'baseline_performance_comparison_valid': False,
            'coverage_after_disable': 'UNKNOWN' if self.saturation or self.invalid else None,
            'invalid': self.invalid, 'saturation': self.saturation, 'faults': self.faults,
        }, emergency=final)
        self.last_checkpoint_ns = now

    def _observe(self, frame, event, returned):
        if event not in ('call', 'return'):
            return
        now = time.monotonic_ns()
        thread_id = threading.get_ident()
        native_id = threading.get_native_id()
        identity = (thread_id, native_id)
        if identity not in self.seen_threads:
            if len(self.seen_threads) >= MAX_THREADS:
                self._stop('profiled_thread_saturation')
                return
            self.seen_threads[identity] = now
            self.active[identity] = {}
        code = frame.f_code
        target = self.targets.get((code.co_filename, code.co_qualname, code.co_firstlineno))
        if target is not None:
            if target['category'] == 'hotspot':
                self.hotspot_events += 1
            cpu = time.thread_time_ns()
            values = self.aggregates[target['id']]
            entries = self.active[identity]
            frame_id = id(frame)
            entry = None
            if event == 'call':
                if len(entries) >= MAX_ACTIVE_PER_THREAD:
                    self._stop('active_frame_saturation')
                    return
                values['calls'] += 1
                entry = {'target_id': target['id'], 'ordinal': values['calls'],
                         'monotonic_ns': now, 'thread_time_ns': cpu}
                entries[frame_id] = entry
            else:
                entry = entries.pop(frame_id, None)
                values['observed_return_events'] += 1
                if entry is None:
                    values['unmatched_return_events'] += 1
                else:
                    wall = max(0, now - entry['monotonic_ns'])
                    thread_cpu = max(0, cpu - entry['thread_time_ns'])
                    values['inclusive_wall_ns'] += wall
                    values['inclusive_thread_cpu_ns'] += thread_cpu
                    values['max_inclusive_wall_ns'] = max(values['max_inclusive_wall_ns'], wall)
                    values['max_inclusive_thread_cpu_ns'] = max(values['max_inclusive_thread_cpu_ns'], thread_cpu)
            common = {'target_id': target['id'], 'event': event,
                      'call_ordinal': None if entry is None else entry['ordinal'],
                      'thread_id': thread_id, 'native_thread_id': native_id,
                      'monotonic_ns': now, 'process_time_ns': time.process_time_ns(),
                      'thread_time_ns': cpu}
            if target['category'] == 'stage':
                self.coarse_events += 1
                if target['qualname'].endswith('._local_supervision_transition') and event == 'return':
                    common['optional_observed_transition'] = self._transition_metadata(frame)
                self._append('stage_event', {**common, 'return_event_success_inferred': False})
                if self.coarse_events >= MAX_COARSE:
                    self._stop('coarse_event_saturation')
            self._size_sample(target, frame, event, returned, common)
            if self.hotspot_events >= MAX_HOTSPOT_EVENTS:
                self._stop('hotspot_event_saturation')
        if self.enabled and now - self.last_checkpoint_ns >= CHECKPOINT_NS:
            self._checkpoint(now)

    def profile(self, frame, event, returned):
        """Exception-neutral callback; never returns a replacement product value."""
        if not self.enabled:
            self._disable_current_and_future()
            return
        entered_cpu = None
        locked = False
        try:
            entered_cpu = time.thread_time_ns()
            self.callbacks += 1
            if self.callbacks >= MAX_CALLBACKS:
                self._stop('profile_callback_saturation')
                return
            if event not in ('call', 'return'):
                return
            # No application function/getter runs while this lock is held.
            # Serialization/wait and I/O are instrumented-run overhead, not
            # baseline application timing; native/parent observations persist.
            self.lock.acquire()
            locked = True
            self._observe(frame, event, returned)
        except BaseException as error:
            self._fault('profile_callback', error)
        finally:
            try:
                if entered_cpu is not None:
                    elapsed = max(0, time.thread_time_ns() - entered_cpu)
                    self.observer_cpu_ns += elapsed
                    self.observer_callback_max_cpu_ns = max(self.observer_callback_max_cpu_ns, elapsed)
                if self.enabled and self.observer_cpu_ns >= MAX_CPU_NS:
                    self._stop('observer_cpu_saturation')
            except BaseException as error:
                self._fault('profile_accounting', error)
            if locked:
                try:
                    self.lock.release()
                except BaseException as error:
                    self._fault('profile_lock_release', error)

    def finish(self):
        """Idempotent profile-only finish; native ownership remains separate."""
        if self.closed:
            return
        self.enabled = False
        self._disable_current_and_future()
        try:
            self._checkpoint(time.monotonic_ns(), final=True)
            os.fsync(self.fd)
        except BaseException as error:
            self._fault('profile_finish', error)
        finally:
            try:
                os.close(self.fd)
            except BaseException as error:
                self._fault('profile_close', error)
            self.closed = True
