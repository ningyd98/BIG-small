"""One-episode visual orchestration using the existing safe physical skill executor.

Only RGB-D and robot proprioception reach online checks. Detached simulator truth
is accumulated for the independent evaluator, which runs after online termination.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import time
import uuid
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
from cloud_edge_robot_arm.contracts import Pose, TaskContract, TaskStep
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
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.top_grasp import CALIBRATED_ASSET_SHA256


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
    """Small scoped color/depth tracker seeded solely by VLM image coordinates.

    It estimates visible geometry, not instance IDs. Ambiguous/disappearing color
    support produces no fact. The frozen planner's target is never refined here.
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

    @staticmethod
    def _color(rgb: np.ndarray, pixel: tuple[int, ...]) -> np.ndarray:
        x, y = pixel
        color = np.median(rgb[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2], axis=(0, 1))
        if color.max() - color.min() < 35:
            raise ValueError("scoped tracker requires a distinguishable colored region")
        return cast(np.ndarray, color / max(float(color.sum()), 1.0))

    @staticmethod
    def _geometry(observation: RGBDObservation, color: np.ndarray) -> dict[str, Any] | None:
        rgb = _pixels(observation)
        chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1.0)
        mask = (np.linalg.norm(chroma - color, axis=2) < 0.14) & (
            rgb.max(axis=2) - rgb.min(axis=2) > 30
        )
        depth = np.asarray(observation.depth_values()).reshape(mask.shape)
        valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(mask.shape)
        mask &= (depth > 0) & np.isfinite(depth) & (valid > 0)
        # Require exactly one substantial connected component. Equal-colored
        # objects never become one claimed identity; <=7 pixel speckles are noise.
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
            if len(component) >= 8:
                components.append(component)
        if len(components) != 1:
            return None
        ys, xs = np.asarray(components[0], dtype=int).T
        # Dense bounding support avoids accepting very sparse silhouettes.
        if len(xs) / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) < 0.10:
            return None
        fx, fy, cx, cy = observation.intrinsics
        z = depth[ys, xs]
        points = np.stack(((xs - cx) * z / fx, (ys - cy) * z / fy, z, np.ones_like(z)))
        world = np.asarray(observation.camera_to_world).reshape(4, 4) @ points
        center = np.median(world[:3], axis=1)
        index = int(np.argmin((xs - np.median(xs)) ** 2 + (ys - np.median(ys)) ** 2))
        return {
            "pixel": [int(xs[index]), int(ys[index])],
            "center": center.tolist(),
            "min": np.min(world[:3], axis=1).tolist(),
            "max": np.max(world[:3], axis=1).tolist(),
            "visible_pixels": len(xs),
        }

    def facts(self, observation: RGBDObservation) -> dict[str, Any]:
        target = self._geometry(observation, self.target_color)
        destination = self._geometry(observation, self.destination_color)
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
        # Occlusion can remove a visible subset; it cannot move the remaining points
        # outside the original observed support by more than this development tolerance.
        unchanged = all(
            target["min"][i] >= self.initial["min"][i] - 0.018
            and target["max"][i] <= self.initial["max"][i] + 0.018
            for i in (0, 1)
        )
        result["target_reachable"] = {
            **envelope,
            "value": unchanged,
            "measured_values": {"stationary_support": unchanged},
        }
        if destination is not None:
            # The target can hide the middle of the region. Its visible outer bounds
            # still describe the green region, and depth must put the block on support.
            inside = all(
                target["min"][i] >= destination["min"][i] - 0.003
                and target["max"][i] <= destination["max"][i] + 0.003
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
    if evidence.get("top_grasp_offset_status") != "CALIBRATED_RGBD_TOP_GRASP_V1":
        raise ValueError("explicit calibrated RGB-D grasp TCP is required")
    if evidence.get("grasp_calibration_asset_sha256") != CALIBRATED_ASSET_SHA256:
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
        self.shield = research_safety_shield(policy.timeout_s)
        self.executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
        config = self.backend._config
        if config is None or hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest() != (
            CALIBRATED_ASSET_SHA256
        ):
            raise ValueError("backend asset differs from calibrated upright-box profile")
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
                    "safety_policy": self.shield.config.hard_limits.to_dict(),
                    "safety_policy_hash": self.shield.config.policy_hash,
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
    ) -> bool:
        while True:
            self.check_active()
            assert self.observation is not None
            facts = self.tracker.facts(self.observation) if self.tracker else {}
            snapshot = OnlineEvidenceSnapshot(
                self.observation,
                self.robot.get_state(),
                facts,
                1,
                1,
                self.policy.model_snapshot_hash,
            )
            verdicts = evaluate_conditions(conditions, snapshot)
            action = self.route(verdicts, kind, extra)
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
            draft = bounded_model_call(
                partial(self.planner.plan, request),
                timeout_s=max(0.001, self.deadline - started),
                cancelled=self.policy.cancelled,
                resource_key=self.planner.base_url,
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
        result = self.executor.execute_attempt(contract=contract, step=step, attempt=1)
        if result.action_result is not None:
            self.actions += 1
        self.records.append(
            {
                "layer": "SKILL_RETURN",
                "step_id": step.step_id,
                "skill": step.skill.value,
                "before_observation_id": before.observation_id,
                "physics_steps": self.backend.total_physics_steps - start_step,
                "result": {
                    **asdict(result),
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

    def run_online(self) -> bool:
        self.recapture()
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
        self.recapture()  # Revalidate after inference, even when inference was fast.
        for original in contract.steps:
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
        run.check_active()

    try:
        with robot._backend.observe_physics_steps(collect):
            try:
                online_complete = run.run_online()
                if not online_complete:
                    reason = "FINAL_VERIFICATION_NOT_PASSED"
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
    outcome = combine_outcome(
        physical,
        online_complete=online_complete,
        records=tuple(run.records),
        terminal_reason=reason,
        model_calls=run.calls,
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
