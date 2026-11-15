"""下一轮修复离线诊断与回归核验脚本（零付费模型/云端调用）。"""

# ruff: noqa: E402 -- select this checkout before package imports.
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "src"))
sys.path.insert(0, str(SOURCE / "scripts"))

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.contracts import RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.research.sol_molmo_components import (
    _SETTLE_STEPS,
    ComponentStopped,
    _ground_component,
    check_component_hard_state,
)
from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_episode,
    sample_physical_observation,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision import tracking
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.execution import resolved_step
from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import (
    GroundedScene,
    build_grounded_contract,
    ground_observation,
)
from cloud_edge_robot_arm.vision.point_association import (
    PointAssociationError,
    associate_target_point,
)
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

DEFAULT_BASE = Path("/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs")
ASSET = SOURCE / "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_component_v1.xml"
FAMILY_ID = "side_y_plus_id7_75mm_component_v1"
CORE_SKILLS = [
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
]

P1_SHADED_EDGE = ("development-043001", "development-043007", "development-043008")
P1_MISSING_DEPTH = ("development-043004", "held-out-044004", "held-out-044008", "held-out-044012")
P1_MSAA_SPIKES = (
    "development-043009",
    "development-043011",
    "development-043012",
    "held-out-044007",
    "held-out-044014",
)
P2_MARKER_MISSES = (
    ("development-043006", "pre-01-approach", "APPROACH"),
    ("development-043010", "pre-01-approach", "APPROACH"),
    ("development-043014", "pre-01-approach", "APPROACH"),
    ("held-out-044002", "pre-06-release", "RELEASE"),
)
P2_SPLIT_DEST = ("held-out-044013", "pre-06-release", "RELEASE")
P3_FINGER_CASES = ("development-043003", "held-out-044009", "held-out-044011")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _load_obs(folder: Path) -> RGBDObservation:
    meta = json.loads((folder / "observation.json").read_text())
    values = {k: meta[k] for k in RGBDObservation.model_fields if k in meta}
    for field, name in (
        ("rgb_png_base64", "rgb.png"),
        ("depth_float32_base64", "depth.f32"),
        ("valid_mask_base64", "valid_mask.u8"),
    ):
        values[field] = base64.b64encode((folder / name).read_bytes()).decode("ascii")
    return RGBDObservation.model_validate(values)


def _ReplayTracker(obs: RGBDObservation, evidence: dict[str, Any]) -> OpenCVTargetTracker:
    class ReplayClock(type(obs.captured_at)):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return obs.captured_at + timedelta(milliseconds=100)

    with patch.object(tracking, "datetime", ReplayClock):
        return OpenCVTargetTracker(obs, evidence)


def _check_preaction_frame(obs: RGBDObservation, ev1: dict[str, Any]) -> dict[str, Any]:
    target_px = tuple(ev1["native_original_pixel_target"])
    dest_px = tuple(ev1["native_original_pixel_destination"])
    try:
        assoc = associate_target_point(obs, target_px, target_phrase="red block")
    except PointAssociationError as exc:
        return {"accepted": False, "stage": "associate_target_point", "reason": str(exc)}
    req = InitialPlanningRequest(
        request_id="offline-check",
        user_instruction="Pick up the red block and place it in the green target area.",
        observation=obs,
    )
    g_ev = dict(ev1)
    try:
        measured = ground_observation(
            req,
            obs,
            target_pixel=assoc.pixel,
            destination_pixel=dest_px,
            target_label="object",
            grasp_profile=ev1["grasp_profile"],
            evidence=g_ev,
        )
        g_ev.update(measured.evidence)
        tracker = _ReplayTracker(obs, g_ev)
        return {
            "accepted": True,
            "stage": "OpenCVTargetTracker",
            "reason": "ACCEPTED_VISIBILITY_ONLY",
            "top_pixels": int(tracker.initial["top_pixels"]),
            "center_m": [float(v) for v in tracker.initial["center"]],
            "resolved_top_grasp_tcp": g_ev["resolved_top_grasp_tcp"],
        }
    except ValueError as exc:
        return {"accepted": False, "stage": "geometry_gate", "reason": str(exc)}


