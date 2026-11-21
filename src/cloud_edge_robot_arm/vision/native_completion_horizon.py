"""Exact explicitly registered S-time recipes, without execution authority.

The rational is the declared mathematical time grid. Its nearest float must be
the actual configuration encoding; a float alone never implies a denominator.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction

from cloud_edge_robot_arm.vision.native_completion import COMPLETION_SKILLS_V2

RATIONAL_HORIZON_V2_SCHEMA = "native.completion.horizon.rational.v2"


def _builtin_tail_duration(skill: str) -> Fraction:
    return Fraction(1, 2) if skill == "LIFT" else Fraction(int(skill == "RELEASE"))


@dataclass(frozen=True, slots=True)
class RationalCompletionHorizonV1:
    skill: str
    dt_numerator: int
    dt_denominator: int
    registered_dt_hex: str
    registered_dt_ratio: tuple[int, int]
    original_timeout_ns: int
    original_expected_ns: int
    compiled_timeout_ns: int
    compiled_expected_ns: int
    effective_owner_required_ns: int
    builtin_tail_included: bool
    base_steps: int
    builtin_tail_steps: int
    added_tail_steps: int
    registered_wait_steps: int
    total_steps: int
    total_duration_numerator: int
    total_duration_denominator: int
    schema_version: str = field(default="native.completion.horizon.rational.v1", init=False)
    evidence_scope: str = field(default="SOFTWARE_ONLY", init=False)
    native_authority: str = field(default="UNAVAILABLE", init=False)
    qualification: str = field(default="UNKNOWN", init=False)


@dataclass(frozen=True, slots=True)
class RationalCompletionHorizonV2:
    """V2 adds physics-step timeout for simulation teacher while preserving wall-clock metrics."""
    skill: str
    dt_numerator: int
    dt_denominator: int
    registered_dt_hex: str
    registered_dt_ratio: tuple[int, int]
    original_timeout_ns: int
    original_expected_ns: int
    compiled_timeout_ns: int
    compiled_expected_ns: int
    effective_owner_required_ns: int
    builtin_tail_included: bool
    base_steps: int
    builtin_tail_steps: int
    added_tail_steps: int
    registered_wait_steps: int
    total_steps: int
    total_duration_numerator: int
    total_duration_denominator: int
    controller_deadline_steps: int
    terminal_steps: int
    timeout_basis: str = field(default="PHYSICS_STEPS", init=False)
    schema_version: str = field(default=RATIONAL_HORIZON_V2_SCHEMA, init=False)
    evidence_scope: str = field(default="SOFTWARE_ONLY", init=False)
    native_authority: str = field(default="UNAVAILABLE", init=False)
    qualification: str = field(default="UNKNOWN", init=False)


def completion_horizon_rational_v1(
    skill: str,
    *,
    dt_numerator: int,
    dt_denominator: int,
    registered_dt_s: float,
    original_timeout_ns: int,
    original_expected_ns: int,
    compiled_timeout_ns: int,
    compiled_expected_ns: int,
    effective_owner_required_ns: int,
    builtin_tail_included: bool = False,
    registered_wait_steps: int = 0,
) -> RationalCompletionHorizonV1:
    """Ceil each required duration exactly; never add an already included tail.

    Inclusion is a public arithmetic input, not proof of recorded tail execution.
    """
    durations = (
        original_timeout_ns,
        original_expected_ns,
        compiled_timeout_ns,
        compiled_expected_ns,
        effective_owner_required_ns,
    )
    if any(type(v) is not int or v <= 0 for v in (dt_numerator, dt_denominator, *durations)):
        raise ValueError("positive built-in integer durations and rational grid required")
    if type(registered_wait_steps) is not int or registered_wait_steps < 0:
        raise ValueError("nonnegative built-in integer wait steps required")
    if type(skill) is not str or skill not in COMPLETION_SKILLS_V2:
        raise ValueError("registered completion skill required")
    if type(builtin_tail_included) is not bool:
        raise ValueError("explicit boolean tail inclusion required")
    if (
        type(registered_dt_s) is not float
        or not math.isfinite(registered_dt_s)
        or registered_dt_s <= 0
    ):
        raise ValueError("actual finite positive float configuration required")
    dt = Fraction(dt_numerator, dt_denominator)
    try:
        encoding = float(dt)
    except OverflowError as error:
        raise ValueError("rational grid outside float configuration range") from error
    if encoding.hex() != registered_dt_s.hex():
        raise ValueError("explicit rational recipe differs from actual float configuration")
    base = math.ceil(Fraction(max(durations), 1_000_000_000) / dt)
    tail = math.ceil(_builtin_tail_duration(skill) / dt)
    if builtin_tail_included and (tail == 0 or base < tail):
        raise ValueError("included tail must exist and fit the original base horizon")
    added = 0 if builtin_tail_included else tail
    total = base + added + registered_wait_steps
    duration = total * dt
    return RationalCompletionHorizonV1(
        skill,
        dt.numerator,
        dt.denominator,
        registered_dt_s.hex(),
        registered_dt_s.as_integer_ratio(),
        *durations,
        builtin_tail_included,
        base,
        tail,
        added,
        registered_wait_steps,
        total,
        duration.numerator,
        duration.denominator,
    )


def completion_horizon_rational_v2(
    skill: str,
    *,
    dt_numerator: int,
    dt_denominator: int,
    registered_dt_s: float,
    original_timeout_ns: int,
    original_expected_ns: int,
    compiled_timeout_ns: int,
    compiled_expected_ns: int,
    effective_owner_required_ns: int,
    builtin_tail_included: bool = False,
    registered_wait_steps: int = 0,
) -> RationalCompletionHorizonV2:
    """Set a deadline for controller motion and an endpoint that includes the tail."""
    v1 = completion_horizon_rational_v1(
        skill,
        dt_numerator=dt_numerator,
        dt_denominator=dt_denominator,
        registered_dt_s=registered_dt_s,
        original_timeout_ns=original_timeout_ns,
        original_expected_ns=original_expected_ns,
        compiled_timeout_ns=compiled_timeout_ns,
        compiled_expected_ns=compiled_expected_ns,
        effective_owner_required_ns=effective_owner_required_ns,
        builtin_tail_included=builtin_tail_included,
        registered_wait_steps=registered_wait_steps,
    )
    dt = Fraction(dt_numerator, dt_denominator)
    controller_deadline_steps = math.ceil(Fraction(original_timeout_ns, 1_000_000_000) / dt)
    terminal_steps = v1.total_steps
    if skill in {"LIFT", "RELEASE"}:
        if controller_deadline_steps >= terminal_steps:
            raise ValueError(f"{skill}: controller deadline must precede terminal step")
    elif controller_deadline_steps != terminal_steps:
        raise ValueError(f"{skill}: controller deadline must equal terminal step")

    return RationalCompletionHorizonV2(
        v1.skill,
        v1.dt_numerator,
        v1.dt_denominator,
        v1.registered_dt_hex,
        v1.registered_dt_ratio,
        v1.original_timeout_ns,
        v1.original_expected_ns,
        v1.compiled_timeout_ns,
        v1.compiled_expected_ns,
        v1.effective_owner_required_ns,
        v1.builtin_tail_included,
        v1.base_steps,
        v1.builtin_tail_steps,
        v1.added_tail_steps,
        v1.registered_wait_steps,
        v1.total_steps,
        v1.total_duration_numerator,
        v1.total_duration_denominator,
        controller_deadline_steps,
        terminal_steps,
    )


def registered_teacher_horizon_v2(skill: str, timeout_ms: int) -> RationalCompletionHorizonV2:
    """Recompute the fixed v10 teacher horizon from the original action timeout."""
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise ValueError("registered teacher timeout must be a positive integer")
    dt = Fraction(1, 240)
    controller_steps = math.ceil(Fraction(timeout_ms, 1000) / dt)
    tail_steps = math.ceil(_builtin_tail_duration(skill) / dt)
    timeout_ns = timeout_ms * 1_000_000
    return completion_horizon_rational_v2(
        skill,
        dt_numerator=dt.numerator,
        dt_denominator=dt.denominator,
        registered_dt_s=float(dt),
        original_timeout_ns=timeout_ns,
        original_expected_ns=timeout_ns,
        compiled_timeout_ns=timeout_ns,
        compiled_expected_ns=timeout_ns,
        effective_owner_required_ns=(controller_steps + tail_steps) * 10**9 // dt.denominator,
        builtin_tail_included=tail_steps > 0,
    )


def controller_window_error_v2(
    horizon: RationalCompletionHorizonV2,
    elapsed_steps: int,
    details: Mapping[str, object],
) -> str | None:
    """Check the controller return window for an exact registered v10 recipe."""
    if type(elapsed_steps) is not int or elapsed_steps < 0:
        return "controller_physics_step_order_invalid"
    controller_steps = elapsed_steps
    if horizon.skill == "LIFT":
        reported_steps = details.get("physics_steps")
        hold_s = details.get("contact_hold_s")
        if (
            type(reported_steps) is not int
            or reported_steps != elapsed_steps
            or horizon.builtin_tail_steps != 120
            or elapsed_steps < horizon.builtin_tail_steps
            or type(hold_s) not in (int, float)
            or hold_s != horizon.builtin_tail_steps * float.fromhex(horizon.registered_dt_hex)
        ):
            return "controller_lift_hold_incomplete"
        # The registered lift controller measures its final contact hold after motion.
        controller_steps -= horizon.builtin_tail_steps
    if controller_steps > horizon.controller_deadline_steps:
        return "controller_exceeded_registered_deadline"
    if horizon.skill == "RELEASE" and (
        horizon.terminal_steps - elapsed_steps < horizon.builtin_tail_steps
    ):
        return "release_open_return_leaves_insufficient_tail"
    return None
