"""Real backend control flow over explicit software physics/counter seams."""

from contextlib import ExitStack
from dataclasses import FrozenInstanceError
from threading import Thread

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from tests.test_visual_raw_recorder_v3 import software_backend


class Rejected(RuntimeError):
    pass


def test_execution_guard_api_required():
    assert callable(getattr(MuJoCoPhysicsBackend, "enforce_execution_guard", None)), (
        "actual execution guard is missing"
    )


@pytest.mark.parametrize("path", ["joint", "gripper", "control", "plain", "legacy", "source"])
def test_precheck_blocks_command_control_and_all_step_paths(path):
    backend = software_backend()
    kinds = {"joint": "COMMAND", "gripper": "COMMAND", "control": "CONTROL"}
    rejected_kind = kinds.get(path, "PHYSICS")
    failure = Rejected("expired")

    def check(event):
        if event.kind == rejected_kind and event.phase == "BEFORE":
            raise failure

    with pytest.raises(Rejected) as caught, ExitStack() as stack:
        if path == "legacy":
            stack.enter_context(backend.observe_physics_steps(lambda _: None))
        if path == "source":
            stack.enter_context(backend.observe_operation_boundaries(lambda _: None))
        stack.enter_context(backend.enforce_execution_guard(check))
        if path == "joint":
            backend.apply_joint_targets(JointCommand([0.2] * 7))
        elif path == "gripper":
            backend.apply_gripper_command(GripperCommand(open=False))
        elif path == "control":
            backend._apply_control()
        else:
            backend.step(3)
    assert caught.value is failure
    assert backend.total_physics_steps == 0
    assert backend.estop_engaged
    assert not backend._pending_joint_targets
    assert not any(row["type"] in {"joint_target", "gripper"} for row in backend.command_records)
    assert any(row["type"] == "emergency_stop" for row in backend.command_records)


@pytest.mark.parametrize(
    "delay,expected_steps", [("begin", 0), ("actuator", 0), ("end", 1), ("legacy", 1)]
)
def test_callback_delays_rechecked_at_effect_and_return(delay, expected_steps):
    backend = software_backend()
    now = [0]

    def check(_event):
        if now[0] >= 10:
            raise Rejected("original deadline")

    def observer(event):
        phase = "BEGIN" if delay == "begin" else "END"
        if delay in {"begin", "end"} and event.kind == "PHYSICS" and event.phase == phase:
            now[0] = 10

    def advance(_):
        now[0] = 10

    with pytest.raises(Rejected), ExitStack() as stack:
        stack.enter_context(backend.observe_operation_boundaries(observer))
        if delay == "actuator":
            stack.enter_context(backend.observe_actuator_steps(advance))
        if delay == "legacy":
            stack.enter_context(backend.observe_physics_steps(advance))
        stack.enter_context(backend.enforce_execution_guard(check))
        backend.step(3)
    assert backend.total_physics_steps == expected_steps
    assert backend.get_sim_time() == expected_steps / 240
    assert backend.estop_engaged


@pytest.mark.parametrize("path", ["plain", "legacy", "source"])
def test_post_expiry_retains_one_effect_and_stops_chunk(path):
    backend = software_backend()
    now = [0]
    original = backend._mujoco.mj_step

    def slow_physics(model, data):
        original(model, data)
        now[0] = 10

    backend._mujoco.mj_step = slow_physics

    def check(_event):
        if now[0] >= 10:
            raise Rejected("late return")

    with pytest.raises(Rejected), ExitStack() as stack:
        if path == "legacy":
            stack.enter_context(backend.observe_physics_steps(lambda _: None))
        if path == "source":
            stack.enter_context(backend.observe_operation_boundaries(lambda _: None))
        stack.enter_context(backend.enforce_execution_guard(check))
        backend.step(3)
    assert backend.total_physics_steps == 1
    assert backend.get_sim_time() == 1 / 240
    assert any(row["physics_step"] == 1 for row in backend.execution_guard_events)
    with pytest.raises(RuntimeError):
        backend.step()
    assert backend.total_physics_steps == 1


@pytest.mark.parametrize("stop_failure", [False, True])
def test_stop_survives_guard_and_observer_failures(stop_failure):
    backend = software_backend()
    backend._pending_joint_targets.append((5, backend._target_positions.copy()))

    class BadMessage(Rejected):
        def __str__(self):
            raise ValueError("unprintable")

    failure = BadMessage()

    def reject(_event):
        raise failure

    def bad_observer(_event):
        raise ValueError("passive sink failed")

    if stop_failure:

        def bad_control():
            raise ValueError("stop control failed")

        backend._apply_control = bad_control
    with pytest.raises(BadMessage) as caught:
        with backend.observe_operation_boundaries(bad_observer):
            with backend.enforce_execution_guard(reject):
                backend.apply_joint_targets(JointCommand([0.2] * 7))
    assert caught.value is failure
    assert backend.estop_engaged
    assert not backend._pending_joint_targets
    assert backend.operation_observer_failures
    if stop_failure:
        assert any(
            row.get("stop_error_type") == "ValueError" for row in backend.execution_guard_events
        )


