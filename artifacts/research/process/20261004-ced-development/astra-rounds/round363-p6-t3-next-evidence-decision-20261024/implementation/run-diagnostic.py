"""R363 diagnostic runner, source-only candidate; never imported during preparation.

Only the single literal diagnostic command is prospective. Capture reads inert new
artifacts, never opens a database engine, and never imports application code.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).absolute().parent.parent
IMPL = D / "implementation"
HELPER = IMPL / "resource-evidence-helpers.py"
AUTHOR = IMPL / "author-command-ledger.json"
BINDING = IMPL / "author-binding.json"
PLAN_SHA = "67fc2af2d937994bc07c553c2ba631b27f6b10d45403775897b69794846c8502"
OLD = D.parent / "round354-p6-t3-live-noncompletion-evidence-20261024"
R350 = D.parent / "round350-p6-t3-successor-lineage-execution-20261024"
OBSERVER = IMPL / "r363_live_observer.py"
HISTORICAL_RUNNER = {"path": str(OLD / "implementation/run-diagnostic.py"), "bytes": 105341,
                     "sha256": "cec15badf5279a4a7c6811bef32dde504391fec8877e37dc289045bb1b638540"}
CHANGE_POLICY = "R363_IDENTITY_ACTIVE_SIGUSR2_WITHDRAWAL_DEPENDENT_REPORTING_AND_LINEAGE_ONLY"
DISABLED_NATIVE = ('stack-requests.jsonl', 'signal-ownership.jsonl', 'stacks.raw',
                   'signal-control.lock', 'signal-state.json', 'stack-ready.json')
HELPER_SHA = "bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b"
HEAD = "729bce11bbd55a4a869e25e52174da3d0db1825b"
BRANCH = "research/20261004-continuation"
KEYS = ("utc_no_sigusr2_01",)
HELD = "HELD_PENDING_ROOT_SOURCE_GATE_AND_INDIVIDUAL_RESERVATION"
RAW_CAP = 33554432
TREE_CAP = 1073741824
ENTRY_CAP = 10000
FREE_MIN = 3221225472
ROUND_CAP = 4294967296
JSONL_CAP = 16777216
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
STAGE_NAMES = ("raw-process-ledger", "source-after-observed", "persistent-inventory", "resources",
               "junit", "cases", "prerequisite-observation")
MONITOR_POLICY = {"maximum_successful_HEAD_completion_gap_seconds": 1.0,
                  "HEAD_target_seconds_after_completion": 0.25,
                  "storage_HEAD_headroom_seconds": 0.1,
                  "git_seconds_max": 2, "storage_seconds_max": 2}
COMPLETION_CONTRACT = {"terminal_record": "completion.json",
                       "wrapper_exit0_required": "Required for normal completed test/capture only; bounded diagnostic evidence may be accepted separately with actual nonzero exit.",
                       "result_is_precommit": True, "ROOT_independent_review_required": True}

# Parent-only diagnostic state. No application clock/window/authority is read.
_TIMER_FRAME = None
_TIMER_SEQUENCE = 0
_DEADLINE_EVENTS = []
_TRIGGER_EVENTS = []
_DIAGNOSTIC_FDS = {}
_DIAGNOSTIC_IDENTITIES = {}






class DeadlineExpired(TimeoutError):
    """Origin facts are an immutable tuple of primitive values, never relabeled."""

    def __init__(self, owner, requested, armed, fired, signum, interrupted_stage, trigger):
        super().__init__('deadline expired: ' + owner[1] + ' / ' + interrupted_stage)
        self._origin_facts = (
            owner[0], owner[1], owner[2], owner[3], owner[4], owner[5],
            requested[0], requested[1], requested[2], requested[3], requested[4],
            armed, fired, signum, interrupted_stage, trigger,
        )

    @property
    def evidence(self):
        names = ('origin_id', 'origin_kind', 'requested_deadline', 'effective_deadline',
                 'requested_seconds', 'owner_armed_monotonic', 'interrupted_request_id',
                 'interrupted_request_kind', 'interrupted_requested_deadline',
                 'interrupted_effective_deadline', 'interrupted_requested_seconds',
                 'current_timer_armed_monotonic', 'fired_monotonic', 'signal',
                 'interrupted_stage', 'trigger')
        return dict(zip(names, self._origin_facts))


def append_diagnostic(name, record):
    """Direct complete-line append; no retry/truncation of a torn prefix."""
    raw = (json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
    require(len(raw) <= 65536, 'individual parent diagnostic JSONL64KiB bound')
    descriptor = _DIAGNOSTIC_FDS[name]
    position = 0
    while position < len(raw):
        count = os.write(descriptor, raw[position:])
        require(count > 0, 'parent diagnostic append made no progress')
        position += count


def open_diagnostic_logs(out):
    """Only fresh fixed output; parent and plugin own distinct exclusive files."""
    directory = out / 'diagnostic'
    directory.mkdir(mode=0o700, exist_ok=False)
    for name in ('head-monitor.jsonl', 'os-samples.jsonl', 'deadline-events.jsonl'):
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        _DIAGNOSTIC_FDS[name] = descriptor
        info = os.fstat(descriptor)
        _DIAGNOSTIC_IDENTITIES[name] = (info.st_dev, info.st_ino)


def close_diagnostic_logs(errors):
    for name, descriptor in list(_DIAGNOSTIC_FDS.items()):
        try:
            os.fsync(descriptor)
        except DeadlineExpired:
            raise
        except BaseException as error:
            errors.append(error_record(name + ' fsync', error))
        finally:
            try:
                os.close(descriptor)
            except DeadlineExpired:
                raise
            except BaseException as error:
                errors.append(error_record(name + ' close', error))
            _DIAGNOSTIC_FDS.pop(name, None)


def proc_sample(pid, expected_starttime, *, seconds, absolute, opportunity, scheduled, records):
    """Owned /proc metadata, <=16 TIDs/64KiB/0.1s; no external sampler.

    procfs values are not an atomic snapshot. Missing/denied data remain UNKNOWN.
    No fd/memory contents, native instrumentation, application SQL or lock owner.
    """
    guard_deadline = min(time.monotonic() + min(0.1, seconds), absolute)
    row = {'opportunity': opportunity, 'scheduled_monotonic': scheduled,
           'observed_monotonic': time.monotonic(), 'pid': pid, 'status': 'UNKNOWN',
           'SC_CLK_TCK': None, 'page_bytes': None, 'bytes_read': 0,
           'process': None, 'threads': [], 'thread_listing_complete': False, 'errors': [],
           'atomic_snapshot': False, 'lock_owner': 'UNKNOWN'}
    row["receipt_persisted"] = False
    row["record_is_prewrite_observation"] = True
    records.append(row)
    remaining = 65536

    def read(path, limit=8192):
        nonlocal remaining
        require(remaining > 0, 'proc opportunity64KiB exhausted')
        cap = min(remaining, limit)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            raw = bytearray()
            while True:
                require(len(raw) < cap, 'proc file reached conservative byte boundary')
                chunk = os.read(fd, min(4096, cap - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                row['bytes_read'] += len(chunk)
                remaining -= len(chunk)
                require(len(raw) <= cap and remaining >= 0, 'proc read exceeds fixed byte bound')
            return bytes(raw)
        finally:
            os.close(fd)

    def parse_stat(raw, wanted):
        first = raw.find(b'(')
        last = raw.rfind(b')')
        require(first > 0 and last > first and int(raw[:first].strip()) == wanted,
                'proc stat numeric PID/comm boundary differs')
        fields = raw[last + 1:].split()
        require(len(fields) >= 22, 'proc stat required fields unavailable')
        return {'pid': wanted, 'state': fields[0].decode('ascii'),
                'user_CPU_ticks': int(fields[11]), 'system_CPU_ticks': int(fields[12]),
                'reported_thread_count': int(fields[17]), 'starttime_ticks': int(fields[19]),
                'virtual_bytes': int(fields[20]), 'RSS_pages': int(fields[21])}

    try:
        with bounded(0.1, guard_deadline, origin='proc_observation', stage='whole owned proc opportunity'):
            try:
                # Reserve the last20ms within the same0.1s for the append receipt.
                with bounded(0.08, guard_deadline - 0.02, origin='proc_observation', stage='fixed owned proc reads'):
                    row['SC_CLK_TCK'] = os.sysconf('SC_CLK_TCK')
                    row['page_bytes'] = os.sysconf('SC_PAGE_SIZE')
                    base = Path('/proc') / str(pid)
                    row['process'] = parse_stat(read(base / 'stat'), pid)
                    require(expected_starttime is None or row['process']['starttime_ticks'] == expected_starttime,
                            'owned process starttime identity changed')
                    status_raw = read(base / 'status')
                    selected = {}
                    for line in status_raw.splitlines():
                        key, separator, value = line.partition(b':')
                        if separator and key in (b'Pid', b'Tgid', b'PPid', b'Threads', b'VmRSS', b'State'):
                            selected[key.decode('ascii')] = value.strip().decode('ascii')
                    row['status_fields'] = selected
                    require(int(selected['Pid']) == pid and int(selected['Tgid']) == pid,
                            'owned process status PID/Tgid differs')
                    tids = []
                    with os.scandir(base / 'task') as entries:
                        for entry in entries:
                            if len(tids) == 16:
                                row['thread_listing_complete'] = False
                                break
                            require(entry.name.isdecimal(), 'non-numeric proc task directory')
                            tids.append(int(entry.name))
                        else:
                            row['thread_listing_complete'] = True
                    row['thread_selection'] = 'first16 actual directory-order TIDs, not invented population'
                    for tid in tids:
                        thread = {'tid': tid, 'stat': None, 'wchan': 'UNKNOWN', 'errors': []}
                        row['threads'].append(thread)
                        try:
                            thread['stat'] = parse_stat(read(base / 'task' / str(tid) / 'stat'), tid)
                        except DeadlineExpired:
                            raise
                        except Exception as error:
                            thread['errors'].append(error_record('owned thread stat', error))
                        try:
                            wchan = read(base / 'task' / str(tid) / 'wchan', 256).strip()
                            if wchan and wchan != b'0':
                                thread['wchan'] = wchan.decode('ascii')
                        except DeadlineExpired:
                            raise
                        except Exception as error:
                            thread['errors'].append(error_record('optional thread wchan', error))
                    row['status'] = 'OBSERVED_CONTEXT_ONLY'
            except DeadlineExpired as error:
                if error.evidence['origin_kind'] != 'proc_observation':
                    raise
                row['errors'].append({'type': type(error).__name__, 'deadline_origin': error.evidence})
            except Exception as error:
                row['errors'].append(error_record('owned proc read missingness', error))
            row['completed_monotonic_before_receipt'] = time.monotonic()
            append_diagnostic('os-samples.jsonl', row)
            row['receipt_persisted'] = True
    except DeadlineExpired as error:
        row['status'] = 'UNKNOWN'
        row['errors'].append({'type': type(error).__name__, 'deadline_origin': error.evidence,
                              'stage': 'whole proc opportunity/receipt'})
        if error.evidence['origin_kind'] != 'proc_observation':
            raise
    except Exception as error:
        row['status'] = 'UNKNOWN'
        row['errors'].append({'type': type(error).__name__, 'message': str(error),
                              'stage': 'proc opportunity/receipt'})
    row['completed_monotonic'] = time.monotonic()
    row['guard_deadline'] = guard_deadline
    row['guard_overrun'] = row['completed_monotonic'] > guard_deadline
    if row['guard_overrun']:
        row['status'] = 'UNKNOWN'
    return row


def deadline_event(owner, requested, armed, *, signum=None, stage, trigger):
    error = DeadlineExpired(owner, requested, armed, time.monotonic(), signum, stage, trigger)
    event = {'sequence': len(_DEADLINE_EVENTS) + 1, **error.evidence}
    _DEADLINE_EVENTS.append(event)
    record_trigger('deadline', {'deadline': error.evidence}, observed=error.evidence['fired_monotonic'])
    try:
        if 'deadline-events.jsonl' in _DIAGNOSTIC_FDS:
            append_diagnostic('deadline-events.jsonl', event)
            event['persistence_state'] = 'APPEND_RETURNED_NOT_FSYNC_ACK'
        else:
            event['persistence_state'] = 'NOT_OPEN_OR_ALREADY_CLOSED'
    except BaseException as failure:
        event['persistence_error'] = {'type': type(failure).__name__, 'message': str(failure)}
    return error


def record_trigger(kind, detail, *, observed=None):
    record = {'sequence': len(_TRIGGER_EVENTS) + 1, 'kind': kind,
              'observed_monotonic': time.monotonic() if observed is None else observed, **detail}
    _TRIGGER_EVENTS.append(record)
    return record


def classify_exception(data, stage, error):
    if isinstance(error, DeadlineExpired):
        # An actual child-wall owner stays child-wall inside HEAD/storage/proc.
        data['timed_out'] |= error.evidence['origin_kind'] == 'child_wall'
    else:
        record_trigger('guard_or_stage_error', {'stage': stage, 'type': type(error).__name__,
                                              'message': str(error)})
    data['primary_trigger'] = _TRIGGER_EVENTS[0] if _TRIGGER_EVENTS else None


def explicit_boundary(origin, deadline, *, stage, owner=None, armed=None):
    global _TIMER_SEQUENCE
    _TIMER_SEQUENCE += 1
    if owner is None:
        owner = (origin + ':explicit:' + str(_TIMER_SEQUENCE), origin, deadline,
                 deadline, None, armed)
    return deadline_event(owner, owner, armed, stage=stage,
                          trigger='explicit_monotonic_deadline_branch')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def error_record(stage, error):
    record = {"stage": stage, "type": type(error).__name__, "message": str(error),
              "traceback": traceback.format_exc()}
    if isinstance(error, DeadlineExpired):
        record['deadline_origin'] = error.evidence
    return record


@contextmanager
def bounded(seconds, absolute=None, *, origin='receipt_write', stage=None):
    """Earlier absolute owner wins; equal deadlines retain the outer owner.

    Named callsites are completed before final source freeze. An unrelated
    active ITIMER_REAL rejects rather than being overwritten or guessed.
    """
    global _TIMER_FRAME, _TIMER_SEQUENCE
    started = time.monotonic()
    requested_deadline = started + seconds
    effective_deadline = min(requested_deadline, absolute) if absolute is not None else requested_deadline
    _TIMER_SEQUENCE += 1
    requested = (origin + ':' + str(_TIMER_SEQUENCE), origin, requested_deadline,
                 effective_deadline, seconds, started)
    previous_frame = _TIMER_FRAME
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    require(previous_timer[1] == 0, 'periodic pre-existing interval timer not allowed')
    require(previous_frame is not None or previous_timer[0] == 0,
            'unowned pre-existing real timer rejects launch')
    require(previous_frame is None or previous_handler is previous_frame['handler'],
            'known timer Python handler ownership changed')
    owner = (previous_frame['owner'] if previous_frame is not None
             and previous_frame['owner'][3] <= effective_deadline else requested)
    interrupted_stage = stage or origin
    if owner[3] <= started:
        raise deadline_event(owner, requested, started, stage=interrupted_stage,
                             trigger='explicit_deadline_before_arm')

    armed = time.monotonic()
    if owner is requested:
        requested = (*requested[:5], armed)
        owner = requested
    frame_record = {'owner': owner, 'requested': requested, 'armed': armed,
                    'stage': interrupted_stage, 'handler': None}

    def expired(signum, frame):
        raise deadline_event(owner, requested, armed, signum=signum,
                             stage=interrupted_stage, trigger='SIGALRM_ITIMER_REAL')

    frame_record['handler'] = expired
    installed = False
    try:
        signal.signal(signal.SIGALRM, expired)
        installed = True
        _TIMER_FRAME = frame_record
        remaining = owner[3] - time.monotonic()
        if remaining <= 0:
            raise deadline_event(owner, requested, armed, stage=interrupted_stage,
                                 trigger='explicit_deadline_at_arm')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield
    finally:
        if installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            _TIMER_FRAME = previous_frame
        if installed and previous_frame is not None:
            remaining = previous_frame['owner'][3] - time.monotonic()
            if remaining > 0:
                signal.setitimer(signal.ITIMER_REAL, remaining)
            elif sys.exc_info()[0] is None:
                # Explicit expired-restore branch, never a renewed budget.
                raise deadline_event(previous_frame['owner'], previous_frame['requested'],
                    previous_frame['armed'], stage=previous_frame['stage'],
                    trigger='explicit_previous_absolute_deadline_at_restore')


def coordinates(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns]


def stable(path):
    """Stable regular-file bytes, no final symlink; source pins are absolute."""
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "regular nofollow file required: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        require(coordinates(before) == coordinates(opened), "file changed before read")
        chunks = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        require(coordinates(opened) == coordinates(os.fstat(fd)) == coordinates(path.lstat())
                and len(raw) == opened.st_size, "file changed during read: " + str(path))
        return raw
    finally:
        os.close(fd)


def bytes_pin(path, raw):
    return {"path": str(Path(path).absolute()), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def pin(path):
    return bytes_pin(path, stable(path))


def check(record):
    require(pin(record["path"]) == {name: record[name] for name in ("path", "bytes", "sha256")},
            "pin changed: " + record["path"])


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def read_json(path):
    value = json.loads(stable(path))
    require(type(value) is dict, "JSON object required")
    return value


def write(path, value):
    path = Path(path)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    actual = pin(path)
    require(actual == bytes_pin(path, raw), "exclusive write readback differs")
    return actual


def full(path):
    raw = stable(path)
    return {**bytes_pin(path, raw), "mode": stat.S_IMODE(Path(path).lstat().st_mode),
            "base64": base64.b64encode(raw).decode("ascii")}


def cas(path, before, after, receipt):
    """Compare exact bytes/mode under a nonblocking owned ledger lock; no retry."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    temporary = path.with_name(path.name + ".r363-next")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check(before)
        require(coordinates(os.fstat(descriptor)) == coordinates(path.lstat()), "ledger inode changed")
        require(stat.S_IMODE(os.fstat(descriptor).st_mode) == before["mode"], "ledger mode changed")
        require(stable(path) == base64.b64decode(before["base64"]), "ledger CAS bytes changed")
        write(receipt.with_name(receipt.stem + "-before.json"), before)
        write(temporary, after)
        os.chmod(temporary, before["mode"])
        check(before)
        require(coordinates(os.fstat(descriptor)) == coordinates(path.lstat()), "ledger inode changed")
        os.replace(temporary, path)
        require(stable(path) == encoded(after), "ledger CAS after differs")
        return write(receipt, {"before": before, "after": full(path)})
    finally:
        os.close(descriptor)


