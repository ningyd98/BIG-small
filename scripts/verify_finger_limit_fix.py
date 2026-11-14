"""核验手指监测修复：冻结快照检查与记录动作回放，零模型调用。"""

# ruff: noqa: E402 -- select this checkout before package imports.
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from dataclasses import asdict
from functools import cache
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "src"))
sys.path.insert(0, str(SOURCE / "scripts"))

from diagnose_joint_limits import read, sha, validate_original, validate_output, write

from cloud_edge_robot_arm.contracts import TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.research.freeze_evidence import _save_joint_limit_diagnostics
from cloud_edge_robot_arm.research.sol_molmo_components import (
    ComponentStopped,
    check_component_hard_state,
)
from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario
from cloud_edge_robot_arm.research.sol_molmo_single_episode import SOURCE_PATHS
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_episode,
    sample_physical_observation,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

BASE_COMMIT = "52df1594ab888038adf7bd21586e691da671817c"
GUARD_PATH = "src/cloud_edge_robot_arm/research/sol_molmo_components.py"
EXPECTED_STOPS = {
    "development-043003": 1189,
    "held-out-044009": 1198,
    "held-out-044011": 1777,
}


def canonical_sha(value):
    """绑定JSON内容而不依赖空白格式。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def physical_prefix_matches(replayed, original, *, truncated_at=None):
    """仅允许新的episode_id；截断必须包含从初始步到指定停止步的全部字段。"""
    expected = original
    if truncated_at is not None:
        indices = [i for i, row in enumerate(original) if row["physics_step"] == truncated_at]
        if len(indices) != 1:
            return False
        expected = original[: indices[0] + 1]
    return len(replayed) == len(expected) and all(
        {k: v for k, v in current.items() if k != "episode_id"}
        == {k: v for k, v in old.items() if k != "episode_id"}
        for current, old in zip(replayed, expected, strict=True)
    )


def verified_diagnostics(episode, diagnosis):
    """把485份快照绑定到已核验的原始实验和原诊断重放身份。"""
    original_hashes = validate_original(episode)
    document_path = diagnosis / "component/joint-limit-diagnostics.json"
    document = read(document_path)
    proof = read(diagnosis / "replay-verification.json")
    original = read(episode / "component/physical-evidence.json")
    bad = [row["physics_step"] for row in original if row["joint_limit_violation"]]
    checks = (
        proof["replay_matches_original"],
        proof["original_evidence_unchanged"],
        proof["all_physical_fields_exact_except_new_episode_id"],
        proof["source_evidence_hashes"] == original_hashes,
        document["schema"] == "joint-limit-diagnostics.v1",
        document["source_case"] == proof["case"] == episode.name,
        document["original_episode_id"]
        == proof["original_episode_id"]
        == read(episode / "result.json")["episode_id"],
        document["episode_id"] == proof["replay_episode_id"],
        sha(document_path) == proof["diagnostic_file_sha256"],
        canonical_sha(document) == proof["diagnostic_content_sha256"],
        [row["physics_step"] for row in document["violations"]]
        == proof["original_flagged_steps"]
        == proof["replayed_flagged_steps"]
        == bad,
    )
    if not bad or not all(checks):
        raise ValueError("diagnostic evidence identity, coverage or hashes do not match")
    return document


def verify_runtime():
    """原包源码只允许增加手指循环；保留原诊断脚本的严格运行时钉住规则。"""
    archive = subprocess.check_output(
        [
            "git",
            "-C",
            str(SOURCE),
            "archive",
            "--format=tar",
            BASE_COMMIT,
            "src/cloud_edge_robot_arm",
        ]
    )
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for member in tree.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            old = tree.extractfile(member).read()
            current = (SOURCE / member.name).read_bytes()
            if current != old:
                if member.name != GUARD_PATH:
                    raise ValueError("unexpected runtime change: " + member.name)
                parsed = ast.parse(current)
                function = next(
                    node
                    for node in parsed.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "check_component_hard_state"
                )
                extra = [
                    node
                    for node in function.body
                    if isinstance(node, ast.For)
                    and isinstance(node.iter, ast.Tuple)
                    and ast.literal_eval(node.iter) == ("finger_left_joint", "finger_right_joint")
                ]
                if len(extra) != 1:
                    raise ValueError("one new finger guard loop required")
                function.body.remove(extra[0])
                if ast.dump(parsed) != ast.dump(ast.parse(old)):
                    raise ValueError("runtime changed beyond the finger guard loop")
            hashes[member.name] = hashlib.sha256(current).hexdigest()
    return {
        "base_commit": BASE_COMMIT,
        "package_source_sha256": hashes,
        "verifier_sha256": sha(Path(__file__)),
    }


def check_frozen_violations(input_root, diagnostic_root):
    """离线注入冻结机器人反馈；不步进，不把快照真值接入在线控制。"""
    rows = []
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig())
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42001))
        robot = MuJoCoSkillRobot(backend)
        names = [*backend.get_joint_state().names, "finger_left_joint", "finger_right_joint"]
        for case in EXPECTED_STOPS:
            diagnosis = diagnostic_root / case
            before = {
                str(p.relative_to(diagnosis)): sha(p) for p in diagnosis.rglob("*") if p.is_file()
            }
            document = verified_diagnostics(input_root / case, diagnosis)
            caught = []
            for sample in document["violations"]:
                positions = [*sample["joint_positions_rad"], *sample["finger_positions_m"]]
                velocities = [*sample["joint_velocities_rad_s"], *sample["finger_velocities_m_s"]]
                limits = [*sample["joint_ranges_rad"], *sample["finger_ranges_m"]]
                for name, position, velocity, limits_ in zip(
                    names, positions, velocities, limits, strict=True
                ):
                    joint = backend._model.joint(name)
                    if backend._model.jnt_range[joint.id].tolist() != limits_:
                        raise ValueError("frozen joint bounds changed")
                    backend._data.qpos[joint.qposadr[0]] = position
                    backend._data.qvel[joint.dofadr[0]] = velocity
                reason = "PASS"
                try:
                    check_component_hard_state(backend, robot)
                except ComponentStopped as error:
                    reason = str(error)
                caught.append({"physics_step": sample["physics_step"], "guard_result": reason})
            unchanged = before == {
                str(p.relative_to(diagnosis)): sha(p) for p in diagnosis.rglob("*") if p.is_file()
            }
            rows.append(
                {
                    "case": case,
                    "frozen_steps": len(caught),
                    "records": caught,
                    "all_caught_as_finger_limit": all(
                        r["guard_result"] == "HARD_FINGER_LIMIT" for r in caught
                    ),
                    "diagnosis_files_sha256": before,
                    "unchanged": unchanged,
                }
            )
        assert backend.total_physics_steps == 0
    finally:
        backend.shutdown()
    return rows


@cache
def original_source_sha(name):
    """原实验声明必须绑定到固定基线字节，而非本次已修改的guard。"""
    raw = subprocess.check_output(
        [
            "git",
            "-C",
            str(SOURCE),
            "show",
            BASE_COMMIT + ":" + name,
        ]
    )
    return hashlib.sha256(raw).hexdigest()


def verify_original_runtime(episode):
    """动作与无动作记录均先验证完整入口源码清单及资产，不允许缺项。"""
    asset = read(episode / "result.json")["scene_file"]
    relative = Path(asset)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".xml":
        raise ValueError("original runtime has an invalid asset path")
    document = read(episode / "source-hashes.json")
    sources = document["files"]
    if document.get("scope") != "SELECTED_ENTRY_SOURCES" or set(sources) != {*SOURCE_PATHS, asset}:
        raise ValueError("original runtime source inventory does not match")
    for name, digest in sources.items():
        expected = original_source_sha(name)
        if digest != expected:
            raise ValueError("original runtime source pin mismatch: " + name)
        # The new guard loop is the sole live difference; freeze_evidence remains
        # byte-pinned to52df by verify_runtime, not arbitrarily exempted here.
        if name != GUARD_PATH and sha(SOURCE / name) != expected:
            raise ValueError("original runtime source differs from current source: " + name)
    return sources


def replay_case(episode, destination):
    """用原技能和已记录参数重放；首次新监测失败立即退出并保持停止状态。"""
    hashes = validate_original(episode)
    sources = verify_original_runtime(episode)
    saved = read(episode / "component/episode.json")
    result = read(episode / "result.json")
    old = read(episode / "component/physical-evidence.json")
    destination.mkdir(parents=True, exist_ok=False)
    report = {
        "case": episode.name,
        "original_physical_success": result["physical_success"],
        "source_evidence_sha256": hashes,
        "original_terminal_reason": saved["terminal_reason"],
        "scope": "RECORDED_ACTION_REPLAY_NO_NEW_PLANNING",
        "original_runtime_verified": True,
        "original_runtime_base": BASE_COMMIT,
        "original_runtime_source_sha256": sources,
    }
    if not saved["actions"]:
        report.update(
            scope="EVIDENCE_ONLY_NO_RECORDED_ACTIONS",
            verified=True,
            fresh_planning_test=False,
            original_evidence_unchanged=True,
        )
        write(destination / "verification.json", report)
        return report
    assets = [name for name in sources if name.endswith(".xml")]
    if len(assets) != 1 or sha(SOURCE / assets[0]) != sources[assets[0]]:
        raise ValueError("frozen physics asset changed")
    config = SimulatorConfig(
        model_path=str(SOURCE / assets[0]),
        seed=result["seed"],
        domain_randomization=False,
        physics_dt_s=1 / 240,
        render_rgb=False,
        render_depth=False,
    )
    backend = MuJoCoPhysicsBackend()
    samples, actions, mismatches = [], [], []
    stopped, stopped_at, stop_phase, stop_snapshot = None, None, None, None
    phase = "INITIAL"
    criteria = CompletionCriteria("object", "target_region")
    try:
        backend.initialize(config)
        backend.reset(
            physical_component_scenario(
                result["seed"], saved["scene_application"]["requested_scene"]
            )
        )
        # Match the original render-enabled reset, then never write physics state again.
        joint1 = backend._model.joint("joint1")
        backend._data.qpos[joint1.qposadr[0]] = -0.8
        backend._target_positions[0] = -0.8
        backend._mujoco.mj_forward(backend._model, backend._data)
        robot = MuJoCoSkillRobot(backend)
        executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
        backend.step(120)
        samples.append(sample_physical_observation(backend.current_physics_observation(), criteria))

        def collect(snapshot):
            nonlocal stop_snapshot
            samples.append(sample_physical_observation(snapshot, criteria))
            try:
                check_component_hard_state(backend, robot)
            except ComponentStopped:
                stop_snapshot = snapshot
                raise

        try:
            with backend.observe_physics_steps(collect):
                for original in saved["actions"]:
                    phase = original["skill"]
                    if backend.total_physics_steps != original["start_step"]:
                        mismatches.append({"skill": phase, "field": "start_step"})
                        break
                    check_component_hard_state(backend, robot)
                    action = {"skill": phase, "start_step": backend.total_physics_steps}
                    actions.append(action)
                    outcome = executor.execute_attempt(
                        contract=TaskContract.model_validate(
                            original["component_execution_contract"]
                        ),
                        step=TaskStep.model_validate(original["resolved_step"]),
                        attempt=1,
                    )
                    action.update(
                        controller_return_step=backend.total_physics_steps,
                        success=outcome.success,
                        error_code=outcome.error_code,
                    )
                    if (
                        backend.total_physics_steps != original["controller_return_step"]
                        or outcome.success != original["controller_result"]["success"]
                        or outcome.error_code
                        != (original["controller_result"].get("error") or {}).get("code")
                    ):
                        mismatches.append({"skill": phase, "field": "controller_result"})
                        break
                    if original.get("diagnostic_settle_steps", 0):
                        backend.step(original["diagnostic_settle_steps"])
                    if backend.total_physics_steps != original["end_step"]:
                        mismatches.append({"skill": phase, "field": "end_step"})
                        break
                    if not outcome.success:
                        break
                if not mismatches and saved["diagnostic_complete"]:
                    phase = "TERMINAL_STABILITY"
                    backend.step(288)
        except ComponentStopped as error:
            stopped, stopped_at, stop_phase = str(error), backend.total_physics_steps, phase
            robot.safe_stop()
            if stop_snapshot is not None:
                component = destination / "component"
                component.mkdir()
                _save_joint_limit_diagnostics(stop_snapshot, component)
        if not saved["diagnostic_complete"] and stopped is None:
            robot.safe_stop()
        outcome = evaluate_episode(backend, criteria, evidence=samples, evaluation_start_step=120)
        normalized = json.loads(json.dumps([asdict(sample) for sample in samples]))
        prefix_ok = physical_prefix_matches(normalized, old, truncated_at=stopped_at)
        expected = EXPECTED_STOPS.get(episode.name)
        stop_ok = (
            (
                stopped_at == expected
                and stopped == "HARD_FINGER_LIMIT"
                and stop_phase == "APPROACH"
                and robot.get_state().estop_engaged
                and backend.total_physics_steps == expected
            )
            if expected
            else stopped is None
        )
        outcome_ok = (
            (not outcome.success and outcome.safety_violation)
            if expected
            else (json.loads(json.dumps(asdict(outcome))) == saved["independent_physical_outcome"])
        )
        integrity = validate_original(episode) == hashes
        report.update(
            verified=prefix_ok and stop_ok and outcome_ok and integrity and not mismatches,
            physical_prefix_exact=prefix_ok,
            stop_matches_expected=stop_ok,
            independent_outcome_matches_expected=outcome_ok,
            replay_physical_success=outcome.success,
            independent_physical_outcome=asdict(outcome),
            original_evidence_unchanged=integrity,
            original_episode_id=result["episode_id"],
            replay_episode_id=backend._episode_id,
            sample_count=len(samples),
            original_sample_count=len(old),
            stopped_at=stopped_at,
            stop_reason=stopped,
            stop_phase=stop_phase,
            estop_engaged=robot.get_state().estop_engaged,
            final_physics_step=backend.total_physics_steps,
            action_mismatches=mismatches,
            attempted_actions=actions,
            physical_evidence_sha256=canonical_sha(normalized),
            initialization=(
                "CPU-only joint1 qpos/target -0.8 matches original render reset; "
                "no later state writes"
            ),
        )
    finally:
        backend.shutdown()
    write(destination / "verification.json", report)
    return report


def main():
    """检查固定40项冻结矩阵并写入全新派生目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path)
    parser.add_argument("diagnostic_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    validate_output(args.input_root, args.output_root)
    validate_output(args.diagnostic_root, args.output_root)
    provenance = verify_runtime()
    cases = sorted(
        path
        for path in args.input_root.iterdir()
        if path.is_dir() and (path / "result.json").is_file()
    )
    expected = {
        *(f"fixed-{seed:06d}" for seed in range(42001, 42011)),
        *(f"development-{seed:06d}" for seed in range(43001, 43016)),
        *(f"held-out-{seed:06d}" for seed in range(44001, 44016)),
    }
    if {path.name for path in cases} != expected:
        raise ValueError("exact original 40-case matrix required")
    args.output_root.mkdir(parents=True)
    write(args.output_root / "source-provenance.json", provenance)
    frozen = check_frozen_violations(args.input_root, args.diagnostic_root)
    write(args.output_root / "frozen-violation-check.json", frozen)
    records = []
    for case in cases:
        row = replay_case(case, args.output_root / case.name)
        records.append(row)
        print(
            json.dumps(
                {
                    key: row.get(key)
                    for key in (
                        "case",
                        "scope",
                        "verified",
                        "stopped_at",
                        "replay_physical_success",
                    )
                }
            ),
            flush=True,
        )
    summary = {
        "scope": "FROZEN_40_CASE_RECORDED_ACTION_REGRESSION",
        "new_end_to_end_test": False,
        "new_success_rate_estimate": False,
        "cases": len(records),
        "recorded_action_replays": sum(
            row["scope"] == "RECORDED_ACTION_REPLAY_NO_NEW_PLANNING" for row in records
        ),
        "evidence_only_cases": sum(
            row["scope"] == "EVIDENCE_ONLY_NO_RECORDED_ACTIONS" for row in records
        ),
        "original_successes": sum(row["original_physical_success"] for row in records),
        "retained_successes_in_recorded_action_replay": sum(
            row["original_physical_success"]
            and row.get("replay_physical_success", False)
            and row["verified"]
            for row in records
        ),
        "finger_stops": {
            row["case"]: row["stopped_at"] for row in records if row.get("stopped_at")
        },
        "frozen_bad_steps": sum(row["frozen_steps"] for row in frozen),
        "all_frozen_violations_caught": all(
            row["all_caught_as_finger_limit"] and row["unchanged"] for row in frozen
        ),
        "all_cases_verified": all(row["verified"] for row in records),
        "model_calls": 0,
        "cloud_requests": 0,
        "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED",
    }
    write(args.output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["all_cases_verified"] and summary["all_frozen_violations_caught"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