@pytest.mark.parametrize("mutation", ["step", "stop", "hold", "reset", "initialize", "shutdown"])
def test_guard_reentry_duplicate_and_closed_session_reject(mutation):
    backend = software_backend()
    actions = {
        "step": lambda: backend.step(),
        "stop": backend.emergency_stop,
        "hold": backend.hold_current_joints,
        "reset": lambda: backend.reset(
            PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0)
        ),
        "initialize": lambda: backend.initialize(SimulatorConfig()),
        "shutdown": backend.shutdown,
    }

    def reenter(_event):
        actions[mutation]()

    with pytest.raises(RuntimeError, match="guard callback"):
        with backend.enforce_execution_guard(reenter):
            backend.step()
    assert backend.total_physics_steps == 0
    assert backend.estop_engaged
    assert_closed(backend)


def assert_closed(backend):
    for action in (
        lambda: backend.step(),
        lambda: backend.apply_joint_targets(JointCommand([0.0] * 7)),
        lambda: backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0)),
        lambda: backend.initialize(SimulatorConfig()),
    ):
        with pytest.raises(RuntimeError):
            action()
    with pytest.raises(RuntimeError):
        with backend.enforce_execution_guard(lambda _: None):
            pass
    backend.emergency_stop()
    backend.shutdown()


def test_normal_exit_duplicate_and_cross_thread_do_not_rearm():
    backend = software_backend()
    with backend.enforce_execution_guard(lambda _: None):
        with pytest.raises(RuntimeError):
            with backend.enforce_execution_guard(lambda _: None):
                pass
        backend.step()
    assert backend.total_physics_steps == 1
    assert_closed(backend)

    backend = software_backend()
    errors = []

    def foreign():
        try:
            backend.step()
        except RuntimeError as error:
            errors.append(error)

    with backend.enforce_execution_guard(lambda _: None):
        thread = Thread(target=foreign)
        thread.start()
        thread.join()
    assert len(errors) == 1
    assert backend.total_physics_steps == 0


def test_effect_exception_and_guard_ledger_are_retained():
    backend = software_backend()
    with pytest.raises(ValueError, match="exactly 7"):
        with backend.enforce_execution_guard(lambda _: None):
            backend.apply_joint_targets(JointCommand([0.0]))
    assert backend.estop_engaged
    rows = backend.execution_guard_events
    assert any(row.get("error_type") == "ValueError" for row in rows)
    with pytest.raises(TypeError):
        rows[0]["physics_step"] = 999
    assert_closed(backend)


def test_guard_ledger_overflow_stops_instead_of_dropping_checks():
    backend = software_backend()
    with pytest.raises(RuntimeError, match="limit"):
        with backend.enforce_execution_guard(lambda _: None):
            for _ in range(400):
                backend.apply_joint_targets(JointCommand([0.0] * 7))
    assert len(backend.execution_guard_events) <= 1024
    assert backend.estop_engaged


@pytest.mark.parametrize("path", ["plain", "legacy", "source"])
def test_no_guard_preserves_operation_order_and_state(path):
    backend = software_backend()
    operations, physics = [], []
    with ExitStack() as stack:
        if path == "source":
            stack.enter_context(backend.observe_operation_boundaries(operations.append))
        if path == "legacy":
            stack.enter_context(backend.observe_physics_steps(physics.append))
        backend.apply_joint_targets(JointCommand([0.1] * 7))
        result = backend.step(2)
    assert result.physics_steps == backend.total_physics_steps == 2
    assert not backend.estop_engaged
    if path == "source":
        assert [(x.kind, x.phase) for x in operations] == [
            (kind, phase)
            for kind in ("COMMAND", "CONTROL", "PHYSICS", "CONTROL", "PHYSICS")
            for phase in ("BEGIN", "END")
        ]
        assert set(operations[1].result) == {"physics_state", "command_records"}
    if path == "legacy":
        assert [x.physics_step for x in physics] == [1, 2]


def test_guard_boundary_is_frozen():
    backend = software_backend()
    seen = []
    with backend.enforce_execution_guard(seen.append):
        backend.step()
    with pytest.raises(FrozenInstanceError):
        seen[0].physics_step = 999
