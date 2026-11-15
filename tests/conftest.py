"""测试结束时回收本项启动的真实后台调度线程，避免污染后续全局资源观察器。"""

import threading

import pytest

from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher


@pytest.fixture(autouse=True)
def _stop_test_owned_simulation_dispatchers(monkeypatch):
    """保留原启动行为和所有断言，只在测试边界停止本项实际启动的线程。"""
    original_start = SimulationJobDispatcher.start
    original_stop = SimulationJobDispatcher.stop
    owned = {}

    def start(dispatcher):
        previous = dispatcher._thread
        already_running = previous is not None and previous.is_alive()
        try:
            return original_start(dispatcher)
        finally:
            thread = dispatcher._thread
            if (
                not already_running
                and isinstance(thread, threading.Thread)
                and thread.ident is not None
            ):
                owned[(id(dispatcher), id(thread))] = (dispatcher, thread)

    monkeypatch.setattr(SimulationJobDispatcher, "start", start)
    yield
    errors = []
    for dispatcher, thread in reversed(list(owned.values())):
        try:
            original_stop(dispatcher)
        except Exception as error:
            errors.append(f"{thread.name}: {type(error).__name__}: {error}")
        if thread.is_alive():
            errors.append(f"{thread.name}: test-owned simulation dispatcher did not stop")
    assert not errors, "; ".join(errors)
