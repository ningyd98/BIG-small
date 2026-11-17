"""Continuous feedback acts inside real MuJoCo motion, with bounded commands."""

from contextlib import nullcontext
from math import sqrt

import numpy as np
import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import (
    MotionGuardViolation,
    MuJoCoSkillRobot,
)

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


@pytest.fixture
def lift_hold_case(backend):
    robot = MuJoCoSkillRobot(backend)
    assert robot.approach("object", resolved_target=Pose(x=0.45, y=0, z=0.045)).success
    assert robot.grasp("object", timeout_ms=1000).success
    start = backend.get_tcp_pose()
    target = Pose(x=start.x, y=start.y, z=0.16)
    path = VerticalClearancePath(
        "task", "lift", "LIFT", (start.x, start.y, start.z), (target.x, target.y, target.z), 0.08,
    )
    options = {"resolved_target": target, "timeout_ms": 10000,
               "tcp_velocity": 0.15, "acceleration": 0.5}
    return robot, path, options


def _assert_lift_hold_stopped(backend, fault_step, *, estop):
    assert fault_step is not None and backend.total_physics_steps == fault_step
    at_fault = [row for row in backend.command_records if row["physics_step"] >= fault_step]
    assert at_fault and all(row["accepted"] for row in at_fault)
    assert {row["type"] for row in at_fault} == (
        {"hold_current_joints", "emergency_stop"} if estop else {"hold_current_joints"}
    )
    assert backend.estop_engaged is estop
    assert not backend._pending_joint_targets
    np.testing.assert_array_equal(backend._target_positions, backend.get_joint_state().positions)


def _assert_lift_hold_failure(action, error, steps, session, code="LIFT_HOLD_FAILED"):
    assert not action.success and action.action_type == "LIFT" and action.error_code == code
    assert action.error is not None
    for details in (action.details, action.error.details):
        assert details["failure_phase"] == "LIFT_HOLD"
        assert details["reason"] == str(error)
        assert details["exception_type"] == type(error).__name__
        assert details["physics_steps"] == steps
    if session is not None:
        assert session.terminal_reason == f"{type(error).__name__}:{error}"
        assert action.details["visual_servo"]["terminal_reason"] == session.terminal_reason
        assert action.details["visual_servo"]["feedback_count"] == len(session.records)


@pytest.mark.parametrize("visual", [True, False], ids=["visual", "without-visual-session"])
def test_lift_hold_step_exception_stops_and_returns_failure(backend, lift_hold_case, monkeypatch,
                                                            visual):
    robot, path, options = lift_hold_case
    _, _, session_type = api()
    session = session_type(lambda value: value, vertical_clearance=path) if visual else None
    start = backend.total_physics_steps
    fault_step = None
    motion_end = None
    error = RuntimeError("physics observer failed during lift hold")
    move = robot._move

    def measure_move(*args, **kwargs):
        nonlocal motion_end
        result = move(*args, **kwargs)
        assert result.success, result.error_code
        motion_end = backend.total_physics_steps
        return result

    def fail_in_hold(snapshot):
        nonlocal fault_step
        if motion_end is not None:
            fault_step = snapshot.physics_step
            raise error

    monkeypatch.setattr(robot, "_move", measure_move)
    with backend.observe_physics_steps(fail_in_hold), (
        robot.visual_servo(session) if session is not None else nullcontext()
    ):
        action = robot.lift(**options)
    assert motion_end is not None and fault_step == motion_end + 1
    _assert_lift_hold_stopped(backend, fault_step, estop=True)
    _assert_lift_hold_failure(action, error, fault_step - start, session)
    assert robot._visual_servo_session is None


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_lift_hold_feedback_exception_preserves_reason(backend, lift_hold_case, error_type):
    robot, path, options = lift_hold_case
    _, _, session_type = api()
    start = backend.total_physics_steps
    fault_step = None
    error = error_type("first hold sample lost its observation")

    def sample(target):
        nonlocal fault_step
        if session.terminal_reason == "SUCCEEDED":
            fault_step = backend.total_physics_steps
            raise error
        return target

    session = session_type(sample, vertical_clearance=path)
    with robot.visual_servo(session):
        action = robot.lift(**options)
    assert fault_step is not None
    _assert_lift_hold_stopped(backend, fault_step, estop=True)
    _assert_lift_hold_failure(action, error, fault_step - start, session)


class _CancelLift(BaseException):
    pass


@pytest.mark.parametrize("fault_source", ["step", "sample"])
def test_lift_hold_base_exception_stops_and_propagates(backend, lift_hold_case, fault_source):
    robot, path, options = lift_hold_case
    _, _, session_type = api()
    fault_step = None
    original = _CancelLift("caller cancelled lift")

    def fail_in_hold(source, step):
        nonlocal fault_step
        if source == fault_source and session.terminal_reason == "SUCCEEDED":
            fault_step = step
            raise original

    def sample(target):
        fail_in_hold("sample", backend.total_physics_steps)
        return target

    session = session_type(sample, vertical_clearance=path)
    with (
        backend.observe_physics_steps(lambda event: fail_in_hold("step", event.physics_step)),
        robot.visual_servo(session),
        pytest.raises(_CancelLift) as caught,
    ):
        robot.lift(**options)
    assert caught.value is original
    _assert_lift_hold_stopped(backend, fault_step, estop=True)
    assert session.terminal_reason == "_CancelLift:caller cancelled lift"
    assert robot._visual_servo_session is None


@pytest.mark.parametrize("code", ["GRASP_LOST", "CLEARANCE_PATH_VIOLATION"])
def test_lift_hold_guard_failure_keeps_domain_code(backend, lift_hold_case, code):
    robot, path, options = lift_hold_case
    _, _, session_type = api()
    session = session_type(lambda value: value, vertical_clearance=path)
    start = backend.total_physics_steps
    fault_step = None
    error = MotionGuardViolation(code, "hold guard rejected measured state")

    def fail_in_hold(snapshot):
        nonlocal fault_step
        if session.terminal_reason == "SUCCEEDED":
            fault_step = snapshot.physics_step
            raise error

    with backend.observe_physics_steps(fail_in_hold), robot.visual_servo(session):
        action = robot.lift(**options)
    assert fault_step is not None
    _assert_lift_hold_stopped(backend, fault_step, estop=False)
    _assert_lift_hold_failure(action, error, fault_step - start, session, code)


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