def git_value(*arguments, timeout=2, absolute=None):
    budget = min(timeout, absolute - time.monotonic()) if absolute is not None else timeout
    require(budget > 0, "nonpositive git observation budget")
    with bounded(budget, absolute, origin="HEAD_freshness", stage="git " + " ".join(arguments)):
        return subprocess.check_output(["/usr/bin/git", *arguments], cwd=ROOT,
                                       text=True, timeout=budget, stderr=subprocess.PIPE).strip()


def observe_sources(gate, target):
    """Mismatch is data. A single bad pin never gates later pin observations."""
    for expected in gate.get("pins", []):
        row = {"expected": expected, "actual": None, "missing": False, "error": None, "match": False}
        target["pins"].append(row)
        try:
            row["actual"] = pin(expected["path"])
            row["match"] = row["actual"] == expected
        except DeadlineExpired:
            raise
        except Exception as error:
            row["missing"] = isinstance(error, FileNotFoundError)
            row["error"] = error_record("source pin", error)
    for field, arguments in (("HEAD", ("rev-parse", "HEAD")),
                             ("branch", ("branch", "--show-current"))):
        try:
            target[field] = git_value(*arguments)
        except DeadlineExpired:
            raise
        except Exception as error:
            target[field + "_error"] = error_record(field, error)
    target["complete"] = len(target["pins"]) == len(gate.get("pins", []))
    target["accepted"] = bool(target["complete"] and target["pins"]
                              and all(row["match"] for row in target["pins"])
                              and target.get("HEAD") == gate.get("HEAD") == HEAD
                              and target.get("branch") == gate.get("branch") == BRANCH)


