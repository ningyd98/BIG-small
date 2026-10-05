"""Reproduce successful-motion hold and bounded payload tracking in real MuJoCo."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from math import dist, sqrt
from pathlib import Path
from typing import cast
from unittest.mock import patch

import mujoco
import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import GripperCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
    MotionTarget,
    MuJoCoMotionController,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

ASSET = Path("assets/robots/franka_panda/scene.xml")
SOURCES = (
    Path("src/cloud_edge_robot_arm/simulation/mujoco/backend.py"),
    Path("src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"),
    Path("src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py"),
    Path("scripts/probe_rgbd_motion_causality.py"),
)


def _sampled_scene() -> SceneSpec:
    return SceneSpec.from_parameters(
        {
            "target": {
                "position": [0.4762015046284934, -0.04689844687318989, 0.03998306396123982],
                "half_size": [0.03485308665224723, 0.03495699307781209,
                              0.03198306396123982],
                "rgba": [0.9, 0.12, 0.08, 1.0],
                "color_name": "red",
                "mass_kg": 0.08367172678085934,
                "friction": 0.5898796962549298,
            },
            "distractors": [],
            "destination": {
                "position": [0.2, 0.25, 0.002],
                "half_size": [0.07, 0.07, 0.002],
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
        },
        hashlib.sha256(ASSET.read_bytes()).hexdigest(),
        seed=20261008,
    )


def _closure_trial(*, suppress_success_hold: bool) -> dict[str, object]:
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        session.apply_scene(_sampled_scene())
        backend = session._backend
        robot = MuJoCoSkillRobot(backend)
        backend.step(steps=120)
        x, y, z = backend.current_physics_observation().object_position_m
        move_above = robot.move_above(
            "object", resolved_target=Pose(x=x, y=y, z=0.16), timeout_ms=8000
        )
        assert move_above.success
        approach_target = Pose(x=x, y=y, z=z + 0.01)
        if suppress_success_hold:
            # Controlled intervention: omit only the final hold latch on
            # APPROACH. All actuators, contacts and mj_step remain real.
            with patch.object(backend, "hold_current_joints", return_value=None):
                approach = robot.approach(
                    "object", resolved_target=approach_target, timeout_ms=8000
                )
        else:
            approach = robot.approach(
                "object", resolved_target=approach_target, timeout_ms=8000
            )
        assert approach.success
        data = backend._data
        assert data is not None
        remaining_joint_target_rad = (
            backend._target_positions - np.asarray(data.qpos[:7])
        ).tolist()
        before = backend.get_tcp_pose()
        grasp = robot.grasp("object", timeout_ms=1000)
        after = backend.get_tcp_pose()
        return {
            "approach_status": approach.success,
            "approach_position_error_m": approach.details["position_error_m"],
            "approach_max_load_compensation_rad": approach.details[
                "max_load_compensation_rad"
            ],
            "remaining_joint_target_rad": remaining_joint_target_rad,
            "grasp_physics_steps": grasp.details["physics_steps"],
            "grasp_success": grasp.success,
            "left_contact_count": grasp.details["left_contact_count"],
            "right_contact_count": grasp.details["right_contact_count"],
            "tcp_before_grasp_m": [before.x, before.y, before.z],
            "tcp_after_grasp_m": [after.x, after.y, after.z],
            "tcp_drift_during_grasp_m": dist(
                (before.x, before.y, before.z),
                (after.x, after.y, after.z),
            ),
        }


def _static_backend() -> MuJoCoPhysicsBackend:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path=str(ASSET)))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
    return backend


def _loaded_trial() -> dict[str, object]:
    backend = _static_backend()
    try:
        model = backend._model
        data = backend._data
        assert model is not None and data is not None
        object_body_id = model.body("object").id
        initial_z = float(data.xpos[object_body_id, 2])
        downward = (sqrt(0.5), 0.0, sqrt(0.5), 0.0)
        controller = MuJoCoMotionController(backend)
        approach = controller.move_tcp(
            MotionTarget(Pose(x=0.45, y=0.0, z=0.045), downward), timeout_s=8.0
        )
        assert approach.status == "SUCCEEDED"
        backend.apply_gripper_command(GripperCommand(open=False))
        backend.step(steps=240)
        lift = controller.move_tcp(
            MotionTarget(Pose(x=0.45, y=0.0, z=0.145), downward), timeout_s=8.0
        )
        backend.step(steps=120)
        contacts = backend.get_contacts()
        return {
            "status": lift.status,
            "position_error_m": lift.position_error_m,
            "orientation_error_deg": lift.orientation_error_deg,
            "physics_steps": lift.physics_steps,
            "max_load_compensation_rad": lift.max_load_compensation_rad,
            "object_lift_after_0_5_s_hold_m": float(data.xpos[object_body_id, 2]) - initial_z,
            "left_contact_count": sum(
                {c.geom1, c.geom2} == {"left_finger_geom", "object_geom"}
                for c in contacts
            ),
            "right_contact_count": sum(
                {c.geom1, c.geom2} == {"right_finger_geom", "object_geom"}
                for c in contacts
            ),
        }
    finally:
        backend.shutdown()


def _unloaded_trial() -> dict[str, object]:
    backend = _static_backend()
    try:
        result = MuJoCoMotionController(backend).move_tcp(
            MotionTarget(Pose(x=0.625, y=0.0, z=0.485), (1.0, 0.0, 0.0, 0.0)),
            timeout_s=5.0,
        )
        return {
            "status": result.status,
            "position_error_m": result.position_error_m,
            "orientation_error_deg": result.orientation_error_deg,
            "physics_steps": result.physics_steps,
            "max_load_compensation_rad": result.max_load_compensation_rad,
        }
    finally:
        backend.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    without_hold = _closure_trial(suppress_success_hold=True)
    with_hold = _closure_trial(suppress_success_hold=False)
    loaded = _loaded_trial()
    unloaded = _unloaded_trial()
    passed = (
        cast(float, without_hold["tcp_drift_during_grasp_m"]) >= 0.05
        and cast(float, with_hold["tcp_drift_during_grasp_m"]) <= 0.01
        and loaded["status"] == "SUCCEEDED"
        and cast(float, loaded["position_error_m"]) <= 0.005
        and cast(float, loaded["orientation_error_deg"]) <= 5.0
        and 0.0 < cast(float, loaded["max_load_compensation_rad"]) <= 0.03
        and cast(float, loaded["object_lift_after_0_5_s_hold_m"]) >= 0.05
        and unloaded["status"] == "SUCCEEDED"
        and unloaded["max_load_compensation_rad"] == 0.0
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "evidence_type": "REAL_MUJOCO_PHYSICS",
        "mujoco_version": mujoco.__version__,
        "asset_sha256": hashlib.sha256(ASSET.read_bytes()).hexdigest(),
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCES
        },
        "closure_index5_seed20261008": {
            "controlled_difference": (
                "APPROACH final hold_current_joints disabled only in diagnostic baseline"
            ),
            "without_success_hold": without_hold,
            "with_success_hold": with_hold,
        },
        "payload_tracking_s01_seed31": {
            "historical_before_compensation": {
                "status": "TIMED_OUT",
                "position_error_m": 0.010771631782566314,
                "orientation_error_deg": 1.4704799581847616,
                "physics_steps": 1919,
                "note": (
                    "Measured on this asset in the prior controller revision; "
                    "not replayed by this executable."
                ),
            },
            "with_bounded_compensation": loaded,
            "unloaded_control": unloaded,
            "max_allowed_correction_rad": 0.03,
            "required_position_error_m": 0.005,
            "required_orientation_error_deg": 5.0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"status": payload["status"], "output": str(args.output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
