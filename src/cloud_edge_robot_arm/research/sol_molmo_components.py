"""经用户显式授权的MuJoCo组件诊断；不授予T10或正式研究资格。"""

from __future__ import annotations

import base64
import io
import json
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import cv2
import numpy as np
from PIL import Image

from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

SCOPE = "MUJOCO_COMPONENT_DIAGNOSTIC"
_SETTLE_STEPS = dict(
    MOVE_ABOVE=24,
    APPROACH=24,
    GRASP=120,
    LIFT=240,
    MOVE_TO_REGION=24,
    PLACE=24,
    RELEASE=288,
    RETREAT=24,
)


class ComponentStopped(RuntimeError):
    """明确停止原因，不复用或升级旧帧和未知证书。"""


def _save(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)

    def encode(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        return item.isoformat()

    encoded = (
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=encode) + "\n"
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
    return encoded


def check_component_hard_state(backend: Any, robot: Any) -> None:
    """只读取机器人反馈和静态关节限位；不读取物体真值进行在线路由。"""
    state = robot.get_state()
    if not state.connected or state.estop_engaged or state.collision_detected:
        raise ComponentStopped("ROBOT_HARD_SAFETY_STOP")
    joint = backend.get_joint_state()
    for name, position, velocity in zip(
        joint.names, joint.positions, joint.velocities, strict=True
    ):
        index = backend._model.joint(name).id
        low, high = backend._model.jnt_range[index]
        if not math.isfinite(position) or position < low - 1e-6 or position > high + 1e-6:
            raise ComponentStopped("HARD_JOINT_LIMIT")
        if not math.isfinite(velocity) or abs(velocity) > 3.0:
            raise ComponentStopped("HARD_JOINT_VELOCITY")
    p = state.tcp_pose
    if not all(math.isfinite(v) for v in (p.x, p.y, p.z)) or (
        not -0.85 <= p.x <= 0.85
        or not -0.85 <= p.y <= 0.85
        or not 0 <= p.z <= 1.2
        or math.hypot(p.x, p.y) > 0.85
    ):
        raise ComponentStopped("HARD_TCP_WORKSPACE")


def check_component_lease(
    worker: Any, job: Any, start_monotonic: float, *, expected_attempt: int | None
) -> Any:
    """每次轮询核对具体租约/开放尝试；不得沿用已释放或变更的来源。"""
    from cloud_edge_robot_arm.vision.worker_owner import read_visual_worker_lease

    worker._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
    try:
        source = read_visual_worker_lease(
            worker.repository,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=worker.worker_id,
            lease_id=job.lease_id,
        )
        if expected_attempt is not None and source.attempt != expected_attempt:
            raise ValueError("component attempt changed")
    except Exception as error:
        raise ComponentStopped("COMPONENT_LEASE_SOURCE_INVALID") from error
    return source


def _visible_support(
    observation: RGBDObservation, color: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=float)
    normalized = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1)
    mask = (
        (np.linalg.norm(normalized - color, axis=2) < 0.12) & (np.ptp(rgb, axis=2) > 35)
    ).astype("uint8")
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    choices = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 4]
    if len(choices) != 1:
        raise ComponentStopped("CURRENT_RGBD_IDENTITY_NOT_UNIQUE_OR_VISIBLE")
    selected = labels == choices[0]
    depths = np.asarray(observation.depth_values()).reshape(observation.height, observation.width)
    if np.count_nonzero(selected & (depths > 0)) < max(4, np.count_nonzero(selected) * 0.8):
        raise ComponentStopped("CURRENT_RGBD_SUPPORT_DEPTH_UNAVAILABLE")
    return selected, {
        "visible_pixels": int(np.count_nonzero(selected)),
        "status": "VISIBLE_COLOR_SUPPORT_ONLY",
        "metric_error_bound_m": None,
    }


