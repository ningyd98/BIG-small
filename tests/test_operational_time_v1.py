"""OC1 SOFTWARE: real owner APIs over raw CPU source fixtures, never verdict mocks."""

from __future__ import annotations

import copy
import inspect
import json
import os
import pickle
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import FrozenInstanceError, asdict, replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cloud_edge_robot_arm.research import operational_time_v1
from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalBracket,
    OperationalClockOwner,
    OperationalDeadline,
    OperationalEventToken,
    OperationalTimeError,
    _open_clock_for_test,
    _parse_namespace_offsets,
    _parse_process_start_ticks,
    _StartupIdentity,
    open_operational_clock,
)


def _identity() -> _StartupIdentity:
    return _StartupIdentity(
        boot_id="fixture-boot",
        pid=os.getpid(),
        process_start_ticks=1,
        thread_id=threading.get_ident(),
        native_thread_id=threading.get_native_id(),
        namespace_device=1,
        namespace_inode=2,
        namespace_offsets=(("monotonic", 0, 0), ("boottime", 0, 0)),
        os_name="Linux",
        os_release="CPU-fixture",
        os_version="CPU-fixture",
        machine="CPU-fixture",
        python_version="CPU-fixture",
    )


class _RawSource:
    """The seam changes only raw counter/identity readings, not reader outcomes."""

    def __init__(self, values: list[object], *, resolution_seconds: float = 1e-9) -> None:
        self.values = iter([0, *values])
        self.current_identity = _identity()
        self.identity_error: Exception | None = None
        self.resolution_seconds = resolution_seconds

    def identity(self) -> _StartupIdentity:
        if self.identity_error is not None:
            raise self.identity_error
        return self.current_identity

    def read_ns(self) -> int:
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return cast(int, value)


def _clock(values: list[object]) -> tuple[OperationalClockOwner, _RawSource]:
    source = _RawSource(values)
    return _open_clock_for_test(source), source


def _event(owner: OperationalClockOwner) -> tuple[OperationalEventToken, OperationalBracket]:
    token = owner.begin_event("acquisition")
    owner.mark_event(token)
    return token, owner.end_event(token)


def test_pair_and_causal_receipts_required() -> None:
    owner, _ = _clock([100, 110, 120, 130])
    fabricated = OperationalEventToken(owner.domain, "not-issued", "acquisition")
    for operation in (owner.mark_event, owner.end_event):
        with pytest.raises(OperationalTimeError):
            operation(fabricated)
    with pytest.raises(OperationalTimeError):
        owner.read_current(after=fabricated)
    token = owner.begin_event("acquisition")
    with pytest.raises(OperationalTimeError):
        owner.read_current(after=token)
    with pytest.raises(OperationalTimeError):
        owner.end_event(token)
    owner.mark_event(token)
    with pytest.raises(OperationalTimeError):
        owner.mark_event(token)
    event = owner.end_event(token)
    with pytest.raises(OperationalTimeError):
        owner.end_event(token)
    current = owner.read_current(after=token)
    assert owner.age_bounds(event, current).lower_ns == 10
    assert owner.age_bounds(event, current).upper_ns == 30
    with pytest.raises(TypeError):
        owner.read_current()  # type: ignore[call-arg]
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(current, event)
    owner.close()
    owner.close()
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)


def test_legal_overlap_uses_occurrence_not_end_order() -> None:
    owner, _ = _clock([100, 150, 180, 200])
    token = owner.begin_event("acquisition")
    owner.mark_event(token)
    current = owner.read_current(after=token)
    event = owner.end_event(token)
    age = owner.age_bounds(event, current)
    assert (event.lower_ns, event.upper_ns) == (100, 200)
    assert (current.lower_ns, current.upper_ns) == (150, 180)
    assert (age.lower_ns, age.upper_ns) == (0, 80)
    fabricated = OperationalBracket(
        event.domain, event.event_identity, event.lower_ns, event.upper_ns
    )
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(fabricated, current)


@pytest.mark.parametrize("bad", [-1, True, 1.0])
def test_invalid_raw_counter_fails_closed(bad: object) -> None:
    owner, source = _clock([bad])
    with pytest.raises(OperationalTimeError):
        owner.begin_event("acquisition")
    source.values = iter([100, 110])
    with pytest.raises(OperationalTimeError):
        owner.begin_event("acquisition")


@pytest.mark.parametrize("lower,upper", [(-1, 2), (True, 2), (1, 2.0), (3, 2)])
def test_invalid_bracket_values_rejected(lower: object, upper: object) -> None:
    owner, _ = _clock([])
    with pytest.raises(OperationalTimeError):
        OperationalBracket(owner.domain, "ordinary-value", cast(int, lower), cast(int, upper))


