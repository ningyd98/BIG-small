"""Pure all-action v2 calibration reduction, not a raw reader or certificate.

Assignments, scores, ancestry and fingerprints are public descriptions. A future
original-data reader must prove them, including complete control points, samples,
source authenticity, exact execution horizon and exchangeability. Finite output
does not grant execution authority. None denotes a positive-infinity score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from cloud_edge_robot_arm.research.native_geometry_calibration import independent_components
from cloud_edge_robot_arm.vision.native_completion import COMPLETION_SKILLS_V2


@dataclass(frozen=True, slots=True)
class CompletionActionAssignmentV2:
    skill: str
    full_horizon_steps: int
    sample_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompletionGroupAssignmentV2:
    group_id: str
    ancestor_ids: tuple[str, ...]
    fingerprints: tuple[str, ...]
    actions: tuple[CompletionActionAssignmentV2, ...]


@dataclass(frozen=True, slots=True)
class CompletionActionDiagnosticsV2:
    skill: str
    outcome: str
    capture_step: int
    dispatch_step: int
    terminal_step: int
    samples: tuple[tuple[str, float | None], ...]


@dataclass(frozen=True, slots=True)
class CompletionCalibrationDiagnosticsV2:
    assigned_group_count: int
    component_count: int
    rank: int
    joint_bound_m: float | None
    group_scores: tuple[tuple[str, float | None], ...]
    components: tuple[tuple[str, ...], ...]
    component_scores: tuple[float | None, ...]
    unavailable_group_ids: tuple[str, ...]
    group_reasons: tuple[tuple[str, tuple[str, ...]], ...]
    schema_version: Literal["native.completion.calibration.diagnostics.v2"] = field(
        default="native.completion.calibration.diagnostics.v2", init=False
    )
    evidence_scope: Literal["SOFTWARE_ONLY"] = field(default="SOFTWARE_ONLY", init=False)
    native_authority: Literal["UNAVAILABLE"] = field(default="UNAVAILABLE", init=False)


def _identifier(value: object) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("nonblank string identity required")


def _identifiers(values: tuple[str, ...]) -> None:
    if type(values) is not tuple or not values:
        raise ValueError("nonempty immutable identity inventory required")
    for value in values:
        _identifier(value)
    if len(values) != len(set(values)):
        raise ValueError("duplicate assigned identity")


def _sequence(value: object) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("ordered record sequence required")


def _step(value: object, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("exact nonnegative integer step required")


def _score(value: float | None) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError("strict nonnegative numeric score required")
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError("score conversion overflow") from error
    if math.isnan(number) or number < 0:
        raise ValueError("nonnegative finite score or explicit unavailability required")
    return None if number == math.inf else number


def _assignments(
    assignments: Sequence[CompletionGroupAssignmentV2],
) -> dict[str, CompletionGroupAssignmentV2]:
    _sequence(assignments)
    if not assignments:
        raise ValueError("complete nonempty assigned inventory required")
    result = {}
    for group in assignments:
        if type(group) is not CompletionGroupAssignmentV2:
            raise ValueError("exact group assignment record required")
        _identifier(group.group_id)
        if group.group_id in result:
            raise ValueError("duplicate assigned group")
        _identifiers(group.ancestor_ids)
        _identifiers(group.fingerprints)
        if type(group.actions) is not tuple:
            raise ValueError("immutable assigned action inventory required")
        skills = []
        for action in group.actions:
            if type(action) is not CompletionActionAssignmentV2:
                raise ValueError("exact action assignment record required")
            _identifier(action.skill)
            _step(action.full_horizon_steps, minimum=1)
            _identifiers(action.sample_ids)
            skills.append(action.skill)
        if len(skills) != 8 or set(skills) != set(COMPLETION_SKILLS_V2):
            raise ValueError("all eight completion actions must be assigned exactly once")
        result[group.group_id] = group
    return result


def _observations(
    groups: Mapping[str, CompletionGroupAssignmentV2],
    observations: Mapping[str, Sequence[CompletionActionDiagnosticsV2]],
) -> dict[str, dict[str, tuple[CompletionActionDiagnosticsV2, dict[str, float | None]]]]:
    if not isinstance(observations, Mapping):
        raise ValueError("group-indexed observations required")
    result = {}
    for group_id, rows in observations.items():
        _identifier(group_id)
        if group_id not in groups:
            raise ValueError("foreign observed group")
        _sequence(rows)
        assigned = {action.skill: action for action in groups[group_id].actions}
        actions = {}
        for row in rows:
            if type(row) is not CompletionActionDiagnosticsV2:
                raise ValueError("exact action diagnostics record required")
            _identifier(row.skill)
            if row.skill not in assigned or row.skill in actions:
                raise ValueError("foreign or duplicate observed action")
            if type(row.outcome) is not str or row.outcome not in (
                "COMPLETE",
                "FAILED",
                "UNKNOWN",
                "INCOMPLETE",
            ):
                raise ValueError("explicit diagnostic action outcome required")
            for step in (row.capture_step, row.dispatch_step, row.terminal_step):
                _step(step)
            if type(row.samples) is not tuple:
                raise ValueError("immutable sample diagnostics required")
            samples = {}
            for sample in row.samples:
                if type(sample) is not tuple or len(sample) != 2:
                    raise ValueError("exact sample identity and score pair required")
                sample_id, score = sample
                _identifier(sample_id)
                if sample_id not in assigned[row.skill].sample_ids or sample_id in samples:
                    raise ValueError("foreign or duplicate observed sample")
                # Validate even FAILED rows; outcome must not hide malformed evidence.
                samples[sample_id] = _score(score)
            actions[row.skill] = (row, samples)
        result[group_id] = actions
    return result


def joint_completion_calibration_v2(
    assignments: Sequence[CompletionGroupAssignmentV2],
    observations: Mapping[str, Sequence[CompletionActionDiagnosticsV2]],
) -> CompletionCalibrationDiagnosticsV2:
    """Reduce complete all-action maxima and exact 9/10 component rank.

    Missing groups still join the dependency graph. Infinity propagates within a
    component, then participates in the fixed rank with every assigned component.
    """
    groups = _assignments(assignments)
    observed = _observations(groups, observations)
    scores: dict[str, float | None] = {}
    reasons_by_group = {}
    for group_id in sorted(groups):
        group = groups[group_id]
        reasons = set()
        finite = []
        if group_id not in observed:
            reasons.add("missing_group")
        rows = observed.get(group_id, {})
        for action in group.actions:
            if action.skill not in rows:
                reasons.add(f"missing_action:{action.skill}")
                continue
            row, samples = rows[action.skill]
            if row.outcome != "COMPLETE":
                reasons.add(f"outcome:{action.skill}:{row.outcome}")
            if row.capture_step != row.dispatch_step:
                reasons.add(f"capture_dispatch_mismatch:{action.skill}")
            if row.terminal_step != row.dispatch_step + action.full_horizon_steps:
                reasons.add(f"terminal_horizon_mismatch:{action.skill}")
            for sample_id in action.sample_ids:
                if sample_id not in samples:
                    reasons.add(f"missing_sample:{action.skill}:{sample_id}")
                elif samples[sample_id] is None:
                    reasons.add(f"unavailable_sample:{action.skill}:{sample_id}")
                else:
                    finite.append(samples[sample_id])
        scores[group_id] = None if reasons else max(v for v in finite if v is not None)
        reasons_by_group[group_id] = tuple(sorted(reasons))
    components = independent_components(
        [
            {"group_id": g.group_id, "ancestor_ids": g.ancestor_ids, "fingerprints": g.fingerprints}
            for g in groups.values()
        ]
    )
    component_scores = tuple(
        None
        if any(scores[key] is None for key in component)
        else max(v for key in component if (v := scores[key]) is not None)
        for component in components
    )
    n = len(components)
    rank = (9 * (n + 1) + 9) // 10
    ordered = sorted(math.inf if value is None else value for value in component_scores)
    selected = ordered[rank - 1] if n >= 9 and rank <= n else math.inf
    return CompletionCalibrationDiagnosticsV2(
        len(groups),
        n,
        rank,
        selected if math.isfinite(selected) else None,
        tuple(sorted(scores.items())),
        components,
        component_scores,
        tuple(key for key, score in sorted(scores.items()) if score is None),
        tuple(sorted(reasons_by_group.items())),
    )
