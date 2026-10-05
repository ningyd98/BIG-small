"""B0 independently ticks and merges pending frames without concurrent model calls."""

import threading
import time

from cloud_edge_robot_arm.research.supervision import PeriodicSupervision
from cloud_edge_robot_arm.vision.request_control import bounded_model_call


def test_supervision_ticks_during_atomic_action_without_skill_boundaries():
    received = []
    serial = iter(range(100))
    with PeriodicSupervision(
        .01, lambda frame: received.append(frame), lambda: next(serial)
    ) as run:
        deadline = time.monotonic() + .06
        while time.monotonic() < deadline:
            run.poll(atomic_action_active=True)
            time.sleep(.002)
        assert run.snapshot()["ticks"] >= 3
        assert len(received) >= 2


def test_one_inflight_and_latest_pending_observation():
    entered, release = threading.Event(), threading.Event()
    frames = []
    counter = iter(range(100))

    def infer(frame):
        frames.append(frame)
        entered.set()
        release.wait(1)
        return frame

    with PeriodicSupervision(.01, infer, lambda: next(counter)) as run:
        time.sleep(.015)
        run.poll(atomic_action_active=True)
        assert entered.wait(.5)
        for _ in range(5):
            time.sleep(.012)
            run.poll(atomic_action_active=True)
        assert len(frames) == 1
        assert run.snapshot()["merged_pending"] >= 3
        release.set()
        time.sleep(.005)
        run.poll(atomic_action_active=False)
        time.sleep(.005)
        assert len(frames) == 2
        assert frames[-1] >= 4  # obsolete pending observations were never sent


def test_result_application_defers_during_atomic_action():
    with PeriodicSupervision(.01, lambda frame: "STOP", lambda: "fresh") as run:
        time.sleep(.015)
        run.poll(atomic_action_active=True)
        time.sleep(.005)
        assert run.poll(atomic_action_active=True) == []
        results = run.poll(atomic_action_active=False)
        assert results and all(result == "STOP" for result in results)


def test_execution_policy_rejects_nonfinite_supervision_period():
    import pytest

    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy

    with pytest.raises(ValueError):
        ExecutionPolicy(instruction="pick", model_snapshot_hash="a" * 64,
                        supervision_period_s=float("nan"))


def test_wall_wait_callback_keeps_main_thread_responsive():
    main_thread = threading.get_ident()
    calls = []
    result = bounded_model_call(lambda: time.sleep(.06) or "response", timeout_s=.5,
                                on_wait=lambda: calls.append(threading.get_ident()))
    assert result == "response"
    assert len(calls) >= 2
    assert set(calls) == {main_thread}
