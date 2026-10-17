"""Reconstruct native calibration from originals; simulator truth stays offline.

Numeric diagnostics, consistency and conformal ranks are not publishers. No
caller residual, accepted flag, future truth or discrete physical speed estimate
is consumed by the online source. Missing assigned errors are ranked as infinity.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

import numpy as np

from cloud_edge_robot_arm.contracts import Pose, RobotState
from cloud_edge_robot_arm.contracts.models import ExecutionCheckpoint, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    RawEpisodeEnvelopeV3,
    RawEpisodeRecordsV3,
    _digest,
    _owner_decode,
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
    _sha,
    _vector,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    DeterministicGroundingPolicy,
    GroundingDurationCheck,
    GroundingFrameInputs,
    VisualOriginalPlan,
    VisualOwnerIdentity,
    bind_step_grounding,
)
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker


@dataclass(frozen=True)
class FullRigidGeometryErrors:
    vertex_error_m: float
    contact_error_m: float
    tcp_contact_error_m: float
    joint_geometry_error_m: float
    vertex_count: int
    contact_count: int


def full_rigid_geometry_errors(
    scope: NativeGeometryRegistration,
    estimated_center: Sequence[float],
    estimated_rotation: Sequence[float],
    truth_center: Sequence[float],
    truth_rotation: Sequence[float],
) -> FullRigidGeometryErrors:
    """Joint point error, including angular lever arms; arithmetic alone is SOFTWARE_ONLY."""
    data = scope.to_payload()
    ec, tc = _vector(list(estimated_center), 3), _vector(list(truth_center), 3)
    er, tr = (
        _vector(list(estimated_rotation), 9).reshape(3, 3),
        _vector(list(truth_rotation), 9).reshape(3, 3),
    )
    for r in (er, tr):
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-7, rtol=0) or not math.isclose(
            float(np.linalg.det(r)), 1, abs_tol=1e-7
        ):
            raise ValueError("original/estimated rigid rotation invalid")
    vertices = np.array(list(itertools.product(*[(-h, h) for h in data["object_half_extent_m"]])))
    contacts = np.array(list(data["contact_points_m"].values()))
    tcp = _rigid(data["object_to_tcp"])[:3, 3].reshape(1, 3)

    def maximum(points: np.ndarray) -> float:
        return float(np.linalg.norm((points @ er.T + ec) - (points @ tr.T + tc), axis=1).max())

    v, c, t = maximum(vertices), maximum(contacts), maximum(tcp)
    return FullRigidGeometryErrors(v, c, t, max(v, c, t), 8, len(contacts))


def reconstruct_geometry(
    observation: RGBDObservation,
    scope: NativeGeometryRegistration,
    original_physics: Mapping[str, Any],
) -> FullRigidGeometryErrors | None:
    """Run the frozen RGBD-only decoder first; compare with separately joined truth afterward."""
    current = RGBDObservation.model_validate_json(_json(observation.model_dump(mode="json")))
    estimate = detect_pose_marker(current, scope.pose_marker)
    if estimate.status != "OBSERVED":
        return None
    data = scope.to_payload()
    if list(original_physics["object_half_extent_m"]) != data["object_half_extent_m"]:
        raise ValueError("truth object dimensions differ from complete registered geometry")
    transform = _rigid(data["marker_to_object"])
    rotation = np.array(estimate.rotation_marker_to_world).reshape(3, 3) @ transform[:3, :3].T
    center = np.array(estimate.marker_center_world_m) - rotation @ transform[:3, 3]
    return full_rigid_geometry_errors(
        scope,
        center.tolist(),
        rotation.ravel().tolist(),
        original_physics["object_geom_position_m"],
        original_physics["object_geom_rotation_row_major"],
    )


@dataclass(frozen=True)
class GroupQuantile:
    bound_m: float | None
    group_count: int
    rank: int
    unavailable_group_ids: tuple[str, ...]


def conformal_group_quantile(
    groups: Mapping[str, float | None], *, coverage: float = 0.9
) -> GroupQuantile:
    """Pure arithmetic diagnostics; retain unavailable/failed groups as +infinity."""
    if type(coverage) not in {int, float} or coverage != 0.9:
        raise ValueError("registered native coverage is exactly 0.9")
    values = []
    missing = []
    for group, residual in groups.items():
        if not isinstance(group, str) or not group:
            raise ValueError("registered independent component identity required")
        if residual is None:
            missing.append(group)
            values.append(math.inf)
        elif type(residual) not in {int, float} or not math.isfinite(residual) or residual < 0:
            raise ValueError("nonnegative reconstructed finite error required")
        else:
            values.append(float(residual))
    values.sort()
    rank = math.ceil((len(values) + 1) * coverage)
    bound = values[rank - 1] if len(values) >= 9 and rank <= len(values) else math.inf
    return GroupQuantile(
        bound if math.isfinite(bound) else None, len(values), rank, tuple(sorted(missing))
    )


def independent_components(groups: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, ...], ...]:
    ids = [g["group_id"] for g in groups]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate allocated group identity")
    parents = list(range(len(groups)))

    def root(i: int) -> int:
        while parents[i] != i:
            i = parents[i]
        return i

    for i, left in enumerate(groups):
        for j in range(i):
            right = groups[j]
            if set(left["ancestor_ids"]) & set(right["ancestor_ids"]) or set(
                left["fingerprints"]
            ) & set(right["fingerprints"]):
                parents[root(i)] = root(j)
    components: dict[int, list[str]] = {}
    for i, group in enumerate(ids):
        components.setdefault(root(i), []).append(group)
    return tuple(sorted(tuple(sorted(v)) for v in components.values()))


def original_rgbd_fingerprint(observation: Mapping[str, Any]) -> str:
    """Identify joint original pixels, excluding metadata and common validity masks."""
    digest = hashlib.sha256()
    for key in ("rgb_png_base64", "depth_float32_base64"):
        value = base64.b64decode(observation[key], validate=True)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return "original-rgbd:" + digest.hexdigest()


def independent_utc_uncertainty_ns(
    payload: Mapping[str, Any], envelope: RawEpisodeEnvelopeV3, records: RawEpisodeRecordsV3
) -> int:
    """Recompute uncertainty from every independently captured UTC bracket original.

    This reader is arithmetic only. The application catalog must authenticate the
    independent acquisition implementation and bytes before native use.
    """
    data = _load(_json(payload))
    if (
        type(data) is not dict
        or set(data)
        != {
            "schema_version",
            "clock_domain_id",
            "clock_descriptor_hash",
            "independent_source_hashes",
            "samples",
        }
        or data["schema_version"] != "native.calibration.utc-originals.v1"
        or data["clock_domain_id"] != envelope.identity.clock_domain_id
        or data["clock_descriptor_hash"] != envelope.clock_descriptor.digest()
        or type(data["independent_source_hashes"]) is not dict
        or not data["independent_source_hashes"]
        or set(data["independent_source_hashes"]) & set(envelope.clock_descriptor.source_hashes)
    ):
        raise ValueError("complete independent clock originals required")
    for value in data["independent_source_hashes"].values():
        _sha(value)
    pairs = {
        pair.digest(): pair
        for interval in records.intervals
        for pair in (interval.start, interval.end)
        if pair is not None
    }
    samples = data["samples"]
    if type(samples) is not list:
        raise ValueError("independent UTC samples must be a complete row list")
    for sample in samples:
        if type(sample) is not dict or set(sample) != {
            "pair_hash",
            "utc_lower_at",
            "utc_upper_at",
        }:
            raise ValueError("independent UTC original requires its exact sample schema")
        _sha(sample["pair_hash"])
        if any(type(sample[key]) is not str for key in ("utc_lower_at", "utc_upper_at")):
            raise ValueError("independent UTC bracket originals must be timestamp strings")
    if (
        not pairs
        or len(samples) != len(pairs)
        or {sample["pair_hash"] for sample in samples} != set(pairs)
    ):
        raise ValueError("every original clock pair requires exactly one independent bracket")
    uncertainty = 0
    for sample in samples:
        lower, upper = (datetime.fromisoformat(sample[k]) for k in ("utc_lower_at", "utc_upper_at"))
        if any(t.tzinfo is None or t.utcoffset() is None for t in (lower, upper)) or lower > upper:
            raise ValueError("ordered aware independent UTC bracket required")
        local = pairs[sample["pair_hash"]].utc_at
        for bound in (lower, upper):
            delta = abs(bound - local)
            uncertainty = max(
                uncertainty,
                (delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000,
            )
    return uncertainty


def required_capture_source_paths() -> tuple[str, ...]:
    from cloud_edge_robot_arm.vision.raw_recorder_v3 import RECORDER_SOURCE_PATHS

    return tuple(sorted(RECORDER_SOURCE_PATHS))


def original_source_reasons(
    envelope: RawEpisodeEnvelopeV3, registry: Mapping[str, Any], scope: NativeGeometryRegistration
) -> tuple[str, ...]:
    """Bind every original producer and the original asset to current registered bytes."""
    reasons = []
    sources = envelope.identity.source_hashes
    if not set(required_capture_source_paths()) <= set(sources):
        reasons.append("original_producer_inventory_unavailable")
    if any(name not in registry["source_hashes"] for name in sources):
        reasons.append("original_producer_source_unregistered")
    if any(
        registry["source_hashes"].get(name) != sha
        for name, sha in sources.items()
        if name in registry["source_hashes"]
    ):
        reasons.append("original_producer_source_mismatch")
    asset = scope.to_payload()["asset_path"]
    expected = scope.pose_marker.marked_asset_sha256
    if registry["source_hashes"].get(asset) != expected:
        reasons.append("registered_marker_asset_inventory_unavailable")
    if envelope.identity.asset_hash != expected:
        reasons.append("original_marker_asset_mismatch")
    return tuple(reasons)


def preregistration_reasons(
    registry: Mapping[str, Any],
    envelope: RawEpisodeEnvelopeV3,
    records: RawEpisodeRecordsV3,
    clock_originals: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Check actual interval UTC originals; v1 has no original RESET wall bracket."""
    reasons = ["reset_utc_originals_unavailable"]
    if clock_originals is None:
        return ("preregistration_chronology_unavailable", *reasons)
    independent_utc_uncertainty_ns(clock_originals, envelope, records)
    preregistered = datetime.fromisoformat(registry["preregistered_at"])
    if preregistered.tzinfo is None or preregistered.utcoffset() is None:
        raise ValueError("aware original preregistration timestamp required")
    samples = {sample["pair_hash"]: sample for sample in clock_originals["samples"]}
    original_begins = [
        interval.start
        for interval in records.intervals
        if interval.kind in {"ACQUISITION", "EXECUTOR_ATTEMPT"}
    ]
    if not original_begins:
        reasons.append("preregistration_chronology_unavailable")
    if any(
        preregistered >= datetime.fromisoformat(samples[pair.digest()]["utc_lower_at"])
        for pair in original_begins
    ):
        reasons.append("preregistration_after_original_boundary")
    return tuple(reasons)


