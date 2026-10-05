"""Offline, read-only physical outcome scoring for a single MuJoCo episode.

The controller must never receive these snapshots or this outcome as an input.
The episode owner samples once after reset and after every physics step; a
terminal skill return or one terminal object pose cannot prove stability.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict

from cloud_edge_robot_arm.simulation.mujoco.backend import (
    MuJoCoPhysicsBackend,
    PhysicsStepObservation,
)

_ALLOWED_CONTACT_PAIRS = frozenset([
    frozenset(("left_finger_geom", "object_geom")),
    frozenset(("right_finger_geom", "object_geom")),
    frozenset(("table", "object_geom")),
] + [
    frozenset(("table", f"dataset_distractor_{index}_geom")) for index in range(3)
])


@dataclass(frozen=True, slots=True)
class CompletionCriteria:
    object_id: str
    target_region_id: str
    lift_m: float = 0.05
    hold_s: float = 0.5
    placed_stable_s: float = 1.0
    max_sample_gap_s: float = 0.005
    max_stable_linear_speed_m_s: float = 0.02
    max_stable_angular_speed_rad_s: float = 0.5
    max_joint_velocity_rad_s: float = 3.0
    self_collision_penetration_tolerance_m: float = 0.001
    # TCP safety envelope around the robot base; the table footprint is not
    # the manipulator workspace. The reference arm's link/TCP reach is <0.9 m.
    workspace_xy_radius_m: float = 0.85
    workspace_min_m: tuple[float, float, float] = (-0.85, -0.85, 0.0)
    workspace_max_m: tuple[float, float, float] = (0.85, 0.85, 1.2)

    def __post_init__(self) -> None:
        if not self.object_id or not self.target_region_id:
            raise ValueError("object and target region IDs are required")
        positive = (
            self.lift_m, self.hold_s, self.placed_stable_s,
            self.max_sample_gap_s, self.max_stable_linear_speed_m_s,
            self.max_stable_angular_speed_rad_s, self.max_joint_velocity_rad_s,
            self.workspace_xy_radius_m,
        )
        if any(not math.isfinite(v) or v <= 0 for v in positive):
            raise ValueError("completion thresholds must be finite and positive")
        if (
            not math.isfinite(self.self_collision_penetration_tolerance_m)
            or self.self_collision_penetration_tolerance_m < 0
        ):
            raise ValueError("self-collision tolerance must be finite and nonnegative")
        if any(
            not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi
            for lo, hi in zip(self.workspace_min_m, self.workspace_max_m, strict=True)
        ):
            raise ValueError("workspace bounds must be finite and ordered")


@dataclass(frozen=True, slots=True)
class PhysicalSample:
    """Offline truth at one physics step, with immutable scalar values only."""

    episode_id: str
    physics_step: int
    sim_time_s: float
    object_position_m: tuple[float, float, float]
    object_bottom_z_m: float
    object_half_extent_xy_m: tuple[float, float]
    object_linear_speed_m_s: float
    object_angular_speed_rad_s: float
    region_center_xy_m: tuple[float, float]
    region_half_extent_xy_m: tuple[float, float]
    table_height_m: float
    gripper_open: bool
    left_finger_contact: bool
    right_finger_contact: bool
    contact_pairs: tuple[tuple[str, str], ...]
    joint_limit_violation: bool
    joint_velocity_violation: bool
    workspace_violation: bool
    self_collision_violation: bool = False
    self_collision_checked_pairs: tuple[tuple[str, str], ...] = ()
    self_collision_evidence_valid: bool = True


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    success: bool
    status: Literal["SUCCESS", "FAILED", "INCOMPLETE", "SAFETY_VIOLATION"]
    safety_violation: bool
    failure_reason: str | None
    measured_lift_m: float
    hold_s: float
    placed_stable_s: float
    elapsed_s: float
    safety_events: tuple[str, ...] = ()
    evidence_samples: int = 0
    self_collision_checked_pairs: tuple[tuple[str, str], ...] = ()
    safety_assessment: Literal["SCOPED_NO_VIOLATION", "PARTIAL", "VIOLATION"] = "PARTIAL"


class _OutcomeMeasurements(TypedDict):
    measured_lift_m: float
    hold_s: float
    placed_stable_s: float
    safety_events: tuple[str, ...]
    self_collision_checked_pairs: tuple[tuple[str, str], ...]
    safety_assessment: Literal["SCOPED_NO_VIOLATION", "PARTIAL", "VIOLATION"]


def sample_physical_state(
    backend: MuJoCoPhysicsBackend, criteria: CompletionCriteria
) -> PhysicalSample:
    """Read MuJoCo truth at the current step without changing physics state."""
    return sample_physical_observation(backend.current_physics_observation(), criteria)


def sample_physical_observation(
    snapshot: PhysicsStepObservation, criteria: CompletionCriteria
) -> PhysicalSample:
    """Convert a detached per-step truth snapshot into evaluator-only evidence."""
    if criteria.object_id != "object" or criteria.target_region_id != "target_region":
        raise ValueError("reference MuJoCo snapshot contains only object and target_region")
    rotation = snapshot.object_geom_rotation_row_major
    size = snapshot.object_half_extent_m
    half_x = sum(abs(rotation[j]) * size[j] for j in range(3))
    half_y = sum(abs(rotation[3 + j]) * size[j] for j in range(3))
    pairs = snapshot.contact_pairs
    left = any(set(pair) == {"left_finger_geom", "object_geom"} for pair in pairs)
    right = any(set(pair) == {"right_finger_geom", "object_geom"} for pair in pairs)
    hard_limit = any(
        not lo - 1e-4 <= position <= hi + 1e-4
        for position, (lo, hi) in zip(
            (*snapshot.joint_positions_rad, *snapshot.finger_positions_m),
            (*snapshot.joint_ranges_rad, *snapshot.finger_ranges_m),
            strict=True,
        )
    )
    velocity_limit = any(
        abs(velocity) > criteria.max_joint_velocity_rad_s
        for velocity in snapshot.joint_velocities_rad_s
    )
    workspace_violation = any(
        not lo <= value <= hi
        for value, lo, hi in zip(
            snapshot.tcp_position_m,
            criteria.workspace_min_m,
            criteria.workspace_max_m,
            strict=True,
        )
    ) or math.hypot(*snapshot.tcp_position_m[:2]) > criteria.workspace_xy_radius_m
    distances = snapshot.self_collision_distances_m
    distances_finite = all(math.isfinite(distance) for _, _, distance in distances)
    return PhysicalSample(
        episode_id=snapshot.episode_id,
        physics_step=snapshot.physics_step,
        sim_time_s=snapshot.sim_time_s,
        object_position_m=snapshot.object_position_m,
        object_bottom_z_m=snapshot.object_bottom_z_m,
        object_half_extent_xy_m=(half_x, half_y),
        object_linear_speed_m_s=_norm3(snapshot.object_linear_velocity_m_s),
        object_angular_speed_rad_s=_norm3(snapshot.object_angular_velocity_rad_s),
        region_center_xy_m=snapshot.region_center_m[:2],
        region_half_extent_xy_m=snapshot.region_half_extent_m[:2],
        table_height_m=snapshot.table_top_m,
        gripper_open=snapshot.gripper_open,
        left_finger_contact=left,
        right_finger_contact=right,
        contact_pairs=pairs,
        joint_limit_violation=hard_limit,
        joint_velocity_violation=velocity_limit,
        workspace_violation=workspace_violation,
        self_collision_violation=any(
            distance < -criteria.self_collision_penetration_tolerance_m
            for _, _, distance in distances
        ),
        self_collision_checked_pairs=tuple((a, b) for a, b, _ in distances),
        self_collision_evidence_valid=distances_finite,
    )


def evaluate_episode(
    backend: MuJoCoPhysicsBackend,
    criteria: CompletionCriteria,
    *,
    evidence: Sequence[PhysicalSample] | None = None,
    evaluation_start_step: int | None = None,
) -> EpisodeOutcome:
    """Score independent truth; settling remains in safety evidence, not lift baseline."""
    if evidence is None:
        return evaluate_evidence(
            (sample_physical_state(backend, criteria),), criteria,
            evaluation_start_step=evaluation_start_step,
        )
    if not evidence:
        return evaluate_evidence(
            evidence, criteria, evaluation_start_step=evaluation_start_step
        )
    if (
        evidence[-1].episode_id != backend._episode_id
        or evidence[-1].physics_step != backend.total_physics_steps
        or abs(evidence[-1].sim_time_s - backend.get_sim_time()) > 1e-6
    ):
        return _outcome("INCOMPLETE", "STALE_OR_FOREIGN_EVIDENCE", evidence)
    return evaluate_evidence(
        evidence, criteria, evaluation_start_step=evaluation_start_step
    )


def evaluate_evidence(
    evidence: Sequence[PhysicalSample],
    criteria: CompletionCriteria,
    *,
    evaluation_start_step: int | None = None,
) -> EpisodeOutcome:
    """Score a full episode without reading skill status or treating settling as lift."""
    if any(not _valid_sample(sample) for sample in evidence):
        return _outcome("INCOMPLETE", "INVALID_PHYSICAL_EVIDENCE", evidence)
    if not _continuous(evidence, criteria):
        return _outcome("INCOMPLETE", "NONCONTIGUOUS_EVIDENCE", evidence)

    baseline_index = 0
    if evaluation_start_step is not None:
        baseline_index = next(
            (index for index, sample in enumerate(evidence)
             if sample.physics_step == evaluation_start_step),
            -1,
        )
        if baseline_index < 0:
            return _outcome("INCOMPLETE", "MISSING_EVALUATION_START", evidence)

    safety = tuple(sorted({event for sample in evidence for event in _safety_events(sample)}))
    checked_pairs = tuple(sorted({
        pair for sample in evidence for pair in sample.self_collision_checked_pairs
    }))
    fully_scoped = bool(checked_pairs) and all(
        tuple(sorted(sample.self_collision_checked_pairs)) == checked_pairs
        for sample in evidence
    )
    safety_assessment: Literal["SCOPED_NO_VIOLATION", "PARTIAL", "VIOLATION"] = (
        "VIOLATION" if safety else "SCOPED_NO_VIOLATION" if fully_scoped else "PARTIAL"
    )
    baseline_z = evidence[baseline_index].object_position_m[2]
    measured_lift = max(
        0.0,
        max(s.object_position_m[2] - baseline_z for s in evidence[baseline_index:]),
    )
    hold_start: float | None = None
    placed_start: float | None = None
    longest_hold = 0.0
    longest_placed = 0.0
    hold_reached = False
    eps = 1e-12

    for sample in evidence[baseline_index:]:
        stable = (
            sample.object_linear_speed_m_s <= criteria.max_stable_linear_speed_m_s
            and sample.object_angular_speed_rad_s <= criteria.max_stable_angular_speed_rad_s
        )
        held = (
            sample.object_position_m[2] - baseline_z >= criteria.lift_m - eps
            and sample.left_finger_contact and sample.right_finger_contact
            and not sample.gripper_open and stable
        )
        if held:
            if hold_start is None:
                hold_start = sample.sim_time_s
            longest_hold = max(longest_hold, sample.sim_time_s - hold_start)
            if longest_hold >= criteria.hold_s - eps:
                hold_reached = True
        else:
            hold_start = None

        placed = (
            hold_reached and sample.gripper_open
            and not sample.left_finger_contact and not sample.right_finger_contact
            and stable and _inside_region(sample)
            and abs(sample.object_bottom_z_m - sample.table_height_m) <= 0.005
        )
        if placed:
            if placed_start is None:
                placed_start = sample.sim_time_s
            longest_placed = max(longest_placed, sample.sim_time_s - placed_start)
        else:
            placed_start = None

    values: _OutcomeMeasurements = dict(
        measured_lift_m=measured_lift,
        hold_s=longest_hold,
        placed_stable_s=longest_placed,
        safety_events=safety,
        self_collision_checked_pairs=checked_pairs,
        safety_assessment=safety_assessment,
    )
    if safety:
        return _outcome("SAFETY_VIOLATION", "PHYSICAL_SAFETY_VIOLATION", evidence, **values)
    if measured_lift < criteria.lift_m - eps:
        return _outcome("FAILED", "LIFT_BELOW_THRESHOLD", evidence, **values)
    if longest_hold < criteria.hold_s - eps:
        return _outcome("FAILED", "HOLD_TOO_SHORT", evidence, **values)
    if longest_placed < criteria.placed_stable_s - eps:
        return _outcome("FAILED", "PLACE_NOT_STABLE", evidence, **values)
    if (
        placed_start is None
        or evidence[-1].sim_time_s - placed_start < criteria.placed_stable_s - eps
    ):
        return _outcome("FAILED", "PLACEMENT_LOST", evidence, **values)
    return _outcome("SUCCESS", None, evidence, **values)


def _norm3(values: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in values))


def _valid_sample(sample: PhysicalSample) -> bool:
    values = (
        sample.sim_time_s,
        *sample.object_position_m,
        sample.object_bottom_z_m,
        *sample.object_half_extent_xy_m,
        sample.object_linear_speed_m_s,
        sample.object_angular_speed_rad_s,
        *sample.region_center_xy_m,
        *sample.region_half_extent_xy_m,
        sample.table_height_m,
    )
    return (
        type(sample.physics_step) is int
        and sample.self_collision_evidence_valid is True
        and all(math.isfinite(value) for value in values)
        and all(value > 0 for value in sample.object_half_extent_xy_m)
        and all(value > 0 for value in sample.region_half_extent_xy_m)
        and sample.object_linear_speed_m_s >= 0
        and sample.object_angular_speed_rad_s >= 0
    )


def _continuous(evidence: Sequence[PhysicalSample], criteria: CompletionCriteria) -> bool:
    if (
        len(evidence) < 2
        or evidence[0].physics_step < 0
        or not math.isfinite(evidence[0].sim_time_s)
        or evidence[0].sim_time_s < 0
    ):
        return False
    episode = evidence[0].episode_id
    if not episode:
        return False
    for previous, current in zip(evidence, evidence[1:], strict=False):
        dt = current.sim_time_s - previous.sim_time_s
        if (
            current.episode_id != episode
            or current.physics_step != previous.physics_step + 1
            or not math.isfinite(dt)
            or not 0 < dt <= criteria.max_sample_gap_s + 1e-9
        ):
            return False
    return True


def _inside_region(sample: PhysicalSample) -> bool:
    return all(
        abs(position - center) + extent <= region_extent + 1e-9
        for position, center, extent, region_extent in zip(
            sample.object_position_m[:2], sample.region_center_xy_m,
            sample.object_half_extent_xy_m, sample.region_half_extent_xy_m,
            strict=True,
        )
    )


def _safety_events(sample: PhysicalSample) -> set[str]:
    events: set[str] = set()
    # Static dataset distractors resting on the table are support contacts;
    # robot/distractor and target/distractor contact remain nonpermitted.
    if any(frozenset(pair) not in _ALLOWED_CONTACT_PAIRS for pair in sample.contact_pairs):
        events.add("NONPERMITTED_CONTACT")
    if sample.joint_limit_violation:
        events.add("HARD_JOINT_LIMIT")
    if sample.joint_velocity_violation:
        events.add("JOINT_VELOCITY_LIMIT")
    if sample.workspace_violation:
        events.add("WORKSPACE_BOUNDARY")
    if sample.self_collision_violation:
        events.add("SELF_COLLISION")
    return events


def _outcome(
    status: Literal["SUCCESS", "FAILED", "INCOMPLETE", "SAFETY_VIOLATION"],
    reason: str | None,
    evidence: Sequence[PhysicalSample],
    *,
    measured_lift_m: float = 0.0,
    hold_s: float = 0.0,
    placed_stable_s: float = 0.0,
    safety_events: tuple[str, ...] = (),
    self_collision_checked_pairs: tuple[tuple[str, str], ...] = (),
    safety_assessment: Literal["SCOPED_NO_VIOLATION", "PARTIAL", "VIOLATION"] = "PARTIAL",
) -> EpisodeOutcome:
    elapsed = evidence[-1].sim_time_s - evidence[0].sim_time_s if evidence else 0.0
    return EpisodeOutcome(
        success=status == "SUCCESS",
        status=status,
        safety_violation=bool(safety_events),
        failure_reason=reason,
        measured_lift_m=measured_lift_m,
        hold_s=hold_s,
        placed_stable_s=placed_stable_s,
        elapsed_s=elapsed,
        safety_events=safety_events,
        evidence_samples=len(evidence),
        self_collision_checked_pairs=self_collision_checked_pairs,
        safety_assessment=safety_assessment,
    )
