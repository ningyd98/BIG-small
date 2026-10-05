"""A read-only replay catches tampered or mixed-version teacher episodes."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import struct
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import TrajectoryFrame, content_digest
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _observation(
    frame_id: str, scene_id: str, episode_id: str, sim_time_s: float
) -> RGBDObservation:
    png = io.BytesIO()
    Image.new("RGB", (1, 1), (90, 30, 20)).save(png, format="PNG")
    return RGBDObservation(
        frame_id=frame_id,
        captured_at=datetime(2026, 10, 3, tzinfo=UTC) + timedelta(seconds=sim_time_s),
        sim_time_s=sim_time_s,
        width=1,
        height=1,
        rgb_png_base64=base64.b64encode(png.getvalue()).decode("ascii"),
        depth_float32_base64=base64.b64encode(struct.pack("<f", 1.0)).decode("ascii"),
        intrinsics=(1.0, 1.0, 0.0, 0.0),
        camera_to_world=(1.0, 0.0, 0.0, 0.0,
                         0.0, 1.0, 0.0, 0.0,
                         0.0, 0.0, 1.0, 0.0,
                         0.0, 0.0, 0.0, 1.0),
        source="mujoco_camera",
        scene_id=scene_id,
        episode_id=episode_id,
    )


def _physical_sample(episode_id: str, step: int) -> PhysicalSample:
    return PhysicalSample(
        episode_id=episode_id,
        physics_step=step,
        sim_time_s=step / 240.0,
        object_position_m=(0.45, 0.0, 0.035),
        object_bottom_z_m=0.0,
        object_half_extent_xy_m=(0.035, 0.035),
        object_linear_speed_m_s=0.0,
        object_angular_speed_rad_s=0.0,
        region_center_xy_m=(0.2, 0.25),
        region_half_extent_xy_m=(0.08, 0.08),
        table_height_m=0.0,
        gripper_open=True,
        left_finger_contact=False,
        right_finger_contact=False,
        contact_pairs=(("table", "object_geom"),),
        joint_limit_violation=False,
        joint_velocity_violation=False,
        workspace_violation=False,
        self_collision_checked_pairs=(("base", "hand"),),
    )


def _dataset(root: Path) -> Path:
    from scripts.generate_rgbd_trajectories import (
        TrajectorySmokeConfig,
        _assignments,
        _payload_for_episode,
        _protocol_snapshot,
        _write_episode,
    )

    config = TrajectorySmokeConfig(episodes=2, seed=31, width=16, height=16)
    asset_hash = hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest()
    protocol = _protocol_snapshot()
    protocol_hash = content_digest(protocol)
    assignments = _assignments(config, asset_hash)
    (root / "episodes").mkdir(parents=True)
    (root / ".staging").mkdir()
    for assignment in assignments:
        episode_id = f"synthetic-{assignment['index']}"
        scene_id = assignment["group_id"]
        observations = [
            _observation(f"f{assignment['index']}-{step}", scene_id, episode_id, step / 240.0)
            for step in range(3)
        ]
        recorder = EpisodeRecorder()
        for before, after in zip(observations, observations[1:], strict=False):
            action = build_action_result(
                action_type="OBSERVE", success=True, state_before={}, state_after={},
                duration_ms=4,
                details={"physics_steps": 1, "teacher_source": "GROUND_TRUTH_TEACHER"},
            )
            recorder.append(TrajectoryFrame(
                observation=before, action=action, next_observation=after,
                sim_time_s=after.sim_time_s, skill_boundary=True,
            ))
        recorder.physical_samples = [_physical_sample(episode_id, step) for step in range(3)]
        recorder.evaluation_start_step = 0
        outcome = evaluate_evidence(
            recorder.physical_samples, CompletionCriteria("object", "target_region"),
            evaluation_start_step=0,
        )
        assert outcome.status == "FAILED"
        recorder._finish(outcome)
        payload = _payload_for_episode(
            assignment, recorder, status=outcome.status, reason=outcome.failure_reason,
            elapsed_wall_s=0.1, protocol_hash=protocol_hash,
        )
        digest = _write_episode(root, assignment, payload)
        assignment.update(
            status=outcome.status,
            episode_path=f"episodes/{assignment['index']:04d}/episode.json.gz",
            sha256=digest, execution_verified=False, physical_success=False,
        )
    manifest = {
        "schema_version": "rgbd.trajectory.manifest.v1",
        "dataset_id": config.dataset_id,
        "config": config.model_dump(mode="json"),
        "config_hash": content_digest({
            "config": config.model_dump(mode="json"), "asset": asset_hash,
            "protocol_hash": protocol_hash,
        }),
        "asset_sha256": asset_hash,
        "protocol_hash": protocol_hash,
        "protocol": protocol,
        "requested_episodes": 2,
        "status": "COMPLETE",
        "assignments": assignments,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_validator_replays_two_episodes_and_detects_checksum_tamper(tmp_path: Path) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    report = validate_trajectory_dataset(root)
    assert report["valid"]
    assert report["status_counts"] == {"FAILED": 2}
    assert report["physical_success"] == 0
    assert report["execution_verified"] == 0

    path = root / "episodes/0000/episode.json.gz"
    path.write_bytes(path.read_bytes() + b"tamper")
    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("SHA256" in error for error in report["errors"])


def test_generator_resumes_json_round_tripped_protocol_without_rendering(tmp_path: Path) -> None:
    from scripts.generate_rgbd_trajectories import TrajectorySmokeConfig, generate_trajectories

    root = _dataset(tmp_path / "teacher")
    manifest = generate_trajectories(
        TrajectorySmokeConfig(episodes=2, seed=31, width=16, height=16), root,
    )
    assert manifest["status"] == "COMPLETE"
    assert all(assignment["sha256"] for assignment in manifest["assignments"])


def test_validator_direct_script_cli_emits_json_report(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "teacher")
    repository = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repository / "scripts/validate_rgbd_trajectories.py"),
         "--dataset", str(root)],
        cwd=repository, capture_output=True, text=True, check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 2  # Both synthetic controls fail, so batch is not accepted.
    assert report["valid"]
    assert report["status_counts"] == {"FAILED": 2}


def test_validator_rejects_legacy_protocol_before_replay(tmp_path: Path) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("protocol_hash")
    manifest_path.write_text(json.dumps(manifest))

    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("protocol" in error.lower() for error in report["errors"])


def test_validator_rejects_changed_scene_assignment_seed(tmp_path: Path) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assignments"][0]["seed"] += 1
    manifest_path.write_text(json.dumps(manifest))

    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("planned scene" in error.lower() for error in report["errors"])


def test_validator_rejects_status_that_disagrees_with_independent_replay(tmp_path: Path) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    path = root / "episodes/0000/episode.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    payload["status"] = "SUCCESS"
    compressed = gzip.compress(json.dumps(payload).encode(), mtime=0)
    path.write_bytes(compressed)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assignments"][0]["status"] = "SUCCESS"
    manifest["assignments"][0]["sha256"] = hashlib.sha256(compressed).hexdigest()
    manifest_path.write_text(json.dumps(manifest))

    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("replay status" in error.lower() for error in report["errors"])


@pytest.mark.parametrize("corruption", ["missing_measurement", "checked_pairs"])
def test_validator_rejects_incomplete_or_changed_outcome(
    tmp_path: Path, corruption: str
) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    path = root / "episodes/0000/episode.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    if corruption == "missing_measurement":
        payload["outcome"].pop("measured_lift_m")
    else:
        payload["outcome"]["self_collision_checked_pairs"] = [["tampered", "pair"]]
    compressed = gzip.compress(json.dumps(payload).encode(), mtime=0)
    path.write_bytes(compressed)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assignments"][0]["sha256"] = hashlib.sha256(compressed).hexdigest()
    manifest_path.write_text(json.dumps(manifest))

    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("outcome replay mismatch" in error.lower() for error in report["errors"])


def test_validator_catches_broken_frame_chain_and_step_gap(tmp_path: Path) -> None:
    from scripts.validate_rgbd_trajectories import validate_trajectory_dataset

    root = _dataset(tmp_path / "teacher")
    path = root / "episodes/0000/episode.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    observation = payload["frames"][1]["observation"]
    observation["frame_id"] = "fresh-but-unlinked"
    observation["observation_id"] = "fresh-but-unlinked"
    observation["checksum_sha256"] = ""
    payload["physical_samples"].pop(1)
    compressed = gzip.compress(json.dumps(payload).encode(), mtime=0)
    path.write_bytes(compressed)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assignments"][0]["sha256"] = hashlib.sha256(compressed).hexdigest()
    manifest_path.write_text(json.dumps(manifest))

    report = validate_trajectory_dataset(root)
    assert not report["valid"]
    assert any("chain" in error.lower() for error in report["errors"])
    assert any("continuous" in error.lower() for error in report["errors"])
