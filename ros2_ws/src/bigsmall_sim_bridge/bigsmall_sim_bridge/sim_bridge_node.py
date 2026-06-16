from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import rclpy  # type: ignore[import-not-found]
from bigsmall_interfaces.msg import (  # type: ignore[import-not-found]
    FaultEvent,
    SafetyEvent,
    SimulationStatus,
)
from bigsmall_interfaces.srv import (  # type: ignore[import-not-found]
    EmergencyStop,
    InjectFault,
    LoadScenario,
    ResetWorld,
    Stop,
)
from rclpy.node import Node  # type: ignore[import-not-found]
from rclpy.qos import (  # type: ignore[import-not-found]
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rosgraph_msgs.msg import Clock  # type: ignore[import-not-found]


def command_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
    )


def telemetry_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=20,
    )


@dataclass
class BridgeState:
    simulation_time_s: float = 0.0
    physics_steps: int = 0
    sensor_frames: int = 0
    emergency_stopped: bool = False
    last_command_seq: dict[str, int] = field(default_factory=dict)
    rejected_duplicate_count: int = 0


class BigsmallSimBridgeNode(Node):
    """ROS 2 boundary node for Phase 9.1 simulation status and control services.

    This node is intended to run in a sourced ROS 2 Jazzy workspace. It does not
    import the BIG-small core Python environment and it does not bypass the core
    SafetyShield; command identity is preserved through CommandHeader.
    """

    def __init__(self) -> None:
        super().__init__("bigsmall_sim_bridge")
        self._state = BridgeState()
        self._clock_pub = self.create_publisher(Clock, "/clock", telemetry_qos())
        self._status_pub = self.create_publisher(
            SimulationStatus, "/bigsmall/simulation/status", telemetry_qos()
        )
        self._safety_pub = self.create_publisher(
            SafetyEvent, "/bigsmall/safety_event", command_qos()
        )
        self._fault_pub = self.create_publisher(FaultEvent, "/bigsmall/fault_event", command_qos())
        self.create_service(EmergencyStop, "/bigsmall/emergency_stop", self._emergency_stop)
        self.create_service(Stop, "/bigsmall/stop", self._stop)
        self.create_service(ResetWorld, "/bigsmall/reset_world", self._reset_world)
        self.create_service(LoadScenario, "/bigsmall/load_scenario", self._load_scenario)
        self.create_service(InjectFault, "/bigsmall/inject_fault", self._inject_fault)
        self.create_timer(0.02, self._publish_status)

    def _accept_once(self, task_id: str, command_seq: int) -> bool:
        last = self._state.last_command_seq.get(task_id, -1)
        if command_seq <= last:
            self._state.rejected_duplicate_count += 1
            return False
        self._state.last_command_seq[task_id] = command_seq
        return True

    def _emergency_stop(
        self,
        request: EmergencyStop.Request,
        response: EmergencyStop.Response,
    ) -> EmergencyStop.Response:
        accepted = self._accept_once(request.header.task_id, request.header.command_seq)
        self._state.emergency_stopped = True
        response.accepted = accepted
        response.status = "EMERGENCY_STOPPED" if accepted else "DUPLICATE_REJECTED"
        response.response_latency_ms = 0.0
        self._publish_safety_event(request.header, "EMERGENCY_STOP", response.status, True)
        return response

    def _stop(self, request: Stop.Request, response: Stop.Response) -> Stop.Response:
        accepted = self._accept_once(request.header.task_id, request.header.command_seq)
        response.accepted = accepted
        response.status = "STOPPED" if accepted else "DUPLICATE_REJECTED"
        response.stopped_sim_time_s = self._state.simulation_time_s
        self._publish_safety_event(request.header, "STOP", response.status, False)
        return response

    def _reset_world(
        self,
        request: ResetWorld.Request,
        response: ResetWorld.Response,
    ) -> ResetWorld.Response:
        accepted = self._accept_once(request.header.task_id, request.header.command_seq)
        if accepted:
            self._state = BridgeState()
        response.accepted = accepted
        response.status = "RESET" if accepted else "DUPLICATE_REJECTED"
        response.reset_sim_time_s = self._state.simulation_time_s
        return response

    def _load_scenario(
        self,
        request: LoadScenario.Request,
        response: LoadScenario.Response,
    ) -> LoadScenario.Response:
        accepted = self._accept_once(request.header.task_id, request.header.command_seq)
        response.accepted = accepted
        response.status = "SCENARIO_LOADED" if accepted else "DUPLICATE_REJECTED"
        response.loaded_sim_time_s = self._state.simulation_time_s
        return response

    def _inject_fault(
        self,
        request: InjectFault.Request,
        response: InjectFault.Response,
    ) -> InjectFault.Response:
        accepted = self._accept_once(request.header.task_id, request.header.command_seq)
        response.accepted = accepted
        response.status = "FAULT_INJECTED" if accepted else "DUPLICATE_REJECTED"
        response.injected_sim_time_s = self._state.simulation_time_s
        if accepted:
            event = FaultEvent()
            event.stamp = request.header.stamp
            event.fault_type = request.fault_type
            event.source = "ros2_bridge"
            event.severity = "injected"
            event.details_json = request.parameters_json
            event.command_seq = request.header.command_seq
            event.plan_version = request.header.plan_version
            self._fault_pub.publish(event)
        return response

    def _publish_safety_event(
        self,
        header: Any,
        decision: str,
        reason: str,
        emergency_stop: bool,
    ) -> None:
        event = SafetyEvent()
        event.stamp = header.stamp
        event.decision = decision
        event.reason = reason
        event.rule_id = "phase9_1_ros2_bridge"
        event.command_seq = header.command_seq
        event.plan_version = header.plan_version
        event.emergency_stop = emergency_stop
        self._safety_pub.publish(event)

    def _publish_status(self) -> None:
        self._state.simulation_time_s += 0.02
        self._state.physics_steps += 1
        clock = Clock()
        clock.clock.sec = int(self._state.simulation_time_s)
        clock.clock.nanosec = int((self._state.simulation_time_s % 1.0) * 1_000_000_000)
        self._clock_pub.publish(clock)

        status = SimulationStatus()
        status.stamp = clock.clock
        status.backend = "isaac_or_mujoco_bridge"
        status.status = "EMERGENCY_STOPPED" if self._state.emergency_stopped else "RUNNING"
        status.simulation_time_s = self._state.simulation_time_s
        status.ros_time_s = self._state.simulation_time_s
        status.wall_time_s = self.get_clock().now().nanoseconds / 1_000_000_000.0
        status.physics_steps = self._state.physics_steps
        status.sensor_frames = self._state.sensor_frames
        status.details_json = json.dumps(
            {"rejected_duplicate_count": self._state.rejected_duplicate_count},
            sort_keys=True,
        )
        self._status_pub.publish(status)


def main() -> None:
    rclpy.init()
    node = BigsmallSimBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
