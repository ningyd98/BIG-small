"""Preregister and execute all 20 independent development visual-physics episodes.

MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_smoke.py --scope closed-loop \
    --episodes 20 --output artifacts/research/visual-smoke
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, write_json
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner
from cloud_edge_robot_arm.vision.observations import RGBDObservation

DEFAULT_CONFIG = Path("configs/research/visual_smoke.yaml")


def smoke_dataset_config() -> DatasetConfig:
    return DatasetConfig(
        dataset_id="t7-visual-smoke-development-v1",
        groups=20,
        seed=71001,
        target_x=(0.34, 0.43),
        target_y=(-0.07, 0.08),
        half_size=(0.032, 0.037),
        camera_height=(1.4, 1.4),
        camera_x=(0.35, 0.35),
        camera_y=(0.0, 0.0),
        camera_fovy=(45.0, 45.0),
        light_intensity=(0.8, 1.0),
        distractor_count=(0, 0),
        depth_noise_m=(0.0,),
        invalid_depth_fractions=(0.0,),
    )


def build_assignments(settings: dict[str, Any]) -> dict[str, Any]:
    kinds = (
        ["NORMAL"] * int(settings["normal_episodes"])
        + ["MISSING_TARGET"] * int(settings["missing_target_episodes"])
        + ["INVALID_DEPTH"] * int(settings["invalid_depth_episodes"])
        + ["SAFETY_STOP"] * int(settings["safety_stop_episodes"])
    )
    if len(kinds) != 20 or settings["episodes"] != 20:
        raise ValueError("the development smoke protocol preregisters exactly 20 cases")
    config = smoke_dataset_config()
    cases = []
    for index, kind in enumerate(kinds):
        seed = int(settings["seed_start"]) + index
        scene = sample_scene(config, seed)
        color = scene.scene_parameters["target"]["color_name"]
        instruction = f"Move the {color} block to the green region."
        if kind == "MISSING_TARGET":
            instruction = "Move the purple block to the green region."
        cases.append(
            {
                "case_id": f"case-{index + 1:02d}",
                "kind": kind,
                "seed": seed,
                "scene": scene.model_dump(mode="json"),
                "scene_hash": scene.scene_hash,
                "instruction": instruction,
            }
        )
    if len({case["scene_hash"] for case in cases}) != 20:
        raise ValueError("smoke assignments must contain independent scenes")
    return {
        "scope": "VISION_CLOSED_LOOP",
        "formal_g1": False,
        "assigned": 20,
        "cases": cases,
        "dataset_config": config.model_dump(mode="json"),
    }


class _FaultCapture(MuJoCoCaptureSession):
    """Predeclared sensor corruption; original sensor frame remains on disk."""

    fault = False
    raw_output: Path | None = None
    raw_count = 0

    def capture(self) -> RGBDObservation:
        observation = super().capture()
        if not self.fault:
            return observation
        from cloud_edge_robot_arm.vision.capture import save_observation

        self.raw_count += 1
        if self.raw_output:
            save_observation(observation, self.raw_output / f"{self.raw_count:03d}")
        depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(
            observation.height,
            observation.width,
        )
        # Preserve the sensor RGB and border depth, corrupt a fixed image rectangle.
        # The fault injector uses no target truth and is not part of online routing.
        depth[5:-5, 5:-5] = 0
        data = observation.model_dump()
        data.update(
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
            checksum_sha256="",
        )
        return RGBDObservation.model_validate(data)


def apply_independent_semantics(case: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Post-run assignment scoring; never passed to online policy or recovery."""
    semantic_success = case["kind"] != "MISSING_TARGET"
    task_success = bool(row.get("success", False) and semantic_success)
    return {
        **row,
        "visual_episode_success": bool(row.get("success", False)),
        "semantic_success": semantic_success,
        "task_success": task_success,
        "success": task_success,
        "false_completion": bool(row.get("online_reported_complete") and not task_success),
        "semantic_reason": (
            "ASSIGNED_TARGET_PRESENT" if semantic_success else "INDEPENDENT_ASSIGNED_TARGET_ABSENT"
        ),
        "semantic_used_for_online_routing": False,
    }