def calibration_policy_digest(
    registration: NativeCalibrationRegistration, skill: str
) -> str | None:
    """Read the unique recipe from all assigned skill-action owner originals, not a flag."""
    registry = registration.revalidate()
    digests = set()
    for group in registry["groups"]:
        records = RawEpisodeRecordsV3.from_json(
            _safe(registration.artifact_root, group["records_path"]).read_text()
        )
        actions = [
            action
            for action in records.actions
            if action.original_plan.requirements[action.step_id].original_step.skill.value == skill
        ]
        if not actions:
            return None
        for action in actions:
            path = group["owner_inputs_paths"].get(action.span_id)
            if path is None or action.grounding is None:
                return None
            owner = _load(_safe(registration.artifact_root, path).read_text())
            policy = DeterministicGroundingPolicy(**owner["grounding_policy"])
            original = _owner_decode(VisualOriginalPlan, owner["original"])
            if (
                original.digest() != action.original_plan.digest()
                or policy.digest() != action.grounding.grounding_policy_hash
            ):
                return None
            digests.add(policy.digest())
    return next(iter(digests)) if len(digests) == 1 else None


def reconstruct_truth_endpoint(
    scope: NativeGeometryRegistration,
    policy: DeterministicGroundingPolicy,
    skill: str,
    original_physics: Mapping[str, Any],
) -> tuple[float, float, float] | None:
    """Offline endpoint arithmetic using the exact already reconstructed owner policy."""
    geometry = scope.to_payload()
    center = _vector(list(original_physics["object_geom_position_m"]), 3)
    rotation = _vector(list(original_physics["object_geom_rotation_row_major"]), 9).reshape(3, 3)
    grasp = center + rotation @ _rigid(geometry["object_to_tcp"])[:3, 3]
    current = _vector(list(original_physics["tcp_position_m"]), 3)
    if skill in {"LIFT", "RETREAT"}:
        target = (
            current[0],
            current[1],
            max(current[2] + policy.clearance_m, policy.minimum_height_m),
        )
    elif skill in {"MOVE_TO_REGION", "PLACE"}:
        region = geometry["region_world_m"]
        z = (
            max(policy.minimum_height_m, grasp[2] + policy.clearance_m)
            if skill == "MOVE_TO_REGION"
            else region[2] + grasp[2] - geometry["support_height_m"]
        )
        target = (region[0], region[1], z)
    elif skill in {"MOVE_ABOVE", "APPROACH"}:
        target = (
            grasp[0],
            grasp[1],
            max(policy.minimum_height_m, grasp[2] + policy.clearance_m)
            if skill == "MOVE_ABOVE"
            else grasp[2],
        )
    else:
        return None
    return (float(target[0]), float(target[1]), float(target[2]))


