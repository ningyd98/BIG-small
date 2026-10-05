"""Offline teacher traces are executed evidence, not planned skill templates."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _observation(
    frame_id: str, sim_time_s: float, *, episode_id: str = "episode-a"
) -> RGBDObservation:
    image = io.BytesIO()
    Image.new("RGB", (1, 1), (90, 30, 20)).save(image, format="PNG")
    return RGBDObservation(
        frame_id=frame_id,
        captured_at=datetime(2026, 10, 3, tzinfo=UTC) + timedelta(seconds=sim_time_s),
        sim_time_s=sim_time_s,
        width=1,
        height=1,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode("ascii"),
        depth_float32_base64=base64.b64encode(struct.pack("<f", 1.0)).decode("ascii"),
        intrinsics=(1.0, 1.0, 0.0, 0.0),
        camera_to_world=(1.0, 0.0, 0.0, 0.0,
                         0.0, 1.0, 0.0, 0.0,
                         0.0, 0.0, 1.0, 0.0,
                         0.0, 0.0, 0.0, 1.0),
        source="mujoco_camera",
        scene_id="scene-a",
        episode_id=episode_id,
    )


def _frame(before: RGBDObservation, after: RGBDObservation):
    from cloud_edge_robot_arm.datasets.rgbd.models import TrajectoryFrame

    action = build_action_result(
        action_type="MOVE_ABOVE",
        success=True,
        state_before={},
        state_after={},
        duration_ms=100,
        details={"physics_steps": 24},
    )
    return TrajectoryFrame(
        observation=before,
        action=action,
        next_observation=after,
        sim_time_s=after.sim_time_s,
        skill_boundary=True,
    )


def test_teacher_recorder_keeps_only_contiguous_same_episode_execution() -> None:
    """A dropped or reordered capture must not be published as an action transition."""
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder

    first = _observation("f0", 0.0)
    second = _observation("f1", 0.1)
    third = _observation("f2", 0.2)
    recorder = EpisodeRecorder()
    recorder.append(_frame(first, second))
    recorder.append(_frame(second, third))

    assert len(recorder.frames) == 2
    assert recorder.source == "GROUND_TRUTH_TEACHER"
    assert not recorder.execution_verified
    with pytest.raises(ValueError, match="contiguous|previous|chain"):
        recorder.append(_frame(first, _observation("f3", 0.3)))
    with pytest.raises(ValueError, match="episode"):
        recorder.append(_frame(
            _observation("f2b", 0.2, episode_id="episode-b"),
            _observation("f3b", 0.3, episode_id="episode-b"),
        ))


def test_teacher_recorder_does_not_self_verify_script_completion() -> None:
    """Finishing a skill list cannot turn a recorded trace into physical success."""
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder

    recorder = EpisodeRecorder()
    recorder.append(_frame(_observation("f0", 0.0), _observation("f1", 0.1)))

    assert recorder.frames[0].action.success
    assert recorder.execution_verified is False


def _fixed_scene():
    from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec

    model_path = Path("assets/robots/franka_panda/scene.xml")
    asset_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    return SceneSpec.from_parameters(
        {
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
            "camera": {"position": [0.35, 0.0, 1.4],
                       "quaternion": [1.0, 0.0, 0.0, 0.0], "fovy": 50.0},
            "light_intensity": 0.8, "depth_noise_m": 0.0,
            "invalid_depth_fraction": 0.0,
        },
        asset_hash,
        seed=31,
    )


def test_teacher_frames_follow_executed_actions() -> None:
    """Every post-action RGB-D frame must come from the advancing physical episode."""
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    scene = _fixed_scene()
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        backend = session._backend
        recorder = EpisodeRecorder()
        outcome = run_teacher_episode(scene, MuJoCoSkillRobot(backend), recorder)

        assert recorder.frames
        assert outcome.evidence_samples == backend.total_physics_steps + 1
        assert recorder.evaluation_start_step == 120
        assert {frame.observation.episode_id for frame in recorder.frames} == {backend._episode_id}
        assert all(
            frame.next_observation.episode_id == backend._episode_id
            for frame in recorder.frames
        )
        assert all(frame.action.details["physics_steps"] > 0 for frame in recorder.frames)
        assert all(
            frame.action.details.get("resolved_target_source") == "GROUND_TRUTH_TEACHER"
            for frame in recorder.frames if "target_pose" in frame.action.details
        )
        assert all(frame.next_observation.sim_time_s > frame.observation.sim_time_s
                   for frame in recorder.frames)
        assert recorder.execution_verified is outcome.success
        assert outcome.success, outcome
        assert outcome.hold_s >= 0.5
        assert outcome.placed_stable_s >= 1.0


def test_teacher_no_contact_case_retains_failed_attempt() -> None:
    """A real no-contact grasp remains a failed episode, even when the script exits."""
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    scene = _fixed_scene()
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        recorder = EpisodeRecorder()
        outcome = run_teacher_episode(
            scene, MuJoCoSkillRobot(session._backend), recorder, case="NO_CONTACT"
        )

    assert not outcome.success
    assert not recorder.execution_verified
    assert len(recorder.frames) == 1
    assert recorder.frames[0].action.action_type == "GRASP"
    assert recorder.frames[0].action.error_code == "NO_GRASP_CONTACT"


def test_trajectory_cli_rejects_unknown_existing_output_without_overwrite(tmp_path: Path) -> None:
    """A partial or foreign dataset path must not be silently treated as resumable."""
    from scripts.generate_rgbd_trajectories import main

    config = tmp_path / "config.yaml"
    config.write_text("episodes: 20\nseed: 31\nwidth: 64\nheight: 64\n")
    output = tmp_path / "teacher"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("pre-existing evidence")

    assert main(["--config", str(config), "--output", str(output)]) == 2
    assert sentinel.read_text() == "pre-existing evidence"
    assert not (output / "manifest.json").exists()


def test_trajectory_config_requires_fixed_positive_and_negative_slots(tmp_path: Path) -> None:
    """Smoke allocation must explicitly contain both a control and a failure case."""
    from scripts.generate_rgbd_trajectories import main

    config = tmp_path / "bad.yaml"
    config.write_text("episodes: 1\nseed: 31\nwidth: 64\nheight: 64\n")
    output = tmp_path / "teacher"

    assert main(["--config", str(config), "--output", str(output)]) == 2
    assert not output.exists()


def test_interrupted_teacher_retains_physical_steps_and_unverified_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recapture failure after motion cannot discard already executed physics."""
    from scripts.generate_rgbd_trajectories import _payload_for_episode

    from cloud_edge_robot_arm.datasets.rgbd import teacher
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    original_capture = teacher._capture
    captures = 0

    def interrupt_after_motion(backend: object):
        nonlocal captures
        captures += 1
        if captures == 2:
            raise RuntimeError("injected recapture failure")
        return original_capture(backend)

    monkeypatch.setattr(teacher, "_capture", interrupt_after_motion)
    scene = _fixed_scene()
    recorder = teacher.EpisodeRecorder()
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        with pytest.raises(RuntimeError, match="injected recapture failure"):
            teacher.run_teacher_episode(scene, MuJoCoSkillRobot(session._backend), recorder)
        actual_steps = session._backend.total_physics_steps

    payload = _payload_for_episode(
        {"index": 0, "case": "NORMAL", "scene_source": "FIXED_S01_CONTROL",
         "scene": scene.model_dump(mode="json"), "group_id": scene.group_id},
        recorder, status="INFRASTRUCTURE_ERROR", reason="injected recapture failure",
        elapsed_wall_s=1.0, protocol_hash="sha-test",
    )
    assert actual_steps > 120
    assert len(recorder.physical_samples) == actual_steps + 1
    assert len(payload["physical_samples"]) == actual_steps + 1
    assert len(payload["unframed_actions"]) == 1
    assert payload["unframed_actions"][0]["action_type"] == "MOVE_ABOVE"
    assert payload["evaluation_start_step"] == 120
    assert payload["protocol_hash"] == "sha-test"
    assert payload["execution_verified"] is False
    assert payload["outcome"] is None


def test_legacy_manifest_cannot_resume_under_new_teacher_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A scoring/teacher implementation change must not silently reuse old episodes."""
    import scripts.generate_rgbd_trajectories as script

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

    config = script.TrajectorySmokeConfig(episodes=2, seed=31, width=64, height=64)
    asset_hash = hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest()
    legacy_hash = content_digest({"config": config.model_dump(mode="json"), "asset": asset_hash})
    output = tmp_path / "legacy-teacher"
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": "rgbd.trajectory.manifest.v1",
        "config_hash": legacy_hash,
        "assignments": script._assignments(config, asset_hash),
    }))

    def forbidden_renderer(_config: object):
        raise AssertionError("old manifest unexpectedly reached the renderer")

    monkeypatch.setattr(script, "MuJoCoCaptureSession", forbidden_renderer)
    with pytest.raises(ValueError, match="protocol|version"):
        script.generate_trajectories(config, output)
