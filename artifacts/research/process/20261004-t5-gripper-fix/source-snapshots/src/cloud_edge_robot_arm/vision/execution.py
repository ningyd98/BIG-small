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
from typing import Any, cast

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


def grounded_contract(
    draft: PlannerDraft, observation: RGBDObservation, policy: ExecutionPolicy
) -> TaskContract:
    """Bind validated planner intent to calibrated RGB-D geometry, not scene truth."""
    evidence = draft.observation_evidence or {}
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
        snapshot = planner.model_snapshot
        if snapshot is None or snapshot.digest() != policy.model_snapshot_hash:
            raise ValueError("episode planner differs from the immutable model snapshot")
        self.planner, self.robot, self.capture, self.policy = planner, robot, capture, policy
        self.backend = robot._backend
        self.started_at = time.monotonic()
        self.deadline = self.started_at + policy.timeout_s
        self.budget = VerificationBudgetState.start(policy.verification_budget)
        self.records: list[dict[str, Any]] = []
        self.observation: RGBDObservation | None = None
        self.count = self.calls = self.actions = 0
        self.tracker: RGBDTargetTracker | None = None
        self.require_continuous_grasp = False
        self.shield = research_safety_shield(policy.timeout_s)
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
        if asset_hash is None or config is None or (
            hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest() != asset_hash
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

    def check_active(self) -> None:
        if self.policy.cancelled is not None and self.policy.cancelled():
            raise _EpisodeStopped("CANCELLED")
        if self.budget.exhausted_reason is not None:
            raise _EpisodeStopped("VERIFICATION_BUDGET_EXHAUSTED")
        if datetime.now(UTC) >= self.budget.deadline_at:
            raise _EpisodeStopped("VERIFICATION_TIMEOUT")
        if time.monotonic() >= self.deadline:
            raise _EpisodeStopped("EPISODE_TIMEOUT")

    def recapture(self) -> RGBDObservation:
        self.check_active()
        previous = self.observation
        observation = self.capture.capture()
        if previous is not None and (
            observation.episode_id != previous.episode_id
            or observation.frame_id == previous.frame_id
            or observation.captured_at <= previous.captured_at
        ):
            raise _EpisodeStopped("STALE_OR_FOREIGN_RECAPTURE")
        self.observation = observation
        self.count += 1
        self.records.append({"layer": "OBSERVATION", **observation.evidence()})
        if self.policy.output_dir:
            save_observation(observation, self.policy.output_dir / "frames" / f"{self.count:03d}")
        return observation

    def verify(
        self,
        conditions: list[ConditionSpec],
        kind: DecisionEventKind,
        extra: dict[str, Any] | None = None,
        facts_transform: Callable[[RGBDObservation, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> bool:
        while True:
            self.check_active()
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
                self.policy.model_snapshot_hash,
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

        while True:
            self.check_active()
            assert self.observation is not None
            request = InitialPlanningRequest(
                request_id="visual-episode",
                user_instruction=self.policy.instruction,
                observation=self.observation,
                scene=SceneSummary(scene_version=1, updated_at=self.observation.captured_at),
            )
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
            scene_version=1,
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
            step = step.model_copy(update={"parameters": pre.limited_parameters})
        self.check_active()
        start_step = self.backend.total_physics_steps
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
        self.recapture()
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
            episode_id=observation.episode_id, plan_version=self._plan_version,
            state_version=self._state_version, next_step_id=self._active_step_id,
            next_skill=self._active_skill, observation_id=observation.observation_id,
            task_instruction=self.policy.instruction,
            captured_at=observation.captured_at,
            proprioception={"gripper_open": state.gripper_open,
                "holding_object_id": state.holding_object_id,
                "estop_engaged": state.estop_engaged,
                "collision_detected": state.collision_detected},
        )

    def capture_supervision_frame(self) -> Any:
        from cloud_edge_robot_arm.vision.supervision import SupervisionFrame

        # This is invoked on the MuJoCo owner thread, including within read-only step hooks.
        observation = self.capture.capture()
        self.records.append({"layer": "SUPERVISION_TICK", **observation.evidence(),
                             "ordinary_result_deferred_until_skill_boundary": True})
        if self.policy.output_dir:
            save_observation(observation, self.policy.output_dir / "supervision-frames"
                             / observation.frame_id)
        return SupervisionFrame(observation, self.supervision_context(observation))

    def supervise_frame(self, frame: Any) -> dict[str, Any]:
        from cloud_edge_robot_arm.vision.request_control import bounded_model_call

        planner = copy.copy(self.planner)
        planner.model_role = "SUPERVISOR"
        observation = frame.observation
        decision = bounded_model_call(
            partial(planner.supervise, observation, frame.context),
            timeout_s=max(.001, self.deadline - time.monotonic()),
            resource_key=planner.base_url,
            cancelled=lambda: bool(self.supervision and self.supervision.snapshot()["closed"]),
        )
        return {"observation_id": observation.observation_id,
                "episode_id": observation.episode_id, "captured_at": observation.captured_at,
                "context": frame.context.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "evidence": observation.evidence()}

    def apply_supervision(self) -> None:
        from cloud_edge_robot_arm.vision.supervision import (
            SupervisionContext,
            SupervisionDecision,
            decide_supervision,
        )

        if self.supervision is None:
            return
        for response in self.supervision.poll(atomic_action_active=False):
            if isinstance(response, Exception):
                self.records.append({"layer": "SUPERVISION_ERROR",
                                     "type": type(response).__name__})
                raise _EpisodeStopped("SUPERVISION_UNAVAILABLE")
            if not isinstance(response, dict) or response.get("episode_id") != (
                self.observation.episode_id if self.observation else None
            ):
                raise _EpisodeStopped("SUPERVISION_FOREIGN_RESPONSE")
            age = (datetime.now(UTC) - response["captured_at"]).total_seconds()
            self.records.append({"layer": "SUPERVISION_RETURN", **response,
                                 "age_s": age, "can_replace_active_contract": False})
            assert self.observation is not None
            action = decide_supervision(
                SupervisionDecision.model_validate(response["decision"]),
                SupervisionContext.model_validate(response["context"]),
                self.supervision_context(self.observation), maximum_age_s=5,
            )
            self.records.append({"layer": "SUPERVISION_DECISION", "action": action,
                                 "state_version": self._state_version})
            if action == "DISCARD":
                continue
            if action in {"REJECT", "STOP"}:
                raise _EpisodeStopped("SUPERVISION_STOPPED_SEQUENCE")
            if action == "REOBSERVE":
                verdict = ConditionVerdict(ConditionStatus.UNKNOWN, "supervision_evidence",
                    self.observation.observation_id, reasons=("supervisor_requested_new_frame",))
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
                    "center": visible["measured_values"]["center"] if visible else None,
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
                facts_transform=held_facts,
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
        self.tracker = RGBDTargetTracker(self.observation, evidence)
        self._plan_version = contract.plan_version
        self._supervision_started = True
        self.recapture()  # Revalidate after inference, even when inference was fast.
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
            [
                ConditionSpec("object_inside_target_region", target_id="object"),
                ConditionSpec("gripper_released"),
                ConditionSpec("robot_in_safe_pose", tolerances={"minimum_safe_height": 0.08}),
            ],
            DecisionEventKind.RESULT_VERIFIED,
        )


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
        with (run.supervision if run.supervision is not None else nullcontext()), (
            robot._backend.observe_physics_steps(collect)
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
        run.records.append({"layer": "CLOCK_MAPPING", **run.wait_clock.mapping(),
                            "actual_episode_sim_s": robot._backend.get_sim_time(),
                            "action_steps_mapping": "unpaced fixed-step actuator execution"})
    outcome = combine_outcome(
        physical,
        online_complete=online_complete,
        records=tuple(run.records),
        terminal_reason=reason,
        model_calls=(planner.cost_ledger.snapshot().model_requests
                     if planner.cost_ledger is not None else run.calls),
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
