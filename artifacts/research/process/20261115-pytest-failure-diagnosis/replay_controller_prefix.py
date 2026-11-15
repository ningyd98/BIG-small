"""独立离线诊断：重放四例的冻结运动前缀，逐物理步记录手指，保留原硬停止。"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.research.sol_molmo_components import (
    ComponentStopped,
    check_component_hard_state,
)
from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
    NetworkDenyGuard,
    load_v3_manifest,
)
from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

CASES = (
    "development-043003",
    "development-043008",
    "held-out-044009",
    "held-out-044011",
)


def inventory(root: Path, spec: Path) -> dict[str, str]:
    """使用全仓验证来源清单记录本独立诊断的准确当前字节。"""
    rows = json.loads(spec.read_bytes())["sources"]
    values = {}
    for row in rows:
        name = row["path"]
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("SOURCE_PATH_ESCAPE")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != row["bytes"] or digest != row["sha256"]:
            raise ValueError("SOURCE_SPEC_MISMATCH:" + name)
        if name in values:
            raise ValueError("DUPLICATE_SOURCE")
        values[name] = digest
    return values


def replay(case, root: Path, output: Path) -> dict:
    """仅用冻结 resolved_step 作离线教师；不冒充新视觉、worker或研究验收。"""
    assignment = case.json("scene-assignment.json")
    episode = case.json("component/episode.json")
    before = case.json("before/observation.json")
    asset = root / assignment["model_path"]
    if hashlib.sha256(asset.read_bytes()).hexdigest() != assignment["asset_sha256"]:
        raise ValueError("FROZEN_ASSET_MISMATCH")
    if [a["skill"] for a in episode["actions"]] not in (["MOVE_ABOVE"], ["MOVE_ABOVE", "APPROACH"]):
        raise ValueError("UNEXPECTED_FROZEN_PREFIX")
    config = SimulatorConfig(
        model_path=str(asset),
        seed=assignment["seed"],
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
        camera_width=320,
        camera_height=240,
        physics_dt_s=1 / 240,
    )
    backend = MuJoCoPhysicsBackend()
    rows, results, checks = [], [], []
    active_skill = "SETTLE"
    started = time.monotonic()
    stopped = None
    initial_matches = False
    final_matches = False
    read_names = {"scene-assignment.json", "component/episode.json", "before/observation.json"}
    try:
        backend.initialize(config)
        backend.reset(
            physical_component_scenario(assignment["seed"], assignment["component_scene"])
        )
        robot = MuJoCoSkillRobot(backend)
        backend.step(120)
        initial_matches = (
            MuJoCoRGBDCamera._physics_state_hash(backend._data) == before["physics_state_hash"]
        )
        if not initial_matches:
            raise ValueError("FROZEN_INITIAL_PHYSICS_STATE_MISMATCH")
        fingers = {
            name: backend._model.joint(name) for name in ("finger_left_joint", "finger_right_joint")
        }

        def observe(snapshot):
            """只读样本先保存，再调用未修改的每步硬检查，异常原样中止物理批次。"""
            sample = {
                "physics_step": backend.total_physics_steps,
                "sim_time_s": float(backend._data.time),
                "skill": active_skill,
                "fingers": {
                    name: {
                        "qpos_m": float(backend._data.qpos[joint.qposadr[0]]),
                        "qvel_m_s": float(backend._data.qvel[joint.dofadr[0]]),
                        "physical_range_m": joint.range.tolist(),
                    }
                    for name, joint in fingers.items()
                },
                "all_actuator_ctrl": backend._data.ctrl.tolist(),
                "contact_pairs": [list(p) for p in snapshot.contact_pairs],
                "physics_state_hash": MuJoCoRGBDCamera._physics_state_hash(backend._data),
            }
            rows.append(sample)
            if backend.total_physics_steps >= 16000 or time.monotonic() - started >= 180:
                raise RuntimeError("DIAGNOSTIC_RESOURCE_CAP")
            try:
                check_component_hard_state(backend, robot)
            except ComponentStopped as error:
                sample["hard_stop"] = str(error)
                raise

        with backend.observe_physics_steps(observe):
            for action in episode["actions"]:
                active_skill = action["skill"]
                index = len(results)
                frame = f"component/frames/pre-{index:02d}-{active_skill.lower()}/observation.json"
                old = case.json(frame)
                read_names.add(frame)
                matches = (
                    backend.total_physics_steps == action["start_step"]
                    and MuJoCoRGBDCamera._physics_state_hash(backend._data)
                    == old["physics_state_hash"]
                )
                checks.append(
                    {"phase": active_skill + "_PRE", "frozen_physics_state_matches": matches}
                )
                if not matches:
                    raise ValueError("FROZEN_ACTION_START_STATE_MISMATCH")
                check_component_hard_state(backend, robot)
                step = action["resolved_step"]
                parameters = dict(step["parameters"])
                parameters["resolved_target"] = Pose.model_validate(parameters.pop("target_pose"))
                parameters["timeout_ms"] = step["timeout_ms"]
                result = getattr(robot, active_skill.lower())(**parameters)
                results.append({"skill": active_skill, "result": result.model_dump(mode="json")})
                if not result.success:
                    stopped = "CONTROLLER_FAILURE:" + result.error_code
                    break
                backend.step(action["diagnostic_settle_steps"])
                post_name = (
                    f"component/frames/post-{index:02d}-{active_skill.lower()}/observation.json"
                )
                old_post = case.json(post_name)
                read_names.add(post_name)
                matches = (
                    backend.total_physics_steps == action["end_step"]
                    and MuJoCoRGBDCamera._physics_state_hash(backend._data)
                    == old_post["physics_state_hash"]
                )
                checks.append(
                    {"phase": active_skill + "_POST", "frozen_physics_state_matches": matches}
                )
                if not matches:
                    raise ValueError("FROZEN_ACTION_END_STATE_MISMATCH")
    except ComponentStopped as error:
        stopped = str(error)
    finally:
        if backend._data is not None:
            final_steps = backend.total_physics_steps
            if "robot" in locals():
                robot.safe_stop()
                if initial_matches and stopped is not None:
                    final_frame = "after/observation.json"
                    read_names.add(final_frame)
                    expected_final = case.json(final_frame)
                    final_hash = MuJoCoRGBDCamera._physics_state_hash(backend._data)
                    final_matches = (
                        final_steps == episode["actions"][-1]["end_step"]
                        and final_hash == expected_final["physics_state_hash"]
                    )
                    checks.append(
                        {
                            "phase": "FAILURE_POST_SAFE_STOP",
                            "frozen_physics_state_matches": final_matches,
                            "actual_physics_step": final_steps,
                            "expected_physics_step": episode["actions"][-1]["end_step"],
                            "actual_physics_state_hash": final_hash,
                            "expected_physics_state_hash": expected_final["physics_state_hash"],
                        }
                    )
        else:
            final_steps = None
        backend.shutdown()
        output.mkdir(exist_ok=False)
        with (output / "physics.jsonl").open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    ranges = (
        {
            name: {
                "minimum_qpos_m": min(row["fingers"][name]["qpos_m"] for row in rows),
                "maximum_qpos_m": max(row["fingers"][name]["qpos_m"] for row in rows),
            }
            for name in ("finger_left_joint", "finger_right_joint")
        }
        if rows
        else {}
    )
    return {
        "scope": "OFFLINE_FROZEN_RESOLVED_PREFIX_PHYSICS_DIAGNOSIS",
        "case": case.root.name,
        "initial_frozen_physics_state_matches": initial_matches,
        "checks": checks,
        "terminal_reason": stopped,
        "original_terminal_reason": episode["terminal_reason"],
        "terminal_reason_matches": stopped == episode["terminal_reason"],
        "failure_final_frozen_physics_state_matches": final_matches,
        "exact_failure_prefix_reproduced": (
            stopped == episode["terminal_reason"]
            and initial_matches
            and final_matches
            and all(check["frozen_physics_state_matches"] for check in checks)
        ),
        "final_physics_step": final_steps,
        "original_final_action_end_step": episode["actions"][-1].get("end_step"),
        "samples": len(rows),
        "finger_ranges": ranges,
        "last_samples": rows[-3:],
        "controller_results": results,
        "original_contract_shield_planner_worker_reexecuted": False,
        "new_models": 0,
        "formal_research_acceptance": False,
        "msaa_or_controller_trajectory_modified": False,
        "bound_inputs": {
            name: {key: case.files[name][key] for key in ("sha256", "bytes")}
            for name in sorted(read_names)
        },
        "trace_sha256": hashlib.sha256((output / "physics.jsonl").read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v3", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("source_spec", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    sources = inventory(args.root, args.source_spec)
    entry_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with NetworkDenyGuard() as guard:
        manifest = load_v3_manifest(args.v3, args.snapshot)
        selected = (args.case,) if args.case is not None else CASES
        summary = [replay(manifest.cases[name], args.root, args.output / name) for name in selected]
    if inventory(args.root, args.source_spec) != sources:
        raise ValueError("SOURCE_CHANGED_DURING_DIAGNOSTIC")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != entry_sha:
        raise ValueError("DIAGNOSTIC_SCRIPT_CHANGED")
    receipt = {
        "scope": "OFFLINE_FROZEN_RESOLVED_PREFIX_PHYSICS_DIAGNOSIS_NOT_FULL_WORKER_REPLAY",
        "sources": sources,
        "cases": summary,
        "network_attempts": guard.attempts,
        "all_reproduced": all(row["exact_failure_prefix_reproduced"] for row in summary),
        "diagnostic_entry_sha256": entry_sha,
    }
    with (args.output / "receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"all_reproduced": receipt["all_reproduced"], "cases": len(summary)}))
    if not receipt["all_reproduced"]:
        raise SystemExit(1)
