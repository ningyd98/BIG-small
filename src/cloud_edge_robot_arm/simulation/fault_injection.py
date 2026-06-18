"""故障注入模型，用于可复现实验中触发网络、感知和安全事件。"""

from __future__ import annotations

from cloud_edge_robot_arm.experiments.models import FaultEvent, FaultType
from cloud_edge_robot_arm.simulation.network import NetworkSimulator
from cloud_edge_robot_arm.simulation.world import SimulatedWorld


class FaultInjector:
    def __init__(self, *, world: SimulatedWorld, network: NetworkSimulator) -> None:
        self._world = world
        self._network = network

    def apply(self, fault: FaultEvent) -> None:
        if fault.fault_type == FaultType.TARGET_MOVED:
            self._world.move_target()
        elif fault.fault_type == FaultType.OBSTACLE_INSERTED:
            self._world.insert_obstacle()
        elif fault.fault_type == FaultType.TARGET_LOST:
            self._world.lose_target()
        elif fault.fault_type == FaultType.PERCEPTION_DEGRADED:
            self._world.degrade_perception()
        elif fault.fault_type == FaultType.NETWORK_OUTAGE:
            self._network.disconnect(duration_ms=fault.duration_ms or 1_000)
        elif fault.fault_type == FaultType.CLOUD_UNAVAILABLE:
            self._world.set_cloud_available(False)
        elif fault.fault_type == FaultType.EMERGENCY_STOP:
            self._world.trigger_emergency_stop()
        elif fault.fault_type == FaultType.NETWORK_DEGRADED:
            return None
        elif fault.fault_type in {
            FaultType.GRASP_FAILURE,
            FaultType.STALE_DUPLICATE_REORDERED_COMMAND,
            FaultType.SKILL_CACHE_HIT,
            FaultType.SKILL_CACHE_QUARANTINE,
            FaultType.MODE_OSCILLATION_PRESSURE,
            FaultType.SQLITE_RESTART,
        }:
            return None
