"""Generate resumable, physically evaluated RGB-D teacher trajectories."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from platform import python_version
from typing import Any, cast
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    SceneSpec,
    canonical_json,
    content_digest,
)
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


class TrajectorySmokeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = "rgbd-teacher-smoke"
    episodes: int = Field(default=20, ge=2, le=10000)
    seed: int = Field(default=0, ge=0)
    width: int = Field(default=320, ge=16, le=1280)
    height: int = Field(default=240, ge=16, le=720)
    model_path: str = "assets/robots/franka_panda/scene.xml"
    settle_steps: int = Field(default=120, ge=0, le=10000)


def _protocol_snapshot() -> dict[str, Any]:
    """Freeze code and criteria that can change execution or physical labels."""
    repository = Path(__file__).resolve().parents[1]
    source_paths = (
        "scripts/generate_rgbd_trajectories.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/teacher.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/scene_sampler.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
        "src/cloud_edge_robot_arm/vision/capture.py",
    )

    def package_version(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "NOT_INSTALLED"

    return {
        "teacher_protocol_version": "rgbd.teacher.v2",
        "scoring_protocol_version": "rgbd.physical.v2",
        "criteria": asdict(CompletionCriteria("object", "target_region")),
        "runtime_versions": {
            "python": python_version(),
            "mujoco": package_version("mujoco"),
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        "source_sha256": {
            name: hashlib.sha256((repository / name).read_bytes()).hexdigest()
            for name in source_paths
        },
    }


def _fixed_scene(config: TrajectorySmokeConfig, asset_hash: str) -> SceneSpec:
    # Match T4's measured S01 grasp geometry. This is a positive control,
    # never an assumed success label: only the independent evaluator decides.
    params: dict[str, Any] = {
        "target": {
            "position": [0.45, 0.0, 0.043], "half_size": [0.035] * 3,
            "rgba": [0.9, 0.12, 0.08, 1.0], "color_name": "red",
            "mass_kg": 0.08, "friction": 0.8,
        },
        "distractors": [],
        "destination": {
            "position": [0.2, 0.25, 0.002], "half_size": [0.08, 0.08, 0.002],
            "rgba": [0.1, 0.6, 0.2, 1.0],
        },
        "camera": {
            "position": [0.35, 0.0, 1.4],
            "quaternion": [1.0, 0.0, 0.0, 0.0],
            "fovy": 50.0,
        },
        "light_intensity": 0.8,
        "depth_noise_m": 0.0,
        "invalid_depth_fraction": 0.0,
    }
    return SceneSpec.from_parameters(params, asset_hash, config.seed)


def _assignments(config: TrajectorySmokeConfig, asset_hash: str) -> list[dict[str, Any]]:
    random_config = DatasetConfig(
        dataset_id=config.dataset_id,
        groups=1,
        seed=config.seed,
        width=config.width,
        height=config.height,
        model_path=config.model_path,
        target_x=(0.40, 0.50),
        target_y=(-0.06, 0.06),
        half_size=(0.03, 0.035),
        distractor_count=(0, 1),
        depth_noise_m=(0.0,),
        invalid_depth_fractions=(0.0,),
    )
    fixed = _fixed_scene(config, asset_hash)
    assignments = []
    for index in range(config.episodes):
        if index == 0:
            scene, case, source = fixed, "NORMAL", "FIXED_S01_CONTROL"
        elif index == 1:
            scene, case, source = fixed, "NO_CONTACT", "FIXED_NO_CONTACT_CONTROL"
        else:
            scene = sample_scene(random_config, config.seed + index)
            case, source = "NORMAL", "SAMPLED_CURRENT_ASSET"
        assignments.append({
            "index": index,
            "case": case,
            "scene_source": source,
            "seed": scene.seed,
            "group_id": scene.group_id,
            "scene_hash": scene.scene_hash,
            "scene": scene.model_dump(mode="json"),
            "status": "PENDING",
            "episode_path": None,
            "sha256": None,
            "execution_verified": False,
            "physical_success": False,
        })
    return assignments


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    data = (canonical_json(payload) + "\n").encode("utf-8")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _payload_for_episode(
    assignment: dict[str, Any], recorder: EpisodeRecorder | None,
    *, status: str, reason: str | None, elapsed_wall_s: float, protocol_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "rgbd.trajectory.v1",
        "assignment_index": assignment["index"],
        "case": assignment["case"],
        "scene_source": assignment["scene_source"],
        "scene": assignment["scene"],
        "group_id": assignment["group_id"],
        "source": "GROUND_TRUTH_TEACHER",
        "protocol_hash": protocol_hash,
        "evaluation_start_step": recorder.evaluation_start_step if recorder else None,
        "status": status,
        "reason": reason,
        "physical_success": bool(recorder and recorder.outcome and recorder.outcome.success),
        "execution_verified": bool(recorder and recorder.execution_verified),
        "outcome": asdict(recorder.outcome) if recorder and recorder.outcome else None,
        "frames": [frame.model_dump(mode="json") for frame in recorder.frames] if recorder else [],
        "unframed_actions": [action.model_dump(mode="json")
                             for action in recorder.unframed_actions] if recorder else [],
        "physical_samples": [asdict(sample) for sample in recorder.physical_samples]
                            if recorder else [],
        "elapsed_wall_s": elapsed_wall_s,
    }


def _episode_file(root: Path, index: int) -> Path:
    return root / "episodes" / f"{index:04d}" / "episode.json.gz"


def _write_episode(root: Path, assignment: dict[str, Any], payload: dict[str, Any]) -> str:
    destination = _episode_file(root, assignment["index"])
    if destination.parent.exists():
        raise ValueError(f"episode directory already exists: {destination.parent}")
    stage = root / ".staging" / f"{assignment['index']:04d}-{uuid4().hex}"
    stage.mkdir(parents=True)
    compressed = gzip.compress(canonical_json(payload).encode("utf-8"), mtime=0)
    try:
        staged_file = stage / "episode.json.gz"
        with staged_file.open("xb") as stream:
            stream.write(compressed)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, destination.parent)
    finally:
        if stage.exists():
            (stage / "episode.json.gz").unlink(missing_ok=True)
            stage.rmdir()
    return hashlib.sha256(compressed).hexdigest()


def _verify_published(root: Path, assignment: dict[str, Any], protocol_hash: str) -> str:
    path = _episode_file(root, assignment["index"])
    compressed = path.read_bytes()
    digest = hashlib.sha256(compressed).hexdigest()
    if assignment["sha256"] and assignment["sha256"] != digest:
        raise ValueError(f"published episode checksum mismatch: {path}")
    payload = json.loads(gzip.decompress(compressed))
    if (
        payload.get("assignment_index") != assignment["index"]
        or payload.get("group_id") != assignment["group_id"]
        or payload.get("case") != assignment["case"]
        or payload.get("scene") != assignment["scene"]
        or payload.get("protocol_hash") != protocol_hash
    ):
        raise ValueError(f"published episode identity mismatch: {path}")
    assignment.update(
        status=payload["status"],
        episode_path=path.relative_to(root).as_posix(),
        sha256=digest,
        execution_verified=payload["execution_verified"],
        physical_success=payload["physical_success"],
    )
    return digest


def generate_trajectories(config: TrajectorySmokeConfig, output: Path) -> dict[str, Any]:
    model = Path(config.model_path)
    asset_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    assignments = _assignments(config, asset_hash)
    protocol = _protocol_snapshot()
    protocol_hash = content_digest(protocol)
    config_hash = content_digest({
        "config": config.model_dump(mode="json"),
        "asset": asset_hash,
        "protocol_hash": protocol_hash,
    })
    manifest_path = output / "manifest.json"
    if output.exists() and any(output.iterdir()) and not manifest_path.exists():
        raise ValueError("output contains unrecognized evidence and cannot be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    (output / "episodes").mkdir(exist_ok=True)
    (output / ".staging").mkdir(exist_ok=True)

    if manifest_path.exists():
        manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        if (
            manifest.get("protocol_hash") != protocol_hash
            or content_digest(manifest.get("protocol")) != protocol_hash
        ):
            raise ValueError("existing trajectory protocol/version differs from current code")
        if (
            manifest.get("schema_version") != "rgbd.trajectory.manifest.v1"
            or manifest.get("config_hash") != config_hash
            or len(manifest.get("assignments", [])) != len(assignments)
        ):
            raise ValueError("existing trajectory manifest has different config or asset")
        for existing, planned in zip(manifest["assignments"], assignments, strict=True):
            if any(existing.get(key) != planned[key] for key in
                   ("index", "case", "scene_source", "seed", "group_id", "scene_hash", "scene")):
                raise ValueError("existing trajectory assignment differs from current plan")
        assignments = manifest["assignments"]
    else:
        manifest = {
            "schema_version": "rgbd.trajectory.manifest.v1",
            "dataset_id": config.dataset_id,
            "config": config.model_dump(mode="json"),
            "config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "protocol": protocol,
            "asset_sha256": asset_hash,
            "requested_episodes": config.episodes,
            "status": "RUNNING",
            "assignments": assignments,
            "reason": None,
        }
        _atomic_json(manifest_path, manifest)

    for assignment in assignments:
        path = _episode_file(output, assignment["index"])
        if path.exists():
            _verify_published(output, assignment, protocol_hash)
            continue
        if assignment["status"] != "PENDING":
            raise ValueError(f"manifest references a missing published episode: {path}")

    pending = [entry for entry in assignments if entry["status"] == "PENDING"]
    if pending:
        sim_config = SimulatorConfig(
            model_path=config.model_path,
            seed=config.seed,
            camera_width=config.width,
            camera_height=config.height,
            render_rgb=True,
            render_depth=True,
        )
        try:
            with MuJoCoCaptureSession(sim_config) as session:
                for assignment in pending:
                    started = time.monotonic()
                    recorder: EpisodeRecorder | None = None
                    try:
                        scene = SceneSpec.model_validate(assignment["scene"])
                        session.apply_scene(scene)
                        recorder = EpisodeRecorder()
                        outcome = run_teacher_episode(
                            scene, MuJoCoSkillRobot(session._backend), recorder,
                            case=assignment["case"], settle_steps=config.settle_steps,
                        )
                        status, reason = str(outcome.status), outcome.failure_reason
                    except (ImportError, OSError, RuntimeError, ValueError) as exc:
                        status, reason = "INFRASTRUCTURE_ERROR", str(exc)
                    payload = _payload_for_episode(
                        assignment, recorder, status=status, reason=reason,
                        elapsed_wall_s=time.monotonic() - started,
                        protocol_hash=protocol_hash,
                    )
                    _write_episode(output, assignment, payload)
                    _verify_published(output, assignment, protocol_hash)
                    _atomic_json(manifest_path, manifest)
        except (ImportError, RuntimeError, OSError) as exc:
            manifest["status"] = "BLOCKED"
            manifest["reason"] = str(exc)
            _atomic_json(manifest_path, manifest)
            return manifest

    manifest["status"] = (
        "COMPLETE" if all(a["status"] in
                          {"SUCCESS", "FAILED", "INCOMPLETE", "SAFETY_VIOLATION"}
                          for a in assignments)
        else "INCOMPLETE"
    )
    manifest["reason"] = None if manifest["status"] == "COMPLETE" else "UNEXECUTED_ASSIGNMENTS"
    manifest["summary"] = {
        "assigned": len(assignments),
        "published": sum(a["episode_path"] is not None for a in assignments),
        "physical_success": sum(bool(a["physical_success"]) for a in assignments),
        "execution_verified": sum(bool(a["execution_verified"]) for a in assignments),
        "negative_control_success": bool(assignments[1]["physical_success"]),
    }
    _atomic_json(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = TrajectorySmokeConfig.model_validate(yaml.safe_load(args.config.read_text()))
        manifest = generate_trajectories(config, args.output)
    except (ValueError, yaml.YAMLError, FileNotFoundError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "output": str(args.output.resolve()),
        "status": manifest["status"],
        "summary": manifest.get("summary"),
        "reason": manifest.get("reason"),
    }, ensure_ascii=False))
    return {"COMPLETE": 0, "BLOCKED": 3}.get(manifest["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())