def walk(root, rows, *, content=False, archive=None, live_sampling=False):
    """Bounded nofollow traversal with per-path errors and independent orphan copies.

    Directory-relative descriptors avoid following links in descendant ancestors.
    Live mode is explicit; content=False alone does not relax postrun checks.
    """
    root = Path(root)
    require(not live_sampling or not content, "live sampler must remain metadata-only")
    result = {"root": str(root), "complete": False, "entries": 0, "regular_bytes": 0,
              "errors": [], "files": rows, "consistent_database_backup": False,
              "live_sampling": live_sampling, "sample_start_monotonic": time.monotonic(),
              "atomic_snapshot": False}
    visited = set()

    def directory_identity(info):
        return ([info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)]
                if live_sampling else coordinates(info))

    def visit(directory_fd, relative):
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                require(len(rows) < ENTRY_CAP, "finite inventory entry cap reached")
                rel = relative / entry.name
                row = {"path": str(root / rel), "relative": rel.as_posix(), "error": None}
                rows.append(row)
                result["entries"] += 1
                try:
                    info = entry.stat(follow_symlinks=False)
                    row.update(mode=info.st_mode, bytes=info.st_size, coordinates=coordinates(info))
                    if stat.S_ISLNK(info.st_mode):
                        row.update(type="symlink", link_target=os.readlink(entry.name, dir_fd=directory_fd))
                    elif stat.S_ISDIR(info.st_mode):
                        row["type"] = "directory"
                        descriptor = os.open(entry.name, DIR_FLAGS, dir_fd=directory_fd)
                        try:
                            require(directory_identity(info) == directory_identity(os.fstat(descriptor)), "directory changed")
                            identity = (info.st_dev, info.st_ino)
                            require(identity not in visited, "duplicate directory identity")
                            visited.add(identity)
                            visit(descriptor, rel)
                            require(directory_identity(os.fstat(descriptor)) == directory_identity(os.stat(
                                entry.name, dir_fd=directory_fd, follow_symlinks=False)), "directory path changed")
                        finally:
                            os.close(descriptor)
                    elif stat.S_ISREG(info.st_mode):
                        row["type"] = "regular"
                        result["regular_bytes"] += info.st_size
                        if content:
                            row.update(read_regular(directory_fd, entry.name, info, root / rel,
                                                    archive / rel if archive is not None and database_name(entry.name)
                                                    else None))
                    else:
                        row["type"] = "special"
                except DeadlineExpired:
                    raise
                except Exception as error:
                    row["error"] = error_record("inventory path", error)
                    result["errors"].append(row["error"])

    descriptor = None
    try:
        descriptor = os.open(root, DIR_FLAGS)
        info = os.fstat(descriptor)
        require(directory_identity(info) == directory_identity(root.lstat()), "root directory changed")
        visited.add((info.st_dev, info.st_ino))
        visit(descriptor, Path())
        require(directory_identity(os.fstat(descriptor)) == directory_identity(root.lstat()), "root path changed")
        result["complete"] = not result["errors"]
    except DeadlineExpired:
        raise
    except Exception as error:
        result["errors"].append(error_record("inventory traversal", error))
    finally:
        if descriptor is not None:
            os.close(descriptor)
        result["sample_end_monotonic"] = time.monotonic()
    return result


def database_name(name):
    base = name
    for suffix in ("-wal", "-shm", "-journal"):
        if name.endswith(suffix):
            base = name[:-len(suffix)]
            break
    return Path(base).suffix.lower() in {".db", ".sqlite", ".sqlite3"}


def read_regular(parent, name, expected, original, destination=None):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    output = None
    row = {"sha256": None, "stable": False, "archive": None, "archive_error": None}
    try:
        opened = os.fstat(fd)
        require(coordinates(expected) == coordinates(opened), "regular file changed before read")
        if destination is not None:
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                output = destination.open("xb")
            except DeadlineExpired:
                raise
            except Exception as error:
                row["archive_error"] = error_record("exclusive DB byte copy", error)
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if output is not None:
                output.write(chunk)
        require(coordinates(opened) == coordinates(os.fstat(fd)) == coordinates(os.stat(
            name, dir_fd=parent, follow_symlinks=False)) and size == opened.st_size,
                "regular file changed during read")
        row.update(sha256=digest.hexdigest(), stable=True, read_bytes=size)
        if output is not None:
            output.flush()
            os.fsync(output.fileno())
            output.close()
            output = None
            row["archive"] = pin(destination)
            require((row["archive"]["bytes"], row["archive"]["sha256"]) == (size, digest.hexdigest()),
                    "DB destination byte readback differs")
        return row
    finally:
        if output is not None:
            output.close()
        os.close(fd)


def storage_observation(command, *, round_tree=False, live_sampling=False, seconds=2, absolute=None):
    with bounded(min(2, seconds), absolute, origin="live_storage", stage="round storage" if round_tree else "persistent live storage"):
        root = D if round_tree else Path(command["output"]) / "persistent-basetemp"
        if not root.exists() and not root.is_symlink():
            census = {"root": str(root), "complete": True, "entries": 0, "regular_bytes": 0, "errors": []}
        else:
            census = walk(root, [], live_sampling=live_sampling)
        space = os.statvfs(D)
        census["free_bytes"] = space.f_bavail * space.f_frsize
        require(census["complete"], "storage scan incomplete")
        require(census["free_bytes"] >= FREE_MIN, "minimum free storage crossed")
        require(census["regular_bytes"] <= (ROUND_CAP if round_tree else TREE_CAP), "storage byte threshold crossed")
        require(census["entries"] <= ENTRY_CAP, "storage entry threshold crossed")
        if round_tree:
            persistent = Path(command['output']) / 'persistent-basetemp'
            selected = [row for row in census.get('files', [])
                        if Path(row['path']).is_relative_to(persistent)]
            subtree_bytes = sum(row.get('bytes', 0) for row in selected if row.get('type') == 'regular')
            census['persistent_subtree'] = {'root': str(persistent), 'entries': len(selected),
                                           'regular_bytes': subtree_bytes,
                                           'derived_from_same_traversal': True}
            require(subtree_bytes <= TREE_CAP and len(selected) <= ENTRY_CAP,
                    'persistent subtree threshold crossed')
        return {key: value for key, value in census.items() if key != "files"}


def verify_interpreter(record, command):
    requested = os.path.abspath(record["requested_path"])
    resolved = os.path.abspath(record["resolved_path"])
    venv = os.path.abspath(record["venv_root"])
    require(requested == str(ROOT / ".venv/bin/python") == command["child_argv"][0]
            == command["launcher_argv"][4], "frozen requested executable differs")
    require(os.path.abspath(sys.executable) == requested, "actual runner executable differs")
    require(os.path.realpath(sys.executable) == os.path.realpath(command["child_argv"][0]) == resolved,
            "actual executable resolution differs")
    require(venv == str(ROOT / ".venv") == os.path.abspath(sys.prefix)
            and os.path.realpath(sys.prefix) == os.path.realpath(venv), "actual venv prefix differs")
    current, seen, actual_chain = Path(requested), set(), []
    require(type(record["symlink_chain"]) is list and len(record["symlink_chain"]) <= 16,
            "finite ordered interpreter chain required")
    for expected in record["symlink_chain"]:
        require(str(current) not in seen, "interpreter symlink loop")
        seen.add(str(current))
        info = current.lstat()
        require(stat.S_ISLNK(info.st_mode), "declared interpreter link missing")
        target = os.readlink(current)
        actual = {"path": str(current), "target": target, "device": info.st_dev,
                  "inode": info.st_ino, "file_type": "symlink"}
        require(actual == expected, "actual interpreter link differs")
        actual_chain.append(actual)
        current = Path(os.path.normpath(target if os.path.isabs(target) else str(current.parent / target)))
    require(str(current) == resolved and stat.S_ISREG(current.lstat().st_mode),
            "extra/missing interpreter link or nonregular endpoint")
    require(record["resolved_binary"]["path"] == resolved
            and record["pyvenv_cfg"]["path"] == str(ROOT / ".venv/pyvenv.cfg"), "interpreter pin path differs")
    check(record["resolved_binary"])
    check(record["pyvenv_cfg"])
    return {"sys_executable": sys.executable, "realpath": os.path.realpath(sys.executable),
            "sys_prefix": sys.prefix, "actual_symlink_chain": actual_chain,
            "resolved_binary": pin(current), "pyvenv_cfg": pin(record["pyvenv_cfg"]["path"]),
            "loaded_memory_attestation": False, "new_interpreter_probe": False}


