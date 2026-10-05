"""One-episode visual orchestration using the existing safe physical skill executor.

Only RGB-D and robot proprioception reach online checks. Detached simulator truth
is accumulated for the independent evaluator, which runs after online termination.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import math
import time
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.auto_mode.runtime_events import (
    DecisionAction,
    DecisionEvent,
    DecisionEventKind,
)
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlannerDraft,
    SceneSummary,
)
from cloud_edge_robot_arm.contracts import Pose, RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionStatus,
    ConditionVerdict,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudgetState,
    route_verification,
)
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.edge.safety.models import HardSafetyLimits
from cloud_edge_robot_arm.edge.safety.policy import OperationalSafetyPolicy, merge_constraints
from cloud_edge_robot_arm.edge.safety.shield import SafetyConfig, SafetyShield, _policy_hash
from cloud_edge_robot_arm.research.clock import ExperimentClock
from cloud_edge_robot_arm.research.supervision import PeriodicSupervision
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_episode,
    sample_physical_observation,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_observation
from cloud_edge_robot_arm.vision.evaluation import (
    ExecutionPolicy,
    VisualEpisodeOutcome,
    combine_outcome,
    write_json,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import (
    RGBDModelCallFailed,
    RGBDModelUnavailable,
    RGBDPlannerAdapter,
)
from cloud_edge_robot_arm.vision.top_grasp import (
    calibration_asset_sha256,
    matches_calibrated_gripper,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker
    from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

TRACK_SUPPORT_TOLERANCE_M = 0.018
TRACK_FOREGROUND_MARGIN_M = 0.005
TRACK_MIN_FOREGROUND_FRACTION = 0.8
TRACK_BOUNDARY_DEPTH_JUMP_M = 0.008
TRACK_MIN_COMPONENT_PIXELS = 8
LIFT_OBSERVATION_HOLD_S = 0.6
LIFT_OBSERVATION_INTERVAL_S = 0.1
LIFT_VISUAL_STABILITY_TOLERANCE_M = 0.012
LIFT_MIN_VISUAL_HEIGHT_M = 0.05


class _EpisodeStopped(RuntimeError):
    pass


def research_safety_shield(timeout_s: float = 120.0) -> SafetyShield:
    """The explicit MuJoCo envelope matches T5 independent physical scoring."""
    hard = HardSafetyLimits(
        workspace_x_min=-0.85,
        workspace_x_max=0.85,
        workspace_y_min=-0.85,
        workspace_y_max=0.85,
        workspace_z_min=0.0,
        workspace_z_max=1.2,
        max_reach_m=0.85,
        max_joint_velocity=3.0,
        watchdog_timeout_ms=math.ceil(timeout_s * 1000),
    )
    policy = OperationalSafetyPolicy(policy_version="mujoco-t7-v1")
    return SafetyShield(
        SafetyConfig(
            hard,
            policy,
            merge_constraints(hard, policy),
            policy.policy_version,
            _policy_hash(policy, hard),
        )
    )


def _pixels(observation: RGBDObservation) -> np.ndarray:
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        return np.asarray(image.convert("RGB"), dtype=float)


class RGBDTargetTracker:
    """Retain an initially unique RGB-D identity through measured tool occlusion.

    Split color support is accepted only inside its predicted historical support
    and when current metric depth proves the missing pixels are foreground
    occlusion. Transport prediction uses bilateral contact plus TCP displacement.
    """

    def __init__(self, observation: RGBDObservation, evidence: dict[str, Any]) -> None:
        rgb = _pixels(observation)
        self.target_pixel = tuple(evidence["original_pixel_target"])
        self.destination_pixel = tuple(evidence["original_pixel_destination"])
        self.target_color = self._color(rgb, self.target_pixel)
        self.destination_color = self._color(rgb, self.destination_pixel)
        self.support_z = float(evidence["top_grasp_support_height_m"])
        self.initial = self._geometry(observation, self.target_color)
        self.destination = self._geometry(observation, self.destination_color)
        if self.initial is None or self.destination is None:
            raise ValueError("RGB-D target or destination color support is ambiguous")
        target_coords = self._initial_support(observation, self.target_color)
        region_coords = self._initial_support(observation, self.destination_color)
        assert target_coords is not None and region_coords is not None
        self._target_support = self._world_points(observation, target_coords[0])
        self._region_support = self._world_points(observation, region_coords[0])
        self._attached_tcp: np.ndarray | None = None
        self._offset = np.zeros(3)
        self._attachment_confirmed = False

    @staticmethod
    def _color(rgb: np.ndarray, pixel: tuple[int, ...]) -> np.ndarray:
        x, y = pixel
        color = np.median(rgb[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2], axis=(0, 1))
        if color.max() - color.min() < 35:
            raise ValueError("scoped tracker requires a distinguishable colored region")
        return cast(np.ndarray, color / max(float(color.sum()), 1.0))

    @staticmethod
    def _mask(observation: RGBDObservation, color: np.ndarray) -> np.ndarray:
        rgb = _pixels(observation)
        chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1.0)
        mask = (np.linalg.norm(chroma - color, axis=2) < 0.14) & (
            rgb.max(axis=2) - rgb.min(axis=2) > 30
        )
        depth = np.asarray(observation.depth_values()).reshape(mask.shape)
        valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(mask.shape)
        return cast(np.ndarray, mask & (depth > 0) & np.isfinite(depth) & (valid > 0))

    @staticmethod
    def _components(mask: np.ndarray) -> list[np.ndarray]:
        remaining = set(zip(*np.nonzero(mask), strict=True))
        components = []
        while remaining:
            stack = [remaining.pop()]
            component = []
            while stack:
                y, x = stack.pop()
                component.append((y, x))
                for neighbor in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
            if len(component) >= TRACK_MIN_COMPONENT_PIXELS:
                components.append(np.asarray(component, dtype=int))
        return components

    @staticmethod
    def _world_points(observation: RGBDObservation, coordinates: np.ndarray) -> np.ndarray:
        ys, xs = coordinates.T
        depth = np.asarray(observation.depth_values()).reshape(
            observation.height, observation.width
        )
        fx, fy, cx, cy = observation.intrinsics
        z = depth[ys, xs]
        points = np.stack(((xs - cx) * z / fx, (ys - cy) * z / fy, z, np.ones_like(z)))
        world = np.asarray(observation.camera_to_world).reshape(4, 4) @ points
        return cast(np.ndarray, world[:3].T)

    @classmethod
    def _measure(cls, observation: RGBDObservation, coordinates: np.ndarray) -> dict[str, Any]:
        points = cls._world_points(observation, coordinates)
        ys, xs = coordinates.T
        index = int(np.argmin((xs - np.median(xs)) ** 2 + (ys - np.median(ys)) ** 2))
        return {
            "pixel": [int(xs[index]), int(ys[index])],
            "center": np.median(points, axis=0).tolist(),
            "min": points.min(axis=0).tolist(),
            "max": points.max(axis=0).tolist(),
            "visible_pixels": len(coordinates),
        }

    @classmethod
    def _filter_boundary_depth(
        cls,
        observation: RGBDObservation,
        mask: np.ndarray,
        coordinates: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
    ) -> tuple[np.ndarray, int] | None:
        points = cls._world_points(observation, coordinates)
        inside = ((points >= lower) & (points <= upper)).all(axis=1)
        if inside.all():
            return coordinates, 0
        good = np.zeros(mask.shape, dtype=bool)
        good[coordinates[inside, 0], coordinates[inside, 1]] = True
        depth = np.asarray(observation.depth_values()).reshape(mask.shape)
        for y, x in coordinates[~inside]:
            boundary = any(
                not (0 <= a < observation.height and 0 <= b < observation.width) or not mask[a, b]
                for a, b in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
            )
            supported_jump = any(
                0 <= a < observation.height
                and 0 <= b < observation.width
                and good[a, b]
                and abs(depth[y, x] - depth[a, b]) > TRACK_BOUNDARY_DEPTH_JUMP_M
                for a in range(y - 1, y + 2)
                for b in range(x - 1, x + 2)
            )
            if not boundary or not supported_jump:
                return None
        # Only one-pixel boundary depth discontinuities are discarded. Interior
        # anomalies and independent out-of-support components remain UNKNOWN.
        return coordinates[inside], int((~inside).sum())

    @classmethod
    def _initial_support(
        cls, observation: RGBDObservation, color: np.ndarray
    ) -> tuple[np.ndarray, int] | None:
        mask = cls._mask(observation, color)
        components = cls._components(mask)
        if len(components) != 1:
            return None
        points = cls._world_points(observation, components[0])
        center_z = float(np.median(points[:, 2]))
        return cls._filter_boundary_depth(
            observation,
            mask,
            components[0],
            np.array([-np.inf, -np.inf, center_z - TRACK_SUPPORT_TOLERANCE_M]),
            np.array([np.inf, np.inf, center_z + TRACK_SUPPORT_TOLERANCE_M]),
        )

    @classmethod
    def _geometry(cls, observation: RGBDObservation, color: np.ndarray) -> dict[str, Any] | None:
        support = cls._initial_support(observation, color)
        if support is None or len(support[0]) < TRACK_MIN_COMPONENT_PIXELS:
            return None
        return {**cls._measure(observation, support[0]), "excluded_boundary_pixels": support[1]}

    def _track(
        self,
        observation: RGBDObservation,
        color: np.ndarray,
        reference: np.ndarray,
        offset: np.ndarray,
    ) -> dict[str, Any] | None:
        mask = self._mask(observation, color)
        components = self._components(mask)
        if not components:
            return None
        coordinates = np.concatenate(components)
        predicted = reference + offset
        filtered = self._filter_boundary_depth(
            observation,
            mask,
            coordinates,
            predicted.min(axis=0) - TRACK_SUPPORT_TOLERANCE_M,
            predicted.max(axis=0) + TRACK_SUPPORT_TOLERANCE_M,
        )
        if filtered is None or len(filtered[0]) < TRACK_MIN_COMPONENT_PIXELS:
            return None
        coordinates, excluded = filtered
        cleaned_mask = np.zeros(mask.shape, dtype=bool)
        cleaned_mask[coordinates[:, 0], coordinates[:, 1]] = True
        components = self._components(cleaned_mask)
        if not components:
            return None
        mask = cleaned_mask
        result = self._measure(observation, np.concatenate(components))
        audit: dict[str, Any] = {
            "component_sizes": [len(component) for component in components],
            "excluded_boundary_pixels": excluded,
            "boundary_exclusion_reason": "RGB_COLOR_EDGE_WITH_ADJACENT_DEPTH_DISCONTINUITY",
            "boundary_depth_jump_m": TRACK_BOUNDARY_DEPTH_JUMP_M,
            "predicted_displacement_m": offset.tolist(),
            "prediction_source": (
                "BILATERAL_CONTACT_AND_TCP_DISPLACEMENT"
                if self._attachment_confirmed and reference is self._target_support
                else "INITIAL_UNIQUE_RGBD_SUPPORT"
            ),
            "occlusion_verified": False,
        }
        if len(components) > 1:
            transform = np.asarray(observation.camera_to_world).reshape(4, 4)
            camera = (predicted - transform[:3, 3]) @ transform[:3, :3]
            if np.any(camera[:, 2] <= 0):
                return None
            fx, fy, cx, cy = observation.intrinsics
            xs = np.rint(fx * camera[:, 0] / camera[:, 2] + cx).astype(int)
            ys = np.rint(fy * camera[:, 1] / camera[:, 2] + cy).astype(int)
            inside = (xs >= 0) & (xs < observation.width) & (ys >= 0) & (ys < observation.height)
            if not inside.all():
                return None
            missing = ~mask[ys, xs]
            depth = np.asarray(observation.depth_values()).reshape(mask.shape)[ys, xs]
            foreground = (depth > 0) & (depth < camera[:, 2] - TRACK_FOREGROUND_MARGIN_M)
            missing_count = int(missing.sum())
            occluded_count = int((missing & foreground).sum())
            fraction = occluded_count / missing_count if missing_count else 0.0
            audit.update(
                missing_support_pixels=missing_count,
                foreground_occluded_pixels=occluded_count,
                foreground_fraction=fraction,
                foreground_depth_margin_m=TRACK_FOREGROUND_MARGIN_M,
                required_foreground_fraction=TRACK_MIN_FOREGROUND_FRACTION,
            )
            if not missing_count or fraction < TRACK_MIN_FOREGROUND_FRACTION:
                return None
            audit["occlusion_verified"] = True
        result["temporal_identity"] = audit
        return result

    def facts(
        self, observation: RGBDObservation, robot_state: RobotState | None = None
    ) -> dict[str, Any]:
        if (
            robot_state
            and robot_state.holding_object_id == "object"
            and not robot_state.gripper_open
        ):
            tcp = np.array([robot_state.tcp_pose.x, robot_state.tcp_pose.y, robot_state.tcp_pose.z])
            if self._attached_tcp is None:
                self._attached_tcp = tcp.copy()
            self._offset = tcp - self._attached_tcp
            self._attachment_confirmed = True
        target = self._track(observation, self.target_color, self._target_support, self._offset)
        destination = self._track(
            observation, self.destination_color, self._region_support, np.zeros(3)
        )
        if target is None:
            return {}
        assert self.initial is not None and self.destination is not None
        envelope = {
            "source": "rgbd_estimate",
            "observation_id": observation.observation_id,
            "target_id": "object",
            "identity_confirmed": True,
            "pixel": target["pixel"],
        }
        result = {"target_visible": {**envelope, "value": True, "measured_values": target}}
        unchanged = all(
            target["min"][i] >= self.initial["min"][i] - TRACK_SUPPORT_TOLERANCE_M
            and target["max"][i] <= self.initial["max"][i] + TRACK_SUPPORT_TOLERANCE_M
            for i in (0, 1)
        )
        result["target_reachable"] = {
            **envelope,
            "value": unchanged,
            "measured_values": {"stationary_support": unchanged},
        }
        if destination is not None:
            # Occluded support may omit the boundary; use independently established
            # initial region bounds only after current identity/depth verification.
            inside = all(
                target["min"][i] >= self.destination["min"][i] - 0.003
                and target["max"][i] <= self.destination["max"][i] + 0.003
                for i in (0, 1)
            )
            top_height = target["center"][2] - self.support_z
            initial_height = self.initial["center"][2] - self.support_z
            on_support = abs(top_height - initial_height) < 0.012
            result["object_inside_target_region"] = {
                **envelope,
                "value": inside and on_support,
                "measured_values": {
                    "inside_visible_region": inside,
                    "on_support": on_support,
                    "target": target,
                    "destination": destination,
                },
            }
        return result


def make_target_tracker(
    observation: RGBDObservation, evidence: dict[str, Any], policy: ExecutionPolicy
) -> RGBDTargetTracker | OpenCVTargetTracker:
    if policy.device_pipeline == "OPENCV":
        from cloud_edge_robot_arm.vision.online_intent import validate_grounded_colors
        from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

        tracker = OpenCVTargetTracker(observation, evidence)
        validate_grounded_colors(
            policy.instruction, tracker.target_color.tolist(), tracker.destination_color.tolist()
        )
        return tracker
    return RGBDTargetTracker(observation, evidence)


def terminal_conditions(policy: ExecutionPolicy) -> list[ConditionSpec]:
    checks = [
        ConditionSpec("object_inside_target_region", target_id="object"),
        ConditionSpec("gripper_released"),
        ConditionSpec("robot_in_safe_pose", tolerances={"minimum_safe_height": 0.08}),
    ]
    if policy.device_pipeline == "OPENCV":
        checks.append(ConditionSpec("placement_stable", target_id="object"))
    return checks


def validated_grounding_evidence(draft: PlannerDraft, policy: ExecutionPolicy) -> dict[str, Any]:
    """Check the complete selected calibration receipt before using its TCP offset."""
    evidence = draft.observation_evidence or {}
    if policy.role_binding is not None and (
        evidence.get("role_bundle_hash") != policy.role_binding.bundle.digest()
    ):
        raise ValueError("planner evidence differs from the selected role bundle")
    snapshot = evidence.get("model_snapshot")
    if evidence.get("model_snapshot_hash") != policy.model_snapshot_hash:
        raise ValueError("planner evidence differs from the selected model snapshot")
    if not isinstance(snapshot, dict) or (
        snapshot.get("grasp_profile") != evidence.get("grasp_profile")
    ):
        raise ValueError("grasp calibration differs from the selected model snapshot")
    if hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest() != (
        policy.model_snapshot_hash
    ):
        raise ValueError("planner snapshot evidence has changed")
    if evidence.get("top_grasp_offset_status") != "CALIBRATED_RGBD_TOP_GRASP_V1":
        raise ValueError("explicit calibrated RGB-D grasp TCP is required")
    asset_hash = calibration_asset_sha256(evidence.get("grasp_profile"))
    if asset_hash is None or evidence.get("grasp_calibration_asset_sha256") != asset_hash:
        raise ValueError("grasp calibration asset mismatch")
    Pose.model_validate(evidence["resolved_top_grasp_tcp"])
    Pose.model_validate(evidence["grounded_destination"])
    return evidence


def grounded_contract(
    draft: PlannerDraft, observation: RGBDObservation, policy: ExecutionPolicy
) -> TaskContract:
    """Bind validated planner intent to calibrated RGB-D geometry, not scene truth."""
    validated_grounding_evidence(draft, policy)
    if draft.parse_error or not draft.parsed_json or draft.parsed_json.get("_sentinel"):
        raise ValueError("planner did not produce an executable visual contract")
    now = datetime.now(UTC)
    payload = dict(draft.parsed_json)
    payload.update(
        task_id=observation.episode_id,
        plan_version=1,
        command_seq=1,
        timestamp=now,
        issued_at=now,
        valid_until=now + timedelta(seconds=policy.timeout_s),
    )
    payload["task_target"] = {
        **payload["task_target"],
        "object_id": "object",
        "target_region_id": "target_region",
    }
    contract = TaskContract.model_validate(payload)
    # HOME is optional in the frozen syntax. Its fixed controller speed cannot
    # consume a constrained intent, so omit it explicitly rather than claim it ran.
    core_steps = [step for step in contract.steps if step.skill.value != "HOME"]
    constraints = contract.safety_constraints.model_copy(update={"max_joint_velocity": 1.5})
    return contract.model_copy(update={"steps": core_steps, "safety_constraints": constraints})


def resolved_step(step: TaskStep, robot: MuJoCoSkillRobot, evidence: dict[str, Any]) -> TaskStep:
    """Only calibrated grasp TCP and measured destination support set physical goals."""
    grasp = Pose.model_validate(evidence["resolved_top_grasp_tcp"])
    destination = Pose.model_validate(evidence["grounded_destination"])
    support = float(evidence["top_grasp_support_height_m"])
    current = robot.get_state().tcp_pose
    skill = step.skill.value
    params: dict[str, Any] = {}
    target = None
    if skill in {"MOVE_ABOVE", "APPROACH", "GRASP"}:
        params["object_id"] = "object"
    if skill == "MOVE_ABOVE":
        target = Pose(x=grasp.x, y=grasp.y, z=max(0.16, grasp.z + 0.10))
    elif skill == "APPROACH":
        target = grasp
    elif skill in {"LIFT", "RETREAT"}:
        target = Pose(x=current.x, y=current.y, z=max(current.z + 0.10, 0.16))
        params["height_m" if skill == "LIFT" else "distance_m"] = target.z - current.z
    elif skill in {"MOVE_TO_REGION", "PLACE"}:
        params["region_id"] = "target_region"
        # Destination's visible floor height transports the calibrated center/TCP offset.
        z = (
            max(0.16, grasp.z + 0.10)
            if skill == "MOVE_TO_REGION"
            else destination.z + grasp.z - support
        )
        target = Pose(x=destination.x, y=destination.y, z=z)
    if target is not None:
        params["target_pose"] = target.model_dump()
        params.update(tcp_velocity=0.15, acceleration=0.5)
    timeout = 1000 if skill in {"GRASP", "RELEASE"} else 10000
    return step.model_copy(
        update={
            "parameters": params,
            "timeout_ms": timeout,
            "retry_limit": 0,
            "preconditions": [],
            "success_conditions": [],
        }
    )


class _VisualEpisode:
    supervision: PeriodicSupervision | None = None
    wait_clock: ExperimentClock | None = None
    _supervision_started = False
    worker_runtime: VisualWorkerRuntime | None = None

    def __init__(
        self,
        planner: RGBDPlannerAdapter,
        robot: MuJoCoSkillRobot,
        capture: MuJoCoCaptureSession,
        policy: ExecutionPolicy,
    ) -> None:
        if capture._backend is not robot._backend:
            raise ValueError("capture and skills must share the same backend")
        if policy.scope != "VISION_CLOSED_LOOP":
            raise ValueError("run_visual_episode requires VISION_CLOSED_LOOP scope")
        if policy.device_pipeline == "OPENCV":
            from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

            if type(policy.worker_runtime) is not VisualWorkerRuntime:
                raise ValueError("OpenCV execution requires a live visual worker runtime")
            if policy.worker_runtime.episode_id != robot._backend._episode_id:
                raise ValueError("worker runtime must belong to the actual shared backend episode")
            definition = policy.worker_runtime.bootstrap.definition
            if (
                definition.user_instruction != policy.instruction
                or definition.model_snapshot_hash != policy.model_snapshot_hash
                or policy.role_binding is None
                or definition.role_bundle_hash != policy.role_binding.bundle.digest()
            ):
                raise ValueError("policy differs from the original live worker source")
        snapshot = planner.model_snapshot
        if snapshot is None or snapshot.digest() != policy.model_snapshot_hash:
            raise ValueError("episode planner differs from the immutable model snapshot")
        if policy.role_binding is not None:
            policy.role_binding.validate(planner)
        self.planner, self.robot, self.capture, self.policy = planner, robot, capture, policy
        self.worker_runtime = policy.worker_runtime
        self.backend = robot._backend
        self.started_at = time.monotonic()
        self.deadline = self.started_at + policy.timeout_s
        if self.worker_runtime is not None:
            original_start = self.worker_runtime.source.task_started_at
            elapsed = (datetime.now(UTC) - original_start).total_seconds()
            if elapsed < 0:
                raise ValueError("original worker task clock is in the future")
            self.started_at -= elapsed
            self.deadline = min(
                self.deadline,
                self.started_at + self.worker_runtime.source.task_timeout_s,
            )
        self.budget = (
            self.worker_runtime.verification_state
            if self.worker_runtime is not None
            else VerificationBudgetState.start(policy.verification_budget)
        )
        self.records: list[dict[str, Any]] = []
        self.observation: RGBDObservation | None = None
        self.count = self.calls = self.actions = 0
        self.tracker: RGBDTargetTracker | OpenCVTargetTracker | None = None
        self.require_continuous_grasp = False
        self.shield = research_safety_shield(policy.timeout_s)
        if policy.raw_recorder is not None:
            from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3

            if (
                type(policy.raw_recorder) is not VisualRawRecorderV3
                or policy.raw_recorder.backend is not self.backend
                or policy.raw_recorder.capture_session is not capture
                or policy.raw_recorder.executor._robot is not robot
            ):
                raise ValueError(
                    "raw recorder must share the actual capture and sole skill executor"
                )
            self.executor = policy.raw_recorder.executor
        else:
            self.executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
        self.supervision: PeriodicSupervision | None = None
        self.wait_clock: ExperimentClock | None = None
        self._supervision_started = False
        self._state_version = 0
        self._plan_version = 0
        self._active_step_id = "planning"
        self._active_skill = "PLANNING"
        config = self.backend._config
        asset_hash = calibration_asset_sha256(snapshot.grasp_profile)
        if (
            asset_hash is None
            or config is None
            or (hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest() != asset_hash)
        ):
            raise ValueError("backend asset differs from calibrated upright-box profile")
        if not matches_calibrated_gripper(self.backend._model, snapshot.grasp_profile):
            raise ValueError("loaded gripper geometry differs from calibrated upright-box profile")
        if policy.advance_physics_during_wait:
            self.wait_clock = ExperimentClock(config.physics_dt_s, self.backend.step)
        if policy.supervision_period_s is not None:
            self.supervision = PeriodicSupervision(
                policy.supervision_period_s, self.supervise_frame, self.capture_supervision_frame
            )
        if policy.output_dir:
            policy.output_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                policy.output_dir / "policy.json",
                {
                    "instruction": policy.instruction,
                    "scope": policy.scope,
                    "timeout_s": policy.timeout_s,
                    "model_snapshot_hash": policy.model_snapshot_hash,
                    "device_pipeline": policy.device_pipeline,
                    "role_binding": policy.role_binding.evidence() if policy.role_binding else None,
                    "verification_budget": asdict(policy.verification_budget),
                    "supervision_period_s": policy.supervision_period_s,
                    "advance_physics_during_wait": policy.advance_physics_during_wait,
                    "safety_policy": self.shield.config.hard_limits.to_dict(),
                    "safety_policy_hash": self.shield.config.policy_hash,
                    "development_config": {
                        "track_support_tolerance_m": TRACK_SUPPORT_TOLERANCE_M,
                        "track_foreground_margin_m": TRACK_FOREGROUND_MARGIN_M,
                        "track_min_foreground_fraction": TRACK_MIN_FOREGROUND_FRACTION,
                        "track_boundary_depth_jump_m": TRACK_BOUNDARY_DEPTH_JUMP_M,
                        "track_min_component_pixels": TRACK_MIN_COMPONENT_PIXELS,
                        "lift_observation_hold_s": LIFT_OBSERVATION_HOLD_S,
                        "lift_observation_interval_s": LIFT_OBSERVATION_INTERVAL_S,
                        "lift_visual_stability_tolerance_m": LIFT_VISUAL_STABILITY_TOLERANCE_M,
                        "lift_min_visual_height_m": LIFT_MIN_VISUAL_HEIGHT_M,
                    },
                },
            )

    def validate_role_boundary(self) -> None:
        if self.policy.role_binding is not None:
            try:
                self.policy.role_binding.validate_execution_policy(self.policy)
                self.policy.role_binding.validate(self.planner)
            except (ValueError, OSError) as error:
                raise _EpisodeStopped("ROLE_BINDING_CHANGED") from error

    def worker_call(self, operation: Callable[[], Any]) -> Any:
        """Source failures stop the episode without disclosing repository/provider payloads."""
        try:
            return operation()
        except (ValueError, OSError, RuntimeError) as error:
            raise _EpisodeStopped("WORKER_RUNTIME_SOURCE_INVALID") from error

    def check_active(self) -> None:
        if self.policy.cancelled is not None and self.policy.cancelled():
            raise _EpisodeStopped("CANCELLED")
        runtime = self.worker_runtime
        if runtime is not None:
            if self.backend._episode_id != runtime.episode_id:
                raise _EpisodeStopped("WORKER_BACKEND_EPISODE_CHANGED")
            self.worker_call(lambda: runtime.check_active(self.robot.get_state()))
            self.budget = runtime.verification_state
        if self.budget.exhausted_reason is not None:
            raise _EpisodeStopped("VERIFICATION_BUDGET_EXHAUSTED")
        if datetime.now(UTC) >= self.budget.deadline_at:
            raise _EpisodeStopped("VERIFICATION_TIMEOUT")
        if time.monotonic() >= self.deadline:
            raise _EpisodeStopped("EPISODE_TIMEOUT")

    def recapture(
        self,
        *,
        advance_steps: int = 0,
        completion: Any = None,
        purpose: str = "AFTER_EFFECT",
    ) -> RGBDObservation:
        self.check_active()
        self.validate_role_boundary()
        if type(advance_steps) is not int or advance_steps < 0:
            raise ValueError("capture advance requires a nonnegative integer")
        previous = self.observation
        claim_id = None
        runtime = self.worker_runtime
        if runtime is not None:
            if completion is None:
                claim_id = self.worker_call(
                    lambda: runtime.reserve_capture(
                        self.robot.get_state(),
                        initial=previous is None,
                    )
                )
            else:
                claim_id = self.worker_call(
                    lambda: runtime.reserve_effect_capture(
                        completion,
                        self.robot.get_state(),
                        purpose=purpose,
                    )
                )
        if advance_steps:
            self.check_active()
            recorder = getattr(self.policy, "raw_recorder", None)
            raw_purpose = (
                {"POST_HOLD": "HOLD", "TERMINAL": "TERMINATION"}.get(
                    purpose,
                    "VERIFY_ADVANCE",
                )
                if completion is not None
                else "VERIFY_ADVANCE"
            )
            with recorder.purpose(raw_purpose) if recorder is not None else nullcontext():
                self.backend.step(steps=advance_steps)
        self.check_active()
        recorder = getattr(self.policy, "raw_recorder", None)
        observation = recorder.capture() if recorder is not None else self.capture.capture()
        self.check_active()
        self.validate_role_boundary()
        if previous is not None and (
            observation.episode_id != previous.episode_id
            or observation.frame_id == previous.frame_id
            or observation.captured_at <= previous.captured_at
        ):
            raise _EpisodeStopped("STALE_OR_FOREIGN_RECAPTURE")
        if runtime is not None:
            assert isinstance(claim_id, str)
            self.worker_call(
                lambda: runtime.complete_capture(
                    claim_id,
                    observation,
                    self.robot.get_state(),
                )
            )
            self.budget = runtime.verification_state
        self.observation = observation
        self.count += 1
        self.records.append({"layer": "OBSERVATION", **observation.evidence()})
        if self.policy.output_dir:
            save_observation(observation, self.policy.output_dir / "frames" / f"{self.count:03d}")
        return observation

    def worker_route(
        self,
        phase: str,
        contract: TaskContract,
        step: TaskStep,
        completion: Any = None,
    ) -> DecisionAction:
        """Let the repository evaluate the complete registered requirement set."""
        assert self.worker_runtime is not None and self.observation is not None
        runtime = self.worker_runtime
        self.check_active()
        self.validate_role_boundary()
        publication = self.worker_runtime.publication
        state = self.robot.get_state()
        online = OnlineEvidenceSnapshot(
            self.observation,
            state,
            self.tracker.facts(self.observation, state) if self.tracker is not None else {},
            contract.plan_version,
            contract.command_seq,
            publication.checkpoint.checkpoint_hash,
        )
        result = self.worker_call(
            lambda: runtime.route(
                online,
                step_id=step.step_id,
                phase=phase,
                execution_contract=contract,
                completion=completion,
            )
        )
        self.records.append(
            {
                "layer": "WORKER_CANONICAL_VERIFICATION",
                "phase": phase,
                "source_record": result.record.to_payload(),
                "write_disposition": result.write_disposition,
                "execution_admitted": False,
            }
        )
        if result.record.route != "STOP":
            self.worker_call(lambda: runtime.check_active(self.robot.get_state()))
        self.validate_role_boundary()
        self.budget = self.worker_runtime.verification_state
        return DecisionAction(result.record.route)

    def verify_worker(
        self,
        phase: str,
        contract: TaskContract,
        step: TaskStep,
        completion: Any = None,
    ) -> bool:
        while True:
            action = self.worker_route(phase, contract, step, completion)
            if action == DecisionAction.CONTINUE:
                return True
            if action != DecisionAction.REOBSERVE:
                return False
            self.recapture(advance_steps=1)

    def prepare_worker_step(
        self,
        step: TaskStep,
        draft: PlannerDraft,
    ) -> tuple[TaskContract, TaskStep]:
        """Resolve a fresh frame while preserving the immutable original action policy."""
        from cloud_edge_robot_arm.vision.owner_registration import (
            DeterministicGroundingPolicy,
            GroundingFrameInputs,
            _resolved_parameters,
            bind_step_grounding,
        )
        from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

        assert self.worker_runtime is not None and self.tracker is not None
        assert self.observation is not None
        runtime = self.worker_runtime
        if not isinstance(self.tracker, OpenCVTargetTracker):
            raise _EpisodeStopped("WORKER_DEVICE_TRACKER_CHANGED")
        tracker = self.tracker
        self.check_active()
        self.validate_role_boundary()
        evidence = validated_grounding_evidence(draft, self.policy)
        original = self.worker_runtime.original
        publication = self.worker_runtime.publication
        state = self.robot.get_state()
        facts = self.tracker.facts(self.observation, state)
        target = facts.get("target_visible", {})
        if target.get("value") is not True:
            raise _EpisodeStopped("WORKER_FRESH_GROUNDING_UNAVAILABLE")
        # Association remains anchored to the original RGB-D identity; coordinate
        # values come from this frame, including the currently observed region.
        target_geometry, _ = tracker._geometry(
            self.observation,
            tracker.target_color,
            target=True,
        )
        region, _ = tracker._geometry(
            self.observation,
            tracker.destination_color,
            target=False,
            occlusion_geometry=target_geometry,
        )
        if target_geometry is None or region is None or self.tracker.initial is None:
            raise _EpisodeStopped("WORKER_FRESH_GROUNDING_UNAVAILABLE")
        center = target_geometry["center"]
        calibrated_tcp = Pose.model_validate(evidence["resolved_top_grasp_tcp"])
        offset = calibrated_tcp.z - float(self.tracker.initial["center"][2])
        inputs = GroundingFrameInputs(
            observation_id=self.observation.observation_id,
            observation_checksum_sha256=self.observation.checksum_sha256,
            episode_id=original.identity.episode_id,
            calibration_version=self.observation.calibration_version or "",
            grasp_tcp={"x": center[0], "y": center[1], "z": center[2] + offset},
            destination=dict(zip("xyz", region["center"], strict=True)),
            support_height_m=float(evidence["top_grasp_support_height_m"]),
            source_hashes=original.source_hashes,
        )
        policy = DeterministicGroundingPolicy(
            policy_id="rgbd-top-grasp-v1",
            version="worker-rgbd-top-grasp-v1",
            source_hashes=original.source_hashes,
            tcp_velocity=min(0.15, original.contract.safety_constraints.max_tcp_velocity),
            acceleration=0.5,
            clearance_m=0.10,
            minimum_height_m=max(0.16, original.contract.safety_constraints.minimum_safe_height),
        )
        online = OnlineEvidenceSnapshot(
            self.observation,
            state,
            facts,
            original.contract.plan_version,
            original.contract.command_seq,
            publication.checkpoint.checkpoint_hash,
        )
        source_step = original.requirements[step.step_id].original_step
        grounded = source_step.model_copy(
            update={
                "parameters": _resolved_parameters(source_step, original, online, inputs, policy),
                # Canonical checks are retained in original.requirements and evaluated
                # by the durable router. The executor consumes this checked view.
                "preconditions": [],
                "success_conditions": [],
            },
            deep=True,
        )
        binding = bind_step_grounding(
            original,
            original_step_id=step.step_id,
            grounded_step=grounded,
            online=online,
            source_checkpoint=publication.checkpoint,
            current_identity=original.identity,
            owner_revision=publication.owner_revision,
            state_generation=publication.state_generation + 1,
            grounding_inputs=inputs,
            grounding_policy=policy,
            now=datetime.now(UTC),
        )
        self.worker_call(lambda: runtime.publish_grounding(binding, state))
        self.records.append(
            {
                "layer": "WORKER_FRESH_GROUNDING",
                "binding": binding.to_payload(),
                "execution_admitted": False,
            }
        )
        self._worker_draft = draft
        self._worker_grounding = binding
        contract = original.contract.model_copy(
            update={
                "steps": [
                    grounded if item.step_id == grounded.step_id else item
                    for item in original.contract.steps
                ],
            },
            deep=True,
        )
        return contract, grounded

    def verify(
        self,
        conditions: list[ConditionSpec],
        kind: DecisionEventKind,
        extra: dict[str, Any] | None = None,
        facts_transform: Callable[[RGBDObservation, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> bool:
        while True:
            self.check_active()
            self.validate_role_boundary()
            assert self.observation is not None
            facts = (
                self.tracker.facts(self.observation, self.robot.get_state()) if self.tracker else {}
            )
            if facts_transform is not None:
                facts = facts_transform(self.observation, facts)
            snapshot = OnlineEvidenceSnapshot(
                self.observation,
                self.robot.get_state(),
                facts,
                1,
                1,
                self.policy.role_binding.bundle.digest()
                if self.policy.role_binding
                else self.policy.model_snapshot_hash,
            )
            verdicts = evaluate_conditions(conditions, snapshot)
            action = self.route(verdicts, kind, {**(extra or {}), "visual_facts": facts})
            if action == DecisionAction.CONTINUE:
                return True
            if action != DecisionAction.REOBSERVE:
                return False
            # A real sensor capture changes observation ID. No crop/reuse can satisfy this.
            self.backend.step(steps=1)
            self.recapture()

    def route(
        self,
        verdicts: list[ConditionVerdict],
        kind: DecisionEventKind,
        extra: dict[str, Any] | None = None,
    ) -> DecisionAction:
        assert self.observation is not None
        status = (
            ConditionStatus.UNKNOWN
            if any(v.status == ConditionStatus.UNKNOWN for v in verdicts)
            else ConditionStatus.FAIL
            if any(v.status == ConditionStatus.FAIL for v in verdicts)
            else ConditionStatus.PASS
            if verdicts
            else ConditionStatus.UNKNOWN
        )
        if kind == DecisionEventKind.RESULT_VERIFIED and status != ConditionStatus.PASS:
            kind = DecisionEventKind.VERIFICATION_FAILED
        event = DecisionEvent(
            str(uuid.uuid4()),
            kind,
            datetime.now(UTC),
            self.observation.observation_id,
            False,
            status,
        )
        before = asdict(self.budget)
        action = route_verification(
            verdicts,
            self.budget,
            {DecisionAction.CONTINUE, DecisionAction.REOBSERVE, DecisionAction.STOP},
        )
        self.records.append(
            {
                "layer": "ONLINE_VERIFICATION",
                "event": asdict(event),
                "conditions": [asdict(v) for v in verdicts],
                "route": action.value,
                "budget_before": before,
                "budget_after": asdict(self.budget),
                **(extra or {}),
            }
        )
        if self.policy.output_dir:
            write_json(
                self.policy.output_dir / "verification-state.json",
                {
                    "episode_id": self.observation.episode_id,
                    "observation_id": self.observation.observation_id,
                    "event_id": event.event_id,
                    "budget": asdict(self.budget),
                    "latest_verification": self.records[-1],
                },
            )
        return action

    def plan(self) -> PlannerDraft:
        from cloud_edge_robot_arm.vision.request_control import bounded_model_call

        runtime = self.worker_runtime
        while True:
            self.check_active()
            self.validate_role_boundary()
            assert self.observation is not None
            request = InitialPlanningRequest(
                request_id="visual-episode",
                user_instruction=self.policy.instruction,
                observation=self.observation,
                scene=SceneSummary(scene_version=1, updated_at=self.observation.captured_at),
            )
            claim_id = None
            if runtime is not None:
                claim_id = self.worker_call(lambda: runtime.reserve_plan(self.robot.get_state()))
            self.calls += 1
            started = time.monotonic()
            if self.wait_clock is not None:
                self.wait_clock.begin_wait()
            draft = bounded_model_call(
                partial(self.planner.plan, request),
                timeout_s=max(
                    0.001,
                    min(
                        self.deadline - started,
                        (self.budget.deadline_at - datetime.now(UTC)).total_seconds(),
                    ),
                ),
                cancelled=self.policy.cancelled,
                resource_key=self.planner.base_url,
                on_wait=self.wait_clock.advance_wait if self.wait_clock is not None else None,
            )
            self.check_active()
            self.validate_role_boundary()
            if self.policy.role_binding is not None:
                draft.observation_evidence = {
                    **(draft.observation_evidence or {}),
                    "role_bundle_hash": self.policy.role_binding.bundle.digest(),
                    "role_binding": self.policy.role_binding.evidence(),
                }
            self.records.append(
                {
                    "layer": "MODEL_RETURN",
                    "call_index": self.calls,
                    "latency_s": time.monotonic() - started,
                    "request_observation_id": self.observation.observation_id,
                    "evidence": draft.observation_evidence,
                    "raw_text": draft.raw_text,
                    "parse_error": draft.parse_error,
                }
            )
            if runtime is not None:
                assert isinstance(claim_id, str)
                self.worker_call(
                    partial(
                        runtime.complete_plan,
                        claim_id,
                        draft,
                        self.robot.get_state(),
                    )
                )
                self.budget = runtime.verification_state
                self.records.append(
                    {
                        "layer": "WORKER_BOOTSTRAP_PLAN",
                        "bootstrap_hash": runtime.bootstrap.digest(),
                        "planning_source_usable": runtime.bootstrap.planning_source_usable,
                        "budget": asdict(self.budget),
                        "execution_admitted": False,
                    }
                )
                self.check_active()
                if runtime.bootstrap.planning_source_usable:
                    return draft
                self.recapture(advance_steps=1)
                continue
            if (
                not draft.parse_error
                and draft.parsed_json
                and not draft.parsed_json.get("_sentinel")
            ):
                route = self.route(
                    [
                        ConditionVerdict(
                            ConditionStatus.PASS,
                            "visual_plan_available",
                            self.observation.observation_id,
                        )
                    ],
                    DecisionEventKind.CLOUD_RETURN,
                )
                if route != DecisionAction.CONTINUE:
                    raise _EpisodeStopped("VERIFICATION_BUDGET_EXHAUSTED")
                return draft
            unknown = ConditionVerdict(
                ConditionStatus.UNKNOWN,
                "visual_plan_available",
                self.observation.observation_id,
                reasons=(draft.parse_error or str(draft.parsed_json),),
            )
            action = self.route([unknown], DecisionEventKind.CLOUD_RETURN)
            if action != DecisionAction.REOBSERVE:
                raise _EpisodeStopped("VISUAL_PLAN_REJECTED_OR_REOBSERVATION_EXHAUSTED")
            self.backend.step(steps=1)
            self.recapture()

    def execute(self, contract: TaskContract, step: TaskStep) -> bool:
        self.check_active()
        self.validate_role_boundary()
        self.require_native_action_evidence(contract, step, boundary="PRE_SAFETY")
        if self.worker_runtime is not None:
            contract, step = self.refresh_worker_grounding(contract, step)
            self.worker_dispatch_guard(contract, step)
        assert self.observation is not None
        before = self.observation
        state = self.robot.get_state()
        params = dict(step.parameters)
        now = datetime.now(UTC)
        step_started_at = time.monotonic()
        ctx = self.shield.context_builder.build(
            contract=contract,
            step=step,
            robot_state=state,
            scene_version=contract.scene_version if self.worker_runtime is not None else 1,
            resolved_parameters=params,
            scene_updated_at=before.captured_at,
            telemetry_timestamp=now,
            wall_clock_now=now,
            step_started_at_mono=step_started_at,
            task_started_at_mono=self.started_at,
            monotonic_now=time.monotonic(),
            requested_joint_velocities=[
                *[abs(value) for value in self.backend.get_joint_state().velocities],
                float(params.get("tcp_velocity", 0.0)) / 0.3,
            ],
            requested_velocity=float(params.get("tcp_velocity", 0.0)),
            requested_acceleration=float(params.get("acceleration", 0.0)),
        )
        pre = self.shield.pre_check(ctx)
        self.records.append(
            {
                "layer": "SAFETY_PRECHECK",
                "step_id": step.step_id,
                "evaluation": asdict(pre),
                "resolved_parameters": params,
            }
        )
        if not pre.allowed:
            if self.worker_runtime is not None:
                raise _EpisodeStopped("SAFETY_REJECTED")
            self.route(
                [
                    ConditionVerdict(
                        ConditionStatus.FAIL,
                        "safety_precheck",
                        before.observation_id,
                        {"hard_safety_fault": True},
                        (pre.decision.value,),
                    )
                ],
                DecisionEventKind.ANOMALY,
            )
            raise _EpisodeStopped("SAFETY_REJECTED")
        if pre.limited_parameters:
            if self.worker_runtime is not None and pre.limited_parameters != step.parameters:
                # A limiter cannot silently change the payload covered by the
                # original grounding. A fresh checked compilation is required.
                raise _EpisodeStopped("WORKER_SAFETY_LIMITS_REQUIRE_RECOMPILATION")
            step = step.model_copy(update={"parameters": pre.limited_parameters})
        self.check_active()
        self.validate_role_boundary()
        self.require_native_action_evidence(contract, step, boundary="PRE_SKILL")
        if self.worker_runtime is not None:
            contract, step = self.refresh_worker_grounding(contract, step)
            self.worker_dispatch_guard(contract, step)
        self.check_active()
        self.validate_role_boundary()
        start_step = self.backend.total_physics_steps
        action_started_at = datetime.now(UTC)
        self.records.append(
            {
                "layer": "ACTION_STARTED",
                "step_id": step.step_id,
                "skill": step.skill.value,
                "physics_step": start_step,
                "observation_id": before.observation_id,
            }
        )
        try:
            if self.policy.raw_recorder is not None:
                result = self.policy.raw_recorder.execute_attempt(
                    contract=contract,
                    step=step,
                    attempt=1,
                    grounding=self._worker_grounding,
                )
            else:
                result = self.executor.execute_attempt(contract=contract, step=step, attempt=1)
        except Exception as exc:
            actual_steps = self.backend.total_physics_steps - start_step
            self.actions += int(actual_steps > 0)
            self.records.append(
                {
                    "layer": "PARTIAL_SKILL_RETURN",
                    "complete": False,
                    "step_id": step.step_id,
                    "skill": step.skill.value,
                    "physics_steps": actual_steps,
                    "before_observation_id": before.observation_id,
                    "state_after": self.robot.get_state().model_dump(mode="json"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            raise
        returned_at = datetime.now(UTC)
        self.actions += int(self.backend.total_physics_steps > start_step)
        self.records.append(
            {
                "layer": "SKILL_RETURN",
                "step_id": step.step_id,
                "skill": step.skill.value,
                "before_observation_id": before.observation_id,
                "physics_steps": self.backend.total_physics_steps - start_step,
                "result": {
                    **asdict(result),
                    "error": result.error.model_dump(mode="json") if result.error else None,
                    "action_result": (
                        result.action_result.model_dump(mode="json")
                        if result.action_result
                        else None
                    ),
                },
            }
        )
        self.check_active()
        completion = None
        if self.worker_runtime is not None:
            from cloud_edge_robot_arm.contracts.models import SkillExecutionResult
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import digest
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
                VisualEffectCompletion,
            )

            original = self.worker_runtime.original
            completion = VisualEffectCompletion(
                result=SkillExecutionResult(
                    task_id=result.task_id,
                    plan_version=contract.plan_version,
                    command_seq=contract.command_seq,
                    timestamp=result.timestamp,
                    step_id=result.step_id,
                    skill=step.skill,
                    scene_version=contract.scene_version,
                    success=result.success,
                    error=result.error,
                    duration_ms=result.duration_ms,
                    details={"attempt": result.attempt},
                ),
                task_id=original.identity.task_id,
                plan_id=original.identity.plan_id,
                robot_id=original.identity.robot_id,
                step_id=step.step_id,
                attempt=result.attempt,
                plan_version=contract.plan_version,
                command_seq=contract.command_seq,
                started_at=action_started_at,
                returned_at=returned_at,
                before_observation_id=before.observation_id,
                execution_payload_hash=digest(contract.model_dump(mode="json")),
                source_checkpoint_hash=self.worker_runtime.publication.checkpoint.checkpoint_hash,
                source_hashes=original.source_hashes,
            )
            self._worker_completion = completion
        self.recapture(completion=completion)
        assert self.observation is not None
        post_ctx = ctx.model_copy(
            update={
                "robot_collision_detected": self.robot.get_state().collision_detected,
                "robot_estop_engaged": self.robot.get_state().estop_engaged,
                "tcp_x": self.robot.get_state().tcp_pose.x,
                "tcp_y": self.robot.get_state().tcp_pose.y,
                "tcp_z": self.robot.get_state().tcp_pose.z,
                "scene_updated_at": self.observation.captured_at,
                "wall_clock_now": datetime.now(UTC),
                "telemetry_timestamp": datetime.now(UTC),
                "monotonic_now": time.monotonic(),
                "joint_velocities": [
                    abs(value) for value in self.backend.get_joint_state().velocities
                ],
            }
        )
        post = self.shield.post_check(post_ctx)
        self.records.append(
            {"layer": "SAFETY_POSTCHECK", "step_id": step.step_id, "evaluation": asdict(post)}
        )
        if self.worker_runtime is not None:
            if not post.allowed:
                raise _EpisodeStopped("WORKER_SAFETY_POSTCHECK_FAILED")
            if not self.verify_worker("AFTER_EFFECT", contract, step, completion):
                return False
            if step.skill.value == "LIFT":
                config = self.backend._config
                assert config is not None
                self.require_continuous_grasp = True
                try:
                    # Hold existing actuator targets and use actual later camera
                    # samples. Native stability remains UNKNOWN without bounds.
                    self.recapture(
                        advance_steps=math.ceil(LIFT_OBSERVATION_HOLD_S / config.physics_dt_s),
                        completion=completion,
                        purpose="POST_HOLD",
                    )
                    if not self.verify_worker("POST_HOLD", contract, step, completion):
                        return False
                finally:
                    self.require_continuous_grasp = False
            if step.step_id == self.worker_runtime.original.contract.steps[-1].step_id:
                config = self.backend._config
                assert config is not None
                self.recapture(
                    advance_steps=math.ceil(1.2 / config.physics_dt_s),
                    completion=completion,
                    purpose="TERMINAL",
                )
                if not self.verify_worker("TERMINAL", contract, step, completion):
                    return False
            return result.success
        if not result.success or not post.allowed:
            self.route(
                [
                    ConditionVerdict(
                        ConditionStatus.FAIL,
                        "skill_effect",
                        self.observation.observation_id,
                        {"hard_safety_fault": not post.allowed},
                        (result.error_code or post.decision.value,),
                    )
                ],
                DecisionEventKind.SKILL_BOUNDARY,
                {"step_id": step.step_id},
            )
            return False
        checks = []
        target = step.parameters.get("target_pose")
        if target:
            checks.append(
                ConditionSpec(
                    "tcp_at_resolved_target",
                    tolerances={
                        **{f"target_{axis}": target[axis] for axis in ("x", "y", "z")},
                        "max_distance_m": 0.02,
                    },
                )
            )
        if step.skill.value in {"GRASP", "LIFT", "MOVE_TO_REGION", "PLACE"}:
            checks.append(ConditionSpec("gripper_holding", target_id="object"))
        if step.skill.value in {"RELEASE", "HOME"}:
            checks.append(ConditionSpec("gripper_released"))
        return self.verify(checks, DecisionEventKind.SKILL_BOUNDARY, {"step_id": step.step_id})

    def refresh_worker_grounding(
        self,
        contract: TaskContract,
        step: TaskStep,
    ) -> tuple[TaskContract, TaskStep]:
        """Every durable route invalidates grounding; keep the safety payload exact."""
        current, grounded = self.prepare_worker_step(step, self._worker_draft)
        if current.model_dump(mode="json") != contract.model_dump(mode="json"):
            raise _EpisodeStopped("WORKER_ACTION_PAYLOAD_CHANGED_REQUIRES_RECOMPILATION")
        return current, grounded

    def worker_dispatch_guard(self, contract: TaskContract, step: TaskStep) -> None:
        """Recheck the newly published binding and native evidence without clearing it."""
        from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract
        from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            native_action_context_hash,
        )
        from cloud_edge_robot_arm.vision.action_evidence import native_action_contract

        assert self.worker_runtime is not None
        self.check_active()
        self.validate_role_boundary()
        current = self.worker_runtime.publication
        grounding = current.to_payload()["grounding"]
        cached = getattr(self, "_worker_grounding", None)
        if grounding is None or cached is None or grounding != cached.to_payload():
            raise _EpisodeStopped("WORKER_DISPATCH_GROUNDING_INVALIDATED")
        assert self.observation is not None
        state = self.robot.get_state()
        original = self.worker_runtime.original
        requirement = original.requirements[step.step_id]
        online = OnlineEvidenceSnapshot(
            self.observation,
            state,
            self.tracker.facts(self.observation, state) if self.tracker is not None else {},
            contract.plan_version,
            contract.command_seq,
            native_action_context_hash(original.role_bundle_hash, contract, step.step_id),
        )
        native = native_action_contract(online, contract, step)
        action = ActionEvidenceContract(
            native.evidence,
            requirement.expected_duration_s,
            requirement.allowed_error_m,
            requirement.sensor_requirements,
            requirement.preconditions,
            requirement.postconditions,
            contract.plan_version,
            contract.command_seq,
            online.context_hash,
        )
        verdict = validate_evidence(
            action,
            datetime.now(UTC),
            online.context_hash,
            self.observation.calibration_version or "",
            online_evidence=online,
        )
        self.records.append(
            {
                "layer": "WORKER_DISPATCH_NATIVE_RECHECK",
                "status": verdict.status,
                "reasons": list(verdict.reasons),
                "step_id": step.step_id,
                "checkpoint_hash": current.checkpoint.checkpoint_hash,
                "grounding_hash": cached.binding_hash,
                "execution_admitted": False,
            }
        )
        if verdict.status != "VALID":
            raise _EpisodeStopped("WORKER_DISPATCH_NATIVE_EVIDENCE_INVALIDATED")
        self.check_native_hard_stop("PRE_SKILL")
        self.check_active()

    def require_native_action_evidence(
        self,
        contract: TaskContract,
        step: TaskStep,
        *,
        boundary: str,
    ) -> None:
        """Apply T10 at action return/commit boundaries on actual current evidence."""
        if self.policy.device_pipeline != "OPENCV":
            return
        from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
        from cloud_edge_robot_arm.vision.action_evidence import native_action_contract

        while True:
            self.check_active()
            self.validate_role_boundary()
            self.check_native_hard_stop(boundary)
            assert self.observation is not None and self.policy.role_binding is not None
            role_hash = self.policy.role_binding.bundle.digest()
            action_context_hash = hashlib.sha256(
                json.dumps(
                    {
                        "role_bundle_hash": role_hash,
                        "contract": contract.model_dump(mode="json"),
                        "step": step.model_dump(mode="json"),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            online = OnlineEvidenceSnapshot(
                self.observation,
                self.robot.get_state(),
                self.tracker.facts(self.observation, self.robot.get_state())
                if self.tracker is not None
                else {},
                contract.plan_version,
                contract.command_seq,
                action_context_hash,
            )
            action = native_action_contract(online, contract, step)
            now = datetime.now(UTC)
            verdict = validate_evidence(
                action,
                now,
                online.context_hash,
                self.observation.calibration_version or "",
                online_evidence=online,
            )
            self.records.append(
                {
                    "layer": "ACTION_EVIDENCE_GATE",
                    "boundary": boundary,
                    "step_id": step.step_id,
                    "status": verdict.status,
                    "reasons": list(verdict.reasons),
                    "bound_at_completion_m": verdict.bound_at_completion_m,
                    "observation_id": self.observation.observation_id,
                    "observation_hash": self.observation.checksum_sha256,
                    "captured_at": self.observation.captured_at.isoformat(),
                    "context_hash": online.context_hash,
                    "role_bundle_hash": role_hash,
                    "plan_version": action.plan_version,
                    "command_seq": action.command_seq,
                    "expected_duration_s": action.expected_duration_s,
                    "allowed_error_m": action.allowed_error_m,
                    "geometry_bound_m": action.evidence.geometric_error_bound_m,
                    "motion_bound_m_s": action.evidence.motion_bound_m_s,
                    "physical_acceptance": False,
                }
            )
            if self.worker_runtime is not None:
                phase = {
                    "CLOUD_RETURN": "CLOUD_RETURN",
                    "PRE_SAFETY": "NATIVE_PRE_SAFETY",
                    "PRE_SKILL": "NATIVE_PRE_SKILL",
                }[boundary]
                route = self.worker_route(phase, contract, step)
                if route == DecisionAction.CONTINUE:
                    if verdict.status != "VALID":
                        raise _EpisodeStopped("WORKER_NATIVE_VERDICT_MISMATCH")
                    return
                if route != DecisionAction.REOBSERVE:
                    raise _EpisodeStopped(f"ACTION_EVIDENCE_{verdict.status}")
                self.recapture(advance_steps=1)
                # A grounded payload is tied to its old frame. Recompile it and
                # rerun SafetyShield rather than reuse it after reobservation.
                if boundary != "CLOUD_RETURN":
                    raise _EpisodeStopped("ACTION_GROUNDING_RECAPTURED_REQUIRES_RECOMPILATION")
                continue
            if verdict.status == "VALID":
                return
            if boundary == "PRE_SKILL":
                # A recapture here would reuse the earlier resolved SafetyShield
                # context. Restarting action compilation/safety is required.
                raise _EpisodeStopped("ACTION_EVIDENCE_POST_SAFETY_INVALIDATED")
            status = (
                ConditionStatus.UNKNOWN if verdict.status == "UNKNOWN" else ConditionStatus.FAIL
            )
            route = self.route(
                [
                    ConditionVerdict(
                        status,
                        "action_submit_evidence",
                        self.observation.observation_id,
                        reasons=verdict.reasons,
                    ),
                ],
                DecisionEventKind.EVIDENCE_INVALIDATED,
                {"boundary": boundary, "step_id": step.step_id},
            )
            if route != DecisionAction.REOBSERVE:
                raise _EpisodeStopped(f"ACTION_EVIDENCE_{verdict.status}")
            self.check_active()
            self.check_native_hard_stop(boundary)
            self.backend.step(steps=1)
            self.recapture()

    def check_native_hard_stop(self, boundary: str) -> None:
        """Hard stops take precedence over an unavailable visual proof and its budget."""
        state = self.robot.get_state()
        reasons = [
            name
            for name, active in (
                ("estop_engaged", state.estop_engaged),
                ("collision_detected", state.collision_detected),
                ("disconnected", not state.connected),
            )
            if active
        ]
        if reasons:
            self.records.append(
                {
                    "layer": "HARD_SAFETY_STOP",
                    "boundary": boundary,
                    "reasons": reasons,
                    "physical_acceptance": False,
                }
            )
            raise _EpisodeStopped("HARD_SAFETY_STOP:" + ",".join(reasons))

    def monitor_physics_state(self) -> None:
        """Proprioceptive contact checks only; detached oracle samples stay separate."""
        self.check_active()
        if self._supervision_started and self.supervision is not None:
            self.supervision.poll(atomic_action_active=True)
        if self.require_continuous_grasp:
            state = self.robot.get_state()
            if state.gripper_open or state.holding_object_id != "object":
                raise _EpisodeStopped("GRASP_LOST_DURING_LIFT_HOLD")

    def supervision_context(self, observation: RGBDObservation) -> Any:
        from cloud_edge_robot_arm.vision.supervision import SupervisionContext

        state = self.robot.get_state()
        if observation.episode_id is None:
            raise _EpisodeStopped("SUPERVISION_FRAME_MISSING_EPISODE")
        return SupervisionContext(
            episode_id=observation.episode_id,
            plan_version=self._plan_version,
            state_version=self._state_version,
            next_step_id=self._active_step_id,
            next_skill=self._active_skill,
            observation_id=observation.observation_id,
            task_instruction=self.policy.instruction,
            captured_at=observation.captured_at,
            proprioception={
                "gripper_open": state.gripper_open,
                "holding_object_id": state.holding_object_id,
                "estop_engaged": state.estop_engaged,
                "collision_detected": state.collision_detected,
            },
        )

    def capture_supervision_frame(self) -> Any:
        from cloud_edge_robot_arm.vision.supervision import SupervisionFrame

        # This is invoked on the MuJoCo owner thread, including within read-only step hooks.
        observation = self.capture.capture()
        self.records.append(
            {
                "layer": "SUPERVISION_TICK",
                **observation.evidence(),
                "ordinary_result_deferred_until_skill_boundary": True,
            }
        )
        if self.policy.output_dir:
            save_observation(
                observation, self.policy.output_dir / "supervision-frames" / observation.frame_id
            )
        return SupervisionFrame(observation, self.supervision_context(observation))

    def supervise_frame(self, frame: Any) -> dict[str, Any]:
        from cloud_edge_robot_arm.vision.request_control import bounded_model_call

        self.validate_role_boundary()
        planner = copy.copy(self.planner)
        planner.model_role = "SUPERVISOR"
        observation = frame.observation
        decision = bounded_model_call(
            partial(planner.supervise, observation, frame.context),
            timeout_s=max(0.001, self.deadline - time.monotonic()),
            resource_key=planner.base_url,
            cancelled=lambda: bool(self.supervision and self.supervision.snapshot()["closed"]),
        )
        self.validate_role_boundary()
        return {
            "observation_id": observation.observation_id,
            "episode_id": observation.episode_id,
            "captured_at": observation.captured_at,
            "context": frame.context.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "evidence": observation.evidence(),
        }

    def apply_supervision(self) -> None:
        from cloud_edge_robot_arm.vision.supervision import (
            SupervisionContext,
            SupervisionDecision,
            decide_supervision,
        )

        if self.supervision is None:
            return
        self.validate_role_boundary()
        for response in self.supervision.poll(atomic_action_active=False):
            if isinstance(response, Exception):
                self.records.append({"layer": "SUPERVISION_ERROR", "type": type(response).__name__})
                raise _EpisodeStopped("SUPERVISION_UNAVAILABLE")
            if not isinstance(response, dict) or response.get("episode_id") != (
                self.observation.episode_id if self.observation else None
            ):
                raise _EpisodeStopped("SUPERVISION_FOREIGN_RESPONSE")
            age = (datetime.now(UTC) - response["captured_at"]).total_seconds()
            self.records.append(
                {
                    "layer": "SUPERVISION_RETURN",
                    **response,
                    "age_s": age,
                    "can_replace_active_contract": False,
                }
            )
            assert self.observation is not None
            action = decide_supervision(
                SupervisionDecision.model_validate(response["decision"]),
                SupervisionContext.model_validate(response["context"]),
                self.supervision_context(self.observation),
                maximum_age_s=5,
            )
            self.records.append(
                {
                    "layer": "SUPERVISION_DECISION",
                    "action": action,
                    "state_version": self._state_version,
                }
            )
            if action == "DISCARD":
                continue
            if action in {"REJECT", "STOP"}:
                raise _EpisodeStopped("SUPERVISION_STOPPED_SEQUENCE")
            if action == "REOBSERVE":
                verdict = ConditionVerdict(
                    ConditionStatus.UNKNOWN,
                    "supervision_evidence",
                    self.observation.observation_id,
                    reasons=("supervisor_requested_new_frame",),
                )
                if self.route([verdict], DecisionEventKind.CLOUD_RETURN) != (
                    DecisionAction.REOBSERVE
                ):
                    raise _EpisodeStopped("SUPERVISION_REOBSERVATION_EXHAUSTED")
                self.recapture()
                self._state_version += 1

    def hold_lift(self) -> bool:
        """Hold existing actuator targets and observe actual RGB-D lift stability."""
        assert self.tracker is not None and self.observation is not None
        assert self.tracker.initial is not None
        config = self.backend._config
        assert config is not None
        samples: list[dict[str, Any]] = []
        initial_top_z = float(self.tracker.initial["center"][2])

        def add_sample(observation: RGBDObservation, facts: dict[str, Any]) -> None:
            if samples and samples[-1]["observation_id"] == observation.observation_id:
                return
            visible = facts.get("target_visible")
            samples.append(
                {
                    "observation_id": observation.observation_id,
                    "sim_time_s": observation.sim_time_s,
                    "center": visible.get("measured_values", {}).get("center") if visible else None,
                }
            )

        def held_facts(observation: RGBDObservation, facts: dict[str, Any]) -> dict[str, Any]:
            add_sample(observation, facts)
            visible = facts.get("target_visible")
            if not visible or any(sample["center"] is None for sample in samples):
                return facts
            centers = np.array([sample["center"] for sample in samples])
            duration = float(samples[-1]["sim_time_s"] - samples[0]["sim_time_s"])
            displacement = float(np.linalg.norm(centers - centers[0], axis=1).max())
            height = float(centers[:, 2].min() - initial_top_z)
            measured = {
                "samples": samples.copy(),
                "observed_sim_duration_s": duration,
                "max_displacement_m": displacement,
                "minimum_visual_lift_m": height,
                "continuous_bilateral_contact": True,
                "required_duration_s": LIFT_OBSERVATION_HOLD_S,
                "required_lift_m": LIFT_MIN_VISUAL_HEIGHT_M,
                "stability_tolerance_m": LIFT_VISUAL_STABILITY_TOLERANCE_M,
            }
            envelope = {**visible, "measured_values": measured}
            return {
                **facts,
                "object_lifted": {**envelope, "value": height >= LIFT_MIN_VISUAL_HEIGHT_M},
                "object_stable": {
                    **envelope,
                    "value": duration >= LIFT_OBSERVATION_HOLD_S
                    and displacement <= LIFT_VISUAL_STABILITY_TOLERANCE_M,
                },
            }

        add_sample(self.observation, self.tracker.facts(self.observation, self.robot.get_state()))
        start_step = self.backend.total_physics_steps
        total_steps = math.ceil(LIFT_OBSERVATION_HOLD_S / config.physics_dt_s)
        chunk_steps = max(1, math.ceil(LIFT_OBSERVATION_INTERVAL_S / config.physics_dt_s))
        self.require_continuous_grasp = True
        try:
            self.monitor_physics_state()
            while self.backend.total_physics_steps - start_step < total_steps:
                chunk_start = self.backend.total_physics_steps
                requested = min(chunk_steps, total_steps - (chunk_start - start_step))
                complete = False
                try:
                    self.backend.step(steps=requested)
                    complete = True
                finally:
                    actual = self.backend.total_physics_steps - chunk_start
                    self.records.append(
                        {
                            "layer": "PASSIVE_OBSERVATION",
                            "purpose": "post_lift_visual_stability",
                            "physics_steps": actual,
                            "actual_sim_duration_s": actual * config.physics_dt_s,
                            "complete": complete,
                        }
                    )
                self.recapture()
                assert self.observation is not None
                add_sample(
                    self.observation, self.tracker.facts(self.observation, self.robot.get_state())
                )
            return self.verify(
                [
                    ConditionSpec("object_lifted", target_id="object"),
                    ConditionSpec("object_stable", target_id="object"),
                    ConditionSpec("gripper_holding", target_id="object"),
                ],
                DecisionEventKind.SKILL_BOUNDARY,
                {"phase": "post_lift_passive_hold", "hold_samples": samples},
                facts_transform=held_facts if self.policy.device_pipeline == "LEGACY" else None,
            )
        finally:
            self.require_continuous_grasp = False

    def run_online(self) -> bool:
        self.recapture()
        assert self.observation is not None
        state = self.robot.get_state()
        if state.estop_engaged or state.collision_detected:
            self.route(
                [
                    ConditionVerdict(
                        ConditionStatus.FAIL,
                        "initial_robot_safety",
                        self.observation.observation_id,
                        {
                            "hard_safety_fault": True,
                            "estop_engaged": state.estop_engaged,
                            "collision_detected": state.collision_detected,
                        },
                        ("preexisting_robot_safety_fault",),
                    )
                ],
                DecisionEventKind.ANOMALY,
            )
            raise _EpisodeStopped("SAFETY_REJECTED")
        draft = self.plan()
        assert self.observation is not None
        if self.worker_runtime is not None:
            return self.run_worker_online(draft)
        evidence = draft.observation_evidence or {}
        contract = grounded_contract(draft, self.observation, self.policy)
        self.records.append(
            {
                "layer": "RUNTIME_CONTRACT_COMPILATION",
                "template_safety_constraints": (draft.parsed_json or {}).get("safety_constraints"),
                "runtime_safety_constraints": contract.safety_constraints.model_dump(mode="json"),
                "omitted_optional_skills": [
                    item
                    for item in (draft.parsed_json or {}).get("steps", [])
                    if item.get("skill") == "HOME"
                ],
                "omission_reason": "NOT_EXECUTED_OPTIONAL_HOME_FIXED_SPEED_NOT_VERIFIABLE",
                "motion_profile": {
                    "tcp_velocity_parameter": 0.15,
                    "requested_joint_velocity_rad_s": 0.5,
                    "requested_joint_acceleration_rad_s2": 0.5 / 0.3,
                },
                "contract": contract.model_dump(mode="json"),
            }
        )
        self.tracker = make_target_tracker(self.observation, evidence, self.policy)
        self._plan_version = contract.plan_version
        self._supervision_started = True
        self.recapture()  # Revalidate after inference, even when inference was fast.
        if contract.steps:
            self.require_native_action_evidence(
                contract,
                contract.steps[0],
                boundary="CLOUD_RETURN",
            )
        for original in contract.steps:
            self._state_version += 1
            self._active_step_id = original.step_id
            self._active_skill = original.skill.value
            self.apply_supervision()
            skill = original.skill.value
            if skill in {"MOVE_ABOVE", "APPROACH"} and not self.verify(
                [
                    ConditionSpec("target_visible", target_id="object"),
                    ConditionSpec("target_reachable", target_id="object"),
                    ConditionSpec("gripper_open"),
                ],
                DecisionEventKind.EVIDENCE_INVALIDATED,
            ):
                raise _EpisodeStopped("TARGET_EVIDENCE_INVALIDATED")
            before_conditions = {
                "GRASP": [
                    ConditionSpec("target_visible", target_id="object"),
                    ConditionSpec("target_reachable", target_id="object"),
                    ConditionSpec("gripper_open"),
                ],
                "LIFT": [ConditionSpec("gripper_holding", target_id="object")],
                "MOVE_TO_REGION": [ConditionSpec("gripper_holding", target_id="object")],
                "PLACE": [ConditionSpec("gripper_holding", target_id="object")],
                "RELEASE": [
                    ConditionSpec("object_inside_target_region", target_id="object"),
                    ConditionSpec("gripper_holding", target_id="object"),
                ],
                "RETREAT": [ConditionSpec("gripper_released")],
            }.get(skill)
            if before_conditions and not self.verify(
                before_conditions,
                DecisionEventKind.EVIDENCE_INVALIDATED,
                {"step_id": original.step_id, "phase": "precondition"},
            ):
                raise _EpisodeStopped(f"{skill}_PRECONDITION_NOT_VERIFIED")
            step = resolved_step(original, self.robot, evidence)
            current_contract = contract.model_copy(
                update={
                    "steps": [
                        step if item.step_id == step.step_id else item for item in contract.steps
                    ],
                }
            )
            if not self.execute(current_contract, step):
                raise _EpisodeStopped(f"{skill}_EFFECT_NOT_VERIFIED")
            if skill == "LIFT" and not self.hold_lift():
                raise _EpisodeStopped("LIFT_HOLD_NOT_VERIFIED")
            self.apply_supervision()
        self.check_active()
        config = self.backend._config
        assert config is not None
        # Passive actuator hold, no target/object teleport and no extra motion skill.
        dwell_steps = math.ceil(1.2 / config.physics_dt_s)
        self.backend.step(steps=dwell_steps)
        self.records.append(
            {
                "layer": "PASSIVE_OBSERVATION",
                "physics_steps": dwell_steps,
                "purpose": "post_release_stability",
                "seconds": 1.2,
            }
        )
        self.recapture()
        return self.verify(
            terminal_conditions(self.policy),
            DecisionEventKind.RESULT_VERIFIED,
        )

    def run_worker_online(self, draft: PlannerDraft) -> bool:
        """Adopt the full source plan before any ordinary verification or dispatch."""
        assert self.worker_runtime is not None and self.observation is not None
        runtime = self.worker_runtime
        contract, publication = self.worker_call(lambda: runtime.adopt_plan(self.robot.get_state()))
        self.records.append(
            {
                "layer": "WORKER_ORIGINAL_PLAN_ADOPTED",
                "contract": contract.model_dump(mode="json"),
                "source_publication": publication.to_payload(),
                "execution_admitted": False,
            }
        )
        recorder = self.policy.raw_recorder
        if recorder is not None:
            self.worker_call(lambda: recorder.bind_worker_source(runtime))
        self.tracker = make_target_tracker(
            self.observation,
            draft.observation_evidence or {},
            self.policy,
        )
        self._plan_version = contract.plan_version
        self._supervision_started = True
        if not contract.steps:
            raise _EpisodeStopped("WORKER_ORIGINAL_PLAN_EMPTY")
        self.require_native_action_evidence(contract, contract.steps[0], boundary="CLOUD_RETURN")
        for original_step in contract.steps:
            self._active_step_id = original_step.step_id
            self._active_skill = original_step.skill.value
            self._state_version += 1
            if not self.verify_worker("PRECONDITION", contract, original_step):
                raise _EpisodeStopped("WORKER_ORIGINAL_PRECONDITIONS_NOT_VERIFIED")
            current_contract, step = self.prepare_worker_step(original_step, draft)
            if not self.execute(current_contract, step):
                raise _EpisodeStopped("WORKER_FULL_EFFECT_NOT_VERIFIED")
            # The coordinator advances the prefix only from its stored canonical
            # complete-effect route. A skill success boolean is insufficient.
            self.worker_call(partial(runtime.complete_step, step.step_id, self.robot.get_state()))
        return True


def run_visual_episode(
    planner: RGBDPlannerAdapter,
    robot: MuJoCoSkillRobot,
    capture: MuJoCoCaptureSession,
    policy: ExecutionPolicy,
) -> VisualEpisodeOutcome:
    """Run online decisions first, then the read-only independent physical verdict."""
    from cloud_edge_robot_arm.vision.request_control import ModelCallCancelled, ModelCallTimedOut

    run = _VisualEpisode(planner, robot, capture, policy)
    criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
    samples: list[PhysicalSample] = [
        sample_physical_observation(robot._backend.current_physics_observation(), criteria),
    ]
    start_step = robot._backend.total_physics_steps
    online_complete = False
    reason = None

    def collect(snapshot: Any) -> None:
        samples.append(sample_physical_observation(snapshot, criteria))
        run.monitor_physics_state()

    try:
        with (
            run.supervision if run.supervision is not None else nullcontext(),
            robot._backend.observe_physics_steps(collect),
        ):
            try:
                online_complete = run.run_online()
                if not online_complete:
                    reason = "FINAL_VERIFICATION_NOT_PASSED"
            except RGBDModelCallFailed:
                reason = "MODEL_REQUEST_FAILED"
            except RGBDModelUnavailable:
                reason = "BLOCKED_BY_ENV_MODEL_UNAVAILABLE"
            except ModelCallCancelled:
                reason = "CANCELLED"
            except ModelCallTimedOut:
                reason = "MODEL_TIMEOUT"
            except Exception as exc:
                reason = (
                    str(exc) if isinstance(exc, _EpisodeStopped) else f"{type(exc).__name__}: {exc}"
                )
            if not online_complete:
                stop = robot.safe_stop()
                run.records.append({"layer": "SAFE_STOP", "action": stop.model_dump(mode="json")})
    finally:
        # This is the first evaluator call; its result can never enter the online router.
        physical = evaluate_episode(
            robot._backend, criteria, evidence=samples, evaluation_start_step=start_step
        )
    run.records.append(
        {
            "layer": "INDEPENDENT_PHYSICAL_RESULT",
            "result": asdict(physical),
            "used_for_online_routing": False,
        }
    )
    if run.supervision is not None:
        run.records.append({"layer": "SUPERVISION_SUMMARY", **run.supervision.snapshot()})
    if run.wait_clock is not None:
        run.records.append(
            {
                "layer": "CLOCK_MAPPING",
                **run.wait_clock.mapping(),
                "actual_episode_sim_s": robot._backend.get_sim_time(),
                "action_steps_mapping": "unpaced fixed-step actuator execution",
            }
        )
    outcome = combine_outcome(
        physical,
        online_complete=online_complete,
        records=tuple(run.records),
        terminal_reason=reason,
        model_calls=(
            planner.cost_ledger.snapshot().model_requests
            if planner.cost_ledger is not None
            else run.calls
        ),
        executed_actions=run.actions,
        observation_count=run.count,
        episode_id=robot._backend._episode_id or "",
    )
    if policy.output_dir:
        write_json(
            policy.output_dir / "physical-evidence.json", [asdict(sample) for sample in samples]
        )
        write_json(policy.output_dir / "physical-outcome.json", asdict(physical))
        write_json(policy.output_dir / "episode.json", asdict(outcome))
    return outcome
