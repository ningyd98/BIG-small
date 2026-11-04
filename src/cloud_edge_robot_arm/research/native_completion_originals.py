"""Offline original-byte observed-return diagnostics, without full-H qualification.

The legacy registry is used as a checked file inventory, not converted into an
operational calibration. An actual return can precede the required nominal
horizon. None of these public records supplies live provenance or native admission.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cloud_edge_robot_arm.contracts import Pose, RobotState
from cloud_edge_robot_arm.contracts.models import ExecutionCheckpoint
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research.native_geometry_calibration import (
    full_rigid_geometry_errors,
    original_rgbd_fingerprint,
    original_source_reasons,
    rebuild_owner_binding,
    reconstruct_truth_endpoint,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    RawEpisodeEnvelopeV3,
    RawEpisodeRecordsV3,
    TypedActionSpanV3,
    _digest,
    validate_raw_episode_v3,
)
from cloud_edge_robot_arm.vision.native_calibration import (
    NativeCalibrationRegistration,
    NativeGeometryRegistration,
    _hash,
    _json,
    _load,
    _rigid,
    _safe,
)
from cloud_edge_robot_arm.vision.native_completion import CompletionMetricV2, completion_metric_v2
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import DeterministicGroundingPolicy
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker

Points = tuple[tuple[float, ...], ...]
_QUALIFICATION_REASONS = (
    "same_session_operational_provenance_unavailable",
    "registered_full_horizon_and_hold_evidence_unavailable",
    "observed_return_is_not_qualified_completion",
)


@dataclass(frozen=True, slots=True)
class _DiagnosticScope:
    evidence_scope: str = field(default="SOFTWARE_ONLY", init=False)
    native_authority: str = field(default="UNAVAILABLE", init=False)
    qualification: str = field(default="UNKNOWN", init=False)


@dataclass(frozen=True, slots=True)
class OriginalCompletionFrameV2:
    acquisition_id: str
    status: str
    geometric_error_m: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedCompletionActionV2(_DiagnosticScope):
    span_id: str
    skill: str | None
    disposition: str | None
    returned_success: bool | None
    capture_step: int | None
    dispatch_step: int | None
    return_step: int | None
    observed_steps: int | None
    command_points_m: Points | None
    capture_reference_points_m: Points | None
    return_reference_points_m: Points | None
    actual_points_m: Points | None
    observed_endpoint_metric: CompletionMetricV2 | None
    reasons: tuple[str, ...]
    qualified_completion_metric: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class ObservedCompletionGroupV2(_DiagnosticScope):
    group_id: str
    ancestor_ids: tuple[str, ...]
    physics_dt_s: float
    raw_status: str
    raw_reasons: tuple[str, ...]
    utc_mapping: str
    allocated_action_span_ids: tuple[str, ...]
    allocated_acquisition_ids: tuple[str, ...]
    frames: tuple[OriginalCompletionFrameV2, ...]
    actions: tuple[ObservedCompletionActionV2, ...]
    geometric_error_m: float | None
    fingerprints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedCompletionReconstructionV2(_DiagnosticScope):
    groups: tuple[ObservedCompletionGroupV2, ...]
    schema_version: str = field(default="native.completion.observed-originals.v2", init=False)


@dataclass(frozen=True)
class _DecodedFrame:
    observation: RGBDObservation
    state: Mapping[str, Any]
    grasp_tcp: tuple[float, ...]


def _decode_frames(
    envelope: RawEpisodeEnvelopeV3,
    records: RawEpisodeRecordsV3,
    scope: NativeGeometryRegistration,
) -> tuple[tuple[OriginalCompletionFrameV2, ...], dict[str, _DecodedFrame], tuple[str, ...]]:
    geometry = scope.to_payload()
    states = {
        _digest(state): state
        for state in (
            envelope.reset_state_payload,
            *(row.post_state_payload for row in records.physics),
        )
    }
    frames = {row.acquisition_id: row for row in records.frames}
    results = []
    decoded = {}
    fingerprints = [
        "episode:" + envelope.identity.episode_id,
        "scene:" + envelope.identity.scene_hash,
    ]
    for acquisition_id in envelope.allocated_acquisition_ids:
        frame = frames.get(acquisition_id)
        error = None
        reasons = []
        if frame is None:
            reasons.append("allocated_frame_missing")
        elif frame.observation_payload is None:
            reasons.append("original_observation_unavailable")
        else:
            observation = RGBDObservation.model_validate_json(_json(frame.observation_payload))
            fingerprints.append(original_rgbd_fingerprint(frame.observation_payload))
            state = states.get(frame.joined_physics_observation_hash or "")
            if state is None:
                reasons.append("exact_frame_physics_join_unavailable")
            elif (
                {key: observation.model_dump(mode="json")[key] for key in geometry["camera"]}
                != geometry["camera"]
                or not math.isclose(
                    observation.sim_time_s, state["sim_time_s"], abs_tol=1e-9, rel_tol=0
                )
                or list(state["object_half_extent_m"]) != geometry["object_half_extent_m"]
            ):
                reasons.append("registered_frame_geometry_or_time_mismatch")
            else:
                estimate = detect_pose_marker(observation, scope.pose_marker)
                if (
                    estimate.status != "OBSERVED"
                    or estimate.rotation_marker_to_world is None
                    or estimate.marker_center_world_m is None
                ):
                    reasons.append("marker_unknown:" + estimate.reason)
                else:
                    transform = _rigid(geometry["marker_to_object"])
                    rotation = (
                        np.array(estimate.rotation_marker_to_world).reshape(3, 3)
                        @ transform[:3, :3].T
                    )
                    center = np.array(estimate.marker_center_world_m) - rotation @ transform[:3, 3]
                    try:
                        errors = full_rigid_geometry_errors(
                            scope,
                            center.tolist(),
                            rotation.ravel().tolist(),
                            state["object_geom_position_m"],
                            state["object_geom_rotation_row_major"],
                        )
                        grasp = center + rotation @ _rigid(geometry["object_to_tcp"])[:3, 3]
                        if (
                            not math.isfinite(errors.joint_geometry_error_m)
                            or not np.isfinite(grasp).all()
                        ):
                            raise ValueError("nonfinite reconstructed geometry")
                        error = errors.joint_geometry_error_m
                        decoded[acquisition_id] = _DecodedFrame(
                            observation, state, tuple(float(value) for value in grasp)
                        )
                    except ValueError as exc:
                        reasons.append("original_geometry_invalid:" + str(exc))
        results.append(
            OriginalCompletionFrameV2(
                acquisition_id,
                "OBSERVED" if error is not None else "UNKNOWN",
                error,
                tuple(reasons),
            )
        )
    return tuple(results), decoded, tuple(fingerprints)


def _observed_action(
    span_id: str,
    action: TypedActionSpanV3 | None,
    records: RawEpisodeRecordsV3,
    decoded: Mapping[str, _DecodedFrame],
    geometry_error: float | None,
    scope: NativeGeometryRegistration,
    registration: NativeCalibrationRegistration,
    group: Mapping[str, Any],
    unavailable_reasons: tuple[str, ...],
) -> ObservedCompletionActionV2:
    reasons = [*unavailable_reasons]
    skill = (
        action.original_plan.requirements[action.step_id].original_step.skill.value
        if action
        else None
    )
    intervals = {row.interval_id: row for row in records.intervals}
    interval = intervals.get(action.interval_id) if action else None
    dispatch = interval.start_step if interval else None
    returned = interval.end_step if interval else None
    observed = returned - dispatch if returned is not None and dispatch is not None else None
    success = action.returned_result["success"] if action and action.returned_result else None
    before = [
        join
        for join in records.joins
        if join.span_id == span_id and join.relation == "BEFORE_SUBMIT"
    ]
    after = [
        join
        for join in records.joins
        if join.span_id == span_id and join.relation == "AFTER_RETURN"
    ]
    capture = decoded.get(before[0].acquisition_id) if len(before) == 1 else None
    terminal = decoded.get(after[0].acquisition_id) if len(after) == 1 else None
    capture_step = capture.state["physics_step"] if capture else None
    command: Points | None = None
    capture_reference: Points | None = None
    return_reference: Points | None = None
    actual: Points | None = None
    metric = None

    if action is None:
        reasons.append("allocated_action_missing")
    elif action.disposition != "RETURNED" or success is not True:
        reasons.append("original_action_not_successful:" + action.disposition)
    if skill not in {"MOVE_ABOVE", "APPROACH"}:
        reasons.append(
            "RELEASE_requires_exact_PLACE_receipt_and_rigid_grasp"
            if skill == "RELEASE"
            else "unsupported_observed_reference:" + str(skill)
        )
    if geometry_error is None:
        reasons.append("complete_allocated_geometry_unavailable")
    if (
        capture is None
        or terminal is None
        or dispatch is None
        or returned is None
        or capture_step != dispatch
        or terminal.state["physics_step"] != returned
    ):
        reasons.append("exact_capture_dispatch_return_join_unavailable")
    owner_path = group["owner_inputs_paths"].get(span_id)
    if action is None or action.grounding is None or owner_path is None:
        reasons.append("original_owner_binding_unavailable")

    if not reasons:
        # The checks above prove the required optional values before reconstruction.
        assert action is not None and action.grounding is not None
        assert capture is not None and terminal is not None and geometry_error is not None
        owner = _load(_safe(registration.artifact_root, owner_path).read_text())
        try:
            geometry = scope.to_payload()
            target = action.original_plan.contract.task_target
            inputs = owner["grounding_inputs"]
            if (
                target.object_id != geometry["object_id"]
                or target.target_region_id != geometry["target_region_id"]
                or target.object_class != geometry["object_class"]
                or not all(
                    type(inputs["grasp_tcp"][key]) in {int, float}
                    and math.isclose(inputs["grasp_tcp"][key], value, abs_tol=1e-9, rel_tol=0)
                    for key, value in zip("xyz", capture.grasp_tcp, strict=True)
                )
                or [inputs["destination"][key] for key in "xyz"] != geometry["region_world_m"]
                or inputs["support_height_m"] != geometry["support_height_m"]
            ):
                raise ValueError("decoded_grasp_or_registered_target_mismatch")
            checkpoint = ExecutionCheckpoint.model_validate_json(_json(owner["source_checkpoint"]))
            online = OnlineEvidenceSnapshot(
                capture.observation,
                RobotState(
                    tcp_pose=Pose(**dict(zip("xyz", capture.state["tcp_position_m"], strict=True))),
                    gripper_open=capture.state["gripper_open"],
                    connected=True,
                ),
                {},
                action.original_plan.contract.plan_version,
                action.original_plan.contract.command_seq,
                checkpoint_digest(checkpoint),
            )
            rebound = rebuild_owner_binding(owner, online, now=action.grounding.created_at)
            if (
                rebound.digest() != action.grounding.digest()
                or rebound.original_plan_hash != action.original_plan.digest()
                or _json(rebound.grounded_step.model_dump(mode="json"))
                != _json(action.executed_step_payload)
            ):
                raise ValueError("original_owner_receipt_or_executed_payload_mismatch")
            policy = DeterministicGroundingPolicy(**owner["grounding_policy"])
            rc = reconstruct_truth_endpoint(scope, policy, str(skill), capture.state)
            rt = reconstruct_truth_endpoint(scope, policy, str(skill), terminal.state)
            if rc is None or rt is None:
                raise ValueError("observed_truth_reference_unavailable")
            target_pose = rebound.grounded_step.parameters["target_pose"]
            command = (tuple(target_pose[key] for key in "xyz"),)
            capture_reference, return_reference = (rc,), (rt,)
            actual = (tuple(terminal.state["tcp_position_m"]),)
            metric = completion_metric_v2(
                geometric_error_m=geometry_error,
                command_points_m=command,
                capture_reference_points_m=capture_reference,
                terminal_reference_points_m=return_reference,
                actual_points_m=actual,
            )
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            reasons.append("observed_owner_reconstruction_unavailable:" + str(exc))
            command = capture_reference = return_reference = actual = None

    return ObservedCompletionActionV2(
        span_id,
        skill,
        action.disposition if action else None,
        success,
        capture_step,
        dispatch,
        returned,
        observed,
        command,
        capture_reference,
        return_reference,
        actual,
        metric,
        tuple(dict.fromkeys((*reasons, *_QUALIFICATION_REASONS))),
    )


def reconstruct_observed_completion_v2(
    registration: NativeCalibrationRegistration,
) -> ObservedCompletionReconstructionV2:
    """Read checked originals and preserve unavailable allocations, never rank them."""
    if type(registration) is not NativeCalibrationRegistration:
        raise ValueError("exact pinned original-file registration required")
    registry = registration.revalidate()
    scope = NativeGeometryRegistration(registry["geometry"])
    groups = []
    for group in registry["groups"]:
        envelope = RawEpisodeEnvelopeV3.from_json(
            _safe(registration.artifact_root, group["envelope_path"]).read_text()
        )
        records = RawEpisodeRecordsV3.from_json(
            _safe(registration.artifact_root, group["records_path"]).read_text()
        )
        for path, expected in envelope.original_file_hashes.items():
            if (
                _hash(_safe(registration.artifact_root, group["directory"] + "/" + path))
                != expected
            ):
                raise ValueError("raw episode original bytes differ")
        raw = validate_raw_episode_v3(envelope, records)
        source_reasons = original_source_reasons(envelope, registry, scope)
        frames, decoded, fingerprints = _decode_frames(envelope, records, scope)
        errors = [frame.geometric_error_m for frame in frames]
        geometry_error = (
            max(value for value in errors if value is not None)
            if errors
            and all(value is not None for value in errors)
            and raw.status == "COMPLETE"
            and not source_reasons
            else None
        )
        unavailable = (
            (*(f"raw:{reason}" for reason in raw.reasons), *source_reasons)
            if raw.status != "COMPLETE" or source_reasons
            else ()
        )
        actions = {action.span_id: action for action in records.actions}
        groups.append(
            ObservedCompletionGroupV2(
                group["group_id"],
                tuple(group["ancestor_ids"]),
                envelope.physics_dt_s,
                raw.status,
                tuple(dict.fromkeys((*raw.reasons, *source_reasons))),
                raw.utc_mapping,
                envelope.allocated_action_span_ids,
                envelope.allocated_acquisition_ids,
                frames,
                tuple(
                    _observed_action(
                        span_id,
                        actions.get(span_id),
                        records,
                        decoded,
                        geometry_error,
                        scope,
                        registration,
                        group,
                        unavailable,
                    )
                    for span_id in envelope.allocated_action_span_ids
                ),
                geometry_error,
                fingerprints,
            )
        )
    return ObservedCompletionReconstructionV2(tuple(groups))
