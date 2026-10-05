"""Real-physics regressions for narrow boxes and open-finger limit overshoot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


@pytest.mark.parametrize("assignment_index", [2, 4, 5, 8, 17])
def test_teacher_completes_frozen_gripper_counterexample(assignment_index: int) -> None:
    # Cases cover an undersized box, weak preload, and open-finger overshoot.
    # Rebind the literal development scenes to the asset under test; never
    # import the old success labels or let scene truth reach online planning.
    path = Path(__file__).parent / "fixtures/t5_gripper_dev_cases.json"
    fixture = json.loads(path.read_text())
    assignment = next(row for row in fixture["assignments"] if row["index"] == assignment_index)
    model_path = Path("assets/robots/franka_panda/scene.xml")
    asset_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    scene = SceneSpec.from_parameters(
        assignment["scene_parameters"], asset_hash, assignment["seed"]
    )
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        recorder = EpisodeRecorder()
        outcome = run_teacher_episode(scene, MuJoCoSkillRobot(session._backend), recorder)

    assert outcome.success, outcome
    assert recorder.execution_verified
    assert outcome.measured_lift_m >= 0.05, outcome
    assert outcome.hold_s >= 0.5, outcome
    assert outcome.placed_stable_s >= 1.0, outcome
    assert not outcome.safety_violation, outcome
