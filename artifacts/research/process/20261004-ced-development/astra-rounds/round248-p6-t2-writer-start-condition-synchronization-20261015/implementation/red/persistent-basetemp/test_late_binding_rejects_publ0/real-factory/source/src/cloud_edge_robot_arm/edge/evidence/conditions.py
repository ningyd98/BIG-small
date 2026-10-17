"""The single online condition entry point; physical oracle results are not inputs.

Visual facts are keyed by condition name. Each RGB-D estimate carries ``source``
(``rgbd_estimate``), ``observation_id``, ``target_id``, ``identity_confirmed``, a
boolean ``value`` and its supporting ``pixel``. Missing or mismatched provenance
is UNKNOWN. Robot-only checks consume the supplied proprioceptive RobotState;
object placement always needs a visual region estimate as well as release.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from math import dist, isfinite
from typing import Any, TypeGuard

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.vision.observations import RGBDObservation


class ConditionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConditionSpec:
    name: str
    target_id: str | None = None
    tolerances: Mapping[str, Any] = field(default_factory=dict)
    sensor_requirements: Sequence[str] = ("rgbd",)


@dataclass(frozen=True)
class OnlineEvidenceSnapshot:
    observation: RGBDObservation
    robot_state: RobotState
    visual_facts: Mapping[str, Any] = field(default_factory=dict)
    plan_version: int = 0
    command_seq: int = 0
    context_hash: str = ""
    operational_reference: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ConditionVerdict:
    status: ConditionStatus
    condition_name: str
    observation_id: str
    measured_values: Mapping[str, Any] = field(default_factory=dict)
    reasons: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ConditionStatus(self.status))


_VISUAL_CONDITIONS = frozenset(
    {
        "target_visible",
        "target_reachable",
        "tcp_above_target",
        "tcp_near_target",
        "tcp_above_region",
        "robot_clear_of_object",
        "robot_at_home",
        "object_inside_target_region",
        "object_grasped",
        "object_held",
        "object_attached",
        "object_lifted",
        "object_stable",
        "placement_stable",
        "object_placed",
    }
)
_ROBOT_CONDITIONS = frozenset(
    {
        "gripper_open",
        "gripper_closed",
        "gripper_released",
        "object_released",
        "robot_stopped",
        "robot_in_safe_pose",
        "tcp_above_safe_height",
        "gripper_holding",
        "tcp_at_resolved_target",
    }
)


def evaluate_conditions(
    conditions: Sequence[ConditionSpec],
    evidence: OnlineEvidenceSnapshot,
    *,
    now: datetime | None = None,
) -> list[ConditionVerdict]:
    """Evaluate without reading a simulator, evaluator, model or implicit truth store."""
    acquired_now = now if now is not None else datetime.now(UTC)
    if acquired_now.tzinfo is None or acquired_now.utcoffset() is None:
        return [
            ConditionVerdict(
                ConditionStatus.UNKNOWN,
                condition.name,
                evidence.observation.observation_id,
                reasons=("evaluation_timestamp_naive",),
            )
            for condition in conditions
        ]
    return [_evaluate(condition, evidence, acquired_now) for condition in conditions]


def _evaluate(
    condition: ConditionSpec,
    evidence: OnlineEvidenceSnapshot,
    now: datetime,
) -> ConditionVerdict:
    observation = evidence.observation
    observation_id = getattr(observation, "observation_id", "")

    def unknown(reason: str) -> ConditionVerdict:
        return ConditionVerdict(
            ConditionStatus.UNKNOWN, condition.name, observation_id, reasons=(reason,)
        )

    timestamp = getattr(observation, "captured_at", None)
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return unknown("acquisition_timestamp_missing_or_naive")
    max_age = condition.tolerances.get("max_age_s", 5.0)
    if not _number(max_age) or max_age <= 0:
        return unknown("invalid_max_age_s")
    local = _operational_freshness(evidence, max_age)
    if local is False:
        return unknown("operational_observation_unavailable_or_stale")
    if local is None:
        age = (now - timestamp).total_seconds()
        if age < 0 or age > max_age:
            return unknown("observation_future_or_stale")
    calibration = condition.tolerances.get("calibration_version")
    if calibration is not None and calibration != observation.calibration_version:
        return unknown("calibration_version_mismatch")
    if any(
        sensor not in {"rgbd", "rgb", "depth", "robot_state"}
        for sensor in condition.sensor_requirements
    ):
        return unknown("unsupported_sensor_requirement")
    if set(condition.sensor_requirements) & {"rgbd", "depth"}:
        try:
            if not any(value > 0 and isfinite(value) for value in observation.depth_values()):
                return unknown("depth_unavailable")
        except (ValueError, TypeError, AttributeError):
            return unknown("depth_unavailable")

    if condition.name.startswith("skill_") and condition.name.endswith("_completed"):
        effect = condition.tolerances.get("effect_condition")
        if not isinstance(effect, str) or effect not in _VISUAL_CONDITIONS:
            return unknown("skill_marker_requires_visual_effect")
        checked = _evaluate(replace(condition, name=effect), evidence, now)
        return replace(checked, condition_name=condition.name)
    if condition.name == "object_placed":
        placed = _evaluate(replace(condition, name="object_inside_target_region"), evidence, now)
        released = _evaluate(replace(condition, name="gripper_released"), evidence, now)
        # Incomplete visual evidence must not become a positive placement from release.
        status = (
            ConditionStatus.UNKNOWN
            if ConditionStatus.UNKNOWN in (placed.status, released.status)
            else ConditionStatus.PASS
            if placed.status == released.status == ConditionStatus.PASS
            else ConditionStatus.FAIL
        )
        return ConditionVerdict(
            status,
            condition.name,
            observation_id,
            {"in_region": placed.status.value, "released": released.status.value},
            (*placed.reasons, *released.reasons),
        )
    if condition.name == "object_held" and condition.tolerances.get("holding_feedback_required"):
        visual = _visual_verdict(condition, evidence)
        holding = _evaluate(replace(condition, name="gripper_holding"), evidence, now)
        status = (
            ConditionStatus.UNKNOWN
            if ConditionStatus.UNKNOWN in (visual.status, holding.status)
            else ConditionStatus.PASS
            if visual.status == holding.status == ConditionStatus.PASS
            else ConditionStatus.FAIL
        )
        return ConditionVerdict(
            status,
            condition.name,
            observation_id,
            {"visual": visual.status.value, "holding": holding.status.value},
            (*visual.reasons, *holding.reasons),
        )
    if condition.name in _VISUAL_CONDITIONS:
        return _visual_verdict(condition, evidence)
    if condition.name not in _ROBOT_CONDITIONS:
        return unknown("condition_not_registered")
    state = evidence.robot_state
    if not isinstance(state, RobotState) or not state.connected:
        return unknown("robot_state_unavailable")
    measurements: dict[str, Any] = {}
    if condition.name == "gripper_open":
        passed = state.gripper_open
    elif condition.name == "gripper_closed":
        passed = not state.gripper_open
    elif condition.name in {"gripper_released", "object_released"}:
        passed = state.gripper_open and state.holding_object_id is None
    elif condition.name == "gripper_holding":
        if not condition.target_id:
            return unknown("target_identity_missing")
        passed = not state.gripper_open and state.holding_object_id == condition.target_id
        measurements = {
            "holding_object_id": state.holding_object_id,
            "gripper_open": state.gripper_open,
        }
    elif condition.name == "tcp_at_resolved_target":
        raw_coordinates = [condition.tolerances.get(f"target_{axis}") for axis in "xyz"]
        coordinates = [float(value) for value in raw_coordinates if _number(value)]
        tolerance = condition.tolerances.get("max_distance_m", 0.015)
        if len(coordinates) != 3 or not _number(tolerance):
            return unknown("resolved_target_or_distance_missing")
        if tolerance <= 0:
            return unknown("invalid_distance_tolerance")
        residual = dist((state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z), coordinates)
        passed = residual <= tolerance
        measurements = {"tcp_distance_m": residual, "max_distance_m": tolerance}
    elif condition.name == "robot_stopped":
        passed = state.stopped or state.estop_engaged
    else:
        minimum = condition.tolerances.get("minimum_safe_height")
        if not _number(minimum) or minimum < 0:
            return unknown("minimum_safe_height_missing")
        passed = (
            state.tcp_pose.z >= minimum and not state.collision_detected and not state.estop_engaged
        )
        measurements = {"tcp_height_m": state.tcp_pose.z, "minimum_safe_height": minimum}
    if state.collision_detected or state.estop_engaged:
        measurements["hard_safety_fault"] = True
        passed = False
    return ConditionVerdict(
        ConditionStatus.PASS if passed else ConditionStatus.FAIL,
        condition.name,
        observation_id,
        measurements,
        ("robot_state_condition_satisfied" if passed else "robot_state_condition_failed",),
    )


def _visual_verdict(
    condition: ConditionSpec,
    evidence: OnlineEvidenceSnapshot,
) -> ConditionVerdict:
    observation = evidence.observation
    fact = evidence.visual_facts.get(condition.name)

    def unknown(reason: str) -> ConditionVerdict:
        return ConditionVerdict(
            ConditionStatus.UNKNOWN, condition.name, observation.observation_id, reasons=(reason,)
        )

    if not isinstance(fact, Mapping) or fact.get("source") != "rgbd_estimate":
        return unknown("visual_fact_missing_or_untrusted_source")
    if fact.get("observation_id") != observation.observation_id:
        return unknown("visual_fact_observation_mismatch")
    if (
        not condition.target_id
        or fact.get("target_id") != condition.target_id
        or fact.get("identity_confirmed") is not True
    ):
        return unknown("target_identity_uncertain")
    pixel = fact.get("pixel")
    if (
        not isinstance(pixel, (tuple, list))
        or len(pixel) != 2
        or any(type(component) is not int for component in pixel)
    ):
        return unknown("target_depth_pixel_missing")
    try:
        point = observation.world_point((pixel[0], pixel[1]))
    except (ValueError, TypeError, AttributeError):
        return unknown("target_depth_invalid")
    value = fact.get("value")
    if type(value) is not bool:
        return unknown("visual_fact_not_boolean")
    measurements: dict[str, Any] = {
        "source": "rgbd_estimate",
        "pixel": list(pixel),
        "world_point": point.model_dump(),
        "value": value,
    }
    supplied = fact.get("measured_values")
    if isinstance(supplied, Mapping):
        # Only attributed numeric residuals may be used by the progress tracker.
        residual = supplied.get("residual_m")
        if _number(residual) and residual >= 0:
            measurements["residual_m"] = residual
    return ConditionVerdict(
        ConditionStatus.PASS if value else ConditionStatus.FAIL,
        condition.name,
        observation.observation_id,
        measurements,
        ("visual_condition_satisfied" if value else "visual_condition_failed",),
    )


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _operational_freshness(evidence: OnlineEvidenceSnapshot, max_age: object) -> bool | None:
    if evidence.operational_reference is None:
        return None
    from cloud_edge_robot_arm.vision.operational_windows import _check_observation

    return _check_observation(
        evidence.observation, "condition", max_age_s=max_age,
        reference=dict(evidence.operational_reference),
    )
