"""运行时 scheduler 包装。

当前 scheduler 只封装 dispatcher start/stop，保留独立类型是为了后续接入
更复杂的定时恢复或多进程 worker 时不改变 API 层依赖。
"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher


class SimulationRuntimeScheduler:
    def __init__(self, dispatcher: SimulationJobDispatcher) -> None:
        self.dispatcher = dispatcher

    def start(self) -> None:
        self.dispatcher.start()

    def stop(self) -> None:
        self.dispatcher.stop()
