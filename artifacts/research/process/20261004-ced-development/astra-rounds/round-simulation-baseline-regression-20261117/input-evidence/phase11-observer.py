import sys
import time
import traceback
import pytest
from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher

class Observer:
    def pytest_configure(self):
        original = SimulationJobDispatcher.stop
        def observe(dispatcher):
            start = time.monotonic()
            thread = dispatcher._thread
            print("PRE_STOP_WORKERS", [(w.backend, w.active_job_id) for w in dispatcher._workers])
            original(dispatcher)
            print("POST_STOP_SECONDS", time.monotonic()-start, "ALIVE", thread.is_alive(), "ACTIVE_WORKERS", [(w.backend, w.active_job_id) for w in dispatcher._workers])
            if thread.is_alive():
                traceback.print_stack(sys._current_frames()[thread.ident])
        SimulationJobDispatcher.stop = observe

raise SystemExit(pytest.main(sys.argv[1:], plugins=[Observer()]))
