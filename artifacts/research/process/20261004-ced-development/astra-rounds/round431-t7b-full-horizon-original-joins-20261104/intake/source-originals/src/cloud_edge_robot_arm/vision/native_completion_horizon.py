"""Exact explicitly registered S-time recipes, without execution authority.

The rational is the declared mathematical time grid. Its nearest float must be
the actual configuration encoding; a float alone never implies a denominator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from cloud_edge_robot_arm.vision.native_completion import COMPLETION_SKILLS_V2


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
    tail_duration = Fraction(1, 2) if skill == "LIFT" else Fraction(int(skill == "RELEASE"))
    tail = math.ceil(tail_duration / dt)
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
