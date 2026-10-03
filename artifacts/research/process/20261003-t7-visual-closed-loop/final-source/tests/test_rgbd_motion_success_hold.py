"""A successful TCP move must not keep driving while the gripper closes."""

from __future__ import annotations

import hashlib
from math import dist
from pathlib import Path

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


def test_successful_approach_holds_tcp_during_physical_gripper_closure() -> None:
    """Regression from a real sampled scene that previously drifted 79 mm."""
    model_path = Path("assets/robots/franka_panda/scene.xml")
    scene = SceneSpec.from_parameters(
        {
            "target": {
                "position": [0.4762015046284934, -0.04689844687318989, 0.03998306396123982],
                "half_size": [0.03485308665224723, 0.03495699307781209,
                              0.03198306396123982],
                "rgba": [0.9, 0.12, 0.08, 1.0], "color_name": "red",
                "mass_kg": 0.08367172678085934, "friction": 0.5898796962549298,
            },
            "distractors": [],
            "destination": {
                "position": [0.2, 0.25, 0.002], "half_size": [0.07, 0.07, 0.002],
                "rgba": [0.1, 0.6, 0.2, 1.0],
            },
            "camera": {
                "position": [0.35, 0.0, 1.4], "quaternion": [1.0, 0.0, 0.0, 0.0],
                "fovy": 50.0,
            },
            "light_intensity": 0.8,
            "depth_noise_m": 0.0,
            "invalid_depth_fraction": 0.0,
        },
        hashlib.sha256(model_path.read_bytes()).hexdigest(),
        seed=20261008,
    )
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(scene)
        backend = session._backend
        robot = MuJoCoSkillRobot(backend)
        backend.step(steps=120)
        object_xyz = backend.current_physics_observation().object_position_m
        assert robot.move_above(
            "object", resolved_target=Pose(x=object_xyz[0], y=object_xyz[1], z=0.16),
            timeout_ms=8000,
        ).success
        assert robot.approach(
            "object", resolved_target=Pose(
                x=object_xyz[0], y=object_xyz[1], z=object_xyz[2] + 0.01,
            ), timeout_ms=8000,
        ).success
        before = backend.get_tcp_pose()

        grasp = robot.grasp("object", timeout_ms=1000)
        after = backend.get_tcp_pose()

        assert grasp.details["physics_steps"] == 239
        assert dist(
            (before.x, before.y, before.z), (after.x, after.y, after.z)
        ) <= 0.010
