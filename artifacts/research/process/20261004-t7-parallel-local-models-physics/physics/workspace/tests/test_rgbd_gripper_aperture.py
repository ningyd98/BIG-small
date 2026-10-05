"""Physical regressions for the T5 narrow-box grasp counterexamples."""
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
def test_teacher_physically_lifts_and_holds_narrow_t5_box(assignment_index: int) -> None:
    # Moving finger centers outward so the closed gap exceeds the sampled box
    # width breaks grasp or preload. Expectations come from unchanged physical
    # completion criteria; the fixture is a literal frozen development scene.
    fixture = json.loads(Path("tests/fixtures/t5_gripper_dev_cases.json").read_text())
    assignment = next(a for a in fixture["assignments"] if a["index"] == assignment_index)
    asset_hash = hashlib.sha256(Path("assets/robots/franka_panda/scene.xml").read_bytes()).hexdigest()
    scene = SceneSpec.from_parameters(
        assignment["scene"]["scene_parameters"], asset_hash, assignment["seed"]
    )
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        recorder = EpisodeRecorder()
        outcome = run_teacher_episode(scene, MuJoCoSkillRobot(session._backend), recorder)

    assert outcome.measured_lift_m >= 0.05, outcome
    assert outcome.hold_s >= 0.5, outcome
    assert not outcome.safety_violation, outcome