def validate_launch_capture(reserved, command, key):
    capture = reserved["launch_capture"]
    require(capture["preopened_exclusive"] is True and capture["launcher_argv"] == command["launcher_argv"],
            "ROOT launcher capture identity differs")
    for stream, descriptor in (("stdout", 1), ("stderr", 2)):
        path = str(D / "root-launch" / (key + "." + stream + ".txt"))
        require(capture[stream + "_path"] == path, "fixed ROOT launch stream path differs")
        actual, opened = Path(path).lstat(), os.fstat(descriptor)
        require(stat.S_ISREG(actual.st_mode) and stat.S_ISREG(opened.st_mode)
                and (actual.st_dev, actual.st_ino) == (opened.st_dev, opened.st_ino),
                "actual wrapper stream is not ROOT preopened regular file")


def validate_completion(completion, key, command, gate_pin, runner_pin):
    require(completion["command_id"] == "R363:" + key and completion["nodes"] == command["nodes"]
            and completion["source_gate"] == gate_pin and completion["runner"] == runner_pin,
            "terminal completion generation/command differs")
    require(completion["finalization_complete"] is True and completion["final_summary_state"] == "COMPLETE"
            and completion["wrapper_exit0_required"] == COMPLETION_CONTRACT["wrapper_exit0_required"]
            and completion["ROOT_accepted"] is False and completion["diagnostic_only"] is True
            and completion["behavior_acceptance_credit"] == 0
            and completion["behavior_candidate_pass"] is False and completion["behavior_checks_passed"] is False,
            "qualified terminal completion required")
    expected_out = IMPL / key
    for field, filename in (("result", "result.json"), ("missingness", "missingness.json"),
                            ("stage_status", "stage-status.json")):
        require(completion[field]["path"] == str(expected_out / filename), "completion reference path differs")
        check(completion[field])
    require(tuple(completion["stage_receipts"]) == STAGE_NAMES, "exact seven terminal stage references required")
    for name, reference in completion["stage_receipts"].items():
        require(reference["path"] == str(expected_out / (name + ".json")), "stage receipt path differs")
        check(reference)
    check(completion["source_gate"])
    check(completion["runner"])
    prior = read_json(completion["result"]["path"])
    require(prior["command_id"] == "R363:" + key and prior["source_gate"] == gate_pin
            and prior["pid"] == completion["pid"] and prior["completion_required"] is True
            and prior["behavior_checks_passed"] is False and prior["behavior_candidate_pass"] is False
            and completion["test_observed_pass"] is prior["test_observed_pass"]
            and completion["normal_completed_test_and_capture"] is prior["normal_completed_test_and_capture"],
            "result/terminal completion facts differ")
    return prior


def retain_prelaunch_rejection(error, key, reserved=None, *, normal_output_created=False):
    """Original stderr first, then at most one fixed fallback file; no authority mutation."""
    record = {"schema": "bigsmall.r363.prelaunch-rejection.v1", "error": error_record("prelaunch", error),
              "argv": list(sys.argv), "key": key if key in KEYS else "invalid-key", "wrapper_pid": os.getpid(),
              "monotonic": time.monotonic(), "no_child_started": True, "normal_output_created": normal_output_created,
              "reservation_status": "VERIFIED_RESERVED" if reserved is not None else "UNKNOWN_NOT_VERIFIED",
              "verified_reservation": reserved, "ROOT_reconciliation_required": True,
              "no_refund_or_retry": True, "AUTHOR_mutated_by_fallback": False, "retention_errors": []}
    deadline = time.monotonic() + 5
    try:
        with bounded(5, deadline, origin="preflight", stage="prelaunch rejection retention"):
            try:
                with bounded(2, deadline, origin="receipt_write", stage="prelaunch stderr"):
                    remaining = memoryview(encoded(record))
                    while remaining:
                        written = os.write(2, remaining)
                        require(written > 0, "stderr made no progress")
                        remaining = remaining[written:]
            except BaseException as failure:
                record["retention_errors"].append(error_record("primary stderr retention", failure))
            if not normal_output_created:
                label = key if key in KEYS else "invalid-key"
                write(IMPL / "prelaunch-rejections" / (label + "-" + str(os.getpid()) + ".json"), record)
    except BaseException as failure:
        record["retention_errors"].append(error_record("fixed prelaunch fallback", failure))
    return record






def diagnostic_sizes(out):
    """Metadata only while child lives, no symlinks or live log content read."""
    directory = out / 'diagnostic'
    result = {'jsonl_bytes': 0, 'files': {}, 'unexpected_native_files': []}
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            require(index < ENTRY_CAP, 'finite diagnostic metadata entry cap')
            info = entry.stat(follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode), 'diagnostic artifact must remain nofollow regular')
            result['files'][entry.name] = info.st_size
            if entry.name.endswith('.jsonl'):
                result['jsonl_bytes'] += info.st_size
            if entry.name in DISABLED_NATIVE:
                result['unexpected_native_files'].append(entry.name)
    return result


def diagnostic_index(out, *, phase):
    """Post-exit byte retention/index, no stack grouping or synthetic receipt."""
    expected = ('head-monitor.jsonl', 'os-samples.jsonl', 'deadline-events.jsonl',
                'observer-profile.jsonl', 'observer-status.json')
    result = {'phase': phase, 'parent_files_may_append_later': bool(_DIAGNOSTIC_FDS),
              'expected_files': {name: 'MISSING_NOT_INFERRED' for name in expected},
              'disabled_artifacts': {name: 'DISABLED_BY_PLAN' for name in DISABLED_NATIVE},
              'unexpected_native_files': [], 'files': [], 'complete': True,
              'stack_grouping': 'DISABLED_BY_PLAN',
              'decoded_semantics': False, 'raw_torn_tails_repaired': False}
    directory = out / 'diagnostic'
    for index, path in enumerate(directory.iterdir()):
        require(index < ENTRY_CAP, 'finite postrun diagnostic entry cap')
        row = {'path': str(path), 'pin': None, 'error': None}
        result['files'].append(row)
        if path.name in DISABLED_NATIVE:
            result['unexpected_native_files'].append(path.name)
            result['disabled_artifacts'][path.name] = 'UNEXPECTED_PRESENT_SINGLE_FACTOR_INVALID'
        try:
            raw = stable(path)
            row['pin'] = bytes_pin(path, raw)
            if path.name in result['expected_files']:
                result['expected_files'][path.name] = 'PRESENT_BYTE_RETAINED'
            if path.suffix == '.jsonl':
                row.update(complete_newline_count=raw.count(b'\n'),
                           ends_with_newline=not raw or raw.endswith(b'\n'),
                           uncertain_tail_preserved=bool(raw and not raw.endswith(b'\n')))
        except DeadlineExpired:
            raise
        except Exception as error:
            row['error'] = error_record('diagnostic raw retention index', error)
            result['complete'] = False
    result['planned_native_absence'] = not result['unexpected_native_files']
    result['all_expected_files_present'] = all(value == 'PRESENT_BYTE_RETAINED'
                                               for value in result['expected_files'].values())
    return result