def rebuild_owner_binding(
    payload: Mapping[str, Any], online: OnlineEvidenceSnapshot, *, now: datetime
) -> Any:
    """Recompute original receipt/horizon; a public carrier is not owner authentication."""
    data = _load(_json(payload))
    keys = {
        "original",
        "source_checkpoint",
        "current_identity",
        "owner_revision",
        "state_generation",
        "grounding_inputs",
        "grounding_policy",
        "required_duration_s",
        "duration_check",
    }
    if set(data) != keys:
        raise ValueError("complete original owner/source inputs required")
    original = _owner_decode(VisualOriginalPlan, data["original"])
    checkpoint = ExecutionCheckpoint.model_validate_json(_json(data["source_checkpoint"]))
    policy = DeterministicGroundingPolicy(**data["grounding_policy"])
    inputs = GroundingFrameInputs(**data["grounding_inputs"])
    check = data["duration_check"]
    if check is not None:
        check = dict(check)
        check["grounded_step"] = TaskStep.model_validate_json(_json(check["grounded_step"]))
        check["checked_at"] = datetime.fromisoformat(check["checked_at"])
        check = GroundingDurationCheck(**check)
    from cloud_edge_robot_arm.vision.owner_registration import _resolved_parameters

    step = original.requirements[checkpoint.current_step_id].original_step
    grounded = step.model_copy(
        update={
            "parameters": _resolved_parameters(step, original, online, inputs, policy),
            "preconditions": [],
            "success_conditions": [],
        }
    )
    return bind_step_grounding(
        original,
        original_step_id=step.step_id,
        grounded_step=grounded,
        online=online,
        source_checkpoint=checkpoint,
        current_identity=VisualOwnerIdentity(**data["current_identity"]),
        owner_revision=data["owner_revision"],
        state_generation=data["state_generation"],
        grounding_inputs=inputs,
        grounding_policy=policy,
        now=now,
        required_duration_s=data["required_duration_s"],
        duration_check=check,
    )