@pytest.mark.parametrize("difference", [1, 1_000_000_001])
def test_future_and_reverse_causality_rejected(difference: int) -> None:
    owner, _ = _clock([difference + 100, difference + 110, 100, 100])
    token, _ = _event(owner)
    with pytest.raises(OperationalTimeError):
        owner.read_current(after=token)
    with pytest.raises(OperationalTimeError):
        owner.begin_event("acquisition")
    reversed_owner, _ = _clock([200, 100])
    reversed_token = reversed_owner.begin_event("acquisition")
    reversed_owner.mark_event(reversed_token)
    with pytest.raises(OperationalTimeError):
        reversed_owner.end_event(reversed_token)


def test_current_must_link_directly_to_original_marked_event() -> None:
    owner, _ = _clock([100, 110, 120, 130, 140, 150])
    _, original = _event(owner)
    other_token, other = _event(owner)
    current = owner.read_current(after=other_token)
    assert owner.age_bounds(other, current).upper_ns == 30
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(original, current)


def test_foreign_equal_descriptor_and_copied_handles_rejected() -> None:
    owner, _ = _clock([100, 110, 120, 130])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    foreign, _ = _clock([100, 110, 120, 130])
    other_token, other_event = _event(foreign)
    other_current = foreign.read_current(after=other_token)
    assert replace(owner.domain, startup_nonce=foreign.domain.startup_nonce) == foreign.domain
    for event_arg, current_arg in (
        (other_event, current),
        (event, other_current),
        (other_event, other_current),
    ):
        with pytest.raises(OperationalTimeError):
            owner.age_bounds(event_arg, current_arg)
    with pytest.raises(OperationalTimeError):
        owner.mark_event(other_token)
    copiers: tuple[Callable[[object], object], ...] = (copy.copy, copy.deepcopy, pickle.dumps)
    for handle in (owner, token, event, current):
        for copier in copiers:
            with pytest.raises(OperationalTimeError):
                copier(handle)
    payload = {
        "domain": event.domain,
        "event_identity": event.event_identity,
        "lower_ns": event.lower_ns,
        "upper_ns": event.upper_ns,
    }
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(OperationalBracket(**payload), current)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "current_lower,current_upper,accepted",
    [
        (5_000_000_099, 5_000_000_100, True),
        (5_000_000_100, 5_000_000_101, False),
        (4_999_999_000, 5_000_000_101, False),
    ],
)
def test_age_exact_five_seconds_and_plus_one_ns(
    current_lower: int, current_upper: int, accepted: bool
) -> None:
    owner, _ = _clock([100, 200, current_lower, current_upper])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    age = owner.age_bounds(event, current)
    assert age.upper_ns == current_upper - 100
    assert age.upper_seconds == Fraction(current_upper - 100, 1_000_000_000)
    assert owner.within_age(event, current) is accepted
    assert owner.within_age(event, current, max_age_ns=5_000_000_000) is accepted
    if current_lower == 4_999_999_000:
        assert age.lower_ns + age.upper_ns < 2 * 5_000_000_000


@pytest.mark.parametrize("limit", [-1, True, 5_000_000_000.0])
def test_age_rejects_noninteger_or_negative_limits(limit: object) -> None:
    owner, _ = _clock([100, 110, 120, 130])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    with pytest.raises(OperationalTimeError):
        owner.within_age(event, current, max_age_ns=cast(int, limit))


@pytest.mark.parametrize("base", [100, 2**60])
@pytest.mark.parametrize("difference,accepted", [(-1, True), (0, False), (1, False)])
def test_deadline_is_origin_lower_and_equality_rejects(
    base: int, difference: int, accepted: bool
) -> None:
    deadline_ns = base + 5_000_000_000
    upper = deadline_ns + difference
    owner, _ = _clock([base, base + 100, upper - 1, upper])
    token, event = _event(owner)
    deadline = owner.start_deadline(task_key="attempt-1", origin=event, budget_ns=5_000_000_000)
    current = owner.read_current(after=token)
    assert deadline.deadline_ns == deadline_ns
    assert deadline.origin is event
    assert owner.before_deadline(deadline, current) is accepted


@pytest.mark.parametrize("budget", [0, -1, True, 5_000_000_000.0])
def test_deadline_budget_requires_positive_integer(budget: object) -> None:
    owner, _ = _clock([100, 200])
    _, origin = _event(owner)
    with pytest.raises(OperationalTimeError):
        owner.start_deadline(task_key="attempt-1", origin=origin, budget_ns=cast(int, budget))