def monitor_child(process, command, data, signals, out, start, deadline):
    last_completion = start
    next_target = start
    head_deadline = start + 1.0
    next_storage = start
    os_opportunity = 0
    data['os_sampling'] = {'maximum_opportunities': 121, 'records': [], 'actual_complete_coverage': 'UNKNOWN'}
    data['stack_sampling'] = {'state': 'DISABLED_BY_PLAN', 'maximum_opportunities': 0,
                              'submissions': 0, 'records': [], 'stack_completion_coverage': None}
    data['native_ownership'] = 'DISABLED_BY_PLAN'
    data['owned_child_starttime'] = None

    def child_elapsed(stage):
        raise explicit_boundary('child_wall', deadline, stage=stage,
                                owner=tuple(data['child_timer_owner']), armed=data['child_timer_owner'][5])

    def observe_head():
        nonlocal last_completion, next_target, head_deadline
        began = time.monotonic()
        budget = min(2.0, deadline - began, head_deadline - began)
        row = {'stage': 'HEAD', 'started_monotonic': began, 'previous_completion_monotonic': last_completion,
               'completion_deadline': head_deadline, 'granted_seconds': budget, 'accepted': False}
        data['monitor'].append(row)
        try:
            if began >= deadline:
                child_elapsed('HEAD before observation')
            if budget <= 0:
                raise explicit_boundary('HEAD_freshness', head_deadline, stage='HEAD before observation')
            with bounded(budget, min(deadline, head_deadline), origin='HEAD_freshness', stage='HEAD query and append'):
                observed = git_value('rev-parse', 'HEAD', timeout=budget, absolute=min(deadline, head_deadline))
                query_completed = time.monotonic()
                row.update(query_completed_monotonic=query_completed, HEAD=observed)
                if query_completed >= deadline:
                    child_elapsed('HEAD query completed at child boundary')
                if query_completed > head_deadline:
                    raise explicit_boundary('HEAD_freshness', head_deadline, stage='HEAD query completion')
                require(observed == HEAD and not signals, 'HEAD changed or wrapper interrupted')
                append_diagnostic('head-monitor.jsonl', {
                    **row, 'query_matches': True, 'guard_commit': 'PREWRITE_OBSERVATION_NOT_ACK',
                    'query_gap_seconds': query_completed - last_completion})
                completed = time.monotonic()
                if completed >= deadline:
                    child_elapsed('HEAD append completed at child boundary')
                if completed > head_deadline:
                    raise explicit_boundary('HEAD_freshness', head_deadline, stage='HEAD append completion')
                row.update(completed_monotonic=completed, gap_seconds=completed - last_completion)
            row['accepted'] = True
            last_completion, next_target, head_deadline = completed, completed + 0.25, completed + 1.0
        except BaseException as error:
            row['accepted'] = False
            row.setdefault('completed_monotonic', time.monotonic())
            row.setdefault('gap_seconds', row['completed_monotonic'] - last_completion)
            row['error'] = error_record('HEAD subdeadline/observation', error)
            data['monitor_rejected'] = True
            classify_exception(data, 'HEAD', error)
            raise

    while True:
        returncode = process.poll()
        now = time.monotonic()
        if returncode is not None:
            tail = {'stage': 'observed child exit', 'monotonic': now, 'returncode': returncode,
                    'last_successful_HEAD_completion': last_completion, 'tail_seconds': now - last_completion,
                    'HEAD_deadline': head_deadline, 'accepted': False}
            data['monitor'].append(tail)
            if returncode != 0:
                record_trigger('actual_child_nonzero_exit', {'returncode': returncode}, observed=now)
            if now >= deadline:
                child_elapsed('observed child exit boundary')
            if now > head_deadline:
                raise explicit_boundary('HEAD_freshness', head_deadline, stage='observed child exit tail')
            with bounded(min(0.1, head_deadline - now), min(deadline, head_deadline),
                         origin='HEAD_freshness', stage='child exit tail receipt'):
                append_diagnostic('head-monitor.jsonl', {**tail, 'tail_within_boundary': True,
                                                       'receipt_is_prewrite_observation': True})
            tail_completed = time.monotonic()
            if tail_completed >= deadline:
                child_elapsed('exit tail receipt completed at child boundary')
            if tail_completed > head_deadline:
                raise explicit_boundary('HEAD_freshness', head_deadline, stage='exit tail receipt completion')
            tail['accepted'] = True
            tail['completed_monotonic'] = tail_completed
            break
        if now >= deadline:
            child_elapsed('explicit original child600s wall branch')
        require(not signals, 'TERM/INT received; enter owned cleanup')
        if now > head_deadline:
            raise explicit_boundary('HEAD_freshness', head_deadline, stage='HEAD gap before next read')
        with bounded(min(0.1, deadline - now, head_deadline - now), min(deadline, head_deadline),
                     origin='live_storage', stage='raw and diagnostic metadata thresholds'):
            sizes = {name: (out / name).lstat().st_size for name in ('stdout.txt', 'stderr.txt')}
            diagnostics = diagnostic_sizes(out)
            require(not diagnostics['unexpected_native_files'],
                    'R363 disabled native artifact unexpectedly present; comparison invalid')
            if (any(size > RAW_CAP for size in sizes.values())
                    or diagnostics['jsonl_bytes'] > JSONL_CAP):
                data['output_limited'] = True
                row = {'stage': 'raw/diagnostic threshold', 'monotonic': now,
                       'stream_bytes': sizes, 'diagnostic_metadata': diagnostics}
                data['monitor'].append(row)
                record_trigger('sampled_output_threshold', row)
                break
        if os_opportunity <= 120 and time.monotonic() >= start + 5 * os_opportunity:
            # Missed fixed slots are explicit missingness, never catch-up work.
            latest = min(120, int((time.monotonic() - start) // 5))
            while os_opportunity < latest:
                data['os_sampling']['records'].append({'opportunity': os_opportunity,
                    'scheduled_monotonic': start + 5 * os_opportunity,
                    'status': 'SKIPPED_MISSED_FIXED_SLOT_NO_CATCHUP', 'no_retry': True})
                os_opportunity += 1
            observe_head()
            began = time.monotonic()
            absolute = min(deadline, head_deadline - 0.1)
            budget = min(0.1, absolute - began)
            if budget > 0:
                sample = proc_sample(process.pid, data['owned_child_starttime'], seconds=budget,
                    absolute=absolute, opportunity=os_opportunity, scheduled=start + 5 * os_opportunity,
                    records=data['os_sampling']['records'])
                if sample.get('process') is not None and sample['status'] == 'OBSERVED_CONTEXT_ONLY':
                    data['owned_child_starttime'] = sample['process']['starttime_ticks']
            else:
                data['os_sampling']['records'].append({'opportunity': os_opportunity, 'status': 'UNKNOWN',
                    'reason': 'no remaining HEAD/child headroom', 'no_retry': True})
            os_opportunity += 1
            observe_head()
        if time.monotonic() >= next_storage:
            observe_head()
            scan_start = time.monotonic()
            budget = min(2.0, deadline - scan_start, head_deadline - scan_start - 0.1)
            row = {'stage': 'round and persistent live storage', 'started_monotonic': scan_start,
                   'granted_seconds': budget, 'deadline': scan_start + budget, 'HEAD_headroom_seconds': 0.1}
            data['monitor'].append(row)
            try:
                require(budget > 0, 'storage scan has no positive HEAD/wall budget')
                # One traversal covers round and persistent subtree thresholds.
                row['observation'] = storage_observation(command, round_tree=True, live_sampling=True,
                    seconds=budget, absolute=min(deadline, head_deadline - 0.1))
                row['completed_monotonic'] = time.monotonic()
                if row['completed_monotonic'] >= deadline:
                    child_elapsed('storage completion at child boundary')
                if row['completed_monotonic'] > scan_start + budget:
                    raise explicit_boundary('live_storage', scan_start + budget, stage='storage scan completion')
            except BaseException as error:
                row['error'] = error_record('storage subdeadline/observation', error)
                data['storage_limited'] = True
                classify_exception(data, 'live storage', error)
                raise
            observe_head()
            next_storage = scan_start + 5
        elif time.monotonic() >= next_target:
            observe_head()
        now = time.monotonic()
        next_os = start + 5 * os_opportunity if os_opportunity <= 120 else float('inf')
        sleep_for = min(0.1, next_target - now, head_deadline - now, deadline - now,
                        next_os - now, next_storage - now)
        if sleep_for > 0:
            time.sleep(sleep_for)


def planned_input(plan, path):
    matches = [row for row in plan["inputs"] if row["path"] == str(path)]
    require(len(matches) == 1, "exact frozen historical input required")
    check(matches[0])
    return matches[0]


def verify_origins(plan, ledger, actor):
    require(ledger['round'] == 'R363' and ledger['actor'] == actor
            and ledger['plan'] == pin(D / 'plan.json')
            and ledger['activation'] == pin(D / 'root-source-preparation-activation.json')
            and ledger['effective_references'] == read_json(D / 'root-source-preparation-activation.json')['effective_references'],
            'R363 actual new ledger identity/activation/baseline differs')
    require(tuple(ledger['commands']) == KEYS, 'R363 only one fresh command allowed')
    slot = ledger['commands']['utc_no_sigusr2_01']
    require(slot['identity'] == 'R363:utc_no_sigusr2_01' and slot['authorized'] == 1
            and slot['kind'] == 'NEW_SEPARATE_LIVE_DIAGNOSTIC' and slot['retry'] is False
            and slot['diagnostic_only'] is True and slot['behavior_acceptance_credit'] == 0,
            'R363 no historical allowance transfer or behavior credit')


def verify_budget(plan, root_ledger):
    require(plan['budgets']['new_allowances'] == 1 and plan['budgets']['stack_sampling_opportunities'] == 0
            and plan['commands']['utc_no_sigusr2_01']['allowance_origin'] == {
                'kind': 'NEW_SEPARATE_LIVE_DIAGNOSTIC', 'old_attempt_reset': False,
                'old_HELD_transfer': False, 'counts_as_behavior_pass': False},
            'R363 only distinct new diagnostic permitted')
    for path in (OLD / 'root-command-ledger.json', OLD / 'implementation/author-command-ledger.json'):
        check(planned_input(plan, path))
        previous = read_json(path)['commands']['live_utc_01']
        require(previous['state'] == 'SPENT' and previous['used'] == 1 and previous['remaining'] == 0,
                'R354 historical diagnostic must remain spent')
    inventory = read_json(OLD / 'source-gate.json')['pins']
    for path in (R350 / 'root-command-ledger.json', R350 / 'implementation/author-command-ledger.json'):
        matches = [item for item in inventory if item['path'] == str(path)]
        require(len(matches) == 1, 'exact R350 historical ledger pin required')
        check(matches[0])
        previous = read_json(path)['commands']
        require(all(previous[key]['state'] == 'SPENT' and previous[key]['used'] == 1
                    and previous[key]['remaining'] == 0 for key in ('t3_01', 't3_02', 't3_03')),
                'R350 three historical spent changed')
        require(all(previous[key]['state'] == HELD and previous[key]['used'] == 0
                    and previous[key]['remaining'] == 1 for key in tuple(previous)[3:]),
                'R350 six historical held changed')
    return {'new_allowances': 1, 'old_allowances_mutated': False, 'behavior_credit': 0}


def verify_lineage(plan, gate, acceptance):
    activation = read_json(D / 'root-source-preparation-activation.json')
    effective = activation['effective_references']
    require(effective == gate['effective_references'] == acceptance['effective_references']
            and effective['baseline_runner'] == HISTORICAL_RUNNER
            and effective['baseline_observer'] == plan['baseline']['implementation/r354_live_observer.py']
            and effective['whole_helper'] == plan['baseline']['implementation/resource-evidence-helpers.py'],
            'R363 exact final R354 baseline required')
    for reference in effective.values():
        check(reference)
    require(stable(HELPER) == stable(effective['whole_helper']['path']), 'whole helper bytes changed')
    check(plan['baseline']['source-gate.json'])
    inherited = read_json(plan['baseline']['source-gate.json']['path'])['pins']
    required_pins = plan['inputs'] + inherited + [pin(D / 'root-command-ledger.initial.json'),
                                                pin(IMPL / 'author-command-ledger.initial.json')]
    actual_inventory = {item['path']: item for item in gate['pins']}
    require(all(actual_inventory.get(item['path']) == item for item in required_pins),
            'R363 gate must retain every direct/inherited dependency and initial snapshot')
    require(str(D / 'root-command-ledger.json') not in actual_inventory
            and str(AUTHOR) not in actual_inventory, 'current mutable ledgers cannot be immutable pins')
    ancestors = plan['frozen_ancestor_references']
    require(gate['frozen_ancestor_references'] == acceptance['frozen_ancestor_references'] == ancestors,
            'R363 immutable ancestor table differs')
    for reference in ancestors.values():
        check(reference)
    persistence = read_json(ancestors['observer_persistence_acceptance']['path'])
    require(persistence['round'] == 'R358' and persistence['actor'] == '/root'
            and persistence['reviewed'] is True
            and persistence['plan'] == ancestors['observer_persistence_clarification']
            and persistence['observer'] == effective['baseline_observer'],
            'old R358 acceptance binds frozen R354 observer only')
    proof = read_json(gate['source_proof']['path'])
    require(proof['before'] == effective['baseline_runner'] and proof['after'] == pin(__file__)
            and proof['observer'] == pin(OBSERVER) and proof['allowed_change_policy'] == CHANGE_POLICY
            and proof['protected_profile_AST_unchanged_after_identity_normalization'] is True
            and proof['active_SIGUSR2_paths'] == 0, 'new R363 protected source difference proof required')
    lineage = read_json(gate['lineage_adoption']['path'])
    expected = {'round': 'R363', 'plan': pin(D / 'plan.json'),
                'activation': pin(D / 'root-source-preparation-activation.json'),
                'effective_references': effective, 'frozen_ancestor_references': ancestors,
                'successor_runner': pin(__file__), 'observer': pin(OBSERVER), 'whole_helper_copy': pin(HELPER),
                'source_proof': gate['source_proof'], 'same_actual_actor': pin(BINDING),
                'historical_acceptance_applies_to_current_runner': False, 'allowed_change_policy': CHANGE_POLICY}
    require(all(lineage[field] == value for field, value in expected.items()), 'R363 new lineage differs')
    binding = read_json(BINDING)
    require(binding['plan'] == pin(D / 'plan.json')
            and binding['activation'] == pin(D / 'root-source-preparation-activation.json')
            and binding['effective_references'] == effective
            and binding['frozen_ancestor_references'] == ancestors
            and binding['old_generations_execution_prohibited'] is True
            and binding['historical_acceptance_applies_to_new_runner'] is False,
            'actual R363 same-seat adoption required')


def verify_gate(command, plan, gate, acceptance, root_ledger, key):
    require(gate["round"] == "R363" and gate["HEAD"] == HEAD and gate["branch"] == BRANCH
            and gate["plan"] == pin(D / "plan.json")
            and gate["activation"] == pin(D / "root-source-preparation-activation.json"), "gate generation differs")
    require(gate["commands"] == plan["commands"] and tuple(plan["commands"]) == KEYS,
            "exact single diagnostic command table differs")
    for field, path in (("runner", Path(__file__)), ("observer", OBSERVER), ("helper", HELPER)):
        require(gate[field] == pin(path) == acceptance[field], "actual new implementation not accepted: " + field)
    for field, path in (("executor_binding", BINDING), ("source_proof", IMPL / "source-proof.json"),
                        ("lineage_adoption", IMPL / "runner-lineage-adoption.json")):
        require(gate[field] == pin(path), "new source relation differs: " + field)
    require(gate["executor_binding"] == acceptance["executor_binding"], "actual binding not accepted")
    binding = read_json(BINDING)
    require(binding["actual_actor"] == "/root/p6_t3_sol"
            and binding["acknowledged_by_actual_live_seat"] is True
            and binding["diagnostic_only"] is True and binding["behavior_acceptance_credit"] == 0,
            "actual same-seat diagnostic author acknowledgment required")
    require(acceptance["round"] == "R363" and acceptance["actor"] == "/root"
            and acceptance["reviewed"] is True and acceptance["source_gate"] == pin(D / "source-gate.json")
            and acceptance["plan"] == gate["plan"]
            and acceptance["activation"] == gate["activation"],
            "new ROOT review must accept actual new generation")
    require(gate['active_signal_sampling'] == acceptance['active_signal_sampling'] == 'DISABLED_BY_PLAN'
            and acceptance['source_proof'] == gate['source_proof'],
            'new R363 source acceptance must cover protected profile and withdrawal')
    verify_budget(plan, root_ledger)
    verify_lineage(plan, gate, acceptance)
    require(plan["capture"]["monitor_policy"] == MONITOR_POLICY
            and plan["capture"]["completion_contract"] == COMPLETION_CONTRACT,
            "original diagnostic monitor/completion contract differs")
    require(key == "utc_no_sigusr2_01" and len(command["nodes"]) == 1
            and [arg for arg in command["child_argv"] if "::" in arg] == command["nodes"]
            and command["nodes"][0] == "tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]"
            and command["diagnostic_only"] is True and command["max_worker_poll_lifecycles"] == 3
            and command["stack_sampling_opportunities"] == 0,
            "unchanged single UTC-memory diagnostic required")
    require(pin(HELPER)["sha256"] == HELPER_SHA, "whole helper changed")
    return 0  # No historical count is reconstructed or charged to this allowance.


def spend(author_before, key, reserved, out, command, plan, root_ledger):
    author = json.loads(base64.b64decode(author_before["base64"]))
    verify_budget(plan, root_ledger)
    verify_origins(plan, author, "/root/p6_t3_sol")
    require(key == "utc_no_sigusr2_01" and reserved["identity"] == "R363:utc_no_sigusr2_01"
            and reserved["diagnostic_only"] is True and reserved["kind"] == "NEW_SEPARATE_LIVE_DIAGNOSTIC",
            "selected diagnostic reservation origin differs")
    slot = author["commands"][key]
    require(slot["state"] == HELD and slot["used"] == 0 and slot["remaining"] == 1,
            "AUTHOR diagnostic allowance not HELD")
    slot.update(state="CONSUMED_BEFORE_START", used=1, remaining=0,
                reservation_id=reserved["reservation_id"])
    return cas(AUTHOR, author_before, author, out / "author-consumed.json")


def reconcile(key, reserved, out):
    before = full(AUTHOR)
    after = json.loads(base64.b64decode(before["base64"]))
    slot = after["commands"][key]
    require(slot["state"] == "CONSUMED_BEFORE_START" and slot["reservation_id"] == reserved["reservation_id"],
            "AUTHOR consumed state changed; ROOT must reconcile")
    slot["state"] = "SPENT"
    return cas(AUTHOR, before, after, out / "author-spent.json")


def run_selected(key):
    out = IMPL / key
    command = gate = helper = reserved = None
    process = None
    errors, signals, monitor, stages = [], [], [], {}
    source_before = {"pins": [], "complete": False, "accepted": False}
    cleanup = {"leader_reaped": None, "group_remaining": None, "cleanup_errors": [], "no_child_started": True}
    data = {"round": "R363", "command_id": "R363:" + key, "source_gate": None,
            "child_exit": None, "pid": None, "pgid": None, "timed_out": False,
            "output_limited": False, "storage_limited": False, "previous_actual_polls": None,
            "behavior_checks_passed": False, "behavior_candidate_pass": False, "test_observed_pass": False,
            "diagnostic_only": True, "behavior_acceptance_credit": 0,
            "completion_required": True, "ROOT_accepted": False,
            "formal_accepted": False, "whole_B_accepted": False, "errors": errors,
            "signals": signals, "cleanup": cleanup, "monitor": monitor,
            "unobserved": {"RSS": None, "OS_handles": None, "GPU_native": None,
                           "external_models": None, "network_calls": None}}
    previous_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def interrupted(signum, frame):
        observed = time.monotonic()
        signals.append({"signal": signum, "monotonic": observed})
        record_trigger("actual_TERM_INT", {"signal": signum}, observed=observed)

    for sig in previous_signals:
        signal.signal(sig, interrupted)
    overall_start = time.monotonic()
    output_created = False
    completion_valid = False
    try:
        try:
            with bounded(35, origin="preflight", stage="selected guards/CAS/source-before"):
                require(pin(D / "plan.json")["sha256"] == PLAN_SHA, "actual Astra plan changed")
                plan = read_json(D / "plan.json")
                command = plan["commands"][key]
                require(command["output"] == str(out) and command["cwd"] == str(ROOT), "literal output/cwd differs")
                root_ledger = read_json(D / "root-command-ledger.json")
                verify_origins(plan, root_ledger, "/root")
                proposed = root_ledger["commands"][key]
                require(proposed["state"] == "RESERVED" and proposed["used"] == 1 and proposed["remaining"] == 0
                        and proposed["identity"] == "R363:" + key
                        and type(proposed["reservation_id"]) is str and proposed["reservation_id"],
                        "ROOT individual reservation required")
                reserved = proposed
                out.mkdir(mode=0o700, exist_ok=False)
                output_created = True
                open_diagnostic_logs(out)
                write(out / "invocation.json", {"command_id": "R363:" + key, "command": command,
                      "root_reservation": reserved, "root_ledger_observed": full(D / "root-command-ledger.json"),
                      "monotonic": overall_start, "wrapper_pid": os.getpid(),
                      "actual_sys_executable": sys.executable, "actual_sys_prefix": sys.prefix})
                # Reservation already spends ROOT. Consume AUTHOR before all remaining prelaunch guards.
                spend(full(AUTHOR), key, reserved, out, command, plan, root_ledger)
                gate = read_json(D / "source-gate.json")
                acceptance = read_json(D / "root-source-acceptance.json")
                require(reserved["source_gate"] == pin(D / "source-gate.json")
                        and reserved["acceptance"] == pin(D / "root-source-acceptance.json")
                        and reserved["executor_binding"] == pin(BINDING), "reservation source/actor identity differs")
                data["source_gate"] = pin(D / "source-gate.json")
                data["observer"] = gate["observer"]
                validate_launch_capture(reserved, command, key)
                data["previous_actual_polls"] = verify_gate(command, plan, gate, acceptance, root_ledger, key)
                data["actual_interpreter"] = verify_interpreter(gate["interpreter_evidence"], command)
                observe_sources(gate, source_before)
                write(out / "source-before.json", source_before)
                require(source_before["accepted"], "before HEAD/source observation rejected")
                monitor.append({"stage": "prelaunch round storage", **storage_observation(command, round_tree=True)})
                require(not signals, "interrupted before child start")
                spec = importlib.util.spec_from_file_location("r363_frozen_helpers", HELPER)
                helper = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(helper)  # Only the new whole frozen stdlib helper; reserved attempt only.
                write(out / "helper-import-identity.json", {"helper": pin(HELPER), "module": "r363_frozen_helpers",
                      "product_imported_in_parent": False, "interpreter_evidence": gate["interpreter_evidence"],
                      "actual_interpreter": data["actual_interpreter"]})
                (out / "resources").mkdir()
        except BaseException as error:
            classify_exception(data, "prelaunch", error)
            errors.append(error_record("prelaunch", error))
            data["prelaunch_rejection"] = retain_prelaunch_rejection(error, key, reserved,
                                                                    normal_output_created=output_created)
            if not output_created:
                return 1

        if not errors:
            try:
                with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
                    start = time.monotonic()
                    deadline = start + command["child_seconds"]
                    data.update(child_start_monotonic=start, child_deadline_monotonic=deadline)
                    with bounded(command["child_seconds"], deadline, origin="child_wall", stage="child launch and monitor"):
                        data["child_timer_owner"] = _TIMER_FRAME["owner"]
                        process = subprocess.Popen(command["child_argv"], cwd=ROOT, env=command["child_env"],
                                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                                   shell=False, start_new_session=True)
                        data.update(pid=process.pid, pgid=process.pid)
                        cleanup["no_child_started"] = False
                        write(out / "actual-child-start.json", {"pid": process.pid, "pgid": os.getpgid(process.pid),
                              "argv": command["child_argv"], "env": command["child_env"],
                              "monotonic_start": start, "deadline": deadline})
                        monitor_child(process, command, data, signals, out, start, deadline)
            except DeadlineExpired as error:
                classify_exception(data, "child/monitor", error)
                errors.append(error_record("child/monitor bounded deadline", error))
            except BaseException as error:
                classify_exception(data, "child/monitor", error)
                errors.append(error_record("child/monitor", error))
    finally:
        # This finally surrounds source guards, ledger CAS, Popen, monitoring and signals.
        # No ledger reconciliation or capture validator can bypass owned-group cleanup.
        if process is not None:
            data.update(pid=process.pid, pgid=process.pid)
            cleanup["no_child_started"] = False
            try:
                cleanup.update(helper._t2_cleanup(process))
            except BaseException as error:
                cleanup["cleanup_errors"].append(error_record("owned cleanup", error))
                # Immediate fail-closed signal; no second polling/test attempt or cleanup budget reset.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as kill_error:
                    cleanup["cleanup_errors"].append(error_record("emergency KILL", kill_error))
            data["child_exit"] = process.returncode
            data["child_elapsed_seconds_through_cleanup"] = time.monotonic() - data["child_start_monotonic"]

        if output_created:
            capture_start = time.monotonic()
            capture_deadline = capture_start + 240

            def stage(name, seconds, action, *, state=None):
                entry = {"state": "STARTED", "seconds_bound": seconds, "started_monotonic": time.monotonic(),
                         "error": None, "persistence_error": None}
                stages[name] = entry
                partial = {} if state is None else state
                try:
                    with bounded(seconds, capture_deadline, origin="capture:" + name, stage=name):
                        action(partial)
                    entry["state"] = "COMPLETE"
                except BaseException as error:
                    entry["state"] = "TIMEOUT" if isinstance(error, DeadlineExpired) else "FAILED"
                    entry["error"] = error_record(name, error)
                    classify_exception(data, name, error)
                    errors.append(entry["error"])
                finally:
                    entry["elapsed_seconds"] = time.monotonic() - entry["started_monotonic"]
                    data[name] = partial
                    # Bookkeeping uses the shared 30s reserve, never an unbounded finally write.
                    try:
                        with bounded(2, capture_deadline, origin="receipt_write", stage=name + " receipt"):
                            write(out / (name + ".json"), {"stage": entry, "observations": partial})
                    except BaseException as error:
                        entry["persistence_error"] = error_record(name + " persistence", error)
                        classify_exception(data, name + " receipt", error)
                        errors.append(entry["persistence_error"])

            def raw_process(partial):
                partial.update(cleanup=cleanup, signals=signals, streams={}, ledger=None)
                partial["diagnostic_index"] = diagnostic_index(out, phase="RAW_STAGE_PARENT_LOGS_STILL_OPEN")
                for name in ("stdout.txt", "stderr.txt"):
                    try:
                        actual = pin(out / name)
                        partial["streams"][name] = {"pin": actual, "overshoot_bytes": max(0, actual["bytes"] - RAW_CAP)}
                        data["output_limited"] |= actual["bytes"] > RAW_CAP
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        failure = error_record(name, error)
                        partial["streams"][name] = {"error": failure}
                        errors.append(failure)
                try:
                    partial["ledger"] = reconcile(key, reserved, out)
                except DeadlineExpired:
                    raise
                except Exception as error:
                    failure = error_record("AUTHOR spent reconciliation", error)
                    partial["ledger"] = {"error": failure, "ROOT_reconciliation_required": True,
                                         "reservation_already_spent": reserved, "no_refund": True}
                    errors.append(failure)
                partial.update(child_started=process is not None, pid=data["pid"], pgid=data["pgid"],
                               child_exit=data["child_exit"], monitor=monitor, original_errors=list(errors))

            def sources(partial):
                partial.update(pins=[], complete=False, accepted=False)
                if gate is None:
                    raise ValueError("source gate unavailable after prelaunch rejection")
                observe_sources(gate, partial)
                if partial["accepted"]:
                    write(out / "source-after.json", partial)

            def inventory(partial):
                partial.update(files=[], complete=False, requested_copies_complete=False,
                               consistent_database_backup=False, originals_deleted=False)
                observed = walk(out / "persistent-basetemp", partial["files"], content=True,
                                archive=out / "retained-databases")
                partial.update(observed)
                candidates = [row for row in partial["files"] if row.get("type") == "regular"
                              and database_name(Path(row["path"]).name)]
                partial["database_and_sidecar_files"] = candidates
                partial["requested_copies_complete"] = all(row.get("archive") and not row.get("error")
                    and not row.get("archive_error") for row in candidates)
                require(partial["complete"] and partial["requested_copies_complete"], "partial inventory/DB retention")

            def resources(partial):
                partial.update(original_sidecar_copies=[], facts={}, summary=None, behavior_complete=False)
                directory = out / "resources"
                # Retain every actual sidecar first, even when parser/provenance validation will reject it.
                for path in directory.iterdir():
                    require(len(partial["original_sidecar_copies"]) < ENTRY_CAP, "sidecar entry cap")
                    row = {"path": str(path), "pin": None, "copy": None, "error": None}
                    partial["original_sidecar_copies"].append(row)
                    try:
                        raw = stable(path)
                        row["pin"] = bytes_pin(path, raw)
                        row["copy"] = write(out / "retained-sidecars" / path.name, raw)
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        row["error"] = error_record("sidecar byte retention", error)
                require(helper is not None, "new frozen helper unavailable")
                summary = helper.diagnostic_resources(directory, "R363:" + key, command["child_argv"], data["pid"])
                partial["summary"] = summary
                partial["behavior_complete"] = helper.behavior_resources_complete(summary, facts=partial["facts"])
                data["resource_counts"] = summary["counts"]
                require(summary["complete_sidecar_set"] and summary["all_records_valid"], "resource sidecars invalid/incomplete")
                counts = summary["counts"]
                require(counts.get("constructed_worker_attempts", 0) <= 64, "inherited actual worker construction64 cap")
                polls = counts.get("attempted_poll_lifecycles", 0)
                require(polls <= command["max_worker_poll_lifecycles"]
                        and data["previous_actual_polls"] is not None
                        and data["previous_actual_polls"] + polls <= 3, "fresh diagnostic actual poll cap")
                require(summary["peak_active_polls_per_node"] <= 2, "concurrent poll cap")
                require(partial["behavior_complete"] is True, "genuine nested assertions did not complete")
                require(all(not row["error"] for row in partial["original_sidecar_copies"]), "sidecar bytes incomplete")

            def junit(partial):
                require(helper is not None, "new frozen helper unavailable")
                partial.update(helper.junit_observation(out / "junit.xml", command["nodes"]))
                require(partial["available"] and partial["tests"] == 1 and partial["failures"] == 0
                        and partial["errors"] == 0 and partial["skips"] == 0, "one genuine passing JUnit required")

            def cases(partial):
                partial.update(files=[], scan=[])
                scanned = walk(out / "persistent-basetemp", partial["scan"])
                require(helper is not None, "new frozen helper unavailable")
                for row in partial["scan"]:
                    path = Path(row["path"])
                    if path.name not in helper.CASE_NAMES:
                        continue
                    item = {"path": str(path), "pin": None, "data": None, "error": None}
                    partial["files"].append(item)
                    try:
                        require(row.get("type") == "regular", "actual case must be regular")
                        raw = stable(path)
                        item["pin"] = bytes_pin(path, raw)
                        write(out / "retained-cases" / row["relative"], raw)
                        value = json.loads(raw)
                        item["data"] = value
                        require(path.name == command["expected_case_filename"]
                                and value["schema_version"] == "bigsmall.r331.t3-case.v1"
                                and value["nodeid"] == command["nodes"][0]
                                and value["command_id"] == "R363:" + key
                                and value["pid"] == data["pid"] and data["pid"] is not None,
                                "case schema/family/node/command/actual PID differs")
                        require(value["observers_restored"] is True and value["cleanup_errors"] == [],
                                "case observer/cleanup unavailable")
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        item["error"] = error_record("actual case", error)
                require(scanned["complete"] and len(partial["files"]) == 1
                        and partial["files"][0]["error"] is None, "exact one genuine case required")
                summary = data.get("resources", {}).get("summary")
                require(summary is not None and len(summary["records"]) == 1, "case/resource join unavailable")
                case = partial["files"][0]["data"]
                sidecar = summary["records"][0]["data"]
                require(case["resources"] == sidecar["resources"]
                        and case["worker_lifecycles"] == sidecar["worker_lifecycles"]
                        and sidecar["observations"]["assertions_completed"] is True,
                        "case/actual resource lifecycle and nested assertion join differs")

            def prerequisite(partial):
                require(helper is not None, "new frozen helper unavailable")
                partial.update(helper.prerequisite(out / "prerequisite.json", {"module": helper.MODULE_PIN}, data["pid"]))
                require(partial["accepted"] is True, "genuine R235 prerequisite rejected")

            stage("raw-process-ledger", 15, raw_process)
            stage("source-after-observed", 30, sources)
            stage("persistent-inventory", 90, inventory)
            stage("resources", 30, resources)
            stage("junit", 10, junit)
            stage("cases", 10, cases)
            stage("prerequisite-observation", 10, prerequisite)

            # Explicit terminal protocol: no generic stage finally may write after completion.
            try:
                with bounded(15, capture_deadline, origin="finalization", stage="explicit terminal protocol"):
                    complete = tuple(stages) == STAGE_NAMES and all(
                        stages[name]["state"] == "COMPLETE" and not stages[name]["persistence_error"]
                        for name in STAGE_NAMES)
                    inventory_data = data.get("persistent-inventory", {})
                    data["artifact_retention_complete"] = bool(complete and not errors
                        and inventory_data.get("complete") is True and inventory_data.get("requested_copies_complete") is True)
                    clean = (process is not None and cleanup.get("leader_reaped") is True
                             and cleanup.get("group_remaining") is False and not cleanup["cleanup_errors"])
                    data["required_evidence_complete"] = bool(complete and source_before["accepted"]
                        and data.get("source-after-observed", {}).get("accepted") is True and clean
                        and data.get("resources", {}).get("behavior_complete") is True)
                    junit_data = data.get('junit', {})
                    data['test_observed_pass'] = bool(data['child_exit'] == 0
                        and junit_data.get('available') is True and junit_data.get('tests') == 1
                        and junit_data.get('failures') == 0 and junit_data.get('errors') == 0
                        and junit_data.get('skips') == 0)
                    data['behavior_checks_passed'] = False
                    data['behavior_candidate_pass'] = False
                    data['whole_B_accepted'] = False
                    data['formal_accepted'] = False
                    close_diagnostic_logs(errors)
                    data['diagnostic_index_final'] = diagnostic_index(out, phase='FINAL_PARENT_LOGS_CLOSED')
                    data['artifact_retention_complete'] &= data['diagnostic_index_final']['complete'] and not errors
                    data['deadline_events'] = list(_DEADLINE_EVENTS)
                    data['trigger_events'] = list(_TRIGGER_EVENTS)
                    data['primary_trigger'] = _TRIGGER_EVENTS[0] if _TRIGGER_EVENTS else None
                    data['diagnostic_observation_acceptance'] = 'ROOT_INDEPENDENT_REVIEW_REQUIRED'
                    data['normal_completed_test_and_capture'] = bool(data['artifact_retention_complete']
                        and data['required_evidence_complete'] and data['test_observed_pass']
                        and data['diagnostic_index_final']['complete']
                        and data['diagnostic_index_final']['all_expected_files_present']
                        and not data['timed_out'] and not data['output_limited'] and not data['storage_limited']
                        and data['diagnostic_index_final']['planned_native_absence'] and not signals and not errors)
                    data["capture_elapsed_seconds_before_final_write"] = time.monotonic() - capture_start
                    data["elapsed_seconds"] = time.monotonic() - overall_start
                    missing = {"command_id": "R363:" + key, "artifacts": {}, "errors": list(errors),
                               "chronology": "PRECOMMIT_OBSERVATION_NOT_REWRITTEN_AFTER_COMPLETION",
                               "source_before_accepted": source_before["accepted"], "ROOT_accepted": False}
                    names = ("invocation.json", "author-consumed.json", "author-spent.json", "source-before.json",
                             "actual-child-start.json", "stdout.txt", "stderr.txt", "source-after.json", "junit.xml",
                             "prerequisite.json", "helper-import-identity.json") + tuple(name + ".json" for name in STAGE_NAMES)
                    for name in names:
                        try:
                            missing["artifacts"][name] = {"status": "present", "pin": pin(out / name)}
                        except DeadlineExpired:
                            raise
                        except Exception as error:
                            missing["artifacts"][name] = {"status": "missing" if isinstance(error, FileNotFoundError)
                                                         else "invalid", "error": error_record(name, error)}
                    missing["artifacts"]["completion.json"] = {"status": "NOT_YET_PUBLISHED",
                                                               "observation_phase": "PRECOMMIT"}
                    missing["diagnostic_files"] = data["diagnostic_index_final"]["expected_files"]
                    missing["disabled_native_artifacts"] = data["diagnostic_index_final"]["disabled_artifacts"]
                    missing["stage_outcomes"] = {name: row["state"] for name, row in stages.items()}
                    missing_pin = write(out / "missingness.json", missing)
                    status_pin = write(out / "stage-status.json", {"stages": stages, "capture_seconds_bound": 240,
                        "bookkeeping_reserve_seconds": 30, "terminal_record": "completion.json",
                        "finalization_state": "PRECOMMIT_TERMINAL_RECORD_REQUIRED", "ROOT_acceptance_required": True})
                    result_pin = write(out / "result.json", data)
                    completion = {"schema": "bigsmall.r363.terminal-completion.v1", "command_id": "R363:" + key,
                        "nodes": command["nodes"], "pid": data["pid"], "source_gate": data["source_gate"],
                        "runner": pin(__file__), "result": result_pin, "missingness": missing_pin,
                        "stage_status": status_pin, "stage_receipts": {name: pin(out / (name + ".json")) for name in STAGE_NAMES},
                        "finalization_complete": True, "final_summary_state": "COMPLETE",
                        "behavior_candidate_pass": False, "behavior_checks_passed": False,
                        "test_observed_pass": data["test_observed_pass"],
                        "normal_completed_test_and_capture": data["normal_completed_test_and_capture"],
                        "diagnostic_only": True, "behavior_acceptance_credit": 0,
                        "wrapper_exit0_required": COMPLETION_CONTRACT["wrapper_exit0_required"],
                        "ROOT_accepted": False, "capture_elapsed_seconds_before_commit": time.monotonic() - capture_start}
                    validate_completion(completion, key, command, data["source_gate"], pin(__file__))
                    write(out / "completion.json", completion)  # Includes stable readback; last success-artifact write.
                    completion_valid = True
            except BaseException as error:
                classify_exception(data, "explicit finalization", error)
                original = error_record("explicit finalization", error)
                errors.append(original)
                failure = {"command_id": "R363:" + key, "original_error": original,
                           "completion_valid": False, "ROOT_accepted": False, "no_retry": True,
                           "deadline_events": list(_DEADLINE_EVENTS), "trigger_events": list(_TRIGGER_EVENTS),
                           "timed_out": data["timed_out"], "behavior_candidate_pass": False}
                try:
                    with bounded(2, capture_deadline, origin="receipt_write", stage="finalization stderr"):
                        remaining = memoryview(encoded(failure))
                        while remaining:
                            count = os.write(2, remaining)
                            require(count > 0, "finalization stderr made no progress")
                            remaining = remaining[count:]
                except BaseException as persistence_error:
                    failure["stderr_error"] = error_record("finalization stderr", persistence_error)
                try:
                    with bounded(2, capture_deadline, origin="receipt_write", stage="finalization error receipt"):
                        write(out / "finalization-error.json", failure)
                except BaseException as persistence_error:
                    errors.append(error_record("finalization error receipt", persistence_error))
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)
    return 0 if completion_valid and data.get("normal_completed_test_and_capture") and not errors and not signals else 1


def main():
    key = sys.argv[1] if len(sys.argv) == 2 and sys.argv[1] in KEYS else "invalid-key"
    try:
        require(len(sys.argv) == 2 and key in KEYS, "one literal R363 command key required")
        return run_selected(key)
    except BaseException as error:
        retain_prelaunch_rejection(error, key)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