def _ground_component(
    observation: RGBDObservation,
    tracker: Any,
    evidence: dict[str, Any],
    family_id: str,
    skill: str,
    state: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """当前像素维持身份；缺完整轮廓时只在已抓取的组件诊断中消费反馈。"""
    target, target_reason = tracker._geometry(observation, tracker.target_color, target=True)
    region, region_reason = tracker._geometry(
        observation, tracker.destination_color, target=False, occlusion_geometry=target
    )
    family = marker_family(family_id)
    marker = detect_pose_marker(
        observation,
        PoseMarkerRegistration(
            marker_id=family.marker_id,
            dictionary=cast(Literal["DICT_4X4_50"], family.dictionary),
            marker_size_m=family.marker_size_m,
            marked_asset_sha256=family.asset_sha256,
        ),
        corner_refinement="SUBPIX",
    )
    if marker.status != "OBSERVED":
        _, visible = _visible_support(observation, tracker.target_color)
    else:
        visible = {"status": "REGISTERED_MARKER_OBSERVED", "metric_error_bound_m": None}
    _visible_support(observation, tracker.destination_color)
    current = dict(evidence)
    audit: dict[str, Any] = {
        "observation_id": observation.observation_id,
        "checksum_sha256": observation.checksum_sha256,
        "target_visibility": visible,
        "target_geometry_reason": target_reason,
        "region_geometry_reason": region_reason,
        "marker_status": marker.status,
        "formal_geometry_qualification": "UNKNOWN",
    }
    if target is not None:
        offset = float(evidence["resolved_top_grasp_tcp"]["z"]) - float(
            tracker.initial["center"][2]
        )
        x, y, z = map(float, target["center"])
        current["resolved_top_grasp_tcp"] = {"x": x, "y": y, "z": z + offset}
        audit["target_source"] = "CURRENT_OPENCV_RGBD_COMPLETE_SUPPORT"
    elif marker.status == "OBSERVED":
        attachment = np.asarray(family.marker_to_object).reshape(4, 4)
        rotation = np.asarray(marker.rotation_marker_to_world).reshape(3, 3) @ attachment[:3, :3].T
        if rotation[2, 2] < 0.98:
            raise ComponentStopped("CURRENT_MARKER_OBJECT_NOT_UPRIGHT")
        center = np.asarray(marker.marker_center_world_m) - rotation @ attachment[:3, 3]
        grasp = center + rotation @ np.array([0.0, 0.0, 0.01])
        current["resolved_top_grasp_tcp"] = dict(zip("xyz", map(float, grasp), strict=True))
        audit["target_source"] = "CURRENT_REGISTERED_MARKER_RGBD_DEVELOPMENT_ESTIMATE"
    elif skill in {"MOVE_ABOVE", "APPROACH"}:
        raise ComponentStopped("CURRENT_GRASP_GEOMETRY_UNAVAILABLE")
    else:
        audit["target_source"] = (
            "VISIBLE_SUPPORT_AND_COMPONENT_PROPRIOCEPTION_NO_EXTENT_CERTIFICATE"
        )
    if skill in {"LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE"} and (
        state.gripper_open or state.holding_object_id != "object"
    ):
        raise ComponentStopped("COMPONENT_GRASP_FEEDBACK_LOST")
    if region is not None:
        current["grounded_destination"] = dict(
            zip("xyz", map(float, region["center"]), strict=True)
        )
        audit["destination_source"] = "CURRENT_OPENCV_RGBD"
    else:
        audit["destination_source"] = "REFERENCE_REGION_CENTER_WITH_CURRENT_VISIBLE_COLOR_SUPPORT"
    return current, audit


def run_component_episode(
    worker: Any, job: Any, draft: Any, *, start_monotonic: float
) -> tuple[dict[str, Any], list, list]:
    """由实际SimulationWorker进入；不经正式VisualWorkerRuntime准入。"""
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_episode,
        sample_physical_observation,
    )
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from cloud_edge_robot_arm.vision.execution import (
        grounded_contract,
        research_safety_shield,
        resolved_step,
    )
    from cloud_edge_robot_arm.vision.marked_asset import validate_development_marker_asset
    from cloud_edge_robot_arm.vision.molmo_worker import MolmoWorkerPlanner
    from cloud_edge_robot_arm.vision.request_control import bounded_owner_model_call
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    if (
        job.backend != "MUJOCO"
        or job.scenario_id != "S01_NORMAL_STATIC"
        or worker.planner_factory is None
    ):
        raise ValueError("component diagnostic supports only the explicit MuJoCo S01 task")
    planner = worker.planner_factory()
    binding = worker.visual_role_binding
    parameters = job.draft.get("parameter_overrides", {})
    family_id = parameters.get("development_marker_family")
    if (
        type(planner) is not MolmoWorkerPlanner
        or binding is None
        or (
            parameters.get("sol_molmo_component_diagnostic") is not True
            or binding.edge_policy.get("component_diagnostic") is not True
            or binding.edge_policy.get("development_marker_family") != family_id
        )
    ):
        raise ValueError("explicit component diagnostic and exact role binding required")
    family = marker_family(family_id)
    snapshot = planner.model_snapshot
    ledger = planner.cost_ledger
    if snapshot is None or ledger is None:
        raise ValueError("component snapshot and cost ledger required")
    output = planner.output.parent
    folder = output / "component"
    folder.mkdir(exist_ok=False)
    asset = binding.root / family.asset_path
    receipt = validate_development_marker_asset(asset, snapshot.grasp_profile, family_id)
    config = SimulatorConfig(
        model_path=str(asset),
        seed=job.seed,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
        camera_width=320,
        camera_height=240,
        physics_dt_s=1 / 240,
    )
    criteria = CompletionCriteria("object", "target_region")
    backend = MuJoCoPhysicsBackend()
    samples: list[Any] = []
    actions: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    row: dict[str, Any] = {
        "status": "FAILED",
        "evaluation_scope": SCOPE,
        "execution_scope": SCOPE,
        "success": False,
        "task_success": False,
        "diagnostic_complete": False,
        "online_reported_complete": None,
        "physical_success": None,
        "executed_actions": 0,
        "native_action_qualification": "UNKNOWN_NOT_GRANTED",
        "formal_research": "NOT_ACCEPTED",
        "qualified_groups_added": 0,
        "asset_policy": receipt,
        "actions": actions,
        "safety_checks": checks,
        "marker_frames": frames,
        "terminal_reason": None,
        "model_calls": 0,
        "physics_step_limit": 16000,
    }

    lease_attempt: int | None = None

    def active() -> None:
        nonlocal lease_attempt
        source = check_component_lease(worker, job, start_monotonic, expected_attempt=lease_attempt)
        lease_attempt = source.attempt
        binding.validate(planner)

    try:
        active()
        backend.initialize(config)
        backend.reset(PhysicalScenarioConfig.scenario(job.scenario_id, seed=job.seed))
        robot = MuJoCoSkillRobot(backend)
        executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
        backend.step(120)
        start_step = backend.total_physics_steps
        samples.append(sample_physical_observation(backend.current_physics_observation(), criteria))
        with MuJoCoCaptureSession(config, backend=backend) as capture:
            last_job_poll = time.monotonic()

            def frame(label: str) -> RGBDObservation:
                active()
                captured = capture.capture_with_instances()
                destination = (
                    output / label if label in {"before", "after"} else folder / "frames" / label
                )
                save_captured_frame(captured, destination)
                marker = detect_pose_marker(
                    captured.observation,
                    PoseMarkerRegistration(
                        marker_id=family.marker_id,
                        marker_size_m=family.marker_size_m,
                        dictionary=cast(Literal["DICT_4X4_50"], family.dictionary),
                        marked_asset_sha256=family.asset_sha256,
                    ),
                    corner_refinement="SUBPIX",
                )
                audit = asdict(marker) | {
                    "continuous_visibility_proven": False,
                    "physics_step": backend.total_physics_steps,
                    "label": label,
                }
                _save(destination / "marker-validation.json", audit)
                frames.append(audit)
                return captured.observation

            def collect(snapshot: Any) -> None:
                nonlocal last_job_poll
                samples.append(sample_physical_observation(snapshot, criteria))
                if backend.total_physics_steps >= 16000:
                    raise ComponentStopped("COMPONENT_PHYSICS_BUDGET_EXHAUSTED")
                now = time.monotonic()
                if (
                    now - start_monotonic >= job.timeout_seconds
                    or worker._heartbeat_failed.is_set()
                ):
                    raise ComponentStopped("COMPONENT_TASK_DEADLINE_OR_LEASE_FAILURE")
                if now - last_job_poll >= 0.05:
                    check_component_lease(
                        worker, job, start_monotonic, expected_attempt=lease_attempt
                    )
                    last_job_poll = now
                check_component_hard_state(backend, robot)

            try:
                before = frame("before")

                def plan(observation: RGBDObservation, name: str) -> Any:
                    return bounded_owner_model_call(
                        lambda: planner.plan(
                            InitialPlanningRequest(
                                request_id=name,
                                user_instruction=draft.user_instruction,
                                observation=observation,
                            )
                        ),
                        timeout_s=max(
                            0.001, job.timeout_seconds - (time.monotonic() - start_monotonic)
                        ),
                        cancelled=lambda: worker._active_job_cancelled(job),
                        resource_key=planner.base_url,
                    )

                first = plan(before, "component-before-cloud")
                if not planner.awaiting_owned_refresh or not first.observation_evidence.get(
                    "owned_refresh_required"
                ):
                    raise ComponentStopped("COMPONENT_INITIAL_PLANNING_REJECTED")
                fresh = frame("post-cloud")
                active()
                proposed = plan(fresh, "component-after-cloud")
                if (
                    proposed.parse_error
                    or not proposed.parsed_json
                    or "_sentinel" in proposed.parsed_json
                ):
                    raise ComponentStopped("COMPONENT_FRESH_PLANNING_REJECTED")
                response = json.loads((planner.output / "planning-stage-02.json").read_text())
                proposed.observation_evidence["role_bundle_hash"] = binding.bundle.digest()
                contract = grounded_contract(
                    proposed,
                    fresh,
                    ExecutionPolicy(
                        instruction=draft.user_instruction,
                        model_snapshot_hash=snapshot.digest(),
                        timeout_s=max(
                            0.001, job.timeout_seconds - (time.monotonic() - start_monotonic)
                        ),
                        device_pipeline="OPENCV",
                        role_binding=binding,
                    ),
                )
                evidence = proposed.observation_evidence
                tracker = OpenCVTargetTracker(fresh, evidence)
                shield = research_safety_shield(job.timeout_seconds)
                row["model_calls"] = ledger.snapshot().model_requests
                row["planning_passed"] = True
                row["contract"] = contract.model_dump(mode="json")
                row["pipeline_validated_contract"] = response["contract"]
                with backend.observe_physics_steps(collect):
                    for index, original in enumerate(contract.steps):
                        active()
                        current = frame(f"pre-{index:02d}-{original.skill.value.lower()}")
                        if (datetime.now(UTC) - current.captured_at).total_seconds() > 5:
                            raise ComponentStopped("CURRENT_COMPONENT_FRAME_EXPIRED")
                        measured, audit = _ground_component(
                            current,
                            tracker,
                            evidence,
                            family_id,
                            original.skill.value,
                            robot.get_state(),
                        )
                        step = resolved_step(original, robot, measured)
                        if step.skill.value == "MOVE_ABOVE" and family_id in {
                            "side_y_plus_id7_75mm_r593",
                            "side_y_plus_id7_75mm_component_v1",
                        }:
                            target = dict(step.parameters["target_pose"])
                            target["y"] -= 0.005
                            step = step.model_copy(
                                update={"parameters": step.parameters | {"target_pose": target}}
                            )
                            audit["registered_side_pregrasp_offset_m"] = [0, -0.005, 0]
                        step_started = time.monotonic()
                        # The diagnostic execution view binds the actual registered resolver's
                        # parameters/timeouts. Preserve the source template separately; neither
                        # SafetyShield nor SkillExecutor may inspect a different step payload.
                        action_contract = contract.model_copy(
                            update={
                                "steps": [
                                    step if item.step_id == step.step_id else item
                                    for item in contract.steps
                                ]
                            },
                            deep=True,
                        )

                        def safety(
                            observation: RGBDObservation,
                            phase: str,
                            *,
                            action_contract: Any = action_contract,
                            step: Any = step,
                            step_started: float = step_started,
                        ) -> None:
                            now = datetime.now(UTC)
                            context = shield.context_builder.build(
                                contract=action_contract,
                                step=step,
                                robot_state=robot.get_state(),
                                scene_version=contract.scene_version,
                                resolved_parameters=dict(step.parameters),
                                scene_updated_at=observation.captured_at,
                                telemetry_timestamp=now,
                                wall_clock_now=now,
                                step_started_at_mono=step_started,
                                task_started_at_mono=start_monotonic,
                                monotonic_now=time.monotonic(),
                                requested_joint_velocities=[
                                    *map(abs, backend.get_joint_state().velocities),
                                    float(step.parameters.get("tcp_velocity", 0)) / 0.3,
                                ],
                                requested_velocity=float(step.parameters.get("tcp_velocity", 0)),
                                requested_acceleration=float(
                                    step.parameters.get("acceleration", 0)
                                ),
                            )
                            verdict = getattr(
                                shield, "pre_check" if phase == "PRE" else "post_check"
                            )(context)
                            checks.append(
                                {
                                    "step_id": step.step_id,
                                    "phase": phase,
                                    "verdict": asdict(verdict),
                                }
                            )
                            if not verdict.allowed or (
                                verdict.limited_parameters is not None
                                and verdict.limited_parameters != step.parameters
                            ):
                                raise ComponentStopped(
                                    "SAFETY_SHIELD_" + phase + "_REJECTED_OR_LIMITED"
                                )

                        check_component_hard_state(backend, robot)
                        safety(current, "PRE")
                        active()
                        beginning = backend.total_physics_steps
                        action = {
                            "step_id": step.step_id,
                            "skill": step.skill.value,
                            "resolved_step": step.model_dump(mode="json"),
                            "grounding": audit,
                            "component_execution_contract": action_contract.model_dump(mode="json"),
                            "source_template_timeout_ms": original.timeout_ms,
                            "original_conditions_preserved_in_contract": True,
                            "original_full_effect_conditions_certified": False,
                            "start_step": beginning,
                        }
                        actions.append(action)
                        try:
                            outcome = executor.execute_attempt(
                                contract=action_contract, step=step, attempt=1
                            )
                            action["controller_result"] = asdict(outcome)
                            action["controller_return_step"] = backend.total_physics_steps
                            if not outcome.success:
                                raise ComponentStopped(
                                    "CONTROLLER_FAILURE:" + (outcome.error_code or "UNKNOWN")
                                )
                            # Check controller return before the separate observation hold.
                            # Keep the real pre-action timestamp subject to the scene TTL.
                            safety(current, "POST")
                            action["diagnostic_settle_steps"] = _SETTLE_STEPS[step.skill.value]
                            backend.step(_SETTLE_STEPS[step.skill.value])
                        finally:
                            action["end_step"] = backend.total_physics_steps
                            row["executed_actions"] += int(backend.total_physics_steps > beginning)
                        frame(f"post-{index:02d}-{step.skill.value.lower()}")
                    backend.step(288)
                    frame("terminal-stability")
                    row["diagnostic_complete"] = True
            except Exception as error:
                row["terminal_reason"] = (
                    str(error) if isinstance(error, ComponentStopped) else type(error).__name__
                )
                robot.safe_stop()
            finally:
                try:
                    frame("after")
                except Exception as error:
                    row["after_capture_error_type"] = type(error).__name__
                    row["diagnostic_complete"] = False
                    if row["terminal_reason"] is None:
                        row["terminal_reason"] = "AFTER_CAPTURE_FAILED:" + type(error).__name__
                physical = evaluate_episode(
                    backend, criteria, evidence=samples, evaluation_start_step=start_step
                )
                row["independent_physical_outcome"] = asdict(physical)
                row["physical_success"] = physical.success
                if row["terminal_reason"] is None and not physical.success:
                    row["terminal_reason"] = physical.failure_reason
                row["status"] = "COMPONENTS_COMPLETED" if row["diagnostic_complete"] else "FAILED"
    except Exception as error:
        if row["terminal_reason"] is None:
            row["terminal_reason"] = type(error).__name__
        raise
    finally:
        row["physics_steps"] = backend.total_physics_steps
        row["episode_id"] = backend._episode_id
        row["observation_count"] = len(frames)
        row["cloud_requests"] = ledger.snapshot().cloud_model_requests
        row["local_generations"] = cast(
            Any, planner.grounded.point_provider
        ).generation_calls_started
        row["model_calls"] = row["cloud_requests"] + row["local_generations"]
        try:
            _save(folder / "physical-evidence.json", [asdict(sample) for sample in samples])
            archived_episode = _save(folder / "episode.json", row)
        finally:
            backend.shutdown()
    # Publish exactly the JSON-compatible diagnostic that was archived locally.
    return json.loads(archived_episode), [], []
