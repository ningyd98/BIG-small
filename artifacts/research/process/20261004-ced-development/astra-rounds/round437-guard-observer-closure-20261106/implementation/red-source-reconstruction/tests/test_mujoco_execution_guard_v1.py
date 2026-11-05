"""Real backend control flow over explicit software physics/counter seams."""

from contextlib import ExitStack
from dataclasses import FrozenInstanceError
from threading import Event, Thread

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


def test_operation_observer_failure_closes_guard_without_guard_rejection():
    for guarded in (True, False):
        for kind in ("COMMAND", "CONTROL", "PHYSICS"):
            for phase in ("BEGIN", "END"):
                backend = software_backend()
                failure = ValueError(f"{kind} {phase} recorder failed")
                raised, before_stop = [], []
                if kind == "CONTROL":
                    backend._pending_joint_targets.append((0, backend._target_positions + 0.2))

                def observe(event):
                    command = event.parameters.get("command_type")
                    if command == "hold_current_joints" and event.phase == "BEGIN":
                        before_stop.append(
                            {
                                "targets": backend._target_positions.copy(),
                                "ctrl": backend._data.ctrl.copy(),
                                "pending": len(backend._pending_joint_targets),
                                "commands": backend.command_records,
                                "steps": backend.total_physics_steps,
                                "time": backend.get_sim_time(),
                            }
                        )
                    if (
                        event.kind == kind
                        and event.phase == phase
                        and (kind != "COMMAND" or command == "joint_target")
                        and not raised
                    ):
                        raised.append(failure)
                        raise failure

                caught = None
                try:
                    with ExitStack() as stack:
                        stack.enter_context(backend.observe_operation_boundaries(observe))
                        if guarded:
                            stack.enter_context(backend.enforce_execution_guard(lambda _: None))
                        if kind == "COMMAND":
                            backend.apply_joint_targets(JointCommand([0.2] * 7))
                        elif kind == "CONTROL":
                            backend._apply_control()
                        else:
                            backend.step()
                except BaseException as error:
                    caught = error
                assert raised == [failure]
                assert backend.operation_observer_failures
                if not guarded:
                    assert caught is None
                    assert not backend.estop_engaged
                    if kind == "COMMAND":
                        assert list(backend._target_positions) == [0.2] * 7
                    elif kind == "CONTROL":
                        assert not backend._pending_joint_targets
                        assert list(backend._data.ctrl[:7]) == [0.1] * 7
                    else:
                        assert backend.total_physics_steps == 1
                    continue
                assert caught is failure, (kind, phase, caught)
                assert backend._execution_guard_closed and backend.estop_engaged
                effect = int(phase == "END")
                observed = before_stop[0]
                if kind == "COMMAND":
                    accepted = [
                        row
                        for row in observed["commands"]
                        if row["type"] == "joint_target" and row["accepted"]
                    ]
                    assert len(accepted) == effect
                    assert list(observed["targets"]) == [0.2 * effect] * 7
                elif kind == "CONTROL":
                    assert observed["pending"] == 1 - effect
                    assert list(observed["ctrl"][:7]) == [0.1 * effect] * 7
                    assert list(observed["targets"]) == [0.2 * effect] * 7
                else:
                    assert observed["steps"] == effect
                    assert observed["time"] == effect / 240
                steps = backend.total_physics_steps
                with pytest.raises(RuntimeError, match="closed"):
                    backend.step()
                assert backend.total_physics_steps == steps

    # A source snapshot failure, without any failing callback, also closes execution.
    backend = software_backend()
    failure = ValueError("source snapshot failed")
    original_result = backend._operation_result

    def bad_result(kind, returned, command_start):
        if kind == "COMMAND" and backend.command_records[-1]["type"] == "joint_target":
            raise failure
        return original_result(kind, returned, command_start)

    backend._operation_result = bad_result
    with pytest.raises(ValueError) as caught:
        with backend.observe_operation_boundaries(lambda _: None):
            with backend.enforce_execution_guard(lambda _: None):
                backend.apply_joint_targets(JointCommand([0.2] * 7))
    assert caught.value is failure
    assert backend.estop_engaged and backend._execution_guard_closed
    assert backend.total_physics_steps == 0

    # A later failing STOP observer is secondary to the original guard rejection.
    backend = software_backend()
    primary = Rejected("original guard failure")

    class BadStopMessage(ValueError):
        def __str__(self):
            raise RuntimeError("unprintable secondary")

    def reject(_):
        raise primary

    def failed_stop(event):
        if backend._execution_guard_closed:
            raise BadStopMessage()

    with pytest.raises(Rejected) as caught:
        with backend.observe_operation_boundaries(failed_stop):
            with backend.enforce_execution_guard(reject):
                backend.apply_joint_targets(JointCommand([0.2] * 7))
    assert caught.value is primary
    assert backend.estop_engaged
    assert any(row["type"] == "emergency_stop" for row in backend.command_records)
    assert backend.operation_observer_failures
    assert all(
        row["observer_error"] == "exception message unavailable"
        for row in backend.operation_observer_failures
    )
    assert not any(row.get("stop_error_type") for row in backend.execution_guard_events)


def test_stop_bypass_rejects_foreign_command_and_physics():
    backend = software_backend()
    at_hold, release = Event(), Event()
    failures, outcomes = [], []
    primary = Rejected("owner deadline expired")
    original_hold = backend.hold_current_joints

    def paused_hold():
        original_hold()
        at_hold.set()
        if not release.wait(5):
            raise TimeoutError("foreign command probe did not finish")

    backend.hold_current_joints = paused_hold

    def foreign():
        try:
            if not at_hold.wait(5):
                failures.append("stop did not reach hold barrier")
                return
            for name, action in (
                ("gripper", lambda: backend.apply_gripper_command(GripperCommand(open=False))),
                ("step", backend.step),
            ):
                error = None
                try:
                    action()
                except BaseException as caught:
                    error = caught
                outcomes.append((name, error))
        except BaseException as error:
            failures.append(error)
        finally:
            release.set()

    def reject(_):
        raise primary

    worker = Thread(target=foreign)
    caught = None
    worker.start()
    try:
        try:
            with backend.enforce_execution_guard(reject):
                backend.apply_joint_targets(JointCommand([0.2] * 7))
        except BaseException as error:
            caught = error
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert not failures
    assert caught is primary
    assert [name for name, _ in outcomes] == ["gripper", "step"]
    assert all(isinstance(error, RuntimeError) for _, error in outcomes), outcomes
    assert list(backend._data.ctrl[7:9]) == [0.039, 0.039]
    assert not any(row["type"] == "gripper" and row["accepted"] for row in backend.command_records)
    assert backend.total_physics_steps == 0
    assert backend.estop_engaged
    assert not any(row.get("stop_error_type") for row in backend.execution_guard_events)
