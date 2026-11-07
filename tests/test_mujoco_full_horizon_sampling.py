"""Real backend sampling boundaries over the software engine, never MuJoCo init."""

from contextlib import ExitStack
from threading import Thread

import numpy as np
import pytest

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from tests.test_visual_raw_recorder_v3 import software_backend, software_sensor_camera


def test_backend_full_horizon_sampling_api_required():
    assert callable(getattr(MuJoCoPhysicsBackend, "capture_each_physics_step", None)), (
        "owner-bound per-step sampling missing"
    )


def sampled_backend():
    backend = software_backend()
    software_sensor_camera(backend)
    return backend


def test_chunk_captures_each_effect_before_next_control_without_mutation():
    backend = sampled_backend()
    events, legacy = [], []
    qpos = backend._data.qpos.copy()
    target = backend._target_positions.copy()
    with ExitStack() as stack:
        stack.enter_context(backend.observe_operation_boundaries(events.append))
        stack.enter_context(backend.observe_physics_steps(lambda p: legacy.append(p.physics_step)))
        stack.enter_context(backend.enforce_execution_guard(lambda _: None))
        stack.enter_context(backend.capture_each_physics_step(max_captures=3))
        backend.step(3)
        assert backend.total_physics_steps == 3
        assert np.array_equal(backend._data.qpos, qpos)
        assert np.array_equal(backend._target_positions, target)
        assert backend._data.ctrl.tolist() == [0.0] * 7 + [0.039] * 2
    rows = [(e.kind, e.phase, e.physics_step) for e in events]
    for step in range(1, 4):
        physics = rows.index(("PHYSICS", "END", step))
        capture = rows.index(("CAPTURE", "BEGIN", step))
        assert physics < capture
        if step < 3:
            assert capture < rows.index(("CONTROL", "BEGIN", step))
    assert [e.physics_step for e in events if e.kind == "CAPTURE" and e.phase == "END"] == [1, 2, 3]
    assert legacy == [1, 2, 3]


@pytest.mark.parametrize("limit", [True, 0, 1023, 500001, 1024.0])
def test_invalid_event_capacity_does_not_consume_session(limit):
    backend = sampled_backend()
    with pytest.raises(ValueError):
        with backend.enforce_execution_guard(lambda _: None, event_limit=limit):
            pass
    assert not backend._execution_guard_used


def test_larger_event_capacity_and_overflow_remain_bounded_and_closed():
    backend = sampled_backend()
    with pytest.raises(RuntimeError, match="event limit"):
        with backend.enforce_execution_guard(lambda _: None, event_limit=1030):
            for _ in range(1030):
                backend._check_execution_guard("TEST", "BEFORE")
    assert len(backend.execution_guard_events) == 1030
    assert backend.execution_guard_events[-1]["kind"] == "FAILURE"
    assert backend.estop_engaged


@pytest.mark.parametrize("limit", [False, 0, 32769, 1.0])
def test_sampler_strict_capacity(limit):
    backend = sampled_backend()
    with backend.observe_operation_boundaries(lambda _: None):
        with backend.enforce_execution_guard(lambda _: None):
            with pytest.raises(ValueError):
                with backend.capture_each_physics_step(max_captures=limit):
                    pass


def test_sampler_needs_guard_observer_and_cannot_reopen_or_cross_thread():
    backend = sampled_backend()
    with pytest.raises(RuntimeError):
        with backend.capture_each_physics_step(max_captures=1):
            pass
    errors = []

    def foreign():
        try:
            with backend.capture_each_physics_step(max_captures=1):
                pass
        except RuntimeError as error:
            errors.append(error)

    with backend.enforce_execution_guard(lambda _: None):
        with pytest.raises(RuntimeError):
            with backend.capture_each_physics_step(max_captures=1):
                pass
        with backend.observe_operation_boundaries(lambda _: None):
            thread = Thread(target=foreign)
            thread.start()
            thread.join()
            with backend.capture_each_physics_step(max_captures=1):
                with pytest.raises(RuntimeError):
                    with backend.capture_each_physics_step(max_captures=1):
                        pass
            with pytest.raises(RuntimeError):
                with backend.capture_each_physics_step(max_captures=1):
                    pass
    assert len(errors) == 1
    with pytest.raises(RuntimeError):
        with backend.capture_each_physics_step(max_captures=1):
            pass


@pytest.mark.parametrize("failure", ["render", "observer", "deadline", "capacity"])
def test_sampling_failure_retains_effect_stops_chunk_and_preserves_cause(failure):
    backend = sampled_backend()
    rejected = RuntimeError(failure)
    late = [False]

    def observer(event):
        if event.kind == "CAPTURE" and event.phase == "END":
            if failure == "observer":
                backend.step()
            if failure == "deadline":
                late[0] = True

    def check(_):
        if late[0]:
            raise rejected

    if failure == "render":

        def bad_render(*args, **kwargs):
            raise rejected

        backend._camera.capture_with_instances = bad_render
    with pytest.raises(RuntimeError) as caught:
        with backend.observe_operation_boundaries(observer):
            with backend.enforce_execution_guard(check):
                with backend.capture_each_physics_step(max_captures=1):
                    backend.step(3)
    assert backend.total_physics_steps == 1
    assert backend.estop_engaged
    if failure in {"render", "deadline"}:
        assert caught.value is rejected
    assert backend.execution_guard_events[-1]["kind"] == "FAILURE"