def test_original_deadline_never_refreshes() -> None:
    owner, _ = _clock(
        [
            100,
            200,
            4_900_000_099,
            4_900_000_100,
            5_050_000_100,
            5_050_000_200,
            5_100_000_099,
            5_100_000_100,
        ]
    )
    token, origin = _event(owner)
    deadline = owner.start_deadline(task_key="attempt-1", origin=origin, budget_ns=5_000_000_000)
    assert (
        owner.start_deadline(task_key="attempt-1", origin=origin, budget_ns=5_000_000_000)
        is deadline
    )
    assert owner.before_deadline(deadline, owner.read_current(after=token))
    _, later_event = _event(owner)
    with pytest.raises(OperationalTimeError):
        owner.start_deadline(task_key="attempt-1", origin=later_event, budget_ns=5_000_000_000)
    with pytest.raises(OperationalTimeError):
        owner.start_deadline(task_key="attempt-1", origin=origin, budget_ns=6_000_000_000)
    late_current = owner.read_current(after=token)
    assert not owner.before_deadline(deadline, late_current)
    assert deadline.deadline_ns == 5_000_000_100
    owner.close()
    with pytest.raises(OperationalTimeError):
        owner.before_deadline(deadline, late_current)
    replacement, _ = _clock([100, 200, 300, 400])
    replacement_token, _ = _event(replacement)
    replacement_current = replacement.read_current(after=replacement_token)
    with pytest.raises(OperationalTimeError):
        replacement.before_deadline(deadline, replacement_current)


def test_deadline_requires_original_event_causal_link_and_exact_handle() -> None:
    owner, _ = _clock([100, 200, 300, 400, 500, 600])
    _, origin = _event(owner)
    other_token, _ = _event(owner)
    deadline = owner.start_deadline(task_key="attempt-1", origin=origin, budget_ns=5_000_000_000)
    unrelated_current = owner.read_current(after=other_token)
    with pytest.raises(OperationalTimeError):
        owner.before_deadline(deadline, unrelated_current)
    with pytest.raises(OperationalTimeError):
        owner.start_deadline(task_key="attempt-2", origin=unrelated_current, budget_ns=1)
    forged = OperationalDeadline(
        deadline.domain,
        deadline.origin,
        deadline.task_key,
        deadline.budget_ns,
        deadline.deadline_ns,
        deadline.issuance_identity,
    )
    with pytest.raises(OperationalTimeError):
        owner.before_deadline(forged, unrelated_current)
    for copier in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(OperationalTimeError):
            copier(deadline)


def test_diagnostics_cannot_create_precision_or_authority() -> None:
    outcomes = []
    for resolution in (1e-9, 1_000.0):
        source = _RawSource([100, 200, 300, 400], resolution_seconds=resolution)
        owner = _open_clock_for_test(source)
        token, event = _event(owner)
        current = owner.read_current(after=token)
        outcomes.append(owner.age_bounds(event, current))
        assert owner.domain.resolution_seconds == resolution
        assert owner.domain.utc_accuracy is None
        assert owner.domain.si_accuracy is None
        assert owner.domain.accuracy_status == "UNVERIFIED"
        assert owner.domain.native_authority == "UNAVAILABLE"
        assert owner.domain.worker_authority == "UNAVAILABLE"
        assert owner.domain.lease_authority == "UNAVAILABLE"
        claimed = replace(owner.domain, utc_accuracy=0)  # type: ignore[arg-type]
        with pytest.raises(OperationalTimeError):
            owner.age_bounds(OperationalBracket(claimed, event.event_identity, 100, 200), current)
        assert owner.age_bounds(event, current).upper_ns == 300
    assert outcomes[0] == outcomes[1]
    for values in ([100, 100, 100, 100], [200, 400, 600, 800]):
        owner, _ = _clock(values)
        token, event = _event(owner)
        assert owner.age_bounds(event, owner.read_current(after=token)).lower_ns >= 0
        assert owner.domain.utc_accuracy is None and owner.domain.si_accuracy is None
        assert owner.domain.future_horizon == "UNKNOWN"


@pytest.mark.parametrize(
    "change",
    [
        {"boot_id": "other-boot"},
        {"pid": os.getpid() + 1},
        {"process_start_ticks": 2},
        {"thread_id": threading.get_ident() + 1},
        {"native_thread_id": threading.get_native_id() + 1},
        {"namespace_device": 2},
        {"namespace_inode": 3},
        {"namespace_offsets": (("monotonic", 0, 0), ("boottime", 1, 0))},
        {"namespace_offsets": (("monotonic", 0, 0),)},
    ],
)
def test_startup_binds_real_process_boot_and_time_namespace(change: dict[str, object]) -> None:
    owner, source = _clock([100, 200, 300, 400])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    original_identity = source.current_identity
    source.current_identity = replace(original_identity, **change)  # type: ignore[arg-type]
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)
    source.current_identity = original_identity
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)