@dataclass(frozen=True)
class CalibrationGroupResult:
    group_id: str
    status: str
    allocated_frames: int
    missing_frames: int
    unknown_frames: int
    failed_actions: int
    geometry_error_m: float | None
    action_errors_m: Mapping[str, float | None]
    reasons: tuple[str, ...]
    fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class NativeCalibrationDiagnostics:
    source_scope: str
    assigned_group_count: int
    independent_group_count: int
    groups: tuple[CalibrationGroupResult, ...]
    components: tuple[tuple[str, ...], ...]
    geometry_quantile: GroupQuantile
    action_quantiles: Mapping[str, GroupQuantile]


def _group(
    registration: NativeCalibrationRegistration,
    registry: Mapping[str, Any],
    group: Mapping[str, Any],
    scope: NativeGeometryRegistration,
) -> CalibrationGroupResult:
    envelope = RawEpisodeEnvelopeV3.from_json(
        _safe(registration.artifact_root, group["envelope_path"]).read_text()
    )
    records = RawEpisodeRecordsV3.from_json(
        _safe(registration.artifact_root, group["records_path"]).read_text()
    )
    if (
        registry["source_scope"] == "REGISTERED_SIMULATION_CALIBRATION"
        and envelope.identity.source_kind == "SOFTWARE_ONLY"
    ):
        raise ValueError("synthetic origins cannot be upgraded by a rehashed scope label")
    view = validate_raw_episode_v3(envelope, records)
    reasons = list(view.reasons)
    geometry = scope.to_payload()
    source_reasons = original_source_reasons(envelope, registry, scope)
    reasons.extend(source_reasons)
    clock_supported = False
    clock = None
    clock_path = group["clock_reference_path"]
    if clock_path is not None:
        try:
            clock = _load(_safe(registration.artifact_root, clock_path).read_text())
            measured = independent_utc_uncertainty_ns(clock, envelope, records)
            if any(
                registry["source_hashes"].get(name) != sha
                for name, sha in clock["independent_source_hashes"].items()
            ):
                raise ValueError("independent UTC acquisition source is not registered")
            declared = envelope.clock_descriptor.utc_uncertainty_ns
            clock_supported = (
                view.utc_mapping == "BRACKETED" and declared is not None and declared >= measured
            )
        except ValueError:
            clock = None
            reasons.append("independent_clock_originals_invalid")
    if not clock_supported:
        reasons.append("clock_mapping_unavailable")
    chronology = preregistration_reasons(registry, envelope, records, clock)
    reasons.extend(chronology)
    if view.status == "INVALID" or any(
        reason in reasons
        for reason in (
            "original_producer_source_mismatch",
            "original_marker_asset_mismatch",
            "preregistration_after_original_boundary",
            "independent_clock_originals_invalid",
        )
    ):
        status = "INVALID"
    elif view.status != "COMPLETE" or source_reasons or chronology:
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    # Original hashes are checked against actual payloads, not an audit result token.
    for name, expected in envelope.original_file_hashes.items():
        actual = _safe(registration.artifact_root, group["directory"] + "/" + name)
        if _hash(actual) != expected:
            raise ValueError("raw episode original payload hash differs from registered bytes")
    raw = {
        envelope.reset_state_payload["physics_step"]: envelope.reset_state_payload,
        **{p.physics_step: p.post_state_payload for p in records.physics},
    }
    by_hash = {_digest(state): state for state in raw.values()}
    intervals = {i.interval_id: i for i in records.intervals}
    frame_by_id = {f.acquisition_id: f for f in records.frames}
    missing = len(set(envelope.allocated_acquisition_ids) - set(frame_by_id))
    unknown = 0
    point_errors = []
    fingerprints = [
        "episode:" + envelope.identity.episode_id,
        "scene:" + envelope.identity.scene_hash,
    ]
    for frame in records.frames:
        if (
            frame.observation_payload is None
            or frame.joined_physics_observation_hash not in by_hash
        ):
            unknown += 1
            continue
        observation = RGBDObservation.model_validate_json(_json(frame.observation_payload))
        fingerprints.append(original_rgbd_fingerprint(frame.observation_payload))
        truth = by_hash[frame.joined_physics_observation_hash]
        descriptor = {k: observation.model_dump(mode="json")[k] for k in geometry["camera"]}
        if descriptor != geometry["camera"] or not math.isclose(
            observation.sim_time_s, truth["sim_time_s"], abs_tol=1e-9
        ):
            unknown += 1
            continue
        errors = reconstruct_geometry(observation, scope, truth)
        if errors is None:
            unknown += 1
        else:
            point_errors.append(errors.joint_geometry_error_m)
    geo = (
        max(point_errors)
        if point_errors and not missing and not unknown and status == "COMPLETE"
        else None
    )
    failed = sum(
        a.disposition != "RETURNED" or a.returned_result is None or not a.returned_result["success"]
        for a in records.actions
    )
    action_errors = {}
    for skill, horizon in registry["supported_actions"].items():
        actions = [
            a
            for a in records.actions
            if a.original_plan.requirements[a.step_id].original_step.skill.value == skill
        ]
        values: list[float] = []
        unavailable = geo is None or status != "COMPLETE" or not clock_supported or not actions
        for action in actions:
            owner_path = group["owner_inputs_paths"].get(action.span_id)
            before = [
                j
                for j in records.joins
                if j.span_id == action.span_id and j.relation == "BEFORE_SUBMIT"
            ]
            interval = intervals.get(action.interval_id)
            if (
                geo is None
                or action.disposition != "RETURNED"
                or action.returned_result is None
                or not action.returned_result["success"]
                or action.grounding is None
                or owner_path is None
                or len(before) != 1
                or interval is None
                or interval.end_step is None
            ):
                unavailable = True
                continue
            frame = frame_by_id.get(before[0].acquisition_id)
            if frame is None or frame.observation_payload is None:
                unavailable = True
                continue
            observation = RGBDObservation.model_validate_json(_json(frame.observation_payload))
            state = by_hash.get(frame.joined_physics_observation_hash)
            if state is None:
                unavailable = True
                continue
            owner = _load(_safe(registration.artifact_root, owner_path).read_text())
            checkpoint = ExecutionCheckpoint.model_validate_json(_json(owner["source_checkpoint"]))
            online = OnlineEvidenceSnapshot(
                observation,
                RobotState(
                    tcp_pose=Pose(
                        x=state["tcp_position_m"][0],
                        y=state["tcp_position_m"][1],
                        z=state["tcp_position_m"][2],
                    ),
                    gripper_open=state["gripper_open"],
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
            ):
                raise ValueError("original action owner receipt differs from source reconstruction")
            duration = rebound.expected_duration_s
            if (
                duration != horizon
                or duration
                < max(rebound.grounded_step.timeout_ms, rebound.grounded_step.expected_duration_ms)
                / 1000
            ):
                unavailable = True
                continue
            # Whole nominal horizon must be present; never shorten to observed success duration.
            start_time = interval.start_sim_time_s
            end_time = start_time + horizon
            terminal = [
                s for s in raw.values() if math.isclose(s["sim_time_s"], end_time, abs_tol=1e-8)
            ]
            if len(terminal) != 1 or any(
                i.kind == "EXECUTOR_ATTEMPT"
                and i.interval_id != interval.interval_id
                and start_time < i.start_sim_time_s < end_time
                for i in records.intervals
            ):
                unavailable = True
                continue
            target = rebound.grounded_step.parameters.get("target_pose")
            if target is None:
                unavailable = True
                continue
            policy = DeterministicGroundingPolicy(**owner["grounding_policy"])
            true_goal = reconstruct_truth_endpoint(scope, policy, skill, state)
            if true_goal is None:
                unavailable = True
                continue
            # Joint completion quantity already includes localization + actual terminal tracking.
            goal_error = float(np.linalg.norm(np.array([target[k] for k in "xyz"]) - true_goal))
            terminal_error = float(
                np.linalg.norm(np.array(terminal[0]["tcp_position_m"]) - true_goal)
            )
            values.append(max(geo, goal_error, terminal_error))
        action_errors[skill] = max(values) if values and not unavailable else None
    return CalibrationGroupResult(
        group["group_id"],
        status,
        len(envelope.allocated_acquisition_ids),
        missing,
        unknown,
        failed,
        geo,
        MappingProxyType(action_errors),
        tuple(dict.fromkeys(reasons)),
        tuple(fingerprints),
    )


def reconstruct_registered_calibration(
    registration: NativeCalibrationRegistration,
) -> NativeCalibrationDiagnostics:
    if type(registration) is not NativeCalibrationRegistration:
        raise ValueError("concrete original registration required, never finite result/provider")
    data = registration.revalidate()
    scope = NativeGeometryRegistration(data["geometry"])
    groups = tuple(_group(registration, data, g, scope) for g in data["groups"])
    graph = [
        dict(
            group_id=g.group_id,
            ancestor_ids=allocation["ancestor_ids"],
            fingerprints=g.fingerprints,
        )
        for g, allocation in zip(groups, data["groups"], strict=True)
    ]
    components = independent_components(graph)
    by_id = {g.group_id: g for g in groups}

    def joint(values: Sequence[float | None]) -> float | None:
        finite = [v for v in values if v is not None]
        return max(finite) if len(finite) == len(values) else None

    geometry = conformal_group_quantile(
        {_json(c): joint([by_id[k].geometry_error_m for k in c]) for c in components}
    )
    actions = {
        skill: conformal_group_quantile(
            {_json(c): joint([by_id[k].action_errors_m[skill] for k in c]) for c in components}
        )
        for skill in data["supported_actions"]
    }
    if geometry.group_count != len(components) or any(
        quantile.group_count != len(components) for quantile in actions.values()
    ):
        raise ValueError("every reconstructed component must remain in each calibration rank")
    return NativeCalibrationDiagnostics(
        data["source_scope"],
        len(groups),
        len(components),
        groups,
        components,
        geometry,
        MappingProxyType(actions),
    )
