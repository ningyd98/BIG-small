"""Single-process OC1 operational counts, with no UTC/SI or worker authority.

Live receipts establish local causality before integer age/deadline arithmetic.
The private CPU seam supplies raw readings only. This module does not integrate
acquisition, consumers, physics, leases, native sources, or research acceptance.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import NoReturn, Protocol, SupportsIndex

_NS_PER_OPERATIONAL_SECOND = 1_000_000_000
_FACTORY_CAPABILITY = object()


class OperationalTimeError(RuntimeError):
    """The requested local capability or causal pair is unavailable."""


def _integer(value: int, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        bound = "positive" if positive else "nonnegative"
        raise OperationalTimeError(f"{name} must be an exact {bound} integer")


def _interval(lower: int, upper: int) -> None:
    _integer(lower, "lower_ns")
    _integer(upper, "upper_ns")
    if lower > upper:
        raise OperationalTimeError("reversed operational bracket")


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise OperationalTimeError(f"{name} must be a nonempty string")


class _LiveHandle:
    __slots__ = ()

    def __copy__(self) -> object:
        raise OperationalTimeError("live operational handles cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> object:
        raise OperationalTimeError("live operational handles cannot be deep-copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise OperationalTimeError("live operational handles cannot be serialized")


@dataclass(frozen=True, slots=True)
class _StartupIdentity:
    boot_id: str
    pid: int
    process_start_ticks: int
    thread_id: int
    native_thread_id: int
    namespace_device: int
    namespace_inode: int
    namespace_offsets: tuple[tuple[str, int, int], ...]
    os_name: str
    os_release: str
    os_version: str
    machine: str
    python_version: str


def _validate_identity(identity: _StartupIdentity) -> None:
    if type(identity) is not _StartupIdentity:
        raise OperationalTimeError("startup identity is unavailable")
    _text(identity.boot_id, "boot_id")
    for name in ("pid", "process_start_ticks", "thread_id", "native_thread_id", "namespace_inode"):
        _integer(getattr(identity, name), name, positive=True)
    _integer(identity.namespace_device, "namespace_device")
    if type(identity.namespace_offsets) is not tuple or len(identity.namespace_offsets) != 2:
        raise OperationalTimeError("time namespace offsets are incomplete")
    for expected, entry in zip(("monotonic", "boottime"), identity.namespace_offsets, strict=True):
        if type(entry) is not tuple or len(entry) != 3:
            raise OperationalTimeError("invalid time namespace offset")
        name, seconds, nanoseconds = entry
        if name != expected or type(seconds) is not int:
            raise OperationalTimeError("invalid time namespace offset")
        _integer(nanoseconds, "namespace offset nanoseconds")
        if nanoseconds >= _NS_PER_OPERATIONAL_SECOND:
            raise OperationalTimeError("namespace offset nanoseconds out of range")
    if identity.os_name != "Linux":
        raise OperationalTimeError("operational time requires Linux BOOTTIME")


@dataclass(frozen=True, slots=True)
class OperationalDomain:
    """Readonly description; equality, a hash, and diagnostics grant no authority."""

    boot_id: str
    pid: int
    process_start_ticks: int
    owner_thread_id: int
    owner_native_thread_id: int
    namespace_device: int
    namespace_inode: int
    namespace_offsets: tuple[tuple[str, int, int], ...]
    startup_nonce: str
    startup_counter_ns: int
    os_name: str
    os_release: str
    os_version: str
    machine: str
    python_version: str
    resolution_seconds: float | None
    schema: str = "simulation.operational-time.v1"
    api: str = "Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME)"
    scope: str = "SOFTWARE_ONLY"
    utc_accuracy: None = None
    si_accuracy: None = None
    accuracy_status: str = "UNVERIFIED"
    worker_authority: str = "UNAVAILABLE"
    lease_authority: str = "UNAVAILABLE"
    native_authority: str = "UNAVAILABLE"
    future_horizon: str = "UNKNOWN"
    restart_suspend_hostpause: str = "NOT_TESTED_OC3_GATE"


@dataclass(frozen=True, slots=True, eq=False)
class OperationalEventToken(_LiveHandle):
    domain: OperationalDomain
    event_identity: str
    kind: str

    def __post_init__(self) -> None:
        _text(self.event_identity, "event_identity")
        _text(self.kind, "kind")


@dataclass(frozen=True, slots=True, eq=False)
class OperationalBracket(_LiveHandle):
    domain: OperationalDomain
    event_identity: str
    lower_ns: int
    upper_ns: int

    def __post_init__(self) -> None:
        _text(self.event_identity, "event_identity")
        _interval(self.lower_ns, self.upper_ns)


@dataclass(frozen=True, slots=True)
class OperationalAge:
    lower_ns: int
    upper_ns: int

    def __post_init__(self) -> None:
        _interval(self.lower_ns, self.upper_ns)

    @property
    def lower_seconds(self) -> Fraction:
        return Fraction(self.lower_ns, _NS_PER_OPERATIONAL_SECOND)

    @property
    def upper_seconds(self) -> Fraction:
        return Fraction(self.upper_ns, _NS_PER_OPERATIONAL_SECOND)


@dataclass(frozen=True, slots=True, eq=False)
class OperationalDeadline(_LiveHandle):
    domain: OperationalDomain
    origin: OperationalBracket
    task_key: str
    budget_ns: int
    deadline_ns: int
    issuance_identity: str

    def __post_init__(self) -> None:
        _text(self.task_key, "task_key")
        _text(self.issuance_identity, "issuance_identity")
        _integer(self.budget_ns, "budget_ns", positive=True)
        _integer(self.deadline_ns, "deadline_ns")
        if self.deadline_ns != self.origin.lower_ns + self.budget_ns:
            raise OperationalTimeError("deadline must use the original lower endpoint")


class _ClockSource(Protocol):
    resolution_seconds: float | None

    def identity(self) -> _StartupIdentity: ...

    def read_ns(self) -> int: ...


@dataclass(slots=True)
class _EventRecord:
    token: OperationalEventToken
    lower_ns: int
    mark_point: int | None = None
    receipt: OperationalBracket | None = None


@dataclass(frozen=True, slots=True)
class _ReceiptRecord:
    receipt: OperationalBracket
    token: OperationalEventToken
    role: str
    occurrence_point: int


class OperationalClockOwner(_LiveHandle):
    """Only the signing owner and its originating thread may use live receipts."""

    def __init__(self, *, _source: _ClockSource, _capability: object) -> None:
        if _capability is not _FACTORY_CAPABILITY:
            raise OperationalTimeError("use the startup factory")
        self._source = _source
        self._closed = False
        self._owner_reference = self
        self._events: dict[int, _EventRecord] = {}
        self._receipts: dict[int, _ReceiptRecord] = {}
        self._deadlines: dict[str, OperationalDeadline] = {}
        self._deadline_handles: dict[int, OperationalDeadline] = {}
        self._sequence = 0
        self._last_ns: int | None = None
        try:
            self._identity = _source.identity()
            _validate_identity(self._identity)
        except Exception as error:
            self._closed = True
            raise OperationalTimeError("startup identity unavailable") from error
        startup_ns = self._read()
        identity = self._identity
        self._domain = OperationalDomain(
            boot_id=identity.boot_id,
            pid=identity.pid,
            process_start_ticks=identity.process_start_ticks,
            owner_thread_id=identity.thread_id,
            owner_native_thread_id=identity.native_thread_id,
            namespace_device=identity.namespace_device,
            namespace_inode=identity.namespace_inode,
            namespace_offsets=identity.namespace_offsets,
            startup_nonce=uuid.uuid4().hex,
            startup_counter_ns=startup_ns,
            os_name=identity.os_name,
            os_release=identity.os_release,
            os_version=identity.os_version,
            machine=identity.machine,
            python_version=identity.python_version,
            resolution_seconds=_source.resolution_seconds,
        )
        self._check()

    @property
    def domain(self) -> OperationalDomain:
        return self._domain

    def _check(self) -> None:
        if self._owner_reference is not self or self._closed:
            raise OperationalTimeError("operational owner is not live")
        try:
            current = self._source.identity()
            _validate_identity(current)
            if (
                current != self._identity
                or os.getpid() != self._identity.pid
                or threading.get_ident() != self._identity.thread_id
                or threading.get_native_id() != self._identity.native_thread_id
            ):
                raise OperationalTimeError("process, boot, thread or time namespace changed")
        except Exception as error:
            self._closed = True
            raise OperationalTimeError("operational startup identity lost") from error

    def _read(self) -> int:
        self._check()
        try:
            value = self._source.read_ns()
            _integer(value, "counter_ns")
            if self._last_ns is not None and value < self._last_ns:
                raise OperationalTimeError("operational counter decreased")
            self._check()
        except Exception as error:
            self._closed = True
            raise OperationalTimeError("operational counter unavailable or invalid") from error
        self._last_ns = value
        return value

    def _point(self) -> int:
        self._sequence += 1
        return self._sequence

    def _event_record(self, token: OperationalEventToken) -> _EventRecord:
        if type(token) is not OperationalEventToken:
            raise OperationalTimeError("event token is not an issued live handle")
        record = self._events.get(id(token))
        if record is None or record.token is not token or token.domain is not self._domain:
            raise OperationalTimeError("event token is foreign or unissued")
        return record

    def _receipt_record(self, receipt: OperationalBracket) -> _ReceiptRecord:
        if type(receipt) is not OperationalBracket:
            raise OperationalTimeError("receipt is not an issued live handle")
        record = self._receipts.get(id(receipt))
        if record is None or record.receipt is not receipt or receipt.domain is not self._domain:
            raise OperationalTimeError("receipt is foreign or unissued")
        _interval(receipt.lower_ns, receipt.upper_ns)
        return record

    def begin_event(self, kind: str) -> OperationalEventToken:
        self._check()
        _text(kind, "kind")
        lower = self._read()
        token = OperationalEventToken(self._domain, uuid.uuid4().hex, kind)
        self._events[id(token)] = _EventRecord(token, lower)
        self._check()
        return token

    def mark_event(self, token: OperationalEventToken) -> None:
        self._check()
        record = self._event_record(token)
        if record.mark_point is not None or record.receipt is not None:
            raise OperationalTimeError("event occurrence may be marked only once")
        record.mark_point = self._point()
        self._check()

    def end_event(self, token: OperationalEventToken) -> OperationalBracket:
        self._check()
        record = self._event_record(token)
        if record.mark_point is None or record.receipt is not None:
            raise OperationalTimeError("event END requires a single prior MARK")
        upper = self._read()
        receipt = OperationalBracket(self._domain, token.event_identity, record.lower_ns, upper)
        self._receipts[id(receipt)] = _ReceiptRecord(receipt, token, "event", record.mark_point)
        record.receipt = receipt
        self._check()
        return receipt

    def read_current(self, *, after: OperationalEventToken) -> OperationalBracket:
        self._check()
        record = self._event_record(after)
        if record.mark_point is None:
            raise OperationalTimeError("current requires a prior event MARK")
        lower = self._read()
        current_point = self._point()
        upper = self._read()
        receipt = OperationalBracket(self._domain, uuid.uuid4().hex, lower, upper)
        self._receipts[id(receipt)] = _ReceiptRecord(receipt, after, "current", current_point)
        self._check()
        return receipt

    def age_bounds(self, event: OperationalBracket, current: OperationalBracket) -> OperationalAge:
        self._check()
        event_record = self._receipt_record(event)
        current_record = self._receipt_record(current)
        token_record = self._event_record(event_record.token)
        if (
            event_record.role != "event"
            or current_record.role != "current"
            or current_record.token is not event_record.token
            or token_record.receipt is not event
            or token_record.mark_point is None
            or token_record.mark_point >= current_record.occurrence_point
            or current.upper_ns < event.lower_ns
        ):
            raise OperationalTimeError("receipt pair lacks event-before-current causality")
        result = OperationalAge(
            max(0, current.lower_ns - event.upper_ns), current.upper_ns - event.lower_ns
        )
        self._check()
        return result

    def within_age(
        self,
        event: OperationalBracket,
        current: OperationalBracket,
        *,
        max_age_ns: int = 5_000_000_000,
    ) -> bool:
        _integer(max_age_ns, "max_age_ns")
        return self.age_bounds(event, current).upper_ns <= max_age_ns

    def start_deadline(
        self, *, task_key: str, origin: OperationalBracket, budget_ns: int
    ) -> OperationalDeadline:
        self._check()
        _text(task_key, "task_key")
        _integer(budget_ns, "budget_ns", positive=True)
        origin_record = self._receipt_record(origin)
        token_record = self._event_record(origin_record.token)
        if origin_record.role != "event" or token_record.receipt is not origin:
            raise OperationalTimeError("deadline origin requires a complete event receipt")
        existing = self._deadlines.get(task_key)
        if existing is not None:
            if existing.origin is not origin or existing.budget_ns != budget_ns:
                raise OperationalTimeError("original task deadline cannot be refreshed")
            self._check()
            return existing
        deadline = OperationalDeadline(
            self._domain,
            origin,
            task_key,
            budget_ns,
            origin.lower_ns + budget_ns,
            uuid.uuid4().hex,
        )
        self._deadlines[task_key] = deadline
        self._deadline_handles[id(deadline)] = deadline
        self._check()
        return deadline

    def before_deadline(self, deadline: OperationalDeadline, current: OperationalBracket) -> bool:
        self._check()
        if (
            type(deadline) is not OperationalDeadline
            or self._deadline_handles.get(id(deadline)) is not deadline
            or deadline.domain is not self._domain
            or self._deadlines.get(deadline.task_key) is not deadline
        ):
            raise OperationalTimeError("deadline is foreign or unissued")
        self.age_bounds(deadline.origin, current)
        return current.upper_ns < deadline.deadline_ns

    def close(self) -> None:
        if self._owner_reference is not self:
            raise OperationalTimeError("operational owner is not live")
        if not self._closed:
            self._check()
            self._closed = True


def _open_clock_for_test(source: _ClockSource) -> OperationalClockOwner:
    """Private SOFTWARE-only seam: supply raw reads/identity, never a verdict."""
    return OperationalClockOwner(_source=source, _capability=_FACTORY_CAPABILITY)


def _read_proc_text(path: str) -> str:
    return Path(path).read_text(encoding="ascii")


def _stat_time_namespace() -> os.stat_result:
    return os.stat("/proc/thread-self/ns/time")


def _parse_process_start_ticks(stat: str, *, expected_pid: int) -> int:
    """Parse field 22 after the whole comm, including spaces and ')' characters."""
    _integer(expected_pid, "expected_pid", positive=True)
    try:
        opening = stat.index("(")
        closing = stat.rindex(")")
        if closing <= opening or int(stat[:opening].strip()) != expected_pid:
            raise OperationalTimeError("proc stat PID/comm mismatch")
        fields_from_three = stat[closing + 1 :].split()
        start_ticks = int(fields_from_three[19])
        _integer(start_ticks, "process_start_ticks", positive=True)
        return start_ticks
    except (ValueError, IndexError) as error:
        raise OperationalTimeError("proc stat lacks an exact process start identity") from error


def _parse_namespace_offsets(text: str) -> tuple[tuple[str, int, int], ...]:
    offsets: dict[str, tuple[str, int, int]] = {}
    try:
        for line in text.splitlines():
            fields = line.split()
            if len(fields) != 3:
                raise OperationalTimeError("invalid time namespace offset row")
            name, seconds_text, nanoseconds_text = fields
            if name not in ("monotonic", "boottime") or name in offsets:
                raise OperationalTimeError("unknown or duplicate time namespace offset")
            seconds, nanoseconds = int(seconds_text), int(nanoseconds_text)
            _integer(nanoseconds, "namespace offset nanoseconds")
            if nanoseconds >= _NS_PER_OPERATIONAL_SECOND:
                raise OperationalTimeError("namespace offset nanoseconds out of range")
            offsets[name] = (name, seconds, nanoseconds)
        if set(offsets) != {"monotonic", "boottime"}:
            raise OperationalTimeError("both time namespace offsets are required")
        return (offsets["monotonic"], offsets["boottime"])
    except ValueError as error:
        raise OperationalTimeError("time namespace offsets must be exact integers") from error


class _LinuxBootTimeSource:
    """The single production source; no injected clocks, flags, or fallback API."""

    def __init__(self) -> None:
        if os.uname().sysname != "Linux" or not hasattr(time, "CLOCK_BOOTTIME"):
            raise OperationalTimeError("Linux CLOCK_BOOTTIME is unavailable")
        self.resolution_seconds: float | None = time.clock_getres(time.CLOCK_BOOTTIME)

    def read_ns(self) -> int:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME)

    def identity(self) -> _StartupIdentity:
        uname = os.uname()
        pid = os.getpid()
        boot_text = _read_proc_text("/proc/sys/kernel/random/boot_id").strip()
        try:
            boot_id = str(uuid.UUID(boot_text))
        except ValueError as error:
            raise OperationalTimeError("boot identity unavailable") from error
        start_ticks = _parse_process_start_ticks(
            _read_proc_text("/proc/self/stat"), expected_pid=pid
        )
        namespace = _stat_time_namespace()
        offsets = _parse_namespace_offsets(_read_proc_text("/proc/self/timens_offsets"))
        return _StartupIdentity(
            boot_id=boot_id,
            pid=pid,
            process_start_ticks=start_ticks,
            thread_id=threading.get_ident(),
            native_thread_id=threading.get_native_id(),
            namespace_device=namespace.st_dev,
            namespace_inode=namespace.st_ino,
            namespace_offsets=offsets,
            os_name=uname.sysname,
            os_release=uname.release,
            os_version=uname.version,
            machine=uname.machine,
            python_version=sys.version,
        )


def open_operational_clock() -> OperationalClockOwner:
    """Bind this process/thread to real Linux BOOTTIME; grant only OC1 counting."""
    try:
        source = _LinuxBootTimeSource()
        return OperationalClockOwner(_source=source, _capability=_FACTORY_CAPABILITY)
    except OperationalTimeError:
        raise
    except Exception as error:
        raise OperationalTimeError(
            "required Linux operational startup capability unavailable"
        ) from error