@pytest.mark.parametrize("boundary", ["begin", "mark", "end", "current", "age", "deadline"])
def test_each_owner_boundary_revalidates_identity(boundary: str) -> None:
    owner, source = _clock([100, 200, 300, 400])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    original_identity = source.current_identity
    source.current_identity = replace(original_identity, namespace_inode=3)
    operations: dict[str, Callable[[], object]] = {
        "begin": lambda: owner.begin_event("acquisition"),
        "mark": lambda: owner.mark_event(token),
        "end": lambda: owner.end_event(token),
        "current": lambda: owner.read_current(after=token),
        "age": lambda: owner.age_bounds(event, current),
        "deadline": lambda: owner.start_deadline(task_key="attempt-1", origin=event, budget_ns=1),
    }
    with pytest.raises(OperationalTimeError):
        operations[boundary]()
    source.current_identity = original_identity
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)


@pytest.mark.parametrize("identity_read", [2, 3, 4])
def test_startup_checks_identity_before_and_after_first_read(identity_read: int) -> None:
    class DriftingSource(_RawSource):
        def __init__(self) -> None:
            super().__init__([])
            self.identity_reads = 0

        def identity(self) -> _StartupIdentity:
            self.identity_reads += 1
            if self.identity_reads >= identity_read:
                return replace(self.current_identity, process_start_ticks=2)
            return self.current_identity

    with pytest.raises(OperationalTimeError):
        _open_clock_for_test(DriftingSource())


def test_actual_other_thread_rejects_and_revokes_owner() -> None:
    owner, _ = _clock([100, 200])
    errors = []

    def other_thread() -> None:
        try:
            owner.begin_event("CPU-thread-probe")
        except OperationalTimeError as error:
            errors.append(error)

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join()
    assert len(errors) == 1
    with pytest.raises(OperationalTimeError):
        owner.begin_event("acquisition")


def test_identity_and_clock_failures_never_fallback() -> None:
    owner, source = _clock([100, 200, 300, 400])
    token, event = _event(owner)
    current = owner.read_current(after=token)
    source.identity_error = OSError("procfs unavailable")
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)
    source.identity_error = None
    with pytest.raises(OperationalTimeError):
        owner.age_bounds(event, current)
    broken_clock, _ = _clock([OSError("BOOTTIME unavailable")])
    with pytest.raises(OperationalTimeError):
        broken_clock.begin_event("acquisition")
    with pytest.raises(OperationalTimeError):
        broken_clock.begin_event("acquisition")
    decreasing, _ = _clock([100, 200, 300, 299])
    decreasing_token, _ = _event(decreasing)
    with pytest.raises(OperationalTimeError):
        decreasing.read_current(after=decreasing_token)


def test_proc_stat_parser_handles_spaces_and_right_parentheses_in_comm() -> None:
    pid = os.getpid()
    fields = ["S", *[str(field) for field in range(4, 53)]]
    fields[19] = "987654321"
    stat = f"{pid} (camera worker ) strange (name)) {' '.join(fields)}\n"
    assert _parse_process_start_ticks(stat, expected_pid=pid) == 987654321
    for malformed in (
        stat.replace(str(pid), str(pid + 1), 1),
        f"{pid} (comm) S 1",
        stat.replace("987654321", "-1"),
    ):
        with pytest.raises(OperationalTimeError):
            _parse_process_start_ticks(malformed, expected_pid=pid)


def test_time_namespace_offsets_require_both_exact_fields() -> None:
    assert _parse_namespace_offsets("boottime -1 2\nmonotonic 0 0\n") == (
        ("monotonic", 0, 0),
        ("boottime", -1, 2),
    )
    for malformed in (
        "monotonic 0 0\n",
        "monotonic 0 0\nboottime 0 1000000000\n",
        "monotonic 0 0\nboottime 0 0\nboottime 0 0\n",
        "monotonic 0 0\nboottime 0.0 0\n",
        "monotonic 0 0\nboottime 0 0\nother 0 0\n",
    ):
        with pytest.raises(OperationalTimeError):
            _parse_namespace_offsets(malformed)