def summarize(assignments: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    assigned = assignments["assigned"]
    normal_success = sum(row["kind"] == "NORMAL" and row.get("success", False) for row in records)
    failed = sum(not row.get("success", False) for row in records)
    blocked = sum(row.get("blocked", False) for row in records)
    kinds = Counter(row["kind"] for row in records)
    return {
        "evaluation_scope": "VISION_CLOSED_LOOP",
        "formal_g1": False,
        "assigned": assigned,
        "recorded": len(records),
        "succeeded": sum(row.get("success", False) for row in records),
        "normal_succeeded": normal_success,
        "false_completions": sum(row.get("false_completion", False) for row in records),
        "failed": failed,
        "blocked": blocked,
        "success_rate_all_assigned": sum(row.get("success", False) for row in records) / assigned,
        "case_kind_counts": dict(kinds),
        "stage_coverage": {
            name: sum(row.get(name, 0) > 0 for row in records) / assigned
            for name in ("observation_count", "model_calls", "executed_actions")
        },
        "smoke_passed": (
            len(records) == assigned == 20 and normal_success > 0 and failed > 0 and not blocked
        ),
        "gate": "all 20 retained; >=1 normal physical+online success; >=1 failure; no env block",
        "failure_reasons": dict(
            Counter(
                row.get("terminal_reason") or row.get("failure_reason") or "SUCCESS"
                for row in records
            )
        ),
    }


def run_smoke(config_path: Path, output: Path, frozen_dir: Path | None = None) -> dict[str, Any]:
    os.environ.setdefault("MUJOCO_GL", "egl")
    settings = yaml.safe_load(config_path.read_text())
    assignments = build_assignments(settings)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "assignments.json", assignments)
    (output / "config.yaml").write_bytes(config_path.read_bytes())
    freeze = frozen_dir or Path(settings["frozen_dir"])
    write_json(
        output / "provenance.json",
        {
            "frozen_dir": str(freeze),
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "assignments_sha256": hashlib.sha256(
                (output / "assignments.json").read_bytes()
            ).hexdigest(),
            "frozen_bundle_sha256": {
                name: hashlib.sha256((freeze / name).read_bytes()).hexdigest()
                for name in ("model-frozen.json", "model-frozen-evidence.json", "probe-report.json")
                if (freeze / name).is_file()
            },
            "source_sha256": {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__),
                    Path("src/cloud_edge_robot_arm/vision/execution.py"),
                    Path("src/cloud_edge_robot_arm/vision/evaluation.py"),
                    Path("src/cloud_edge_robot_arm/vision/capture.py"),
                    Path("src/cloud_edge_robot_arm/vision/observations.py"),
                    Path("src/cloud_edge_robot_arm/vision/planner.py"),
                    Path("src/cloud_edge_robot_arm/vision/messages.py"),
                    Path("src/cloud_edge_robot_arm/vision/top_grasp.py"),
                    Path("src/cloud_edge_robot_arm/vision/model_resolver.py"),
                    Path("src/cloud_edge_robot_arm/vision/frozen_model.py"),
                    Path("src/cloud_edge_robot_arm/vision/request_control.py"),
                    Path("src/cloud_edge_robot_arm/edge/evidence/conditions.py"),
                    Path("src/cloud_edge_robot_arm/edge/recovery/verification_router.py"),
                    Path("src/cloud_edge_robot_arm/auto_mode/runtime_events.py"),
                    Path("src/cloud_edge_robot_arm/edge/runtime/skill_executor.py"),
                    Path("src/cloud_edge_robot_arm/edge/runtime/skill_registry.py"),
                    Path("src/cloud_edge_robot_arm/edge/runtime/condition_evaluator.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/shield.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/models.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/policy.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/context_builder.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/rules.py"),
                    Path("src/cloud_edge_robot_arm/edge/safety/rule_registry.py"),
                    Path("src/cloud_edge_robot_arm/simulation/mujoco/backend.py"),
                    Path("src/cloud_edge_robot_arm/simulation/mujoco/camera.py"),
                    Path("src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py"),
                    Path("src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"),
                    Path("src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py"),
                    Path("src/cloud_edge_robot_arm/simulation/config.py"),
                    Path("src/cloud_edge_robot_arm/datasets/rgbd/models.py"),
                    Path("src/cloud_edge_robot_arm/datasets/rgbd/scene_sampler.py"),
                    Path("src/cloud_edge_robot_arm/datasets/rgbd/capture.py"),
                    Path("assets/robots/franka_panda/scene.xml"),
                    config_path,
                )
            },
        },
    )
    planner = None
    blocked_reason = None
    try:
        planner = load_frozen_planner(freeze)
    except Exception as exc:
        blocked_reason = f"BLOCKED_BY_ENV: {type(exc).__name__}: {exc}"
    records = []
    for case in assignments["cases"]:
        directory = output / "cases" / case["case_id"]
        directory.mkdir(parents=True)
        write_json(directory / "assignment.json", case)
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "kind": case["kind"],
            "scene_hash": case["scene_hash"],
            "success": False,
        }
        try:
            if planner is None:
                raise RuntimeError(blocked_reason)
            scene = SceneSpec.model_validate(case["scene"])
            config = SimulatorConfig(
                render_rgb=True, render_depth=True, domain_randomization=False, seed=case["seed"]
            )
            capture = _FaultCapture(config)
            with capture:
                capture.apply_scene(scene)
                capture._backend.step(steps=120)
                capture.fault = case["kind"] == "INVALID_DEPTH"
                capture.raw_output = directory / "raw-fault-frames"
                if case["kind"] == "SAFETY_STOP":
                    capture._backend.emergency_stop()
                robot = MuJoCoSkillRobot(capture._backend)
                assert planner.model_snapshot is not None
                policy = ExecutionPolicy(
                    instruction=case["instruction"],
                    timeout_s=float(settings["timeout_s"]),
                    model_snapshot_hash=planner.model_snapshot.digest(),
                    output_dir=directory,
                    verification_budget=VerificationBudget(**settings["verification_budget"]),
                )
                result = run_visual_episode(planner, robot, capture, policy)
                row.update(
                    {
                        key: value
                        for key, value in asdict(result).items()
                        if key != "verification_records"
                    }
                )
                row["blocked"] = bool(
                    result.terminal_reason and result.terminal_reason.startswith("BLOCKED_BY_ENV")
                )
        except Exception as exc:
            row.update(
                blocked=True,
                terminal_reason=f"BLOCKED_BY_ENV: {type(exc).__name__}: {exc}",
                observation_count=0,
                model_calls=0,
                executed_actions=0,
            )
        row = apply_independent_semantics(case, row)
        write_json(directory / "case-result.json", row)
        records.append(row)
        write_json(output / "progress.json", summarize(assignments, records))
        print(
            f"{case['case_id']} {case['kind']}: {row.get('status', 'BLOCKED')} "
            f"{row.get('terminal_reason') or row.get('failure_reason') or ''}",
            flush=True,
        )
    summary = summarize(assignments, records)
    write_json(output / "summary.json", summary)
    write_json(output / "results.json", records)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["closed-loop"], default="closed-loop")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--frozen-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.episodes != 20:
        parser.error("this preregistered development smoke requires --episodes 20")
    try:
        summary = run_smoke(args.config, args.output, args.frozen_dir)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"smoke not started: {exc}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["smoke_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
