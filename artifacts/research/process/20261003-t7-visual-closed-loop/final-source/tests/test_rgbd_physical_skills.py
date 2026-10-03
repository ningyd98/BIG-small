"""T4: real MuJoCo motion and contact evidence for research skills."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import GripperCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


@pytest.fixture
def backend() -> MuJoCoPhysicsBackend:
    physical = MuJoCoPhysicsBackend()
    physical.initialize(SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"))
    physical.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
    try:
        yield physical
    finally:
        physical.shutdown()


def test_tcp_motion_requires_physics_steps(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    target = MotionTarget(
        position=Pose(x=0.625, y=0.0, z=0.485),
        orientation_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    start = backend.total_physics_steps
    result = MuJoCoMotionController(backend).move_tcp(target, timeout_s=5.0)

    assert result.status == "SUCCEEDED"
    assert result.physics_steps == backend.total_physics_steps - start > 0
    assert result.position_error_m <= 0.005
    assert result.orientation_error_deg <= 5.0
    assert result.max_load_compensation_rad == 0.0
    assert backend.command_records


def test_unreachable_target_times_out(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    result = MuJoCoMotionController(backend).move_tcp(
        MotionTarget(
            position=Pose(x=2.0, y=0.0, z=2.0),
            orientation_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
        timeout_s=0.1,
    )
    assert result.status in {"UNREACHABLE", "TIMED_OUT"}
    assert result.position_error_m > 0.5
    assert result.physics_steps <= 24


def test_timeout_does_not_resume_old_joint_target_on_later_step(
    backend: MuJoCoPhysicsBackend,
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    downward = (sqrt(0.5), 0.0, sqrt(0.5), 0.0)
    result = MuJoCoMotionController(backend).move_tcp(
        MotionTarget(Pose(x=0.45, y=0.0, z=0.20), downward), timeout_s=0.5
    )
    assert result.status == "TIMED_OUT"
    stopped_pose = backend.get_tcp_pose()
    backend.step(steps=120)
    after = backend.get_tcp_pose()
    drift_m = sqrt(
        (after.x - stopped_pose.x) ** 2
        + (after.y - stopped_pose.y) ** 2
        + (after.z - stopped_pose.z) ** 2
    )
    assert drift_m <= 0.01


def test_grasp_without_contact_fails(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    result = robot.grasp("object", timeout_ms=1000)

    assert not result.success
    assert result.error_code == "NO_GRASP_CONTACT"
    assert result.details["physics_steps"] > 0
    assert result.details["grasp_contact_count"] == 0
    assert robot.get_state().holding_object_id is None


def test_motion_needs_explicit_resolved_target(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    before = backend.total_physics_steps
    rejected = robot.move_above("object", timeout_ms=8000)
    assert not rejected.success
    assert rejected.error_code == "TARGET_NOT_RESOLVED"
    assert backend.total_physics_steps == before

    resolved = Pose(x=0.45, y=0.0, z=0.20)
    accepted = robot.move_above("object", resolved_target=resolved, timeout_ms=8000)
    assert accepted.success
    assert accepted.details["physics_steps"] > 0
    assert accepted.details["max_load_compensation_rad"] == 0.0
    assert abs(backend.get_tcp_pose().x - resolved.x) <= 0.005
    assert abs(backend.get_tcp_pose().z - resolved.z) <= 0.005


def test_backend_reset_opens_fingers_physically(backend: MuJoCoPhysicsBackend) -> None:
    model = backend._model
    data = backend._data
    assert model is not None and data is not None
    finger_ids = [model.joint(name).id for name in ("finger_left_joint", "finger_right_joint")]
    finger_qpos = [float(data.qpos[model.jnt_qposadr[joint_id]]) for joint_id in finger_ids]
    assert min(finger_qpos) >= 0.039
    assert min(data.ctrl[7:9]) >= 0.039


def test_stop_prevents_new_motion(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    stop = robot.emergency_stop()
    before = backend.total_physics_steps
    result = robot.move_above(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.20), timeout_ms=8000
    )

    assert stop.success
    assert not result.success
    assert result.error_code == "EMERGENCY_STOP"
    assert backend.total_physics_steps == before


def test_emergency_stop_holds_arm_after_physics_advances(
    backend: MuJoCoPhysicsBackend,
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    moved = robot.move_above(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.16), timeout_ms=8000
    )
    assert moved.success
    assert robot.emergency_stop().success
    stopped_pose = backend.get_tcp_pose()
    backend.step(steps=120)
    after = backend.get_tcp_pose()
    drift_m = sqrt(
        (after.x - stopped_pose.x) ** 2
        + (after.y - stopped_pose.y) ** 2
        + (after.z - stopped_pose.z) ** 2
    )
    assert drift_m <= 0.01


def test_zero_timeout_rejects_motion_without_stepping(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    before = backend.total_physics_steps
    result = robot.move_above(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.20), timeout_ms=0
    )

    assert not result.success
    assert result.error_code == "INVALID_MOTION_REQUEST"
    assert backend.total_physics_steps == before


@pytest.mark.parametrize("timeout_ms", [0, -1])
def test_invalid_gripper_timeout_rejects_without_stepping(
    backend: MuJoCoPhysicsBackend, timeout_ms: int
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    before = backend.total_physics_steps
    grasp = robot.grasp("object", timeout_ms=timeout_ms)
    release = robot.release(timeout_ms=timeout_ms)

    assert not grasp.success and grasp.error_code == "INVALID_TIMEOUT"
    assert not release.success and release.error_code == "INVALID_TIMEOUT"
    assert backend.total_physics_steps == before


def test_short_resolved_lift_is_rejected_even_with_contact(
    backend: MuJoCoPhysicsBackend,
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    assert robot.approach(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.045), timeout_ms=8000
    ).success
    assert robot.grasp("object", timeout_ms=1000).success
    current = backend.get_tcp_pose()
    before = backend.total_physics_steps
    result = robot.lift(
        height_m=0.10,
        resolved_target=Pose(x=current.x, y=current.y, z=current.z + 0.01),
        timeout_ms=8000,
    )

    assert not result.success
    assert result.error_code == "INVALID_LIFT_HEIGHT"
    assert backend.total_physics_steps == before


def test_empty_hand_cannot_claim_place_or_carry(
    backend: MuJoCoPhysicsBackend,
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    robot = MuJoCoSkillRobot(backend)
    before = backend.total_physics_steps
    carry = robot.move_to_region(
        "target_region", resolved_target=Pose(x=0.20, y=0.25, z=0.16),
        timeout_ms=10000,
    )
    place = robot.place(
        "target_region", resolved_target=Pose(x=0.20, y=0.25, z=0.045),
        timeout_ms=10000,
    )

    assert not carry.success and carry.error_code == "NO_GRASP_CONTACT"
    assert not place.success and place.error_code == "NO_GRASP_CONTACT"
    assert backend.total_physics_steps == before


def test_contact_grasp_lifts_object_and_holds(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    model = backend._model
    data = backend._data
    assert model is not None and data is not None
    object_id = model.body("object").id
    initial_z = float(data.xpos[object_id, 2])
    downward = (sqrt(0.5), 0.0, sqrt(0.5), 0.0)
    controller = MuJoCoMotionController(backend)

    backend.apply_gripper_command(GripperCommand(open=True))
    approach = controller.move_tcp(
        MotionTarget(Pose(x=0.45, y=0.0, z=0.045), downward), timeout_s=8.0
    )
    assert approach.status == "SUCCEEDED"
    backend.apply_gripper_command(GripperCommand(open=False))
    backend.step(steps=240)
    left = any(
        {contact.geom1, contact.geom2} == {"left_finger_geom", "object_geom"}
        for contact in backend.get_contacts()
    )
    right = any(
        {contact.geom1, contact.geom2} == {"right_finger_geom", "object_geom"}
        for contact in backend.get_contacts()
    )
    assert left and right

    lift = controller.move_tcp(
        MotionTarget(Pose(x=0.45, y=0.0, z=0.145), downward), timeout_s=8.0
    )
    assert np.allclose(backend._target_positions, data.qpos[:7], atol=1e-12)
    backend.step(steps=120)  # 0.5 s hold after lifting
    held_z = float(data.xpos[object_id, 2])
    assert lift.status == "SUCCEEDED"
    assert lift.position_error_m <= 0.005
    assert lift.orientation_error_deg <= 5.0
    assert 0 < lift.max_load_compensation_rad <= 0.03
    assert held_z - initial_z >= 0.05
    assert any(contact.expected for contact in backend.get_contacts())


def test_skill_robot_physically_places_object_and_stabilizes(
    backend: MuJoCoPhysicsBackend,
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    model = backend._model
    data = backend._data
    assert model is not None and data is not None
    object_id = model.body("object").id
    initial_z = float(data.xpos[object_id, 2])
    robot = MuJoCoSkillRobot(backend)

    assert robot.move_above(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.16), timeout_ms=8000
    ).success
    assert robot.approach(
        "object", resolved_target=Pose(x=0.45, y=0.0, z=0.045), timeout_ms=8000
    ).success
    grasp = robot.grasp("object", timeout_ms=1000)
    assert grasp.success
    assert grasp.details["left_contact_count"] > 0
    assert grasp.details["right_contact_count"] > 0
    lift = robot.lift(height_m=0.10, timeout_ms=8000)
    assert lift.success
    assert 0.0 <= lift.details["max_load_compensation_rad"] <= 0.03
    backend.step(steps=120)
    assert float(data.xpos[object_id, 2]) - initial_z >= 0.05
    assert any(contact.expected for contact in backend.get_contacts())

    assert robot.move_to_region(
        "target_region", resolved_target=Pose(x=0.20, y=0.25, z=0.16),
        timeout_ms=10000,
    ).success
    assert robot.place(
        "target_region", resolved_target=Pose(x=0.20, y=0.25, z=0.045),
        timeout_ms=8000,
    ).success
    assert robot.release(timeout_ms=1000).success
    backend.step(steps=240)  # 1.0 s after release
    final = data.xpos[object_id]
    assert 0.12 <= float(final[0]) <= 0.28
    assert 0.17 <= float(final[1]) <= 0.33
    assert abs(float(final[2]) - 0.035) <= 0.005
    assert not any(contact.expected for contact in backend.get_contacts())


def test_execution_never_writes_object_pose(
    backend: MuJoCoPhysicsBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    # Reset has ended. Any command-side object pose setter is now forbidden.
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("object pose setter called during execution")

    monkeypatch.setattr(backend, "_set_free_body_pose", forbidden)
    model = backend._model
    data = backend._data
    assert model is not None and data is not None
    object_joint = model.joint("object_free").id
    qpos_addr = int(model.jnt_qposadr[object_joint])
    object_before = np.array(data.qpos[qpos_addr : qpos_addr + 7], copy=True)
    result = MuJoCoMotionController(backend).move_tcp(
        MotionTarget(
            position=Pose(x=0.635, y=0.0, z=0.485),
            orientation_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
        timeout_s=5.0,
    )

    assert result.status == "SUCCEEDED"
    assert result.physics_steps > 0
    # Static object remains on the table; numerical settling is permitted.
    np.testing.assert_allclose(data.qpos[qpos_addr : qpos_addr + 2], object_before[:2], atol=1e-4)
    assert abs(float(data.qpos[qpos_addr + 2]) - float(object_before[2])) < 0.003


def test_rejects_non_unit_orientation(backend: MuJoCoPhysicsBackend) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
        MotionTarget,
        MuJoCoMotionController,
    )

    controller = MuJoCoMotionController(backend)
    with pytest.raises(ValueError, match="quaternion"):
        controller.move_tcp(
            MotionTarget(
                position=Pose(x=0.6, y=0.0, z=0.5),
                orientation_wxyz=(sqrt(0.5), 0.0, 0.0, 0.0),
            ),
            timeout_s=1.0,
        )