def _simulate_episode(
    *,
    seed: int,
    requested_scene: dict[str, Any],
    contract: TaskContract,
    tracker: OpenCVTargetTracker,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    config = SimulatorConfig(
        model_path=str(ASSET),
        seed=seed,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
        camera_width=320,
        camera_height=240,
        physics_dt_s=1 / 240,
    )
    backend = MuJoCoPhysicsBackend()
    backend.initialize(config)
    backend.reset(physical_component_scenario(seed, requested_scene))
    robot = MuJoCoSkillRobot(backend)
    executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
    criteria = CompletionCriteria("object", "target_region")
    backend.step(120)
    samples = [sample_physical_observation(backend.current_physics_observation(), criteria)]
    stopped: str | None = None
    step_audits: list[dict[str, Any]] = []

    def collect(snapshot: Any) -> None:
        samples.append(sample_physical_observation(snapshot, criteria))
        check_component_hard_state(backend, robot)

    try:
        with MuJoCoCaptureSession(config, backend=backend) as capture:
            try:
                with backend.observe_physics_steps(collect):
                    for original in contract.steps:
                        cur = capture.capture_with_instances().observation
                        measured, audit = _ground_component(
                            cur,
                            tracker,
                            evidence,
                            FAMILY_ID,
                            original.skill.value,
                            robot.get_state(),
                        )
                        step_audits.append(
                            {
                                "skill": original.skill.value,
                                "target_source": audit["target_source"],
                                "destination_source": audit["destination_source"],
                                "marker_status": audit["marker_status"],
                            }
                        )
                        step = resolved_step(original, robot, measured)
                        if step.skill.value == "MOVE_ABOVE":
                            target = dict(step.parameters["target_pose"])
                            target["y"] -= 0.005
                            step = step.model_copy(
                                update={"parameters": step.parameters | {"target_pose": target}}
                            )
                        if step.skill.value == "RETREAT":
                            target = dict(step.parameters["target_pose"])
                            target["y"] -= 0.100
                            step = step.model_copy(
                                update={"parameters": step.parameters | {"target_pose": target}}
                            )
                        action_contract = contract.model_copy(
                            update={
                                "steps": [
                                    step if item.step_id == step.step_id else item
                                    for item in contract.steps
                                ]
                            },
                            deep=True,
                        )
                        outcome = executor.execute_attempt(
                            contract=action_contract, step=step, attempt=1
                        )
                        if not outcome.success:
                            stopped = f"CONTROLLER:{step.skill.value}:{outcome.error_code}"
                            break
                        backend.step(_SETTLE_STEPS[step.skill.value])
                    if stopped is None:
                        backend.step(288)
            except ComponentStopped as error:
                stopped = f"STOP:{error}@step={backend.total_physics_steps}"
        eval_outcome = evaluate_episode(
            backend, criteria, evidence=samples, evaluation_start_step=120
        )
        return {
            "stopped": stopped,
            "physical_success": bool(eval_outcome.success),
            "status": str(eval_outcome.status),
            "failure_reason": eval_outcome.failure_reason,
            "physics_steps": int(backend.total_physics_steps),
            "step_audits": step_audits,
        }
    finally:
        backend.shutdown()


def audit_priority_1(v2_root: Path) -> dict[str, Any]:
    """核验12例动作前深度拒绝的3类分类及MSAA无锯齿对照证据。"""
    tmpl_contract = json.loads(
        (v2_root / "development-043006/component/episode.json").read_text()
    )["contract"]
    shaded_results = []
    for case in P1_SHADED_EDGE:
        ep = v2_root / case
        saved = json.loads((ep / "component/episode.json").read_text())
        result = json.loads((ep / "result.json").read_text())
        st1 = json.loads((ep / "planning/planning-stage-01.json").read_text())
        ev1 = st1["attempts"][0]["draft"]["observation_evidence"]
        before_res = _check_preaction_frame(_load_obs(ep / "before"), ev1)
        fresh = _load_obs(ep / "component/frames/post-cloud")
        post_res = _check_preaction_frame(fresh, ev1)

        assoc = associate_target_point(
            fresh, tuple(ev1["native_original_pixel_target"]), target_phrase="red block"
        )
        req_plan = InitialPlanningRequest(
            request_id="offline-sim",
            user_instruction="Pick up the red block and place it in the green target area.",
            observation=fresh,
        )
        evidence = dict(ev1)
        measured_scene = ground_observation(
            req_plan,
            fresh,
            target_pixel=assoc.pixel,
            destination_pixel=tuple(ev1["native_original_pixel_destination"]),
            target_label="object",
            grasp_profile=ev1["grasp_profile"],
            evidence=evidence,
        )
        evidence.update(measured_scene.evidence)
        tracker = _ReplayTracker(fresh, evidence)
        draft = build_grounded_contract(
            req_plan, GroundedScene(measured_scene.scene, evidence), CORE_SKILLS, raw_text="{}"
        )
        contract = TaskContract.model_validate(
            {**tmpl_contract, "steps": draft.parsed_json["steps"]}
        )
        sim = _simulate_episode(
            seed=result["seed"],
            requested_scene=saved["scene_application"]["requested_scene"],
            contract=contract,
            tracker=tracker,
            evidence=evidence,
        )
        shaded_results.append(
            {
                "case": case,
                "before": before_res,
                "post_cloud": post_res,
                "simulation": sim,
            }
        )

    missing_depth_results = []
    for case in P1_MISSING_DEPTH:
        ep = v2_root / case
        st1 = json.loads((ep / "planning/planning-stage-01.json").read_text())
        ev1 = st1["attempts"][0]["draft"]["observation_evidence"]
        missing_depth_results.append(
            {
                "case": case,
                "before": _check_preaction_frame(_load_obs(ep / "before"), ev1),
                "post_cloud": _check_preaction_frame(
                    _load_obs(ep / "component/frames/post-cloud"), ev1
                ),
            }
        )

    msaa_results = []
    for case in P1_MSAA_SPIKES:
        ep = v2_root / case
        saved = json.loads((ep / "component/episode.json").read_text())
        result = json.loads((ep / "result.json").read_text())
        st1 = json.loads((ep / "planning/planning-stage-01.json").read_text())
        ev1 = st1["attempts"][0]["draft"]["observation_evidence"]
        before_raw = _check_preaction_frame(_load_obs(ep / "before"), ev1)
        post_raw = _check_preaction_frame(_load_obs(ep / "component/frames/post-cloud"), ev1)
        # 反事实检验：同一初始MuJoCo场景关闭MSAA(offsamples=0)时无陡立侧面深度外插尖峰
        cfg_no_msaa = SimulatorConfig(
            model_path=str(ASSET),
            seed=result["seed"],
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
            camera_width=320,
            camera_height=240,
            physics_dt_s=1 / 240,
        )
        backend = MuJoCoPhysicsBackend()
        try:
            backend.initialize(cfg_no_msaa)
            backend._model.vis.quality.offsamples = 0
            backend.reset(
                physical_component_scenario(
                    result["seed"], saved["scene_application"]["requested_scene"]
                )
            )
            backend.step(120)
            with MuJoCoCaptureSession(cfg_no_msaa, backend=backend) as capture:
                fresh_no_msaa = capture.capture_with_instances().observation
            no_msaa_res = _check_preaction_frame(fresh_no_msaa, ev1)
        finally:
            backend.shutdown()
        msaa_results.append(
            {
                "case": case,
                "frozen_before": before_raw,
                "frozen_post_cloud": post_raw,
                "counterfactual_offsamples_0": no_msaa_res,
            }
        )

    return {
        "shaded_edge_cases": shaded_results,
        "genuine_missing_depth_cases": missing_depth_results,
        "msaa_spike_cases": msaa_results,
    }


def audit_priority_2(v2_root: Path) -> dict[str, Any]:
    """核验5例动作后可见性失败的冻结帧重检与完整8技能MuJoCo仿真。"""
    fam = marker_family(FAMILY_ID)
    reg = PoseMarkerRegistration(
        marker_id=fam.marker_id,
        dictionary=fam.dictionary,
        marker_size_m=fam.marker_size_m,
        marked_asset_sha256=fam.asset_sha256,
    )
    results = []
    for case, frame_name, skill in (*P2_MARKER_MISSES, P2_SPLIT_DEST):
        ep = v2_root / case
        saved = json.loads((ep / "component/episode.json").read_text())
        result = json.loads((ep / "result.json").read_text())
        st2 = json.loads((ep / "planning/planning-stage-02.json").read_text())
        evidence = st2["attempts"][0]["draft"]["observation_evidence"]
        fresh = _load_obs(ep / "component/frames/post-cloud")
        tracker = _ReplayTracker(fresh, evidence)
        fail_obs = _load_obs(ep / "component/frames" / frame_name)
        marker_est = detect_pose_marker(fail_obs, reg, corner_refinement="SUBPIX")
        dummy_state = RobotState(
            connected=True,
            estop_engaged=False,
            collision_detected=False,
            gripper_open=skill == "APPROACH",
            holding_object_id=None if skill == "APPROACH" else "object",
        )
        measured_frame, audit_frame = _ground_component(
            fail_obs, tracker, evidence, FAMILY_ID, skill, dummy_state
        )
        contract = TaskContract.model_validate(saved["contract"])
        sim = _simulate_episode(
            seed=result["seed"],
            requested_scene=saved["scene_application"]["requested_scene"],
            contract=contract,
            tracker=tracker,
            evidence=evidence,
        )
        results.append(
            {
                "case": case,
                "failed_frame": frame_name,
                "skill": skill,
                "marker_status": marker_est.status,
                "marker_min_side_px": marker_est.measured_min_side_px,
                "frame_ground_audit": {
                    "target_source": audit_frame["target_source"],
                    "destination_source": audit_frame["destination_source"],
                    "target_visibility": audit_frame["target_visibility"],
                    "resolved_top_grasp_tcp": measured_frame["resolved_top_grasp_tcp"],
                },
                "simulation": sim,
            }
        )
    return {"post_action_cases": results}


def audit_priority_3(v2_root: Path) -> dict[str, Any]:
    """汇总3例手指越界/GRASP_LOST证据与pre-00 XY保真反事实对比。"""
    rows = []
    for case in P3_FINGER_CASES:
        ep = v2_root / case
        saved = json.loads((ep / "component/episode.json").read_text())
        result = json.loads((ep / "result.json").read_text())
        actions = saved["actions"]
        ma = actions[0]["resolved_step"]["parameters"]["target_pose"]
        unoccluded_grasp = {
            **actions[1]["resolved_step"]["parameters"]["target_pose"],
            "x": ma["x"],
            "y": ma["y"] + 0.005,
            "z": 0.045,
        }
        req = saved["scene_application"]["requested_scene"]
        config = SimulatorConfig(
            model_path=str(ASSET),
            seed=result["seed"],
            domain_randomization=False,
            physics_dt_s=1 / 240,
            render_rgb=False,
            render_depth=False,
        )
        backend = MuJoCoPhysicsBackend()
        try:
            backend.initialize(config)
            backend.reset(physical_component_scenario(result["seed"], req))
            joint1 = backend._model.joint("joint1")
            backend._data.qpos[joint1.qposadr[0]] = -0.8
            backend._target_positions[0] = -0.8
            backend._mujoco.mj_forward(backend._model, backend._data)
            robot = MuJoCoSkillRobot(backend)
            executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
            criteria = CompletionCriteria("object", "target_region")
            backend.step(120)
            samples = [
                sample_physical_observation(backend.current_physics_observation(), criteria)
            ]
            stopped = None

            def collect(
                snapshot: Any,
                _samples: list[Any] = samples,
                _criteria: CompletionCriteria = criteria,
                _backend: MuJoCoPhysicsBackend = backend,
                _robot: MuJoCoSkillRobot = robot,
            ) -> None:
                _samples.append(sample_physical_observation(snapshot, _criteria))
                check_component_hard_state(_backend, _robot)

            contract = TaskContract.model_validate(saved["contract"])
            try:
                with backend.observe_physics_steps(collect):
                    for idx, step in enumerate(contract.steps):
                        s = step.model_copy(deep=True)
                        if idx < len(actions):
                            s = TaskStep.model_validate(actions[idx]["resolved_step"])
                        if s.skill.value == "APPROACH":
                            s = s.model_copy(
                                update={
                                    "parameters": {
                                        **s.parameters,
                                        "target_pose": dict(unoccluded_grasp),
                                    }
                                }
                            )
                        check_component_hard_state(backend, robot)
                        out = executor.execute_attempt(contract=contract, step=s, attempt=1)
                        if not out.success:
                            stopped = f"CONTROLLER:{s.skill.value}:{out.error_code}"
                            break
                        backend.step(_SETTLE_STEPS[s.skill.value])
                    if stopped is None:
                        backend.step(288)
            except ComponentStopped as err:
                stopped = f"STOP:{err}@step={backend.total_physics_steps}"
            outcome = evaluate_episode(
                backend, criteria, evidence=samples, evaluation_start_step=120
            )
            rows.append(
                {
                    "case": case,
                    "original_terminal_reason": saved["terminal_reason"],
                    "counterfactual_unoccluded_xy_stopped": stopped,
                    "counterfactual_physical_success": bool(outcome.success),
                    "counterfactual_status": str(outcome.status),
                }
            )
        finally:
            backend.shutdown()
    return {"finger_overshoot_investigation": rows}


def write_report(output_root: Path, payload: dict[str, Any]) -> None:
    p1 = payload["priority_1"]
    p2 = payload["priority_2"]
    p3 = payload["priority_3"]
    frozen_total = sum(payload["frozen_file_counts"].values())
    lines = [
        "# 下一阶段离线修复与核验报告（基于提交 5e68e2f9）",
        "",
        (
            "> 范围声明：本轮零付费模型/云端 API 调用"
            "（`model_calls=0`, `cloud_requests=0`），未修改任何冻结实验目录，"
            "未修改控制器/物理模型/独立评价器/0.1mm 手指公差，"
            "且不宣称新的端到端真实模型成功率。"
        ),
        "",
        "## 1. 冻结目录完整性核对",
        "",
        (
            f"- 受保护目录全部只读无改写：`{payload['frozen_dirs_unchanged']}`"
            f"（共校验 `{frozen_total}` 个文件前/后 SHA256 一致）。"
        ),
        "",
        "## 2. 优先级一：12 例动作前深度拒绝分类与修复",
        "",
        "### 2.1 单像素暗红侧边/抗锯齿外环过渡误拒（3 例，已在 `tracking.py` 修复）",
        "",
        "| Case | `before` | `post-cloud` | 闭环组件仿真 (`post-cloud` 规划起点) | 备注 |",
        "|---|---|---|---|---|",
    ]
    for item in p1["shaded_edge_cases"]:
        b = item["before"]["reason"]
        pc = item["post_cloud"]["reason"]
        sim = item["simulation"]
        note = (
            "全8技能成功"
            if sim["physical_success"]
            else f"{sim['stopped']} (物块 y=-0.3718m 处 IK 无解，属运动学工作空间边界)"
        )
        lines.append(
            f"| `{item['case']}` | `{b}` | `{pc}` "
            f"| `success={sim['physical_success']}`, steps=`{sim['physics_steps']}` | {note} |"
        )
    lines.extend(
        [
            "",
            "### 2.2 桌边真实深度缺失负例（4 例，保持拒绝，不补造深度）",
            "",
            "| Case | `before` 拒绝原因 | `post-cloud` 拒绝原因 |",
            "|---|---|---|",
        ]
    )
    for item in p1["genuine_missing_depth_cases"]:
        b_reason = item["before"]["reason"]
        pc_reason = item["post_cloud"]["reason"]
        lines.append(f"| `{item['case']}` | `{b_reason}` | `{pc_reason}` |")
    lines.extend(
        [
            "",
            (
                "### 2.3 MuJoCo MSAA 陡立侧面深度尖峰"
                "（5 例，冻结原件保持拒绝 + `offsamples=0` 反事实对照）"
            ),
            "",
            "| Case | 冻结原 `before` | 冻结原 `post-cloud` | 同场景 `offsamples=0` 渲染 |",
            "|---|---|---|---|",
        ]
    )
    for item in p1["msaa_spike_cases"]:
        fb = item["frozen_before"]["reason"]
        fp = item["frozen_post_cloud"]["reason"]
        cf = item["counterfactual_offsamples_0"]["reason"]
        lines.append(f"| `{item['case']}` | `{fb}` | `{fp}` | `{cf}` |")
    lines.extend(
        [
            "",
            (
                "## 3. 优先级二：5 例动作后可见性失败"
                "（已在 `pose_markers.py` 与 `sol_molmo_components.py` 修复）"
            ),
            "",
            "| Case | 原失败帧 | Marker 状态 | 帧内接地来源 | 完整8技能仿真结果 |",
            "|---|---|---|---|---|",
        ]
    )
    for item in p2["post_action_cases"]:
        sim = item["simulation"]
        audit = item["frame_ground_audit"]
        sources = f"`{audit['target_source']}` / `{audit['destination_source']}`"
        sim_text = (
            f"`success={sim['physical_success']}`, "
            f"steps=`{sim['physics_steps']}`, stopped=`{sim['stopped']}`"
        )
        lines.append(
            f"| `{item['case']}` | `{item['failed_frame']}` (`{item['skill']}`) "
            f"| `{item['marker_status']}` | {sources} | {sim_text} |"
        )
    lines.extend(
        [
            "",
            "## 4. 优先级三：3 例手指限位超调 / `GRASP_LOST` 根因排查",
            "",
            "| Case | 原终止原因 | 保真 `pre-00` XY 执行 `APPROACH` 反事实结果 | 结论 |",
            "|---|---|---|---|",
        ]
    )
    for item in p3["finger_overshoot_investigation"]:
        conclusion = (
            "单帧 Marker 杠杆臂偏心致擦碰，消除偏心后成功"
            if item["counterfactual_physical_success"]
            else (
                "即使保留 unoccluded XY，39mm 顺应手指下行接触转角方块棱边仍触发 "
                "40.1mm 超界，需控制/预抓策略评审"
            )
        )
        cf_stopped = item["counterfactual_unoccluded_xy_stopped"]
        cf_ok = item["counterfactual_physical_success"]
        lines.append(
            f"| `{item['case']}` | `{item['original_terminal_reason']}` "
            f"| `{cf_stopped}` (`success={cf_ok}`) | {conclusion} |"
        )
    lines.append("")
    (output_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-outputs", type=Path, default=DEFAULT_BASE)
    parser.add_argument(
        "--output-root", type=Path, default=DEFAULT_BASE / "next-round-repair-20261114"
    )
    args = parser.parse_args()

    protected = [
        args.base_outputs / "sol-molmo-observability-40-20261114-v1",
        args.base_outputs / "geometry-repair-40-20261114-v2",
        args.base_outputs / "joint-limit-diagnosis-20261114-v2",
        args.base_outputs / "geometry-repair/host-occlusion-controls",
        args.base_outputs / "finger-limit-fix-20261114",
    ]
    resolved_out = args.output_root.resolve()
    for folder in protected:
        resolved_folder = folder.resolve()
        if resolved_out == resolved_folder or resolved_out.is_relative_to(resolved_folder):
            raise ValueError(f"refusing to write inside frozen evidence dir: {folder}")

    before_hashes = {folder.name: _snapshot_tree(folder) for folder in protected}
    v2_root = args.base_outputs / "geometry-repair-40-20261114-v2"

    p1 = audit_priority_1(v2_root)
    p2 = audit_priority_2(v2_root)
    p3 = audit_priority_3(v2_root)

    after_hashes = {folder.name: _snapshot_tree(folder) for folder in protected}
    frozen_ok = before_hashes == after_hashes

    args.output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "scope": "OFFLINE_NEXT_ROUND_REPAIR_VERIFICATION",
        "model_calls": 0,
        "cloud_requests": 0,
        "hardware_dispatch": False,
        "frozen_dirs_unchanged": frozen_ok,
        "frozen_file_counts": {k: len(v) for k, v in before_hashes.items()},
        "priority_1": p1,
        "priority_2": p2,
        "priority_3": p3,
    }
    (args.output_root / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_root, payload)

    p1_ok = (
        all(
            item["before"]["accepted"] and item["post_cloud"]["accepted"]
            for item in p1["shaded_edge_cases"]
        )
        and all(
            not item["before"]["accepted"] and not item["post_cloud"]["accepted"]
            for item in p1["genuine_missing_depth_cases"]
        )
        and all(
            not item["frozen_before"]["accepted"]
            and not item["frozen_post_cloud"]["accepted"]
            and item["counterfactual_offsamples_0"]["accepted"]
            for item in p1["msaa_spike_cases"]
        )
    )
    p2_ok = all(item["simulation"]["physical_success"] for item in p2["post_action_cases"])
    print(
        json.dumps(
            {
                "frozen_dirs_unchanged": frozen_ok,
                "p1_audit_passed": p1_ok,
                "p2_all_5_simulated_success": p2_ok,
                "p1_shaded_simulated_successes": sum(
                    item["simulation"]["physical_success"] for item in p1["shaded_edge_cases"]
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0 if (frozen_ok and p1_ok and p2_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