@pytest.mark.parametrize("failure", ["boottime", "clock", "procfs", "namespace"])
def test_production_factory_rejects_missing_capabilities(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def unavailable(*args: object, **kwargs: object) -> object:
        raise OSError("required Linux capability unavailable")

    fallback_calls = []

    def forbidden_fallback(*args: object, **kwargs: object) -> object:
        fallback_calls.append((args, kwargs))
        return 0

    raw_time = SimpleNamespace(
        CLOCK_BOOTTIME=time.CLOCK_BOOTTIME,
        clock_gettime_ns=time.clock_gettime_ns,
        clock_getres=time.clock_getres,
    )
    for name in (
        "monotonic",
        "monotonic_ns",
        "perf_counter",
        "perf_counter_ns",
        "time",
        "time_ns",
        "process_time",
        "process_time_ns",
    ):
        setattr(raw_time, name, forbidden_fallback)
    monkeypatch.setattr(operational_time_v1, "time", raw_time)
    if failure == "boottime":
        del raw_time.CLOCK_BOOTTIME
    elif failure == "clock":
        raw_time.clock_gettime_ns = unavailable
    elif failure == "procfs":
        monkeypatch.setattr(operational_time_v1, "_read_proc_text", unavailable)
    else:
        monkeypatch.setattr(operational_time_v1, "_stat_time_namespace", unavailable)
    with pytest.raises(OperationalTimeError):
        open_operational_clock()
    assert not fallback_calls


def test_factory_has_no_caller_clock_or_source_flags() -> None:
    assert not inspect.signature(open_operational_clock).parameters
    for name in (
        "clock",
        "ns",
        "domain",
        "source",
        "pid",
        "source_flags",
        "ppm",
        "accuracy",
        "resolution",
        "_source",
    ):
        with pytest.raises(TypeError):
            open_operational_clock(**{name: 0})  # type: ignore[call-arg]
    owner, _ = _clock([100, 200])
    with pytest.raises(FrozenInstanceError):
        owner.domain.boot_id = "caller"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        owner.domain = replace(owner.domain, boot_id="caller")  # type: ignore[misc]


def test_real_linux_startup_factory_cpu_only(tmp_path: Path) -> None:
    artifact = tmp_path / "real-startup-cpu.json"
    before_imports = set(sys.modules)
    try:
        owner = open_operational_clock()
    except OperationalTimeError as error:
        artifact.write_text(
            json.dumps(
                {"status": "SUPPORT_UNAVAILABLE", "scope": "SOFTWARE_ONLY", "error": str(error)},
                indent=2,
            )
            + "\n"
        )
        pytest.fail(f"real Linux startup SUPPORT_UNAVAILABLE: {error}")
    token = owner.begin_event("CPU-capability-probe")
    owner.mark_event(token)
    event = owner.end_event(token)
    current = owner.read_current(after=token)
    age = owner.age_bounds(event, current)
    domain = owner.domain
    assert domain.scope == "SOFTWARE_ONLY"
    assert domain.api == "Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME)"
    assert domain.boot_id == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    assert domain.pid == os.getpid()
    assert domain.process_start_ticks == _parse_process_start_ticks(
        Path("/proc/self/stat").read_text(), expected_pid=os.getpid()
    )
    namespace = os.stat("/proc/thread-self/ns/time")
    assert (domain.namespace_device, domain.namespace_inode) == (namespace.st_dev, namespace.st_ino)
    assert domain.namespace_offsets == _parse_namespace_offsets(
        Path("/proc/self/timens_offsets").read_text()
    )
    assert domain.owner_thread_id == threading.get_ident()
    assert domain.owner_native_thread_id == threading.get_native_id()
    assert 0 <= age.lower_ns <= age.upper_ns
    assert domain.utc_accuracy is None and domain.si_accuracy is None
    assert (
        domain.native_authority
        == domain.worker_authority
        == domain.lease_authority
        == "UNAVAILABLE"
    )
    assert not any(
        ".simulation" in name or ".native_" in name or ".provider" in name
        for name in set(sys.modules) - before_imports
    )
    artifact.write_text(
        json.dumps(
            {
                "status": "PASS_REAL_LINUX_STARTUP_CPU_ONLY",
                "scope": "SOFTWARE_ONLY",
                "domain": asdict(domain),
                "event": {"lower_ns": event.lower_ns, "upper_ns": event.upper_ns},
                "current": {"lower_ns": current.lower_ns, "upper_ns": current.upper_ns},
                "age": asdict(age),
                "real_counter_reads": 5,
                "physics_provider_renderer_camera_decoder_hardware_actual": 0,
                "restart_suspend_hostpause": "NOT_TESTED_OC3_GATE",
                "formal_accepted": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    owner.close()
