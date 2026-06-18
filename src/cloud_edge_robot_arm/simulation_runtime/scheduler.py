from __future__ import annotations

from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher


class SimulationRuntimeScheduler:
    def __init__(self, dispatcher: SimulationJobDispatcher) -> None:
        self.dispatcher = dispatcher

    def start(self) -> None:
        self.dispatcher.start()

    def stop(self) -> None:
        self.dispatcher.stop()
