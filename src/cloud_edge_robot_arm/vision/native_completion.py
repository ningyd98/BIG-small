"""Pure v2 completion diagnostics for the future independent original-data reader.

Point correspondence, complete geometry, source authenticity and horizon inclusion
are external proof obligations. Public numbers grant no native authority. The
completion quantity is an empirical terminal error, never continuous velocity or
a future wall-time bound; it does not populate the legacy e/v evidence fields.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

COMPLETION_SKILLS_V2 = (
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
)
COMPLETION_RECIPE_V2 = "FULL_HORIZON_JOINT_CONTACT_COMPLETION_V2"


def _finite_number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("built-in finite numeric coordinate required")
    try:
        number = float(cast(int | float, value))
    except (OverflowError, ValueError) as error:
        raise ValueError("coordinate outside finite numeric range") from error
    if not math.isfinite(number):
        raise ValueError("finite numeric coordinate required")
    return number


def _points(value: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("nonempty ordered point sequence required")
    result = []
    for point in value:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 3:
            raise ValueError("exactly three coordinates per point required")
        result.append(tuple(_finite_number(v) for v in point))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CompletionMetricV2:
    geometric_error_m: float
    point_u_m: tuple[float, ...]
    point_l_m: tuple[float, ...]
    point_m_m: tuple[float, ...]
    point_endpoint_error_m: tuple[float, ...]
    u_m: float
    l_m: float
    m_m: float
    completion_error_m: float
    endpoint_error_m: float
    schema_version: Literal["native.completion.metric.v2"] = field(
        default="native.completion.metric.v2", init=False
    )
    recipe_id: str = field(default=COMPLETION_RECIPE_V2, init=False)
    evidence_scope: Literal["SOFTWARE_ONLY"] = field(default="SOFTWARE_ONLY", init=False)
    native_authority: Literal["UNAVAILABLE"] = field(default="UNAVAILABLE", init=False)


def completion_metric_v2(
    *,
    geometric_error_m: float,
    command_points_m: Sequence[Sequence[float]],
    capture_reference_points_m: Sequence[Sequence[float]],
    terminal_reference_points_m: Sequence[Sequence[float]],
    actual_points_m: Sequence[Sequence[float]],
) -> CompletionMetricV2:
    """Compute max(G, max_i(U_i + L_i + M_i)) for corresponding 3D points.

    Multiple points may have different worst terms; summing separate maxima
    changes this registered metric. The caller must supply every required point.
    """
    geometry = _finite_number(geometric_error_m)
    if geometry < 0:
        raise ValueError("nonnegative geometric error required")
    command, capture, terminal, actual = (
        _points(points)
        for points in (
            command_points_m,
            capture_reference_points_m,
            terminal_reference_points_m,
            actual_points_m,
        )
    )
    if len({len(command), len(capture), len(terminal), len(actual)}) != 1:
        raise ValueError("complete corresponding point arrays required")
    u, tracking, motion, endpoint, completion = [], [], [], [], []
    for p, rc, rt, x in zip(command, capture, terminal, actual, strict=True):
        ui, li, mi, ei = math.dist(p, rc), math.dist(x, p), math.dist(rt, rc), math.dist(x, rt)
        ci = ui + li + mi
        if not all(math.isfinite(v) for v in (ui, li, mi, ei, ci)):
            raise ValueError("derived completion arithmetic overflow")
        u.append(ui)
        tracking.append(li)
        motion.append(mi)
        endpoint.append(ei)
        completion.append(ci)
    return CompletionMetricV2(
        geometry,
        tuple(u),
        tuple(tracking),
        tuple(motion),
        tuple(endpoint),
        max(u),
        max(tracking),
        max(motion),
        max(geometry, max(completion)),
        max(endpoint),
    )


@dataclass(frozen=True, slots=True)
class CompletionHorizonV2:
    physics_dt_ns: int
    base_steps: int
    builtin_tail_steps: int
    added_tail_steps: int
    registered_wait_steps: int
    total_steps: int
    total_sim_ns: int
    schema_version: Literal["native.completion.horizon.v2"] = field(
        default="native.completion.horizon.v2", init=False
    )
    evidence_scope: Literal["SOFTWARE_ONLY"] = field(default="SOFTWARE_ONLY", init=False)
    native_authority: Literal["UNAVAILABLE"] = field(default="UNAVAILABLE", init=False)


def completion_horizon_v2(
    skill: str,
    *,
    physics_dt_ns: int,
    original_timeout_ns: int,
    original_expected_ns: int,
    compiled_timeout_ns: int,
    compiled_expected_ns: int,
    effective_owner_required_ns: int,
    builtin_tail_included: bool = False,
    registered_wait_steps: int = 0,
) -> CompletionHorizonV2:
    """Describe integer S steps; this neither executes nor certifies a full horizon.

    An included tail is the caller's claim that the largest duration already
    covers it. The producer must prove that claim from the real action recipe.
    Wait steps here are exclusively additional waits, never already counted ones.
    """
    durations = (
        original_timeout_ns,
        original_expected_ns,
        compiled_timeout_ns,
        compiled_expected_ns,
        effective_owner_required_ns,
    )
    if type(skill) is not str or skill not in COMPLETION_SKILLS_V2:
        raise ValueError("registered completion skill required")
    if any(type(v) is not int or v <= 0 for v in (physics_dt_ns, *durations)):
        raise ValueError("positive exact integer nanoseconds required")
    if type(registered_wait_steps) is not int or registered_wait_steps < 0:
        raise ValueError("nonnegative exact integer additional wait steps required")
    if type(builtin_tail_included) is not bool:
        raise ValueError("explicit boolean tail inclusion required")
    base = (max(durations) + physics_dt_ns - 1) // physics_dt_ns
    tail_ns = {"LIFT": 500_000_000, "RELEASE": 1_000_000_000}.get(skill, 0)
    tail = (tail_ns + physics_dt_ns - 1) // physics_dt_ns
    if builtin_tail_included and (tail == 0 or base < tail):
        raise ValueError("base cannot describe an included complete registered tail")
    added = 0 if builtin_tail_included else tail
    total = base + added + registered_wait_steps
    return CompletionHorizonV2(
        physics_dt_ns, base, tail, added, registered_wait_steps, total, total * physics_dt_ns
    )
