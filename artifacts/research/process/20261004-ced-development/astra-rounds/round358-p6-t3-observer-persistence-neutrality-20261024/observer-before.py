"""R354 bounded diagnostic plugin, source preparation only until ROOT release.

R356 controls native registration/retirement; R357 alone permits the transparent
one-item _b_t2_exercise binding adapter. No product source/function is replaced.
No hook installs itself merely by importing this module.
"""

import json
import faulthandler
import fcntl
import hashlib
import signal
import os
from pathlib import Path
import stat
import sys
import threading
import time
import types

import pytest


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


class _SignalGuardError(ValueError):
    def __init__(self, reason, observation):
        super().__init__(reason)
        self.observation = {**observation, "failure_monotonic": time.monotonic()}


def _kernel_signal_snapshot(pid, *, deadline, require_single):
    """R356 bounded kernel snapshot, never native handler-pointer attestation.

    Per snapshot: <=one64KiB status read, one8KiB stat read, <=two task
    entries. Caller caps startup/retirement at four status reads each.
    All snapshots share the caller's original <=0.1s guard deadline.
    """

    observation = {'pid': pid, 'guard_deadline': deadline, 'native_handler_pointer_verified': False}
    try:
        began = time.monotonic()

        def need(ok, message):
            if not ok:
                raise _SignalGuardError(message, observation)

        def read(path, cap):
            need(time.monotonic() < deadline, "signal guard elapsed before read")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                raw = bytearray()
                while True:
                    need(time.monotonic() < deadline, "signal guard elapsed during read")
                    need(len(raw) < cap, "signal proc file reached conservative byte boundary")
                    chunk = os.read(descriptor, min(4096, cap - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                need(time.monotonic() < deadline, "signal guard read overrun")
                return bytes(raw)
            finally:
                os.close(descriptor)

        base = Path('/proc') / str(pid)
        raw = read(base / 'status', 65536)
        fields = {}
        wanted = (b'Pid', b'Tgid', b'Threads', b'TracerPid', b'SigCgt', b'SigIgn',
                  b'SigBlk', b'SigPnd', b'ShdPnd')
        for line in raw.splitlines():
            key, separator, value = line.partition(b':')
            if separator and key in wanted:
                need(key not in fields, "duplicate required signal status field")
                fields[key] = value.strip()
        observation['available_field_names'] = [key.decode('ascii') for key in fields]
        observation['available_status_fields'] = {key.decode('ascii'): (value.decode('ascii', 'replace') if len(value) <= 256 else None) for key, value in fields.items()}
        need(all(key in fields for key in wanted), "missing required signal status field")
        numeric = {key.decode('ascii'): int(fields[key]) for key in wanted[:4]}
        observation['available_status_fields'] = {key.decode('ascii'): (value.decode('ascii', 'replace') if len(value) <= 256 else None) for key, value in fields.items()}
        observation['oversize_status_fields'] = {key.decode('ascii'): len(value) for key, value in fields.items() if len(value) > 256}
        need(not observation['oversize_status_fields'], 'oversize required signal status field')
        observation['numeric_status_fields'] = numeric
        masks = {key.decode('ascii'): fields[key].decode('ascii') for key in wanted[4:]}
        mask_values = {key: int(value, 16) for key, value in masks.items()}
        observation['raw_mask_fields'] = masks
        bit = 1 << (int(signal.SIGUSR2) - 1)
        observation['target_bits'] = {key: bool(value & bit) for key, value in mask_values.items()}
        need(numeric['Pid'] == numeric['Tgid'] == pid, "signal kernel leader identity mismatch")
        stat_raw = read(base / 'stat', 8192)
        first, last = stat_raw.find(b'('), stat_raw.rfind(b')')
        need(first > 0 and last > first and int(stat_raw[:first].strip()) == pid,
             "signal proc stat numeric PID boundary mismatch")
        stat_fields = stat_raw[last + 1:].split()
        need(len(stat_fields) >= 20, "signal process starttime unavailable")
        starttime = int(stat_fields[19])
        observation['process_starttime_ticks'] = starttime
        tasks = None
        if require_single:
            tasks = []
            observation['kernel_tasks'] = tasks
            with os.scandir(base / 'task') as entries:
                for entry in entries:
                    need(time.monotonic() < deadline, "signal task guard elapsed")
                    need(entry.name.isdecimal(), "signal task name nonnumeric")
                    tasks.append(int(entry.name))
                    if len(tasks) == 2:
                        break
            need(tasks == [pid] and numeric['Threads'] == 1, "signal guard requires one kernel task")
        bit = 1 << (int(signal.SIGUSR2) - 1)
        completed = time.monotonic()
        need(completed < deadline, "signal guard completed beyond original deadline")
        return {'pid': pid, 'process_starttime_ticks': starttime,
                'status_fields': numeric, 'raw_mask_fields': masks,
                'target_bits': {key: bool(value & bit) for key, value in mask_values.items()},
                'kernel_tasks': tasks, 'observed_monotonic': began,
                'completed_monotonic': completed, 'elapsed_seconds': completed - began,
                'status_read_bytes': len(raw), 'stat_read_bytes': len(stat_raw),
                'native_handler_pointer_verified': False, 'atomic_install_or_restore': False}
    except _SignalGuardError:
        raise
    except BaseException as error:
        raise _SignalGuardError(type(error).__name__ + ': ' + str(error)[:256], observation) from error


class _SignalControl:
    """R356 conditional controlled-child contract; never native-pointer proof."""

    def __init__(self, directory, plugin_pin, gate_pin):
        self.directory = directory
        self.plugin_pin = plugin_pin
        self.gate_pin = gate_pin
        self.pid = os.getpid()
        self.epoch = str(self.pid) + ':' + str(time.monotonic_ns())
        self.starttime = None
        self.lock_fd = None
        self.log_fd = None
        self.stack_fd = None
        self.lock_identity = None
        self.stack_identity = None
        self.register_attempted = False
        self.registration_success = False
        self.unregister_attempted = False
        self.unregister_returned_true = False
        self.retirement_attempted = False
        self.ownership_drift = False
        self.saved_mask = None
        self.mask_restored = None
        self.mask_temporarily_blocked = False
        self.read_counts = {'startup': 0, 'retirement': 0}
        self.last_snapshot = None
        self.state_sequence = 0
        self.ready_pin = None
        self.native_state = 'UNCLAIMED'

    def _need(self, condition, message):
        if not condition:
            raise ValueError(message)

    def _time(self, deadline):
        self._need(time.monotonic() < deadline, 'R356 original0.1s guard deadline exceeded')

    def _log(self, kind, data):
        raw = (json.dumps({'schema': 'bigsmall.r356.signal-ownership.v1', 'kind': kind,
                           'command_id': COMMAND, 'pid': self.pid, 'epoch': self.epoch,
                           'monotonic': time.monotonic(), **data},
                          ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
        self._need(len(raw) <= 8192 and os.fstat(self.log_fd).st_size + len(raw) <= 65536,
                   'R356 ownership log64KiB bound')
        _write_all(self.log_fd, raw)

    def _snapshot(self, phase, deadline):
        self.read_counts[phase] += 1
        self._need(self.read_counts[phase] <= 4, 'R356 four status reads per phase')
        try:
            snapshot = _kernel_signal_snapshot(self.pid, deadline=deadline, require_single=True)
        except BaseException as error:
            self._log('kernel_snapshot_rejected', {'phase': phase, 'reason': str(error)[:512],
                'error_type': type(error).__name__,
                'observed_partial': getattr(error, 'observation', None),
                'status_reads_attempted': self.read_counts[phase]})
            raise
        self.last_snapshot = snapshot
        if self.starttime is None:
            self.starttime = snapshot['process_starttime_ticks']
        self._need(snapshot['process_starttime_ticks'] == self.starttime, 'R356 process identity drift')
        self._need(snapshot['status_fields']['TracerPid'] == 0, 'R356 traced child ineligible')
        self._log('kernel_snapshot', {'phase': phase, 'snapshot': snapshot})
        self._time(deadline)
        return snapshot

    def _eligible(self, snapshot, *, caught, blocked):
        bits = snapshot['target_bits']
        self._need(signal.getsignal(signal.SIGUSR2) is signal.SIG_DFL,
                   'R356 requires Python-visible exact SIG_DFL')
        self._need(bits['SigCgt'] is caught and bits['SigBlk'] is blocked
                   and not bits['SigIgn'] and not bits['SigPnd'] and not bits['ShdPnd'],
                   'R356 disposition/mask/pending eligibility rejected')

    def _state(self, value, *, deadline=None):
        self.state_sequence += 1
        record = {'schema': 'bigsmall.r356.signal-state.v1', 'command_id': COMMAND,
                  'pid': self.pid, 'process_starttime_ticks': self.starttime,
                  'epoch': self.epoch, 'state': value, 'state_sequence': self.state_sequence,
                  'plugin': self.plugin_pin, 'source_gate': self.gate_pin,
                  'control_lock': {'path': str(self.directory / 'signal-control.lock'), **self.lock_identity},
                  'stack': None if self.stack_identity is None else {
                      'path': str(self.directory / 'stacks.raw'), **self.stack_identity},
                  'ready_pin': self.ready_pin,
                  'last_observed_masks': None if self.last_snapshot is None else self.last_snapshot['raw_mask_fields'],
                  'own_registration_success': self.registration_success,
                  'unregister_attempted': self.unregister_attempted,
                  'mask_restored': self.mask_restored,
                  'saved_thread_mask': None if self.saved_mask is None else sorted(int(value) for value in self.saved_mask),
                  'native_handler_pointer_verified': False,
                  'controlled_exclusive_use_assumed': True,
                  'atomic_install_or_restore': False}
        raw = (json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
        self._need(len(raw) <= 4096, 'R356 signal-state4KiB bound')
        if deadline is not None:
            self._time(deadline)
        temporary = self.directory / 'signal-state.next'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.directory / 'signal-state.json')
        self.native_state = value
        self._log('state', {'state': value, 'state_sequence': self.state_sequence,
                            'mask_restored': self.mask_restored})
        if deadline is not None:
            self._time(deadline)

    def _lock(self):
        current = os.lstat(self.directory / 'signal-control.lock')
        opened = os.fstat(self.lock_fd)
        self._need(stat.S_ISREG(current.st_mode) and stat.S_ISREG(opened.st_mode)
                   and _identity(current) == _identity(opened) == self.lock_identity,
                   'R356 stable nofollow lock inode changed')
        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _restore_mask(self):
        self._need(self.saved_mask is not None, 'R356 saved mask unavailable')
        signal.pthread_sigmask(signal.SIG_SETMASK, self.saved_mask)
        actual = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        self._need(actual == self.saved_mask and signal.SIGUSR2 not in actual,
                   'R356 exact saved thread mask restoration failed')
        self.mask_temporarily_blocked = False
        self.mask_restored = True

    def start(self):
        """Called once at sessionstart, before profile install or test behavior."""
        deadline = time.monotonic() + 0.1
        locked = False
        self._need(self.lock_fd is None and not self.register_attempted, 'R356 startup once only')
        try:
            self._need(threading.current_thread() is threading.main_thread()
                       and threading.get_native_id() == self.pid,
                       'R356 main Python and native leader required')
            self._need(sys.getprofile() is None and threading.getprofile() is None,
                       'R356 registration must precede profile installation')
            self._need(sys.gettrace() is None and threading.gettrace() is None,
                       'R356 no tracing callback may interpose registration')
            self.lock_fd = os.open(self.directory / 'signal-control.lock',
                                   os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self.lock_identity = _identity(os.fstat(self.lock_fd))
            self.log_fd = os.open(self.directory / 'signal-ownership.jsonl',
                                  os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self._lock()
            locked = True
            self._state('INSTALLING', deadline=deadline)
            # Two independent snapshots, not an atomic ownership guarantee.
            self._eligible(self._snapshot('startup', deadline), caught=False, blocked=False)
            self._eligible(self._snapshot('startup', deadline), caught=False, blocked=False)
            self.saved_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR2})
            self.mask_temporarily_blocked = True
            self.mask_restored = False
            self._log('saved_thread_mask', {'phase': 'startup',
                'prior_mask': sorted(int(value) for value in self.saved_mask)})
            self._need(signal.SIGUSR2 not in self.saved_mask, 'R356 prior target mask was blocked')
            self._eligible(self._snapshot('startup', deadline), caught=False, blocked=True)
            self._time(deadline)
            self.stack_fd = os.open(self.directory / 'stacks.raw',
                                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self.stack_identity = _identity(os.fstat(self.stack_fd))
            # No product callback/import or profile is interposed here.
            self.register_attempted = True
            faulthandler.register(signal.SIGUSR2, file=self.stack_fd, all_threads=True, chain=False)
            self.registration_success = True
            self._eligible(self._snapshot('startup', deadline), caught=True, blocked=True)
            self._restore_mask()
            self._time(deadline)
            ready = {'schema': 'bigsmall.r356.native-stack-ready.v1', 'command_id': COMMAND,
                     'pid': self.pid, 'process_starttime_ticks': self.starttime, 'epoch': self.epoch,
                     'plugin': self.plugin_pin, 'source_gate': self.gate_pin,
                     'control_lock': {'path': str(self.directory / 'signal-control.lock'), **self.lock_identity},
                     'stack': {'path': str(self.directory / 'stacks.raw'), **self.stack_identity},
                     'target_mask_unblocked_verified': True,
                     'native_handler_pointer_verified': False, 'atomic_install_or_restore': False,
                     'controlled_exclusive_use_assumed': True}
            raw = (json.dumps(ready, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
            self._need(len(raw) <= 4096, 'R356 immutable readiness4KiB bound')
            path = self.directory / 'stack-ready.json'
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                _write_all(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.ready_pin = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            self._state('READY', deadline=deadline)
        except BaseException as error:
            # No unregister probe or blind restore after partial installation.
            if self.log_fd is not None:
                try:
                    self._log('startup_rejected', {'type': type(error).__name__, 'reason': str(error)[:512],
                        'observed_partial': getattr(error, 'observation', None),
                        'last_complete_snapshot': self.last_snapshot,
                        'registration_attempted': self.register_attempted,
                        'own_registration_success': self.registration_success,
                        'mask_restoration': 'UNKNOWN' if self.mask_temporarily_blocked else self.mask_restored,
                        'descriptor_retained_to_process_exit': self.stack_fd is not None})
                    if locked:
                        self._state('REJECTED')
                except BaseException as retention_error:
                    _stderr_fault('native_startup_retention', type(retention_error).__name__)
            raise
        finally:
            if locked:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)

    def retire(self):
        """At most one safe unregister; uncertainty retains fd to process exit."""
        if self.retirement_attempted:
            return
        self.retirement_attempted = True
        deadline = time.monotonic() + 0.1
        locked = False
        current_snapshot = None
        try:
            self._need(self.lock_fd is not None and self.log_fd is not None, 'R356 control was not initialized')
            self._lock()
            locked = True
            self._state('CLOSED', deadline=deadline)
            self._need(self.registration_success and not self.ownership_drift
                       and not self.unregister_attempted, 'R356 no safe owned registration to retire')
            current_snapshot = self._snapshot('retirement', deadline)
            self._eligible(current_snapshot, caught=True, blocked=False)
            self.saved_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR2})
            self.mask_temporarily_blocked = True
            self.mask_restored = False
            self._log('saved_thread_mask', {'phase': 'retirement',
                'prior_mask': sorted(int(value) for value in self.saved_mask)})
            self._need(signal.SIGUSR2 not in self.saved_mask, 'R356 teardown prior target mask was blocked')
            current_snapshot = None
            current_snapshot = self._snapshot('retirement', deadline)
            self._eligible(current_snapshot, caught=True, blocked=True)
            self._time(deadline)
            self.unregister_attempted = True
            self.unregister_returned_true = faulthandler.unregister(signal.SIGUSR2) is True
            self._need(self.unregister_returned_true, 'R356 unregister did not report owned success')
            current_snapshot = self._snapshot('retirement', deadline)
            self._eligible(current_snapshot, caught=False, blocked=True)
            self._restore_mask()
            current_snapshot = self._snapshot('retirement', deadline)
            self._eligible(current_snapshot, caught=False, blocked=False)
            self._state('RETIRED_VERIFIED_DEFAULT', deadline=deadline)
            os.fsync(self.log_fd)
            self._time(deadline)
            os.close(self.stack_fd)
            self.stack_fd = None
        except BaseException as error:
            # Restoring an actual saved mask is safe only with a still-owned,
            # observed caught handler. Never unblock an uncertain default/pending
            # state after an unregister attempt, or close/reuse its descriptor.
            if (self.mask_temporarily_blocked and not self.unregister_attempted
                    and self.registration_success and current_snapshot is not None
                    and current_snapshot['target_bits']['SigCgt']
                    and not current_snapshot['target_bits']['SigIgn']
                    and signal.getsignal(signal.SIGUSR2) is signal.SIG_DFL):
                try:
                    self._restore_mask()
                except BaseException:
                    self.mask_restored = None
            elif self.mask_temporarily_blocked:
                self.mask_restored = None
            self.native_state = 'RETIRED_PROCESS_EXIT_ONLY'
            try:
                if self.log_fd is not None:
                    self._log('retirement_deferred', {'type': type(error).__name__, 'reason': str(error)[:512],
                        'observed_partial': getattr(error, 'observation', None),
                        'last_complete_snapshot': self.last_snapshot,
                        'state': self.native_state, 'mask_restored': self.mask_restored,
                        'descriptor_retained_to_process_exit': self.stack_fd is not None,
                        'in_process_restoration_success': False})
                    if locked:
                        self._state('RETIRED_PROCESS_EXIT_ONLY')
            except BaseException as retention_error:
                _stderr_fault('native_retirement_retention', type(retention_error).__name__)
        finally:
            if locked:
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                except BaseException as error:
                    _stderr_fault('native_retirement_unlock', type(error).__name__)


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
        self.delegate = self.delegated
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
            self.active_bridge_epoch = None


def _regular_bytes(path, cap):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
        raise ValueError('R354 bounded regular nofollow artifact required: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                                value.st_mtime_ns, value.st_ctime_ns)
        if fields(before) != fields(opened):
            raise ValueError('R354 artifact changed before read')
        raw = bytearray()
        while len(raw) < opened.st_size:
            chunk = os.read(descriptor, min(65536, opened.st_size - len(raw)))
            if not chunk:
                raise OSError('R354 incomplete artifact read')
            raw.extend(chunk)
        if fields(opened) != fields(os.fstat(descriptor)) or fields(opened) != fields(os.lstat(path)):
            raise ValueError('R354 artifact changed during read')
        return bytes(raw)
    finally:
        os.close(descriptor)


def _pin_bytes(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _json_artifact(path, cap=2 * 1024 * 1024):
    raw = _regular_bytes(path, cap)
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError('R354 JSON object required')
    return value, _pin_bytes(path, raw)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _startup_contract():
    plan, plan_pin = _json_artifact(ROUND / 'plan.json')
    _require(plan_pin['sha256'] == '76e611bde7f12851a59bb8fafbb4b4a91b129ba36af32857b335c908b6fa6784',
             'R354 observer exact plan changed')
    gate, gate_pin = _json_artifact(ROUND / 'source-gate.json')
    accepted, _ = _json_artifact(ROUND / 'root-source-acceptance.json')
    plugin_path = ROUND / 'implementation/r354_live_observer.py'
    _require(Path(__file__).absolute() == plugin_path, 'R354 actual plugin path differs')
    plugin_pin = _pin_bytes(plugin_path, _regular_bytes(plugin_path, 2 * 1024 * 1024))
    _require(gate['round'] == accepted['round'] == 'R354'
             and gate['plan'] == accepted['plan'] == plan_pin
             and gate['observer'] == accepted['observer'] == plugin_pin
             and accepted['actor'] == '/root' and accepted['reviewed'] is True
             and accepted['source_gate'] == gate_pin,
             'R354 actual observer/gate lacks exact new ROOT acceptance')
    for field in ('baseline_clarification', 'native_signal_clarification', 'native_signal_acceptance',
                  'profiler_coexistence_clarification', 'profiler_coexistence_acceptance'):
        reference = gate[field]
        _require(accepted[field] == reference
                 and _pin_bytes(Path(reference['path']), _regular_bytes(Path(reference['path']), 2 * 1024 * 1024)) == reference,
                 'R354 effective clarification/acceptance differs: ' + field)
    command = plan['commands']['live_utc_01']
    _require(gate['commands'] == plan['commands'] and command['nodes'] == [NODE]
             and command['output'] == str(DIRECTORY.parent)
             and os.getcwd() == str(ROOT), 'R354 literal node/cwd/output differs')
    _require(sys.orig_argv == command['child_argv'], 'R354 actual original child argv differs')
    _require(all(os.environ.get(key) == value for key, value in command['child_env'].items()),
             'R354 planned child environment differs')
    _require(os.environ.get('BIGSMALL_R158_COMMAND') == COMMAND
             and os.environ.get('BIGSMALL_R354_DIAGNOSTIC_DIR') == str(DIRECTORY),
             'R354 actual diagnostic identity differs')
    root, _ = _json_artifact(ROUND / 'root-command-ledger.json')
    author, _ = _json_artifact(ROUND / 'implementation/author-command-ledger.json')
    root_slot, author_slot = root['commands']['live_utc_01'], author['commands']['live_utc_01']
    _require(root_slot['state'] == 'RESERVED' and author_slot['state'] == 'CONSUMED_BEFORE_START'
             and root_slot['reservation_id'] == author_slot['reservation_id']
             and root_slot['source_gate'] == gate_pin
             and root_slot['used'] == author_slot['used'] == 1
             and root_slot['remaining'] == author_slot['remaining'] == 0,
             'R354 actual consume-before-child reservation differs')
    _require(sys.getprofile() is None and threading.getprofile() is None,
             'R354 refuses existing profile ownership')
    info = os.lstat(DIRECTORY)
    _require(stat.S_ISDIR(info.st_mode), 'R354 real diagnostic output directory required')
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
            _require(owner is not None and owner['both_previous_hooks_owned'] is True
                     and owner['state_id'] == id(observed),
                     'R357 actual previous outer diagnostic hook ownership UNKNOWN/foreign')
            _require(observed.__dict__.get('wait_observer') is None,
                     'R357 foreign wait_observer callback cannot be replaced')
            epoch = 'bridge:' + str(profiler.bridge_ordinal)
            profiler.active_bridge_epoch = epoch
            profiler._append('bridge_entry', {
                'bridge_epoch': epoch, 'scenario_ordinal': profiler.bridge_ordinal,
                'monotonic_ns': time.monotonic_ns(), 'process_time_ns': time.process_time_ns(),
                'thread_time_ns': time.thread_time_ns(), 'thread_id': threading.get_ident(),
                'native_thread_id': threading.get_native_id(), 'resource_profile_id': id(current),
                'state_id': id(observed), 'delegate_attached': profiler.enabled,
                'coverage_disabled': not profiler.enabled, 'measured_target': False,
            })
            if profiler.enabled:
                observed.wait_observer = profiler.delegate
        except BaseException as error:
            profiler._fault('bridge_setup', error)
            raise
        try:
            # Exactly one original call with all five object identities intact.
            return original(monkeypatch, directory, backend, observed, callback)
        finally:
            unwinding = sys.exc_info()[0] is not None
            try:
                seam = observed.__dict__.get('wait_observer')
                if seam is profiler.delegate:
                    observed.wait_observer = None
                elif seam is not None:
                    profiler._fault('bridge_foreign_seam', RuntimeError('foreign callback preserved'))
                profiler.end_exercise_unobserved(epoch, unwinding)
            except BaseException as error:
                # Never mask the original result or original exception.
                profiler._fault('bridge_finally', error)

    return module, original, adapter


_STATE = None


def pytest_sessionstart(session):
    global _STATE
    _require(_STATE is None, 'R354 observer session starts once only')
    gate, gate_pin, plugin_pin, directory_identity = _startup_contract()
    profiler = _Profiler(DIRECTORY, directory_identity)
    native = _SignalControl(DIRECTORY, plugin_pin, gate_pin)
    _STATE = {'profiler': profiler, 'native': native, 'status_attempted': False,
              'gate': gate_pin, 'observer': plugin_pin, 'selection_verified': False}
    native.start()  # Must precede profiles; no behavior before READY.
    profiler.previous_sys_profile = sys.getprofile()
    profiler.previous_thread_profile = threading.getprofile()
    _require(profiler.previous_sys_profile is None and profiler.previous_thread_profile is None,
             'R354 profile owner changed during native startup')
    profiler._append('start', {'targets': TARGETS, 'pid': os.getpid(),
        'main_thread_id': threading.get_ident(), 'main_native_thread_id': threading.get_native_id(),
        'coverage': 'main and future Python threads only; native tasks are not Python-profile coverage',
        'resource_delegate_mode': 'R357 authenticated fixture seam',
        'observer_CPU_is_lower_bound': True, 'baseline_performance_comparison_valid': False})
    profiler.enabled = True
    threading.setprofile(profiler.callback)
    sys.setprofile(profiler.callback)


def pytest_collection_finish(session):
    _require(_STATE is not None and len(session.items) == 1 and session.items[0].nodeid == NODE,
             'R354 requires exactly the literal one collected UTC-memory item')
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
    profiler, native = _STATE['profiler'], _STATE['native']
    profiler.finish()
    native.retire()
    try:
        record = {'schema': 'bigsmall.r354.observer-status.v1', 'command_id': COMMAND,
                  'pid': os.getpid(), 'observer': _STATE['observer'], 'source_gate': _STATE['gate'],
                  'selection_verified': _STATE['selection_verified'],
                  'observation_invalid': profiler.invalid, 'saturation': profiler.saturation,
                  'faults': profiler.faults, 'profile_restoration': profiler.profile_restoration,
                  'binding_restoration': profiler.binding_restoration,
                  'bridge_calls': profiler.bridge_ordinal,
                  'exercise_tail_and_original_return': 'UNOBSERVED_AFTER_ORIGINAL_EARLY_CLEAR',
                  'native_state': native.native_state, 'native_registration_success': native.registration_success,
                  'native_unregister_attempted': native.unregister_attempted,
                  'stack_fd_retained_to_process_exit': native.stack_fd is not None,
                  'mask_restored': native.mask_restored, 'native_handler_pointer_verified': False,
                  'in_process_default_disposition_verified': native.native_state == 'RETIRED_VERIFIED_DEFAULT',
                  'diagnostic_only': True, 'behavior_acceptance_credit': 0}
        raw = (json.dumps(record, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')
        _require(len(raw) <= 65536, 'R354 observer status64KiB bound')
        descriptor = os.open(DIRECTORY / 'observer-status.json',
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException as error:
        _stderr_fault('observer_status', type(error).__name__)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _finish_observer()


def pytest_unconfigure(config):
    _finish_observer()
