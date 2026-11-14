"""离线重放冻结动作并采集关节诊断；不调用模型、不覆盖原始实验。"""

# ruff: noqa: E402 -- CLI bootstrap selects this checkout before package imports.
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
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "src"))

from cloud_edge_robot_arm.contracts import TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.research.freeze_evidence import _save_joint_limit_diagnostics
from cloud_edge_robot_arm.research.sol_molmo_components import check_component_hard_state
from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    sample_physical_observation,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

CASES = ("development-043003", "held-out-044009", "held-out-044011")
PINNED_RUNTIME_COMMIT = "afc43e805ad898d3fce03e2472ca2c174f9fcd9b"


def read(path):
    """读取一个显式诊断输入。"""
    return json.loads(path.read_text())


def sha(path):
    """绑定原始字节与源码身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    """只在新建诊断目录写派生记录。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def verify_runtime():
    """逐文件核对实测提交的全部包源码，并绑定诊断实现的当前字节。"""
    archive = subprocess.check_output(
        [
            "git",
            "-C",
            str(SOURCE),
            "archive",
            "--format=tar",
            PINNED_RUNTIME_COMMIT,
            "src/cloud_edge_robot_arm",
        ]
    )
    hashes = {}
    writer = "src/cloud_edge_robot_arm/research/freeze_evidence.py"
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for member in tree.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            original = tree.extractfile(member).read()
            path = SOURCE / member.name
            digest = sha(path)
            if digest != hashlib.sha256(original).hexdigest():
                if member.name != writer or not path.read_bytes().startswith(original):
                    raise ValueError(f"pinned runtime changed: {member.name}")
                extra = ast.parse(path.read_bytes()[len(original) :].decode()).body
                if not (
                    len(extra) == 1
                    and isinstance(extra[0], ast.FunctionDef)
                    and extra[0].name == "_save_joint_limit_diagnostics"
                ):
                    raise ValueError("pinned freeze runtime changed beyond diagnostic function")
            hashes[member.name] = digest
    implementations = {
        name: sha(SOURCE / name)
        for name in (
            writer,
            "scripts/diagnose_joint_limits.py",
            "scripts/analyze_joint_limit_diagnostics.py",
        )
    }
    return {
        "pinned_runtime_commit": PINNED_RUNTIME_COMMIT,
        "pinned_runtime_hashes": hashes,
        "diagnostic_implementation_hashes": implementations,
    }


def finish_diagnostics(path, case, original_episode_id, guards, errors):
    """诊断文件损坏时保留失败证据，让物理重放及验证报告继续完成。"""
    try:
        diagnostics = read(path)
        if (
            not isinstance(diagnostics, dict)
            or diagnostics.get("schema") != "joint-limit-diagnostics.v1"
        ):
            raise ValueError("invalid diagnostic schema")
        rows = diagnostics.get("violations")
        if not isinstance(rows, list) or not rows:
            raise ValueError("missing diagnostic violations")
        for row in rows:
            if not isinstance(row, dict) or type(row.get("physics_step")) is not int:
                raise ValueError("invalid diagnostic physics step")
            if row["physics_step"] not in guards:
                raise ValueError("diagnostic step has no matching guard evidence")
        for row in rows:
            row.update(guards[row["physics_step"]])
        diagnostics["source_case"] = case
        diagnostics["original_episode_id"] = original_episode_id
        write(path, diagnostics)
        return diagnostics
    except (ValueError, OSError) as error:
        errors.append({"phase": "diagnostic_finalization", "error": str(error)})
        return None


def validate_output(source, output):
    """禁止输出与原始证据互相包含。"""
    source, output = source.resolve(), output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("diagnostic output overlaps original source evidence")
    if output.exists():
        raise FileExistsError(output)


def validate_original(episode):
    """检查样本全部清单项，拒绝越界路径、软链接和字节漂移。"""
    manifest = episode / "evidence-manifest.json"
    hashes = {"evidence-manifest.json": sha(manifest)}
    for entry in read(manifest)["files"]:
        relative = Path(entry["path"])
        path = episode / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink():
            raise ValueError("invalid original evidence path")
        if not path.resolve().is_relative_to(episode.resolve()):
            raise ValueError("original evidence escapes episode")
        digest = sha(path)
        if digest != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"original evidence mismatch: {relative}")
        hashes[str(relative)] = digest
    return hashes


