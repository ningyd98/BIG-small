"""Pure, offline sampled point-motion calibration input from recorded raw-v3.

Matching supplied inventories does not authenticate measurements. A sampled
secant, even with recorded clock brackets, cannot bound continuous motion.
No risk fitting, IO, online truth input, native dispatch or source admission.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from typing import Any, ClassVar, Literal
from xml.etree import ElementTree

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    FrameAcquisitionV3,
    RawEpisodeEnvelopeV3,
    RawEpisodeRecordsV3,
    RawIntervalV3,
    TypedActionSpanV3,
    validate_raw_episode_v3,
)
from cloud_edge_robot_arm.research.risk_sources import RiskSourceRegistration
from cloud_edge_robot_arm.research.risk_supervision import _detached_criteria
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration
from cloud_edge_robot_arm.vision.risk.features import extract_risk_features

Point = tuple[float, float, float]


@dataclass(frozen=True)
class SampledPointSegment:
    """Offline endpoints and clock brackets, never a continuous velocity bound."""

    start_step: int
    end_step: int
    simulation_elapsed_s: float
    wall_elapsed_lower_s: float
    wall_elapsed_upper_s: float
    start_point_m: Point
    end_point_m: Point
    displacement_m: float
    secant_lower_m_s: float
    secant_upper_m_s: float


@dataclass(frozen=True)
class PointMotionResidualRow:
    span_id: str
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    reasons: tuple[str, ...]
    observation_id: str | None = None
    previous_observation_id: str | None = None
    start_step: int | None = None
    end_step: int | None = None
    command_seq_start: int | None = None
    command_seq_end: int | None = None
    original_expected_duration_s: float | None = None
    original_requirement_hash: str | None = None
    observed_motion_m_s: float | None = None
    sampled_max_secant_upper_m_s: float | None = None
    motion_residual_m_s: float | None = None
    segments: tuple[SampledPointSegment, ...] = ()
    geometry_scope: ClassVar[str] = "MARKER_CENTER_TRANSLATION"
    observed_scope: ClassVar[str] = "DEPTH_PIXEL_TEMPORAL_MAX"
    sampling_limit_clock: ClassVar[str] = "SIMULATION_TIME"
    horizon_scope: ClassVar[str] = "BEFORE_SUBMIT_TO_ACTUAL_ACTION_END"

    @property
    def sampled_segments(self) -> int:
        return len(self.segments)


@dataclass(frozen=True)
class PointMotionPreparation:
    raw_status: Literal["COMPLETE", "INCOMPLETE", "INVALID"]
    raw_reasons: tuple[str, ...]
    raw_source_digest: str
    source_kind: Literal["SOFTWARE_ONLY", "ONLINE_CED", "GROUND_TRUTH_TEACHER"]
    case_id: str
    marked_asset_sha256: str | None
    criteria: CompletionCriteria
    criteria_hash: str
    allocated_actions: int
    rows: tuple[PointMotionResidualRow, ...]
    scope: ClassVar[str] = "CALIBRATION_INPUT"
    continuous_motion: ClassVar[str] = "NOT_CERTIFIED"
    actual_source_status: ClassVar[str] = "UNKNOWN"

    @property
    def available_rows(self) -> int:
        return sum(row.status == "AVAILABLE" for row in self.rows)


def _vector(value: str) -> Point:
    result = tuple(float(item) for item in value.split())
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise ValueError("finite registered three-dimensional geometry required")
    return result[0], result[1], result[2]


def _registered_point(
    registration: RiskSourceRegistration,
    case_id: str,
    envelope: RawEpisodeEnvelopeV3,
    asset: bytes,
) -> tuple[Point, str]:
    matches = [case for case in registration.cases if case.case_id == case_id]
    if len(matches) != 1 or matches[0].marker_registration is None:
        raise ValueError("registered_marker_point_unavailable")
    marker = matches[0].marker_registration
    if type(marker) is not PoseMarkerRegistration:
        raise ValueError("concrete_pose_marker_registration_required")
    marker = replace(marker)
    asset_hash = marker.marked_asset_sha256
    paths = [
        path
        for path, digest in registration.current_source_hashes.items()
        if path.endswith(".xml") and digest == asset_hash
    ]
    if len(paths) != 1 or envelope.identity.asset_hash != asset_hash:
        raise ValueError("registered_marker_asset_mismatch")
    if type(asset) is not bytes or hashlib.sha256(asset).hexdigest() != asset_hash:
        raise ValueError("marked_asset_bytes_mismatch")
    body = ElementTree.fromstring(asset).find(".//body[@name='object']")
    if body is None or marker.marker_id != 7:
        raise ValueError("unsupported_registered_marker_geometry")
    shape = body.find("geom[@name='object_geom']")
    # Physics records express the point using object_geom's frame. Existing
    # registered assets place that frame at the object body's identity frame.
    orientation_keys = {"quat", "axisangle", "euler", "xyaxes", "zaxis", "fromto"}
    if (
        shape is None
        or shape.get("type") != "box"
        or _vector(shape.get("pos", "0 0 0")) != (0, 0, 0)
        or orientation_keys & shape.attrib.keys()
    ):
        raise ValueError("unsupported_registered_object_reference_frame")
    cells = [
        geom
        for geom in body.findall("geom")
        if re.fullmatch(
            r"pose_marker_(?:v1|color_v2)_r[0-5]c[0-5]",
            geom.get("name", ""),
        )
    ]
    names = {geom.attrib["name"] for geom in cells}
    if len(cells) != 36 or len(names) != 36:
        raise ValueError("registered_marker_cell_coverage_invalid")
    positions = [_vector(geom.attrib["pos"]) for geom in cells]
    sizes = [_vector(geom.attrib["size"]) for geom in cells]
    if any(
        geom.get("type") != "box"
        or bool(orientation_keys & geom.attrib.keys())
        or any(value <= 0 for value in size)
        or abs(size[0] * 12 - marker.marker_size_m) > 1e-9
        or abs(size[1] * 12 - marker.marker_size_m) > 1e-9
        or abs(position[2] - positions[0][2]) > 1e-9
        or abs(size[2] - sizes[0][2]) > 1e-9
        for geom, position, size in zip(cells, positions, sizes, strict=True)
    ):
        raise ValueError("registered_marker_plane_dimensions_invalid")
    return (
        sum(position[0] for position in positions) / 36,
        sum(position[1] for position in positions) / 36,
        positions[0][2] + sizes[0][2],
    ), asset_hash


def _point(snapshot: Mapping[str, Any], local: Point) -> Point:
    rotation = snapshot["object_geom_rotation_row_major"]
    origin = snapshot["object_geom_position_m"]
    rows = [rotation[index * 3 : (index + 1) * 3] for index in range(3)]
    if any(
        abs(sum(a * b for a, b in zip(rows[i], rows[j], strict=True)) - (i == j)) > 1e-6
        for i in range(3)
        for j in range(3)
    ):
        raise ValueError("recorded_point_rotation_invalid")
    determinant = (
        rotation[0] * (rotation[4] * rotation[8] - rotation[5] * rotation[7])
        - rotation[1] * (rotation[3] * rotation[8] - rotation[5] * rotation[6])
        + rotation[2] * (rotation[3] * rotation[7] - rotation[4] * rotation[6])
    )
    if abs(determinant - 1) > 1e-6:
        raise ValueError("recorded_point_rotation_invalid")
    result = tuple(origin[i] + sum(rows[i][j] * local[j] for j in range(3)) for i in range(3))
    if not all(math.isfinite(value) for value in result):
        raise ValueError("recorded_point_numeric_range_invalid")
    return result[0], result[1], result[2]


def _previous_online(
    before: FrameAcquisitionV3,
    records: RawEpisodeRecordsV3,
    intervals: Mapping[str, RawIntervalV3],
) -> FrameAcquisitionV3:
    start_ns = intervals[before.interval_id].start.mono_before_ns
    candidates = []
    for frame in records.frames:
        boundary = intervals[frame.interval_id].end
        if (
            frame.input_role == "ONLINE"
            and frame.acquisition_id != before.acquisition_id
            and boundary is not None
            and boundary.mono_after_ns <= start_ns
        ):
            candidates.append((boundary.mono_after_ns, frame))
    if not candidates:
        raise ValueError("previous_online_acquisition_unavailable")
    last_end = max(end for end, _ in candidates)
    closest = [frame for end, frame in candidates if end == last_end]
    if len(closest) != 1:
        raise ValueError("previous_online_acquisition_ambiguous")
    return closest[0]


def _retained_action(
    action: TypedActionSpanV3, intervals: Mapping[str, RawIntervalV3]
) -> PointMotionResidualRow:
    attempt = intervals.get(action.interval_id)
    requirement = action.original_plan.requirements[action.step_id]
    return PointMotionResidualRow(
        action.span_id, "UNAVAILABLE", (),
        start_step=attempt.start_step if attempt else None,
        end_step=attempt.end_step if attempt else None,
        command_seq_start=action.command_seq_start,
        command_seq_end=action.command_seq_end,
        original_expected_duration_s=requirement.expected_duration_s,
        original_requirement_hash=requirement.digest(),
    )


def _action_row(
    action: TypedActionSpanV3,
    envelope: RawEpisodeEnvelopeV3,
    records: RawEpisodeRecordsV3,
    criteria: CompletionCriteria,
    local: Point,
) -> PointMotionResidualRow:
    intervals = {interval.interval_id: interval for interval in records.intervals}
    attempt = intervals[action.interval_id]
    retained = _retained_action(action, intervals)
    try:
        if action.disposition != "RETURNED" or attempt.end_step == attempt.start_step:
            raise ValueError("executed_action_motion_unavailable")
        before_join = next(
            join
            for join in records.joins
            if join.span_id == action.span_id and join.relation == "BEFORE_SUBMIT"
        )
        before = next(
            frame for frame in records.frames if frame.acquisition_id == before_join.acquisition_id
        )
        previous = _previous_online(before, records, intervals)
        if before.observation_payload is None or previous.observation_payload is None:
            raise ValueError("original_online_observation_unavailable")
        observation = RGBDObservation.model_validate(dict(before.observation_payload))
        predecessor = RGBDObservation.model_validate(dict(previous.observation_payload))
        retained = replace(
            retained,
            observation_id=observation.observation_id,
            previous_observation_id=predecessor.observation_id,
        )
        # The calibration channel is intentionally absent. Only the existing
        # depth motion/pair validity observable is consumed; no risk estimate.
        features = extract_risk_features(observation, predecessor, ())
        if features.values["motion_pair_valid"].value != 1:
            raise ValueError("original_online_motion_pair_invalid")
        observed = features.values["observed_motion_m_s"].value
        raw_states = {item.physics_step: item.post_state_payload for item in records.physics}
        raw_states[0] = envelope.reset_state_payload
        physical = {item.physics_step: item for item in records.physics}
        assert attempt.end_step is not None
        previous_interval = intervals[before.interval_id]
        previous_point = _point(raw_states[attempt.start_step], local)
        segments = []
        for step in range(attempt.start_step + 1, attempt.end_step + 1):
            current = physical[step]
            interval = intervals[current.physics_interval_id]
            assert previous_interval.end is not None and interval.end is not None
            sim_elapsed = raw_states[step]["sim_time_s"] - raw_states[step - 1]["sim_time_s"]
            if sim_elapsed > criteria.max_sample_gap_s:
                raise ValueError("physics_sample_gap_exceeds_original_criterion")
            lower = (interval.start.mono_before_ns - previous_interval.end.mono_after_ns) / 1e9
            upper = (interval.end.mono_after_ns - previous_interval.start.mono_before_ns) / 1e9
            if not 0 < lower <= upper:
                raise ValueError("point_sampling_clock_bracket_unavailable")
            point = _point(raw_states[step], local)
            displacement = math.dist(previous_point, point)
            secant_lower, secant_upper = displacement / upper, displacement / lower
            if not all(
                math.isfinite(value) for value in (displacement, secant_lower, secant_upper)
            ):
                raise ValueError("point_sampling_numeric_range_invalid")
            segments.append(
                SampledPointSegment(
                    step - 1,
                    step,
                    sim_elapsed,
                    lower,
                    upper,
                    previous_point,
                    point,
                    displacement,
                    secant_lower,
                    secant_upper,
                )
            )
            previous_interval, previous_point = interval, point
        sampled = max(segment.secant_upper_m_s for segment in segments)
        return replace(
            retained,
            status="AVAILABLE",
            reasons=(),
            observed_motion_m_s=observed,
            sampled_max_secant_upper_m_s=sampled,
            motion_residual_m_s=max(0, sampled - observed),
            segments=tuple(segments),
        )
    except (ValueError, KeyError, TypeError, StopIteration) as error:
        return replace(retained, status="UNAVAILABLE", reasons=(str(error),))


def prepare_point_motion_residuals(
    registration: RiskSourceRegistration,
    case_id: str,
    envelope: RawEpisodeEnvelopeV3,
    records: RawEpisodeRecordsV3,
    *,
    marked_asset_xml: bytes,
) -> PointMotionPreparation:
    """Retain every allocated action and reconstruct only complete sampled inputs.

    Horizon endpoints come from original action/acquisition/command records.
    Simulation velocities are never mixed with the wall-time depth observable.
    Clock brackets use entire physical/acquisition intervals, not an assumed
    instant at a convenient clock reading. All coordinates stay offline.
    """
    if type(registration) is not RiskSourceRegistration:
        raise TypeError("concrete original risk source registration required")
    criteria = _detached_criteria(registration.criteria)
    for item in fields(criteria):
        if item.name in {"object_id", "target_region_id", "workspace_min_m", "workspace_max_m"}:
            continue
        value = getattr(criteria, item.name)
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError("strict finite criterion required")
    view = validate_raw_episode_v3(envelope, records)
    reasons = []
    local, asset_hash = None, None
    if view.status != "COMPLETE":
        reasons.append("raw_graph_not_complete")
    if view.utc_mapping != "BRACKETED":
        reasons.append("utc_monotonic_mapping_unavailable")
    if criteria.object_id != "object" or criteria.target_region_id != "target_region":
        reasons.append("criterion_reference_target_mismatch")
    try:
        local, asset_hash = _registered_point(registration, case_id, envelope, marked_asset_xml)
    except (ValueError, KeyError, ElementTree.ParseError) as error:
        reasons.append(str(error))
    actions = {action.span_id: action for action in records.actions}
    intervals = {interval.interval_id: interval for interval in records.intervals}
    rows = []
    for span_id in envelope.allocated_action_span_ids:
        action = actions.get(span_id)
        if reasons or action is None:
            row = (
                _retained_action(action, intervals)
                if action else PointMotionResidualRow(span_id, "UNAVAILABLE", ())
            )
            rows.append(replace(row, reasons=tuple(reasons or ["allocated_action_unavailable"])))
        else:
            assert local is not None
            rows.append(_action_row(action, envelope, records, criteria, local))
    return PointMotionPreparation(
        view.status,
        view.reasons,
        view.source_digest,
        envelope.identity.source_kind,
        case_id,
        asset_hash,
        criteria,
        content_digest(asdict(criteria)),
        len(envelope.allocated_action_span_ids),
        tuple(rows),
    )
