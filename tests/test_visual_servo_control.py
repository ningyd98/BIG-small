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


@pytest.mark.parametrize("visual", [False, True])
def test_each_physics_step_is_guarded_and_exception_cancels_motion(backend, visual):
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController

    controller, _, session_type = api()
    target = MotionTarget(Pose(x=0.45, y=0, z=0.20), DOWNWARD)
    seen = []

    def guard():
        seen.append(backend.total_physics_steps)
        if backend.total_physics_steps == 3:
            raise RuntimeError("inter-step fault")

    instance = controller(backend) if visual else MuJoCoMotionController(backend)
    options = {"session": session_type(lambda value: value)} if visual else {}
    with pytest.raises(RuntimeError, match="inter-step fault"):
        instance.move_tcp(target, timeout_s=8, state_guard=guard, **options)
    assert {0, 1, 2, 3} <= set(seen)
    assert backend.total_physics_steps == 3
    assert backend.command_records[-1]["type"] == "hold_current_joints"
    assert not [record for record in backend.command_records
                if record["type"] == "joint_target" and record["physics_step"] >= 3]


def test_clearance_target_cannot_be_retargeted_by_visual_callback(backend):
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    controller, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    backend.step(240)
    start = backend.get_tcp_pose()
    target = MotionTarget(Pose(x=start.x, y=start.y, z=0.16), DOWNWARD)
    path = VerticalClearancePath(
        task_id="task", step_id="retreat", skill="RETREAT",
        start_m=(start.x, start.y, start.z),
        target_m=(target.position.x, target.position.y, target.position.z), minimum_height_m=0.08,
    )
    session = session_type(
        lambda value: MotionTarget(value.position.model_copy(update={"x": start.x + 0.001}),
                                   value.orientation_wxyz),
        vertical_clearance=path,
    )
    before = backend.total_physics_steps
    with pytest.raises(ValueError, match="clearance target"):
        controller(backend).move_tcp(target, timeout_s=8, session=session)
    assert backend.total_physics_steps == before
    assert backend.command_records[-1]["type"] == "hold_current_joints"


def test_low_grasp_rises_inside_fixed_vertical_corridor_and_holds(backend):
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    _, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    assert robot.grasp("object", timeout_ms=1000).success
    start = backend.get_tcp_pose()
    target = Pose(x=start.x, y=start.y, z=0.16)
    path = VerticalClearancePath(
        task_id="task", step_id="lift", skill="LIFT",
        start_m=(start.x, start.y, start.z), target_m=(start.x, start.y, target.z),
        minimum_height_m=0.08,
    )
    session = session_type(lambda value: value, vertical_clearance=path)
    measured = []
    beginning = backend.total_physics_steps

    def record(_event):
        pose = backend.get_tcp_pose()
        measured.append((pose.x, pose.y, pose.z))

    with backend.observe_physics_steps(record), robot.visual_servo(session):
        action = robot.lift(resolved_target=target, timeout_ms=10000,
                            tcp_velocity=0.15, acceleration=0.5)
    assert action.success, action.details
    peak = start.z
    for position in measured:
        path.check_position(position, peak_z=peak)
        peak = max(peak, position[2])
    assert peak - start.z >= 0.05
    assert len([r for r in session.records if r.get("phase") == "HOLD"]) >= 15
    commands = [r for r in backend.command_records
                if r["type"] == "joint_target" and r["physics_step"] >= beginning]
    times = np.array([r["sim_time_s"] for r in commands])
    positions = np.array([r["target_positions_rad"] for r in commands])
    assert set(np.diff([r["physics_step"] for r in commands])) == {5}
    velocity = np.diff(positions, axis=0) / np.diff(times)[:, None]
    acceleration = np.diff(velocity, axis=0) / np.diff(times)[1:, None]
    assert np.max(np.abs(velocity)) <= 0.5 + 1e-8
    assert np.max(np.abs(acceleration)) <= 0.5 / 0.3 + 1e-8
    np.testing.assert_array_equal(positions[-1], positions[-2])


def test_clearance_requires_a_settled_entry_before_any_new_motion(backend):
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    controller, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    assert max(abs(v) for v in backend.get_joint_state().velocities) > 0.02
    start = backend.get_tcp_pose()
    target = MotionTarget(Pose(x=start.x, y=start.y, z=0.16), DOWNWARD)
    path = VerticalClearancePath(
        "task", "retreat", "RETREAT", (start.x, start.y, start.z),
        (start.x, start.y, target.position.z), 0.08,
    )
    before = backend.total_physics_steps
    session = session_type(lambda value: value, vertical_clearance=path)
    with pytest.raises(ValueError, match="settled"):
        controller(backend).move_tcp(target, timeout_s=8, session=session)
    assert backend.total_physics_steps == before
    assert backend.command_records[-1]["type"] == "hold_current_joints"


@pytest.mark.parametrize("handoff_gap_steps", [0, 24])
def test_transport_and_place_keep_tool_attitude_and_continuous_command_limits(
    backend, handoff_gap_steps,
):
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    _, _, session_type = api()
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    assert robot.grasp("object", timeout_ms=1000).success
    start = backend.get_tcp_pose()
    lifted = Pose(x=start.x, y=start.y, z=0.16)
    path = VerticalClearancePath(
        "task", "lift", "LIFT", (start.x, start.y, start.z),
        (lifted.x, lifted.y, lifted.z), 0.08,
    )
    beginning = len(backend.command_records)
    with robot.visual_servo(session_type(lambda value: value, vertical_clearance=path)):
        assert robot.lift(resolved_target=lifted, timeout_ms=10000,
                          tcp_velocity=0.15, acceleration=0.5).success
    kinematics = MuJoCoMotionController(backend)
    angles = []

    def record(_snapshot):
        pose = backend.get_tcp_pose()
        _, angle = kinematics._pose_error(
            np.array([pose.x, pose.y, pose.z]), np.array(DOWNWARD), backend._model.site("tcp").id,
        )
        angles.append(angle)

    for skill, target in ((robot.move_to_region, Pose(x=0.2, y=0.25, z=0.16)),
                          (robot.place, Pose(x=0.2, y=0.25, z=0.045))):
        session = session_type(lambda value: value)
        with backend.observe_physics_steps(record), robot.visual_servo(session):
            action = skill("region", resolved_target=target, timeout_ms=10000,
                           tcp_velocity=0.15, acceleration=0.5)
        assert action.success, action.details
        assert robot.get_state().holding_object_id == "object"
        assert max(angles) <= 5.0
        # Production post-action evidence advances physics with the retained
        # equilibrium target. Also cover an immediate controller handoff.
        if handoff_gap_steps:
            backend.step(handoff_gap_steps)
    commands = [row for row in backend.command_records[beginning:]
                if row["type"] == "joint_target"]
    dt = np.diff([row["sim_time_s"] for row in commands])
    assert (dt > 0).all(), "handoff must not send two targets at one simulation time"
    positions = np.array([row["target_positions_rad"] for row in commands])
    velocity = np.diff(positions, axis=0) / dt[:, None]
    acceleration = np.diff(velocity, axis=0) / dt[1:, None]
    assert np.max(np.abs(velocity)) <= 0.5 + 1e-8
    assert np.max(np.abs(acceleration)) <= 0.5 / 0.3 + 1e-8
