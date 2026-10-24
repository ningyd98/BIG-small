"""R363 observer: active SIGUSR2 subsystem removed by this plan.

Retained profile/resource coexistence and persistence algorithms are frozen R354
ancestry. Pytest's built-in fatal handler remains untouched.
"""

import json
import hashlib
import os
from pathlib import Path
import stat
import sys
import threading
import time
import types

import pytest


ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round363-p6-t3-next-evidence-decision-20261024'
COMMAND = 'R363:utc_no_sigusr2_01'
NODE = 'tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]'
DIRECTORY = ROUND / 'implementation/utc_no_sigusr2_01/diagnostic'

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
        raw = ('R363 observation invalid: ' + stage[:96] + ' / ' + error_type[:96] + '\n').encode('ascii', 'replace')
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
            raise ValueError('R363 exact diagnostic directory required')
        before = os.lstat(directory)
        if not stat.S_ISDIR(before.st_mode) or _identity(before) != directory_identity:
            raise ValueError('R363 diagnostic directory identity mismatch')
        self.directory = directory
        self.directory_identity = directory_identity
        self.fd = os.open(directory / 'observer-profile.jsonl',
                          os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.file_identity = _identity(os.fstat(self.fd))
        self.callback = self.profile
        self.delegate = self.delegated
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.enabled = False
        self.closed = False
        self.invalid = False
        self.persistence_failed = False
        self.fault_channels = set()
        self.owner_receipt_unknown_after_persistence = False
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
        self.resource_code = None
        self.resource_profile_code = None
        self.resource_owner_receipt = None
        self.item_active = False
        self.bridge_ordinal = 0
        self.active_bridge_epoch = None
        self.binding_restoration = None
        self.profile_restoration = None
        self.mode_counts = {'DIRECT': 0, 'RESOURCE_DELEGATED': 0}
        self.targets = {}
        self.aggregates = {}
        for index, (category, path, qualname, line) in enumerate(TARGETS):
            target = {'id': index, 'category': category, 'path': path,
                      'qualname': qualname, 'first_line': line}
            self.targets[(str(ROOT / path), qualname, line)] = target
            self.targets[(path, qualname, line)] = target
            self.aggregates[index] = {
                'calls': 0, 'observed_return_events': 0, 'unmatched_return_events': 0,
                'ended_unobserved_calls': 0,
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
        if self.persistence_failed:
            return False
        try:
            self.seq += 1
            raw = (json.dumps({'schema': 'bigsmall.r363.profile.v1', 'sequence': self.seq,
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
        except BaseException as error:
            self._fault('profile_optional_log', error, persistence=True)
            return False

    def _fault(self, stage, error, *, persistence=False):
        # At most16 primitive receipts and one bounded stderr attempt per channel.
        # Never detach stable hooks or recursively invoke optional persistence.
        try:
            self.invalid = True
            self.enabled = False
            if persistence:
                self.persistence_failed = True
            if stage not in self.fault_channels and len(self.fault_channels) < 16:
                self.fault_channels.add(stage)
                if len(self.faults) < 16:
                    self.faults.append({'stage': stage, 'error_type': type(error).__name__,
                                        'persistence_failure': persistence})
                _stderr_fault(stage, type(error).__name__)
        except BaseException:
            # Even a failed stderr/memory report must not reach the application.
            pass

    def _disable_current_and_future(self):
        # R357: called only by outer plugin finalization after item/resource
        # context and binding restoration. Disabled callbacks remain stable
        # no-ops until the genuine observer's restoration assertion has run.
        try:
            if self.item_active:
                raise RuntimeError('R357 cannot restore hooks during item/resource context')
            main_owned = sys.getprofile() is self.callback
            future_owned = threading.getprofile() is self.callback
            self.profile_restoration = {
                'main_hook_owned_before': main_owned, 'future_hook_owned_before': future_owned,
                'already_running_other_threads': 'UNKNOWN', 'foreign_hooks_overwritten': False,
            }
            if main_owned:
                sys.setprofile(self.previous_sys_profile)
            if future_owned:
                threading.setprofile(self.previous_thread_profile)
            self.profile_restoration.update(
                main_restored=main_owned and sys.getprofile() is self.previous_sys_profile,
                future_restored=future_owned and threading.getprofile() is self.previous_thread_profile)
            if not main_owned or not future_owned:
                self.invalid = True
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
            'received_modes': self.mode_counts,
            'resource_owner_receipt': self.resource_owner_receipt,
            'active_bridge_epoch': self.active_bridge_epoch,
            'exercise_tail_and_return_coverage': 'UNKNOWN_AFTER_ORIGINAL_EARLY_SEAM_CLEAR',
            'binding_restoration': self.binding_restoration,
            'profile_restoration': self.profile_restoration,
            'active_threads': active_threads, 'aggregates': aggregates,
            'inclusive_times_overlap': True, 'return_events_prove_success': False,
            'baseline_performance_comparison_valid': False,
            'coverage_after_disable': 'UNKNOWN' if self.saturation or self.invalid else None,
            'invalid': self.invalid, 'saturation': self.saturation, 'faults': self.faults,
        }, emergency=final)
        self.last_checkpoint_ns = now

    def _observe(self, frame, event, returned, mode):
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
                         'monotonic_ns': now, 'thread_time_ns': cpu,
                         'mode': mode, 'bridge_epoch': self.active_bridge_epoch}
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
                      'mode': mode, 'bridge_epoch': self.active_bridge_epoch,
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
        return self._dispatch(frame, event, returned, 'DIRECT')

    def delegated(self, frame, event, returned):
        # Genuine resource accounting has already run. Never call it again.
        return self._dispatch(frame, event, returned, 'RESOURCE_DELEGATED')

    def _capture_resource_owner(self, frame):
        # R357 bounded control receipt, not a24th measured target. Only the
        # current frame/direct parent can be the authentic fixture generator.
        if self.resource_code is None or self.resource_owner_receipt is not None:
            return
        owner = frame if frame.f_code is self.resource_code else frame.f_back
        if owner is None or owner.f_code is not self.resource_code:
            return
        local = owner.f_locals
        if not all(name in local for name in ('previous_profile', 'previous_thread_profile', 'state')):
            return
        previous_main = local['previous_profile']
        previous_future = local['previous_thread_profile']
        owned = (previous_main is self.callback and previous_future is self.callback
                 and sys.getprofile() is self.callback and threading.getprofile() is self.callback)
        self.resource_owner_receipt = {
            'monotonic_ns': time.monotonic_ns(), 'thread_id': threading.get_ident(),
            'native_thread_id': threading.get_native_id(),
            'fixture_code_id': id(self.resource_code), 'state_id': id(local['state']),
            'previous_main_profile_id': id(previous_main),
            'previous_future_profile_id': id(previous_future),
            'stable_callback_id': id(self.callback), 'both_previous_hooks_owned': owned,
            'direct_current_hooks_owned': sys.getprofile() is self.callback and threading.getprofile() is self.callback,
            'frame_retained': False, 'measured_target': False,
        }
        self._append('resource_outer_hook_ownership', self.resource_owner_receipt)
        if not owned:
            self._fault('resource_outer_hook_ownership', RuntimeError('foreign previous profile hook'))

    def _dispatch(self, frame, event, returned, mode):
        """Exception-neutral callback; never returns a replacement product value."""
        if not self.enabled:
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
            self.mode_counts[mode] += 1
            # No application function/getter runs while this lock is held.
            # Serialization/wait and I/O are instrumented-run overhead, not
            # baseline application timing; native/parent observations persist.
            self.lock.acquire()
            locked = True
            if mode == 'DIRECT':
                self._capture_resource_owner(frame)
            if self.enabled:
                self._observe(frame, event, returned, mode)
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

    def end_exercise_unobserved(self, epoch, unwinding):
        """Original4133 clears delegation; do not invent its missing return."""
        ended = 0
        try:
            with self.lock:
                for entries in self.active.values():
                    for frame_id, entry in list(entries.items()):
                        if entry['target_id'] == 0 and entry['bridge_epoch'] == epoch:
                            entries.pop(frame_id)
                            self.aggregates[0]['ended_unobserved_calls'] += 1
                            ended += 1
                self._append('bridge_exit', {
                    'bridge_epoch': epoch, 'monotonic_ns': time.monotonic_ns(),
                    'process_time_ns': time.process_time_ns(), 'thread_time_ns': time.thread_time_ns(),
                    'original_outcome': 'UNWIND' if unwinding else 'RETURNED_TO_ADAPTER',
                    'original_return_event': 'UNOBSERVED', 'ended_unobserved_calls': ended,
                    'cleanup_tail_coverage': 'UNKNOWN_AFTER_ORIGINAL_EARLY_SEAM_CLEAR',
                    'measured_target': False, 'successful_assertions_inferred': False,
                })
        finally:
            self.active_bridge_epoch = None


def _regular_bytes(path, cap):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
        raise ValueError('R363 bounded regular nofollow artifact required: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                                value.st_mtime_ns, value.st_ctime_ns)
        if fields(before) != fields(opened):
            raise ValueError('R363 artifact changed before read')
        raw = bytearray()
        while len(raw) < opened.st_size:
            chunk = os.read(descriptor, min(65536, opened.st_size - len(raw)))
            if not chunk:
                raise OSError('R363 incomplete artifact read')
            raw.extend(chunk)
        if fields(opened) != fields(os.fstat(descriptor)) or fields(opened) != fields(os.lstat(path)):
            raise ValueError('R363 artifact changed during read')
        return bytes(raw)
    finally:
        os.close(descriptor)


def _pin_bytes(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _json_artifact(path, cap=2 * 1024 * 1024):
    raw = _regular_bytes(path, cap)
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError('R363 JSON object required')
    return value, _pin_bytes(path, raw)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _startup_contract():
    plan, plan_pin = _json_artifact(ROUND / 'plan.json')
    _require(plan_pin['sha256'] == '67fc2af2d937994bc07c553c2ba631b27f6b10d45403775897b69794846c8502',
             'R363 observer exact plan changed')
    gate, gate_pin = _json_artifact(ROUND / 'source-gate.json')
    accepted, _ = _json_artifact(ROUND / 'root-source-acceptance.json')
    plugin_path = ROUND / 'implementation/r363_live_observer.py'
    _require(Path(__file__).absolute() == plugin_path, 'R363 actual plugin path differs')
    plugin_pin = _pin_bytes(plugin_path, _regular_bytes(plugin_path, 2 * 1024 * 1024))
    _require(gate['round'] == accepted['round'] == 'R363'
             and gate['plan'] == accepted['plan'] == plan_pin
             and gate['observer'] == accepted['observer'] == plugin_pin
             and accepted['actor'] == '/root' and accepted['reviewed'] is True
             and accepted['source_gate'] == gate_pin,
             'R363 actual observer/gate lacks exact new ROOT acceptance')
    _require(gate['effective_references'] == accepted['effective_references']
             and gate['effective_references']['baseline_observer']
                 == plan['baseline']['implementation/r354_live_observer.py'],
             'R363 exact immediate baseline differs')
    _require(gate['frozen_ancestor_references'] == accepted['frozen_ancestor_references']
             == plan['frozen_ancestor_references'], 'R363 frozen ancestor references differ')
    for reference in plan['frozen_ancestor_references'].values():
        _require(_pin_bytes(Path(reference['path']), _regular_bytes(Path(reference['path']), 2 * 1024 * 1024))
                 == reference, 'R363 frozen ancestor changed')
    persistence, _ = _json_artifact(Path(plan['frozen_ancestor_references']['observer_persistence_acceptance']['path']))
    _require(persistence['round'] == 'R358' and persistence['actor'] == '/root'
             and persistence['reviewed'] is True
             and persistence['plan'] == plan['frozen_ancestor_references']['observer_persistence_clarification']
             and persistence['observer'] == plan['baseline']['implementation/r354_live_observer.py'],
             'R358 acceptance binds only frozen R354 ancestor')
    _require(gate['active_signal_sampling'] == accepted['active_signal_sampling'] == 'DISABLED_BY_PLAN'
             and accepted['source_proof'] == gate['source_proof'],
             'R363 new protected-profile/source review required')
    command = plan['commands']['utc_no_sigusr2_01']
    _require(gate['commands'] == plan['commands'] and command['nodes'] == [NODE]
             and command['output'] == str(DIRECTORY.parent)
             and os.getcwd() == str(ROOT), 'R363 literal node/cwd/output differs')
    _require(sys.orig_argv == command['child_argv'], 'R363 actual original child argv differs')
    _require(all(os.environ.get(key) == value for key, value in command['child_env'].items()),
             'R363 planned child environment differs')
    _require(os.environ.get('BIGSMALL_R158_COMMAND') == COMMAND
             and os.environ.get('BIGSMALL_R363_DIAGNOSTIC_DIR') == str(DIRECTORY),
             'R363 actual diagnostic identity differs')
    root, _ = _json_artifact(ROUND / 'root-command-ledger.json')
    author, _ = _json_artifact(ROUND / 'implementation/author-command-ledger.json')
    root_slot, author_slot = root['commands']['utc_no_sigusr2_01'], author['commands']['utc_no_sigusr2_01']
    _require(root_slot['state'] == 'RESERVED' and author_slot['state'] == 'CONSUMED_BEFORE_START'
             and root_slot['reservation_id'] == author_slot['reservation_id']
             and root_slot['source_gate'] == gate_pin
             and root_slot['used'] == author_slot['used'] == 1
             and root_slot['remaining'] == author_slot['remaining'] == 0,
             'R363 actual consume-before-child reservation differs')
    _require(sys.getprofile() is None and threading.getprofile() is None,
             'R363 refuses existing profile ownership')
    info = os.lstat(DIRECTORY)
    _require(stat.S_ISDIR(info.st_mode), 'R363 real diagnostic output directory required')
    return gate, gate_pin, plugin_pin, _identity(info)


def _function_code(function, qualname, line):
    _require(type(function) is types.FunctionType, 'R357 original exact Python function required')
    code = function.__code__
    _require(code.co_filename in (str(ROOT / 'tests/test_operational_runtime_closure.py'),
                                  'tests/test_operational_runtime_closure.py')
             and code.co_qualname == qualname and code.co_firstlineno == line,
             'R357 frozen fixture code coordinate differs')
    return code


def _item_adapter(item, profiler):
    _require(item.nodeid == NODE and type(item.module) is types.ModuleType,
             'R357 exact already-collected item/module required')
    module = item.module
    path = ROOT / 'tests/test_operational_runtime_closure.py'
    _require(Path(module.__file__).absolute() == path
             and sys.modules.get(module.__name__) is module
             and hashlib.sha256(_regular_bytes(path, 1024 * 1024)).hexdigest()
                 == '54b988c6257f51efcc796fd5a3f376c45fee84c31c6b3fa3f7593853da0d11ca',
             'R357 actual collected module/source identity differs')
    original = module.__dict__['_b_t2_exercise']
    code = _function_code(original, '_b_t2_exercise', 4082)
    _require(code.co_argcount == 5 and code.co_kwonlyargcount == 0 and not code.co_flags & 12
             and '__wrapped__' not in original.__dict__, 'R357 unexpected exercise wrapper/signature')
    observer = module.__dict__['_b_t2_observe']
    _require(type(observer) is types.FunctionType and type(observer.__dict__.get('__wrapped__')) is types.FunctionType,
             'R357 actual contextmanager original required')
    generator = observer.__dict__['__wrapped__']
    profiler.resource_code = _function_code(generator, '_b_t2_observe', 3516)
    nested = [value for value in profiler.resource_code.co_consts
              if type(value) is types.CodeType and value.co_qualname == '_b_t2_observe.<locals>.profile'
              and value.co_firstlineno == 3809]
    _require(len(nested) == 1, 'R357 unique authentic nested resource profile required')
    profiler.resource_profile_code = nested[0]

    def adapter(monkeypatch, directory, backend, observed, callback):
        # Pure ownership guards remain rejecting, independent of optional I/O.
        try:
            profiler.bridge_ordinal += 1
            _require(profiler.bridge_ordinal <= 3, 'R357 at most three original scenario calls')
            current = sys.getprofile()
            _require(current is threading.getprofile() and type(current) is types.FunctionType
                     and current.__code__ is profiler.resource_profile_code,
                     'R357 authentic current main/future resource profile required')
            cells = dict(zip(current.__code__.co_freevars, current.__closure__ or ()))
            _require('state' in cells and cells['state'].cell_contents is observed
                     and type(observed) is types.SimpleNamespace,
                     'R357 actual resource closure state must be passed observed identity')
            owner = profiler.resource_owner_receipt
            if owner is not None:
                _require(owner['both_previous_hooks_owned'] is True and owner['state_id'] == id(observed),
                         'R357 actual previous outer diagnostic hooks foreign/wrong state')
            else:
                _require(profiler.persistence_failed and not profiler.enabled,
                         'R357 actual previous outer diagnostic hook ownership UNKNOWN')
                profiler.owner_receipt_unknown_after_persistence = True
            _require(observed.__dict__.get('wait_observer') is None,
                     'R357 foreign wait_observer callback cannot be replaced')
        except BaseException as error:
            profiler._fault('bridge_setup', error)
            raise
        epoch = 'bridge:' + str(profiler.bridge_ordinal)
        entry_written = profiler._append('bridge_entry', {
            'bridge_epoch': epoch, 'scenario_ordinal': profiler.bridge_ordinal,
            'monotonic_ns': time.monotonic_ns(), 'process_time_ns': time.process_time_ns(),
            'thread_time_ns': time.thread_time_ns(), 'thread_id': threading.get_ident(),
            'native_thread_id': threading.get_native_id(), 'resource_profile_id': id(current),
            'state_id': id(observed), 'delegate_attached': profiler.enabled and owner is not None,
            'owner_receipt': 'AUTHENTICATED' if owner is not None else 'UNKNOWN_AFTER_PERSISTENCE_FAILURE',
            'coverage_disabled': not profiler.enabled, 'measured_target': False,
        })
        bookkeeping_open = entry_written and profiler.enabled and owner is not None
        if bookkeeping_open:
            profiler.active_bridge_epoch = epoch
            observed.wait_observer = profiler.delegate
        try:
            # Exactly one original call, outside observer-catching guards.
            return original(monkeypatch, directory, backend, observed, callback)
        finally:
            unwinding = sys.exc_info()[0] is not None
            try:
                seam = observed.__dict__.get('wait_observer')
                if seam is profiler.delegate:
                    observed.wait_observer = None
                elif seam is not None:
                    profiler._fault('bridge_foreign_seam', RuntimeError('foreign callback preserved'))
                if bookkeeping_open:
                    profiler.end_exercise_unobserved(epoch, unwinding)
            except BaseException as error:
                # Never mask the exact original result/exception.
                profiler._fault('bridge_finally', error)
            finally:
                profiler.active_bridge_epoch = None

    return module, original, adapter


_STATE = None


def pytest_sessionstart(session):
    global _STATE
    _require(_STATE is None, 'R363 observer session starts once only')
    gate, gate_pin, plugin_pin, directory_identity = _startup_contract()
    profiler = _Profiler(DIRECTORY, directory_identity)
    _STATE = {'profiler': profiler, 'status_attempted': False,
              'gate': gate_pin, 'observer': plugin_pin, 'selection_verified': False}
    profiler.previous_sys_profile = sys.getprofile()
    profiler.previous_thread_profile = threading.getprofile()
    _require(profiler.previous_sys_profile is None and profiler.previous_thread_profile is None,
             'R363 profile owner changed during profile startup')
    profiler._append('start', {'targets': TARGETS, 'pid': os.getpid(),
        'main_thread_id': threading.get_ident(), 'main_native_thread_id': threading.get_native_id(),
        'coverage': 'main and future Python threads only; native tasks are not Python-profile coverage',
        'resource_delegate_mode': 'R357 authenticated fixture seam',
        'observer_CPU_is_lower_bound': True, 'baseline_performance_comparison_valid': False})
    profiler.enabled = not profiler.persistence_failed and not profiler.invalid and profiler.saturation is None
    threading.setprofile(profiler.callback)
    sys.setprofile(profiler.callback)


def pytest_collection_finish(session):
    _require(_STATE is not None and len(session.items) == 1 and session.items[0].nodeid == NODE,
             'R363 requires exactly the literal one collected UTC-memory item')
    _STATE['selection_verified'] = True


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    _require(_STATE is not None and _STATE['selection_verified'] and item.nodeid == NODE,
             'R357 exact selected-item call wrapper only')
    profiler = _STATE['profiler']
    module, original, adapter = _item_adapter(item, profiler)
    _require(module.__dict__.get('_b_t2_exercise') is original,
             'R357 original binding changed before transparent adapter')
    profiler.item_active = True
    module._b_t2_exercise = adapter
    try:
        yield  # Preserve pytest's exact outcome; never force a result/exception.
    finally:
        try:
            owned = module.__dict__.get('_b_t2_exercise') is adapter
            if owned:
                module._b_t2_exercise = original
            profiler.binding_restoration = {
                'adapter_owned_before_restore': owned,
                'original_binding_restored': owned and module.__dict__.get('_b_t2_exercise') is original,
                'foreign_replacement_overwritten': False,
            }
            if not owned:
                profiler._fault('item_binding_restore', RuntimeError('foreign module binding preserved'))
        except BaseException as error:
            profiler._fault('item_binding_restore', error)
        finally:
            profiler.item_active = False
            profiler.finish()


def _finish_observer():
    if _STATE is None or _STATE['status_attempted']:
        return
    _STATE['status_attempted'] = True
    profiler = _STATE['profiler']
    profiler.finish()
    try:
        record = {'schema': 'bigsmall.r363.observer-status.v1', 'command_id': COMMAND,
                  'pid': os.getpid(), 'observer': _STATE['observer'], 'source_gate': _STATE['gate'],
                  'selection_verified': _STATE['selection_verified'],
                  'observation_invalid': profiler.invalid, 'saturation': profiler.saturation,
                  'persistence_failed': profiler.persistence_failed,
                  'coverage_after_disable': 'UNKNOWN',
                  'owner_receipt_unknown_after_persistence': profiler.owner_receipt_unknown_after_persistence,
                  'faults': profiler.faults, 'profile_restoration': profiler.profile_restoration,
                  'binding_restoration': profiler.binding_restoration,
                  'bridge_calls': profiler.bridge_ordinal,
                  'exercise_tail_and_original_return': 'UNOBSERVED_AFTER_ORIGINAL_EARLY_CLEAR',
                  'active_signal_sampling': 'DISABLED_BY_PLAN',
                  'native_ownership': 'DISABLED_BY_PLAN', 'stack_sampling_opportunities': 0,
                  'signal_submissions': 0, 'native_registration_success': None,
                  'native_unregister_attempted': None, 'stack_fd_retained_to_process_exit': None,
                  'mask_restored': None, 'native_handler_pointer_verified': None,
                  'in_process_default_disposition_verified': None,
                  'diagnostic_only': True, 'behavior_acceptance_credit': 0}
        raw = (json.dumps(record, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')
        _require(len(raw) <= 65536, 'R363 observer status64KiB bound')
        descriptor = os.open(DIRECTORY / 'observer-status.json',
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException as error:
        profiler._fault('observer_status', error, persistence=True)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _finish_observer()


def pytest_unconfigure(config):
    _finish_observer()
