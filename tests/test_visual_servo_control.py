"""Continuous feedback acts inside real MuJoCo motion, with bounded commands."""

from math import sqrt

import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget

DOWNWARD = (sqrt(0.5), 0.0, sqrt(0.5), 0.0)


@pytest.fixture
def backend():
    physical = MuJoCoPhysicsBackend()
    physical.initialize(SimulatorConfig(physics_dt_s=1 / 240))
    physical.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
    try:
        yield physical
    finally:
        physical.shutdown()


def api():
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import (
        MuJoCoVisualServoController,
        VisualServoConfig,
        VisualServoSession,
    )

    return MuJoCoVisualServoController, VisualServoConfig, VisualServoSession


def test_same_motion_retargets_with_exact_visual_cadence_and_bounded_commands(backend):
    controller, _, session_type = api()
    initial = MotionTarget(Pose(x=0.45, y=0, z=0.20), DOWNWARD)
    shifted = MotionTarget(Pose(x=0.455, y=0, z=0.20), DOWNWARD)

    def sample(_target):
        return shifted if backend.get_sim_time() >= 0.2 else initial

    session = session_type(sample)
    result = controller(backend).move_tcp(
        initial, timeout_s=8, session=session,
        max_joint_velocity_rad_s=0.8, max_joint_acceleration_rad_s2=2.0,
    )
    assert result.status == "SUCCEEDED"
    assert backend.get_tcp_pose().x == pytest.approx(shifted.position.x, abs=0.005)
    assert len(session.records) > 10
    steps = [r["physics_step"] for r in session.records]
    assert set(np.diff(steps)) == {8}
    assert session.records[0]["target_pose"]["x"] == initial.position.x
    assert session.records[-1]["target_pose"]["x"] == shifted.position.x
    commands = [r for r in backend.command_records if r["type"] == "joint_target"]
    positions = np.array([r["target_positions_rad"] for r in commands])
    times = np.array([r["sim_time_s"] for r in commands])
    velocities = np.diff(positions, axis=0) / np.diff(times)[:, None]
    assert np.max(np.abs(velocities)) <= 0.8 + 1e-8
    accelerations = np.diff(velocities, axis=0) / np.diff(times)[1:, None]
    assert np.max(np.abs(accelerations)) <= 2.0 + 1e-8
    assert len(positions) > 10


def test_lost_feedback_stops_before_another_actuator_command(backend):
    controller, _, session_type = api()
    target = MotionTarget(Pose(x=0.45, y=0, z=0.20), DOWNWARD)
    calls = []

    def sample(_target):
        calls.append(backend.total_physics_steps)
        if len(calls) == 3:
            raise RuntimeError("target lost")
        return target

    session = session_type(sample)
    with pytest.raises(RuntimeError, match="target lost"):
        controller(backend).move_tcp(target, timeout_s=8, session=session)
    assert backend.total_physics_steps == 16
    assert backend.command_records[-1]["type"] == "hold_current_joints"
    held = np.array(backend._target_positions)
    backend.step(5)
    np.testing.assert_array_equal(backend._target_positions, held)


@pytest.mark.parametrize("fault", ["jump", "orientation", "slow"])
def test_invalid_or_late_feedback_does_not_advance_physics(backend, fault):
    import time

    controller, config_type, session_type = api()
    target = MotionTarget(Pose(x=0.45, y=0, z=0.20), DOWNWARD)

    def sample(_target):
        if fault == "slow":
            time.sleep(0.003)
            return target
        if fault == "orientation":
            return MotionTarget(target.position, (2, 0, 0, 0))
        return MotionTarget(Pose(x=0.50, y=0, z=0.20), DOWNWARD)

    session = session_type(sample, config_type(max_sample_latency_s=0.001))
    with pytest.raises(ValueError):
        controller(backend).move_tcp(target, timeout_s=8, session=session)
    assert backend.total_physics_steps == 0
    assert backend.command_records[-1]["type"] == "hold_current_joints"


def test_skill_session_is_cleared_after_exception_and_cannot_nest(backend):
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    _, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    session = session_type(lambda target: target)
    with pytest.raises(RuntimeError, match="application failure"):
        with robot.visual_servo(session):
            with pytest.raises(RuntimeError, match="already"):
                with robot.visual_servo(session):
                    pass
            raise RuntimeError("application failure")
    assert robot._visual_servo_session is None


def test_skill_adapter_actually_uses_continuous_feedback(backend):
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    _, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    session = session_type(lambda target: target)
    with robot.visual_servo(session):
        action = robot.move_above("object", resolved_target=Pose(x=0.45, y=0, z=0.20))
    assert action.success
    assert action.details["visual_servo"]["feedback_count"] >= 3
    assert len(session.records) >= 3
    assert robot._visual_servo_session is None


def test_lift_keeps_visual_feedback_through_contact_hold(backend):
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    _, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    assert robot.grasp("object", timeout_ms=1000).success
    session = session_type(lambda target: target)
    with robot.visual_servo(session):
        action = robot.lift(resolved_target=Pose(x=0.45, y=0, z=0.16))
    assert action.success, action.error_code
    held = [record for record in session.records if record.get("phase") == "HOLD"]
    assert len(held) >= 15
    assert held[-1]["sim_time_s"] == backend.get_sim_time()
    assert max(np.diff([record["physics_step"] for record in session.records])) <= 8
