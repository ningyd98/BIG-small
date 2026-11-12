"""Finite teacher skeleton and the existing pixel/proprioceptive grounding path.

No simulator, instance segmentation or object truth is accepted by these APIs.
The role description is development input; it grants no execution authority.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from cloud_edge_robot_arm.contracts import (
    ControlMode,
    ExecutionCheckpoint,
    FailurePolicy,
    RobotState,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research.native_calibration_collection import (
    BASE_ASSET,
    BASE_SHA,
    ROOT,
    action_horizons,
    digest,
    regular,
)
from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY, marker_family
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    DeterministicGroundingPolicy,
    GroundingFrameInputs,
    StepGroundingBinding,
    VisualOriginalPlan,
    _resolved_parameters,
    bind_step_grounding,
    freeze_original_visual_plan,
)
from cloud_edge_robot_arm.vision.registered_object_tracking import (
    RegisteredObjectTrackerV1,
    RegisteredObjectTrackV1,
)
from cloud_edge_robot_arm.vision.registered_objects import derive_registered_object_geometry
from cloud_edge_robot_arm.vision.top_grasp import (
    CURRENT_GRASP_PROFILE,
    calibration_asset_sha256,
    resolve_top_grasp,
)
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker, _rgb
from cloud_edge_robot_arm.vision.worker_owner import compile_worker_original_plan


def _transform(x: float = 0, y: float = 0, z: float = 0) -> list[float]:
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1]


def release_reference_registration(
    source_hashes: Mapping[str, str], geometry: Mapping[str, Any]
) -> dict[str, Any]:
    """Nominal upright controller reference, never a measured achieved grasp."""
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.vision.top_grasp import _TCP_ABOVE_ESTIMATED_CENTER_M

    registered = NativeGeometryRegistration(geometry)
    registered.validate_asset(ROOT)
    family = marker_family(registered.marker_family_id or LEGACY_FAMILY)
    paths = (
        "simulation/mujoco/skill_robot.py",
        "simulation/mujoco/motion_controller.py",
        "simulation/mujoco/backend.py",
        "simulation/models.py",
        "vision/top_grasp.py",
    )
    sources = {
        "src/cloud_edge_robot_arm/" + p: source_hashes["src/cloud_edge_robot_arm/" + p]
        for p in paths
    }
    sources.update({p: source_hashes[p] for p in (BASE_ASSET, family.asset_path)})
    if sources[family.asset_path] != family.asset_sha256:
        raise ValueError("selected release asset source differs from registered family")
    w, x, y, z = _DOWNWARD
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    if (
        not np.allclose(rotation, [[0, 0, 1], [0, 1, 0], [-1, 0, 0]], atol=1e-14, rtol=0)
        or _TCP_ABOVE_ESTIMATED_CENTER_M != 0.01
    ):
        raise ValueError("registered original upright controller convention changed")
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = (0, 0, _TCP_ABOVE_ESTIMATED_CENTER_M)
    extent = geometry["object_half_extent_m"]
    return dict(
        schema_version="native.release.reference.v1",
        frame_convention="COLUMN_VECTORS_A_T_B_MAPS_B_TO_A",
        source_hashes=sources,
        source_generation=digest(dict(source_hashes)),
        nominal_object_rotation=np.eye(3).ravel().tolist(),
        command_tcp_quaternion_wxyz=list(_DOWNWARD),
        command_tcp_rotation=rotation.ravel().tolist(),
        nominal_object_to_tcp=transform.ravel().tolist(),
        tool_to_tcp=geometry["tool_to_tcp"],
        object_contact_offset_m=[0, 0, _TCP_ABOVE_ESTIMATED_CENTER_M],
        vertices_object_m=[list(v) for v in itertools.product(*[(-h, h) for h in extent])],
        grasp_profile=CURRENT_GRASP_PROFILE,
        base_asset_sha256=BASE_SHA,
        marked_asset_sha256=family.asset_sha256,
        formula="WORLD_TCP_COMMAND_TIMES_INVERSE_NOMINAL_OBJECT_TCP_V1",
        measured_tcp_rotation=False,
        reference_kind="NOMINAL_UPRIGHT_CONTROLLER_PROFILE",
    )


def geometry_registration(*, marker_family_id: str | None = None) -> dict[str, Any]:
    """Derive the registered top camera from immutable XML, without compilation."""
    family = marker_family(LEGACY_FAMILY if marker_family_id is None else marker_family_id)
    if (
        hashlib.sha256(regular(ROOT / family.asset_path).read_bytes()).hexdigest()
        != family.asset_sha256
        or hashlib.sha256(regular(ROOT / BASE_ASSET).read_bytes()).hexdigest() != BASE_SHA
        or CURRENT_GRASP_PROFILE != "mujoco_upright_box_v2"
        or calibration_asset_sha256(CURRENT_GRASP_PROFILE) != BASE_SHA
    ):
        raise ValueError("exact marked asset and separate base grasp profile required")
    tree = ET.fromstring((ROOT / family.asset_path).read_bytes())
    camera = tree.find("./worldbody/camera[@name='rgbd']")
    if camera is None or (camera.get("pos"), camera.get("quat"), camera.get("fovy")) != (
        "0.35 0 1.4",
        "1 0 0 0",
        "50",
    ):
        raise ValueError("registered fixed top camera changed")
    focal = 120 / math.tan(math.radians(50) / 2)
    intrinsics = [focal, focal, 159.5, 119.5]
    transform = [1, 0, 0, 0.35, 0, -1, 0, 0, 0, 0, -1, 1.4, 0, 0, 0, 1]
    calibration = hashlib.sha256(
        np.asarray(intrinsics + transform, dtype="<f8").tobytes()
    ).hexdigest()[:16]
    geometry = dict(
        registration_id=family.registration_id,
        object_id="object",
        object_class="cube",
        target_region_id="target_region",
        asset_path=family.asset_path,
        pose_marker=dict(
            marker_id=family.marker_id,
            marker_size_m=family.marker_size_m,
            marked_asset_sha256=family.asset_sha256,
            dictionary=family.dictionary,
        ),
        marker_to_object=list(family.marker_to_object),
        object_half_extent_m=[0.035] * 3,
        contact_points_m={"top": [0, 0, 0.035], "left": [0, 0.035, 0], "right": [0, -0.035, 0]},
        object_to_tcp=_transform(0, 0, 0.01),
        tool_to_tcp=_transform(0.105, 0, 0),
        camera=dict(
            width=320,
            height=240,
            intrinsics=intrinsics,
            camera_to_world=transform,
            calibration_version=calibration,
            source="mujoco_camera",
        ),
        region_world_m=[0.2, 0.25, 0.004],
        support_height_m=0.0,
    )
    if family.family_id != LEGACY_FAMILY:
        geometry["marker_family"] = family.family_id
    NativeGeometryRegistration(geometry).validate_asset(ROOT)
    return geometry


def validate_camera(observation: RGBDObservation, registration: Mapping[str, Any]) -> None:
    actual = observation.model_dump(mode="json")
    expected = registration["camera"]
    if any(actual.get(key) != value for key, value in expected.items()):
        raise ValueError("actual acquisition differs from preregistered camera")


def validate_registration_handoff(
    original: VisualOriginalPlan,
    lease: Mapping[str, Any],
    bootstrap: RGBDObservation,
    dispatch: RGBDObservation,
    *,
    step_before: int,
    step_after: int,
    now: datetime,
) -> None:
    """Check source chronology; this pure check grants no execution authority."""
    registered = original.registered_at
    acquired, observed, expires = (
        datetime.fromisoformat(lease[name]) for name in ("acquired_at", "observed_at", "expires_at")
    )
    if (
        any(
            lease[key] != getattr(original.identity, key)
            for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")
        )
        or not acquired <= bootstrap.captured_at <= registered
        or not observed <= registered < expires
        or not registered
        <= dispatch.captured_at
        <= now
        < min(original.effective_deadline_at, expires, dispatch.captured_at + timedelta(seconds=5))
    ):
        raise ValueError("original registration/capture/lease chronology mismatch")
    if (
        bootstrap.observation_id == dispatch.observation_id
        or bootstrap.checksum_sha256 == dispatch.checksum_sha256
        or bootstrap.episode_id != dispatch.episode_id
        or dispatch.episode_id != original.identity.episode_id
        or bootstrap.calibration_version != dispatch.calibration_version
        or bootstrap.source != dispatch.source
        or step_before != step_after
        or step_before != 120
        or bootstrap.sim_time_s != dispatch.sim_time_s
        or not math.isclose(dispatch.sim_time_s, step_before / 240, abs_tol=1e-9)
    ):
        raise ValueError("distinct same-step original registration captures required")


def collection_bootstrap_evidence(
    observation: RGBDObservation, registration: Mapping[str, Any]
) -> dict[str, Any]:
    validate_camera(observation, registration)
    scope = NativeGeometryRegistration(registration)
    geometry = derive_registered_object_geometry(observation, scope)
    if geometry.status != "DERIVED":
        raise ValueError("registered marker unavailable: " + geometry.reason)
    assert geometry.object_center_world_m is not None
    center = np.asarray(geometry.object_center_world_m)
    transform = np.asarray(observation.camera_to_world).reshape(4, 4)
    optical = transform[:3, :3].T @ (center - transform[:3, 3])
    if optical[2] <= 0:
        raise ValueError("registered marker object projects behind camera")
    fx, fy, cx, cy = observation.intrinsics
    target = (round(fx * optical[0] / optical[2] + cx), round(fy * optical[1] / optical[2] + cy))
    rgb = _rgb(observation).astype(float)
    green = (
        (rgb[:, :, 1] > rgb[:, :, 0]) & (rgb[:, :, 1] > rgb[:, :, 2]) & (np.ptp(rgb, axis=2) > 35)
    ).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(green, connectivity=8)
    candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 8]
    if len(candidates) != 1:
        raise ValueError("unique registered green region unavailable")
    ys, xs = np.nonzero(labels == candidates[0])
    distance = (xs - np.median(xs)) ** 2 + (ys - np.median(ys)) ** 2
    index = int(np.argmin(distance))
    destination = (int(xs[index]), int(ys[index]))
    top_grasp = resolve_top_grasp(observation, target, float(registration["support_height_m"]))
    evidence = dict(
        top_grasp,
        original_pixel_target=target,
        original_pixel_destination=destination,
        depth_error_bound_m=None,
    )
    return evidence


def bootstrap_collection_tracker(
    observation: RGBDObservation, registration: Mapping[str, Any]
) -> tuple[OpenCVTargetTracker, dict[str, Any]]:
    evidence = collection_bootstrap_evidence(observation, registration)
    return OpenCVTargetTracker(observation, evidence), evidence


def collection_grounding_inputs(
    observation: RGBDObservation,
    robot_state: RobotState,
    registration: Mapping[str, Any],
    *,
    tracker: OpenCVTargetTracker,
    evidence: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> GroundingFrameInputs:
    validate_camera(observation, registration)
    if type(robot_state) is not RobotState or not robot_state.connected:
        raise ValueError("actual proprioceptive robot state required")
    target, reason = tracker._geometry(observation, tracker.target_color, target=True)
    region, region_reason = tracker._geometry(
        observation, tracker.destination_color, target=False, occlusion_geometry=target
    )
    if target is None or region is None or tracker.initial is None:
        raise ValueError(
            "fresh pixel identity/geometry unavailable: " + str(reason or region_reason)
        )
    offset = float(evidence["resolved_top_grasp_tcp"]["z"]) - float(tracker.initial["center"][2])
    center = target["center"]
    return GroundingFrameInputs(
        observation_id=observation.observation_id,
        observation_checksum_sha256=observation.checksum_sha256,
        episode_id=observation.episode_id or "",
        calibration_version=observation.calibration_version or "",
        grasp_tcp=dict(x=center[0], y=center[1], z=center[2] + offset),
        destination=dict(zip("xyz", region["center"], strict=True)),
        support_height_m=float(registration["support_height_m"]),
        source_hashes=source_hashes,
    )


def build_collection_contract(
    *,
    assignment: Mapping[str, Any],
    current_owner: Mapping[str, Any],
    geometry: Mapping[str, Any],
    source_hashes: Mapping[str, str],
    observation: RGBDObservation,
) -> VisualOriginalPlan:
    validate_camera(observation, geometry)
    horizons = action_horizons()
    issued = current_owner["issued_at"]
    contract = TaskContract(
        task_id=current_owner["task_id"],
        plan_version=1,
        command_seq=1,
        timestamp=issued,
        issued_at=issued,
        valid_until=current_owner["deadline_at"],
        control_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        user_instruction="Move the red block to the green region.",
        scene_version=0,
        expected_scene_version=0,
        task_target=TaskTarget(
            object_id="object", object_class="cube", target_region_id="target_region"
        ),
        steps=[
            TaskStep(
                step_id=f"step-{i + 1}",
                skill=SkillName(row["skill"]),
                expected_duration_ms=row["original_timeout_ms"],
                timeout_ms=row["original_timeout_ms"],
                retry_limit=0,
            )
            for i, row in enumerate(horizons)
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=3.0,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.0,
            workspace_id="mujoco-t7-v1",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=0,
            on_timeout="STOP",
            on_safety_rejection="STOP",
            on_network_loss="STOP",
        ),
        completion_criteria=["object_placed", "placement_stable"],
    )
    lease = current_owner["lease"]
    identity = lease.identity(
        episode_id=observation.episode_id,
        task_id=contract.task_id,
        plan_id=current_owner["plan_id"],
        robot_id="native-collection-panda",
    )
    original = compile_worker_original_plan(
        lease_source=lease,
        identity=identity,
        contract=contract,
        observation=observation,
        proposal_hash=digest(dict(assignment)),
        role_bundle_hash=current_owner["role_sha256"],
        source_hashes=source_hashes,
        registered_at=datetime.now(UTC),
        task_deadline_at=current_owner["deadline_at"],
        verification_deadline_at=current_owner["deadline_at"],
    )
    requirements = {
        step.step_id: replace(
            original.requirements[step.step_id],
            expected_duration_s=row["horizon"]["total_steps"] / 240,
        )
        for step, row in zip(contract.steps, horizons, strict=True)
    }
    # The draft has not been published or issued. Only this complete full-H original is bound.
    return freeze_original_visual_plan(**{**original.freeze_inputs(), "requirements": requirements})


def _collection_checkpoint(original, index, state, now):
    """复用原有有序采集检查点，仅生成来源数据。"""
    contract = original.contract
    source_step = contract.steps[index]
    checkpoint = ExecutionCheckpoint(
        checkpoint_id=f"{original.identity.plan_id}:checkpoint-{index}",
        task_id=contract.task_id,
        plan_id=original.identity.plan_id,
        plan_version=1,
        command_seq=1,
        robot_id=original.identity.robot_id,
        current_step_id=source_step.step_id,
        current_step_index=index,
        completed_step_ids=[s.step_id for s in contract.steps[:index]],
        pending_step_ids=[s.step_id for s in contract.steps[index:]],
        created_at=now,
        updated_at=now,
        robot_state=state.model_dump(mode="json"),
        execution_state="STARTED",
    )
    checkpoint.checkpoint_hash = checkpoint_digest(checkpoint)
    return checkpoint


def grounded_collection_step(
    original: VisualOriginalPlan,
    *,
    index: int,
    observation: RGBDObservation,
    state: RobotState,
    tracker: OpenCVTargetTracker,
    evidence: Mapping[str, Any],
    geometry: Mapping[str, Any],
    evidence_sink: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[
    TaskContract, TaskStep, StepGroundingBinding, OnlineEvidenceSnapshot, ExecutionCheckpoint
]:
    inputs = collection_grounding_inputs(
        observation,
        state,
        geometry,
        tracker=tracker,
        evidence=evidence,
        source_hashes=original.source_hashes,
    )
    contract = original.contract
    source_step = contract.steps[index]
    now = datetime.now(UTC)
    checkpoint = _collection_checkpoint(original, index, state, now)
    online = OnlineEvidenceSnapshot(
        observation, state, tracker.facts(observation, state), 1, 1, checkpoint.checkpoint_hash
    )
    tracker_evaluated_at = tracker.last_binding_evaluated_at
    policy = DeterministicGroundingPolicy(
        policy_id="rgbd-top-grasp-v1",
        version="worker-rgbd-top-grasp-v1",
        source_hashes=original.source_hashes,
        tcp_velocity=min(0.15, contract.safety_constraints.max_tcp_velocity),
        acceleration=0.5,
        clearance_m=0.10,
        minimum_height_m=max(0.16, contract.safety_constraints.minimum_safe_height),
    )
    step = source_step.model_copy(
        update=dict(
            parameters=_resolved_parameters(source_step, original, online, inputs, policy),
            preconditions=[],
            success_conditions=[],
        ),
        deep=True,
    )
    binding = bind_step_grounding(
        original,
        original_step_id=source_step.step_id,
        grounded_step=step,
        online=online,
        source_checkpoint=checkpoint,
        current_identity=original.identity,
        owner_revision=index + 1,
        state_generation=index + 1,
        grounding_inputs=inputs,
        grounding_policy=policy,
        now=now,
    )
    executed = contract.model_copy(
        update={"steps": [step if s.step_id == step.step_id else s for s in contract.steps]},
        deep=True,
    )
    if evidence_sink is not None:
        evidence_sink(
            dict(
                original_plan_sha256=original.digest(),
                identity=original.identity.to_payload(),
                index=index,
                step_id=source_step.step_id,
                source_generation=digest(dict(original.source_hashes)),
                checkpoint=checkpoint.model_dump(mode="json"),
                checkpoint_sha256=checkpoint.checkpoint_hash,
                binding_now=now.isoformat(),
                tracker_evaluated_at=tracker_evaluated_at.isoformat(),
                inputs=inputs.to_payload(),
                inputs_sha256=inputs.digest(),
                policy=policy.to_payload(),
                policy_sha256=policy.digest(),
                binding=binding.to_payload(),
                binding_sha256=binding.digest(),
                executed_contract=executed.model_dump(mode="json"),
                grounded_step=step.model_dump(mode="json"),
                online=dict(
                    robot_state=state.model_dump(mode="json"),
                    visual_facts=online.visual_facts,
                    plan_version=online.plan_version,
                    command_seq=online.command_seq,
                    context_hash=online.context_hash,
                ),
                observation_id=observation.observation_id,
                checksum_sha256=observation.checksum_sha256,
            )
        )
    return executed, step, binding, online, checkpoint


def collection_unknown_row(
    *,
    phase: str,
    skill: str,
    condition: str,
    verdict: Mapping[str, Any],
    facts: Mapping[str, Any],
    holding: bool,
    tcp_reached: bool,
    full_horizon: bool,
    nominal_release: bool,
    released: bool,
    tracker_has_no_held: bool,
    depth_bound_missing: bool,
) -> str | None:
    """Pure exact R441 lookup; this returns a row name, never an execution capability."""
    if verdict.get("status") != "UNKNOWN":
        return None
    reasons = tuple(verdict.get("reasons", ()))
    terminal = phase == "TERMINAL" or phase == "POST" and skill == "RETREAT"
    if condition == "object_held" and phase == "POST" and skill == "LIFT":
        if (
            condition not in facts
            and tracker_has_no_held
            and holding
            and tcp_reached
            and full_horizon
            and reasons
            in {
                ("visual_fact_missing_or_untrusted_source",),
                ("visual_fact_missing_or_untrusted_source", "robot_state_condition_satisfied"),
            }
        ):
            return "POST_LIFT_HELD_INTERFACE"
        return None
    actual_condition = "object_inside_target_region" if condition == "object_placed" else condition
    fact = facts.get(actual_condition, {})
    if not isinstance(fact, Mapping) or fact.get("value") is not None:
        return None
    depth = (
        tuple(fact.get("reasons", ())) == ("calibrated_depth_error_bound_missing",)
        and depth_bound_missing
    )
    continuity = set(fact.get("reasons", ())) == {
        "inter_frame_motion_not_bounded",
        "quarter_turn_symmetry_unresolved",
    }
    if condition == "object_placed":
        return (
            "TERMINAL_PLACED_DEPTH"
            if terminal
            and full_horizon
            and released
            and depth
            and reasons == ("visual_fact_not_boolean", "robot_state_condition_satisfied")
            else None
        )
    if reasons != ("visual_fact_not_boolean",):
        return None
    if (
        phase == "PRE"
        and skill in {"MOVE_ABOVE", "APPROACH", "GRASP"}
        and condition == "target_reachable"
        and depth
        and fact.get("measured_values", {}).get("stationary_support") is True
    ):
        return "PRE_INITIAL_REACHABLE_DEPTH"
    if phase == "POST" and skill == "LIFT" and holding and tcp_reached and full_horizon:
        if condition in {"object_lifted", "object_stable"} and depth:
            return "POST_LIFT_DEPTH"
        if condition == "object_stable" and continuity:
            return "POST_LIFT_CONTINUITY"
    if (
        phase == "PRE"
        and skill == "RELEASE"
        and condition == "object_inside_target_region"
        and depth
        and holding
        and nominal_release
    ):
        return "PRE_RELEASE_NOMINAL_DEPTH"
    if terminal and full_horizon and released:
        if condition in {"object_inside_target_region", "placement_stable"} and depth:
            return "TERMINAL_DEPTH"
        if condition == "placement_stable" and continuity:
            return "TERMINAL_CONTINUITY"
    return None
@dataclass(frozen=True, slots=True)
class RegisteredCollectionGroundingPreviewV1:
    """仅供准备的当前几何结果，不产生动作绑定或准入事实。"""

    status: Literal["DERIVED", "UNKNOWN"]
    reason: str
    track: RegisteredObjectTrackV1
    evaluated_at: datetime
    source_sha256: str
    registration_sha256: str
    grasp_tcp_world_m: tuple[float, float, float] | None
    object_center_world_m: tuple[float, float, float] | None
    rotation_object_to_world: tuple[float, ...] | None
    destination_world_m: tuple[float, float, float] | None
    destination_observation_id: str | None
    destination_observation_checksum_sha256: str | None
    schema_version: Literal["native.collection.registered-preview.v1"] = (
        "native.collection.registered-preview.v1"
    )
    prepare_only: Literal[True] = True
    execution_allowed: Literal[False] = False
    geometry_basis: Literal["REGISTERED_RIGID_MODEL"] = "REGISTERED_RIGID_MODEL"
    region_basis: Literal["RGBD_COLOR_REGION_UNCALIBRATED"] = "RGBD_COLOR_REGION_UNCALIBRATED"
    object_surface_visibility: Literal["UNKNOWN"] = "UNKNOWN"
    geometric_error_bound_m: None = None
    region_geometric_error_bound_m: None = None
    native_authority: Literal["UNAVAILABLE"] = "UNAVAILABLE"

    def to_payload(self) -> dict[str, Any]:
        """导出独立JSON值，保留版本、推导来源及不可执行标记。"""
        payload = asdict(self)
        payload["track"] = self.track.to_payload()
        return json.loads(
            json.dumps(payload, default=lambda value: value.isoformat(), allow_nan=False)
        )

    def digest(self) -> str:
        """将准备接口的当前帧、来源和未知量一起绑定。"""
        return digest(self.to_payload())


class RegisteredCollectionPreviewTrackerV1:
    """组合自有标记跟踪器和完整颜色参考，颜色只用于当前目标区域。"""

    def __init__(
        self,
        observation: RGBDObservation,
        registration: NativeGeometryRegistration,
        *,
        source_root: Path,
        source_hashes: Mapping[str, str],
    ) -> None:
        self._provider = RegisteredObjectTrackerV1(
            observation, registration, source_root=source_root, source_hashes=source_hashes
        )
        reference = RGBDObservation.model_validate(observation.model_dump())
        self._region_tracker, _ = bootstrap_collection_tracker(
            reference, self._provider._registration.to_payload()
        )
        assert self._region_tracker.destination is not None
        footprint = np.asarray(self._region_tracker.destination["mask"], dtype=bool)
        self._reference_region_footprint = (tuple(footprint.shape), footprint.tobytes(order="C"))
        reason, _ = self._provider._recheck_current(reference)
        if reason:
            raise ValueError("registered collection bootstrap unavailable: " + reason)


def bootstrap_registered_collection_tracker_v1(
    observation: RGBDObservation,
    registration: NativeGeometryRegistration,
    *,
    source_root: Path,
    source_hashes: Mapping[str, str],
) -> RegisteredCollectionPreviewTrackerV1:
    """用完整颜色参考创建准备接口；不配置旧执行器或发放动作权限。"""
    return RegisteredCollectionPreviewTrackerV1(
        observation, registration, source_root=source_root, source_hashes=source_hashes
    )


def registered_collection_grounding_preview_v1(
    tracker: RegisteredCollectionPreviewTrackerV1,
    observation: RGBDObservation,
    robot_state: RobotState,
) -> RegisteredCollectionGroundingPreviewV1:
    """结合当前标记模型姿态和独立完整区域，只返回不可执行的准备结果。"""
    if (
        type(tracker) is not RegisteredCollectionPreviewTrackerV1
        or type(tracker._provider) is not RegisteredObjectTrackerV1
        or type(tracker._region_tracker) is not OpenCVTargetTracker
        or type(observation) is not RGBDObservation
        or type(robot_state) is not RobotState
    ):
        raise TypeError("exact owned registered collection tracker, observation and state required")
    return _shared_registered_collection_preview(tracker, observation, robot_state)


def _shared_registered_collection_preview(tracker, observation, robot_state):
    """共用纯计算；live入口与独立历史adapter各自验证其来源类型。"""
    current = RGBDObservation.model_validate(observation.model_dump())
    state = RobotState.model_validate(robot_state.model_dump())
    track = tracker._provider.update(current)
    reason = track.reason if track.status != "DERIVED" else None
    region = None
    if reason is None and (not state.connected or state.estop_engaged or state.collision_detected):
        reason = "current_robot_state_unavailable"
    if reason is None:
        region, region_reason = tracker._region_tracker._geometry(
            current,
            tracker._region_tracker.destination_color,
            target=False,
            occlusion_geometry=None,
        )
        if region is None:
            reason = "independent_current_region_unavailable:" + str(region_reason)
        else:
            footprint = np.asarray(region["mask"], dtype=bool)
            if (tuple(footprint.shape), footprint.tobytes(order="C")) != (
                tracker._reference_region_footprint
            ):
                reason = "independent_current_region_footprint_changed"
    post_reason, evaluated_at = tracker._provider._recheck_current(current)
    reason = post_reason or reason
    if reason:
        track = replace(
            track,
            status="UNKNOWN",
            reason=reason,
            geometry=None,
            evaluated_at=evaluated_at,
            wrapper_freshness="REJECTED" if post_reason else track.wrapper_freshness,
        )
    geometry = None if reason else track.geometry
    if geometry is not None:
        assert region is not None
    return RegisteredCollectionGroundingPreviewV1(
        status="UNKNOWN" if reason else "DERIVED",
        reason=reason or "prepare_only_uncalibrated_registered_geometry",
        track=track,
        evaluated_at=evaluated_at,
        source_sha256=track.source_sha256,
        registration_sha256=track.registration_sha256,
        grasp_tcp_world_m=None if geometry is None else geometry.grasp_tcp_world_m,
        object_center_world_m=None if geometry is None else geometry.object_center_world_m,
        rotation_object_to_world=None if geometry is None else geometry.rotation_object_to_world,
        destination_world_m=None if geometry is None else tuple(float(v) for v in region["center"]),
        destination_observation_id=None if geometry is None else current.observation_id,
        destination_observation_checksum_sha256=None
        if geometry is None
        else current.checksum_sha256,
    )


def registered_collection_step(
    original, *, index, observation, state, tracker, lease_source, evidence_sink=None
):
    """把当前模型坐标绑定到原采集步骤；原条件仍由采集应用核验。"""
    from cloud_edge_robot_arm.vision.owner_registration import (
        RegisteredCollectionStepBinding,
        RegisteredGroundingFrameInputs,
        RegisteredGroundingPolicy,
        prepare_registered_step_binding,
    )

    started = datetime.now(UTC)
    if (
        type(original) is not VisualOriginalPlan
        or type(index) is not int
        or not (0 <= index < len(original.contract.steps))
    ):
        raise ValueError("exact original collection pending index required")
    if type(tracker) is not RegisteredCollectionPreviewTrackerV1:
        raise TypeError("owned live registered collection tracker required")
    if dict(original.source_hashes) != tracker._provider._source_hashes:
        raise ValueError("registered collection source inventory differs from original")
    contract = original.contract
    source_step = contract.steps[index]
    checkpoint = _collection_checkpoint(original, index, state, started)
    preview = registered_collection_grounding_preview_v1(tracker, observation, state)
    if preview.status != "DERIVED":
        raise ValueError("registered collection geometry unavailable: " + preview.reason)
    inputs = RegisteredGroundingFrameInputs.from_preview(
        preview, observation, tracker._provider._registration
    )
    policy = RegisteredGroundingPolicy.for_original(original, original.source_hashes)
    online = OnlineEvidenceSnapshot(
        observation,
        state,
        {},
        contract.plan_version,
        contract.command_seq,
        checkpoint.checkpoint_hash,
    )
    now = datetime.now(UTC)
    prepared = prepare_registered_step_binding(
        original,
        original_step_id=source_step.step_id,
        online=online,
        source_checkpoint=checkpoint,
        current_identity=original.identity,
        owner_revision=index + 1,
        state_generation=index + 1,
        grounding_inputs=inputs,
        grounding_policy=policy,
        lease_source=lease_source,
        now=now,
    )
    binding = RegisteredCollectionStepBinding.from_prepared(
        prepared, collection_policy_id="registered-model-collection-v1"
    )
    step = binding.grounded_step
    executed = contract.model_copy(
        update={"steps": [step if s.step_id == step.step_id else s for s in contract.steps]},
        deep=True,
    )
    reason, finished = tracker._provider._recheck_current(observation)
    if reason or not observation.captured_at <= started <= now <= finished < binding.valid_until:
        raise ValueError("registered collection final frame/deadline invalid")
    if evidence_sink is not None:
        evidence_sink(
            dict(
                schema_version="native.registered.grounding.v1",
                original_plan_sha256=original.digest(),
                identity=original.identity.to_payload(),
                index=index,
                step_id=source_step.step_id,
                source_generation=digest(dict(original.source_hashes)),
                checkpoint=checkpoint.model_dump(mode="json"),
                checkpoint_sha256=checkpoint.checkpoint_hash,
                binding_now=now.isoformat(),
                tracker_evaluated_at=preview.evaluated_at.isoformat(),
                inputs=inputs.to_payload(),
                inputs_sha256=inputs.digest(),
                policy=policy.to_payload(),
                policy_sha256=policy.digest(),
                binding=binding.to_payload(),
                binding_sha256=binding.digest(),
                lease_source=lease_source.to_payload(),
                registered_preview=preview.to_payload(),
                executed_contract=executed.model_dump(mode="json"),
                grounded_step=step.model_dump(mode="json"),
                online=dict(
                    robot_state=state.model_dump(mode="json"),
                    visual_facts={},
                    plan_version=online.plan_version,
                    command_seq=online.command_seq,
                    context_hash=online.context_hash,
                ),
                observation_id=observation.observation_id,
                checksum_sha256=observation.checksum_sha256,
            )
        )
    return executed, step, binding, online, checkpoint