def replay(episode, destination):
    """使用已记录动作和原控制器重放，逐步比对独立物理证据。"""
    originals = validate_original(episode)
    provenance = verify_runtime()
    saved = read(episode / "component/episode.json")
    result = read(episode / "result.json")
    old_samples = read(episode / "component/physical-evidence.json")
    sources = read(episode / "source-hashes.json")["files"]
    assets = [name for name in sources if name.endswith(".xml")]
    if len(assets) != 1:
        raise ValueError("one frozen marked physics asset is required")
    runtime = {}
    for name, expected in sources.items():
        if name.startswith("src/") or name.endswith(".xml"):
            digest = sha(SOURCE / name)
            if (
                digest != expected
                and name != "src/cloud_edge_robot_arm/research/freeze_evidence.py"
            ):
                raise ValueError(f"frozen runtime changed: {name}")
            runtime[name] = digest
    destination.mkdir(parents=True, exist_ok=False)
    component = destination / "component"
    component.mkdir()
    scene = saved["scene_application"]["requested_scene"]
    scenario = physical_component_scenario(result["seed"], scene)
    config = SimulatorConfig(
        model_path=str(SOURCE / assets[0]),
        seed=result["seed"],
        domain_randomization=False,
        physics_dt_s=1 / 240,
        render_rgb=False,
        render_depth=False,
    )
    backend = MuJoCoPhysicsBackend()
    samples, actions, mismatches, diagnostics_errors = [], [], [], []
    guard_at_violations = {}
    phase = "INITIAL"
    try:
        backend.initialize(config)
        backend.reset(scenario)
        # Match the frozen render-enabled reset without invoking any renderer.
        joint1 = backend._model.joint("joint1")
        backend._data.qpos[joint1.qposadr[0]] = -0.8
        backend._target_positions[0] = -0.8
        backend._mujoco.mj_forward(backend._model, backend._data)
        robot = MuJoCoSkillRobot(backend)
        executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
        backend.step(120)
        criteria = CompletionCriteria("object", "target_region")
        samples.append(
            asdict(sample_physical_observation(backend.current_physics_observation(), criteria))
        )
        arm_names = list(backend.get_joint_state().names)
        names = arm_names + ["finger_left_joint", "finger_right_joint"]
        mapping = []
        for index, name in enumerate(names):
            joint_id = backend._model.joint(name).id
            mapping.append(
                {
                    "index": index,
                    "name": name,
                    "joint_id": int(joint_id),
                    "qpos_address": int(backend._model.jnt_qposadr[joint_id]),
                    "qvel_address": int(backend._model.jnt_dofadr[joint_id]),
                    "range": backend._model.jnt_range[joint_id].tolist(),
                    "online_covered": name in arm_names,
                }
            )

        def collect(snapshot):
            sample = sample_physical_observation(snapshot, criteria)
            samples.append(asdict(sample))
            error = None
            try:
                check_component_hard_state(backend, robot)
            except RuntimeError as stopped:
                error = str(stopped)
            if sample.joint_limit_violation:
                state = backend.get_joint_state()
                guard_at_violations[snapshot.physics_step] = {
                    "controller_phase": phase,
                    "online_guard_result": error or "PASS",
                    "online_joint_names": list(state.names),
                    "online_joint_positions_rad": list(state.positions),
                    "control_targets": backend._data.ctrl.tolist(),
                }
                try:
                    _save_joint_limit_diagnostics(snapshot, component)
                except (ValueError, OSError) as failure:
                    diagnostics_errors.append(
                        {"physics_step": snapshot.physics_step, "error": str(failure)}
                    )
            if error:
                raise RuntimeError(error)

        with backend.observe_physics_steps(collect):
            for old_action in saved["actions"]:
                phase = old_action["skill"]
                if backend.total_physics_steps != old_action["start_step"]:
                    mismatches.append({"action": phase, "field": "start_step"})
                    break
                contract = TaskContract.model_validate(old_action["component_execution_contract"])
                step = TaskStep.model_validate(old_action["resolved_step"])
                outcome = executor.execute_attempt(contract=contract, step=step, attempt=1)
                returned = backend.total_physics_steps
                original_controller = old_action["controller_result"]
                matched = (
                    returned == old_action["controller_return_step"]
                    and outcome.success == original_controller["success"]
                    and outcome.error_code == (original_controller.get("error") or {}).get("code")
                )
                actions.append(
                    {
                        "skill": phase,
                        "start_step": old_action["start_step"],
                        "controller_return_step": returned,
                        "success": outcome.success,
                        "error_code": outcome.error_code,
                        "matches_original_controller": matched,
                    }
                )
                if not matched:
                    mismatches.append({"action": phase, "field": "controller_result_or_step"})
                    break
                settle = old_action.get("diagnostic_settle_steps", 0)
                if settle:
                    backend.step(settle)
                if backend.total_physics_steps != old_action["end_step"]:
                    mismatches.append({"action": phase, "field": "end_step"})
                    break
                if not outcome.success:
                    break
            if not mismatches and saved["diagnostic_complete"]:
                phase = "TERMINAL_STABILITY"
                backend.step(288)
        if not saved["diagnostic_complete"]:
            robot.safe_stop()
        # The original evaluates a detached final snapshot after safe_stop too.
        if backend.total_physics_steps != old_samples[-1]["physics_step"]:
            mismatches.append(
                {
                    "field": "final_physics_step",
                    "replayed": backend.total_physics_steps,
                    "original": old_samples[-1]["physics_step"],
                }
            )
        path = component / "joint-limit-diagnostics.json"
        replay_episode_id = backend._episode_id
        diagnostics = finish_diagnostics(
            path,
            episode.name,
            result["episode_id"],
            guard_at_violations,
            diagnostics_errors,
        )
    finally:
        backend.shutdown()
    normalized = json.loads(json.dumps(samples))
    different = []
    if len(normalized) != len(old_samples):
        mismatches.append(
            {"field": "sample_count", "replayed": len(normalized), "original": len(old_samples)}
        )
    for current, old in zip(normalized, old_samples, strict=False):
        changed = [key for key in old if key != "episode_id" and current.get(key) != old[key]]
        if changed:
            different.append({"physics_step": old["physics_step"], "fields": changed})
    old_bad = [row["physics_step"] for row in old_samples if row["joint_limit_violation"]]
    new_bad = [row["physics_step"] for row in normalized if row["joint_limit_violation"]]
    integrity = validate_original(episode) == originals
    report = {
        **provenance,
        "case": episode.name,
        "original_episode_id": result["episode_id"],
        "replay_episode_id": replay_episode_id,
        "diagnostic_file_sha256": sha(path) if path.exists() else None,
        "diagnostic_content_sha256": hashlib.sha256(
            json.dumps(diagnostics, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        if diagnostics is not None
        else None,
        "scope": "OFFLINE_RECORDED_ACTION_REPLAY",
        "replay_matches_original": not (mismatches or different or diagnostics_errors)
        and old_bad == new_bad,
        "sample_count": len(normalized),
        "original_sample_count": len(old_samples),
        "all_physical_fields_exact_except_new_episode_id": not different
        and len(normalized) == len(old_samples),
        "mismatched_samples": different[:20],
        "mismatched_sample_count": len(different),
        "action_mismatches": mismatches,
        "actions": actions,
        "original_flagged_steps": old_bad,
        "replayed_flagged_steps": new_bad,
        "online_guard_coverage": ["arm"],
        "joint_mapping": mapping,
        "diagnostic_errors": diagnostics_errors,
        "original_evidence_unchanged": integrity,
        "source_evidence_hashes": originals,
        "runtime_hashes": runtime,
        "initialization": (
            "CPU-only renderer-disabled reset; joint1 qpos/target -0.8 "
            "matches frozen render-enabled reset; no later state writes"
        ),
        "model_calls": 0,
        "cloud_requests": 0,
        "hardware_dispatch": False,
    }
    write(destination / "replay-verification.json", report)
    return {
        key: report[key]
        for key in (
            "case",
            "replay_matches_original",
            "sample_count",
            "original_evidence_unchanged",
            "mismatched_sample_count",
        )
    }


def main():
    """接受原始批量根目录与全新的派生输出目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    validate_output(args.input_root, args.output_root)
    args.output_root.mkdir(parents=True)
    results = [replay(args.input_root / case, args.output_root / case) for case in CASES]
    write(args.output_root / "replay-summary.json", results)
    print(json.dumps(results, ensure_ascii=False))
    return (
        0
        if all(
            row["replay_matches_original"] and row["original_evidence_unchanged"] for row in results
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
