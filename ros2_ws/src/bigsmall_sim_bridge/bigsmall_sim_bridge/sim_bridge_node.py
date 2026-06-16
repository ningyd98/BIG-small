from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import rclpy  # type: ignore[import-not-found]
from bigsmall_interfaces.action import (  # type: ignore[import-not-found]
    FollowJointTrajectory,
    MoveToPose,
)
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
from rclpy.action import (  # type: ignore[import-not-found]
    ActionServer,
    CancelResponse,
    GoalResponse,
)
from rclpy.callback_groups import ReentrantCallbackGroup  # type: ignore[import-not-found]
from rclpy.executors import (  # type: ignore[import-not-found]
    ExternalShutdownException,
    MultiThreadedExecutor,
)
from rclpy.node import Node  # type: ignore[import-not-found]
from rclpy.qos import (  # type: ignore[import-not-found]
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rosgraph_msgs.msg import Clock  # type: ignore[import-not-found]

from bigsmall_sim_bridge.safety_limits import trajectory_joint_limit_violation


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
    bridge_session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_restart_generation: int = 0
    simulation_time_s: float = 0.0
    physics_steps: int = 0
    sensor_frames: int = 0
    emergency_stopped: bool = False
    shutdown_requested: bool = False
    motion_active: bool = False
    backend_connected: bool = False
    last_command_seq: dict[str, int] = field(default_factory=dict)
    rejected_duplicate_count: int = 0
    feedback_stale_count: int = 0
    last_feedback_sim_time_s: float = 0.0


class BigsmallSimBridgeNode(Node):
    """ROS 2 boundary node for Phase 9.1 simulation status and control services.

    This node is intended to run in a sourced ROS 2 Jazzy workspace. It does not
    import the BIG-small core Python environment and it does not bypass the core
    SafetyShield; command identity is preserved through CommandHeader.
    """

    def __init__(self) -> None:
        super().__init__("bigsmall_sim_bridge")
        self._state = BridgeState()
        self._callback_group = ReentrantCallbackGroup()
        self.declare_parameter("backend_connected", True)
        self._state.backend_connected = bool(
            self.get_parameter("backend_connected").get_parameter_value().bool_value
        )
        self._clock_pub = self.create_publisher(Clock, "/clock", telemetry_qos())
        self._status_pub = self.create_publisher(
            SimulationStatus, "/bigsmall/simulation/status", telemetry_qos()
        )
        self._safety_pub = self.create_publisher(
            SafetyEvent, "/bigsmall/safety_event", command_qos()
        )
        self._fault_pub = self.create_publisher(FaultEvent, "/bigsmall/fault_event", command_qos())
        self._services = [
            self.create_service(EmergencyStop, "/bigsmall/emergency_stop", self._emergency_stop),
            self.create_service(Stop, "/bigsmall/stop", self._stop),
            self.create_service(ResetWorld, "/bigsmall/reset_world", self._reset_world),
            self.create_service(LoadScenario, "/bigsmall/load_scenario", self._load_scenario),
            self.create_service(InjectFault, "/bigsmall/inject_fault", self._inject_fault),
        ]
        self._move_to_pose_server = ActionServer(
            self,
            MoveToPose,
            "/bigsmall/move_to_pose",
            execute_callback=self._execute_move_to_pose,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._callback_group,
        )
        self._follow_joint_trajectory_server = ActionServer(
            self,
            FollowJointTrajectory,
            "/bigsmall/follow_joint_trajectory",
            execute_callback=self._execute_follow_joint_trajectory,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._callback_group,
        )
        self._status_timer = self.create_timer(0.02, self._publish_status)

    def close(self) -> None:
        self._state.shutdown_requested = True
        self._state.motion_active = False
        self._move_to_pose_server.destroy()
        self._follow_joint_trajectory_server.destroy()
        self.destroy_timer(self._status_timer)
        for service in self._services:
            self.destroy_service(service)

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
        if accepted:
            self._state.shutdown_requested = True
            self._state.motion_active = False
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
            backend_connected = self._state.backend_connected
            self._state = BridgeState(backend_connected=backend_connected)
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
            {
                "bridge_session_id": self._state.bridge_session_id,
                "backend_connected": self._state.backend_connected,
                "feedback_stale_count": self._state.feedback_stale_count,
                "node_restart_generation": self._state.node_restart_generation,
                "reconnect_state": "RECONNECT_READY",
                "rejected_duplicate_count": self._state.rejected_duplicate_count,
            },
            sort_keys=True,
        )
        self._status_pub.publish(status)

    def _goal_callback(self, goal_request: Any) -> GoalResponse:
        header = goal_request.header
        if self._state.shutdown_requested:
            return GoalResponse.REJECT
        if self._state.emergency_stopped:
            return GoalResponse.REJECT
        if not self._accept_once(header.task_id, header.command_seq):
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle: Any) -> CancelResponse:
        self._state.motion_active = False
        self._publish_safety_event(
            goal_handle.request.header,
            "ACTION_CANCEL",
            "CANCEL_ACCEPTED",
            False,
        )
        return CancelResponse.ACCEPT

    def _execute_move_to_pose(self, goal_handle: Any) -> Any:
        request = goal_handle.request
        result = MoveToPose.Result()
        started = self._state.simulation_time_s
        timeout_s = float(request.timeout_s)
        if not self._state.backend_connected:
            goal_handle.abort()
            result.success = False
            result.status = "BACKEND_NOT_CONNECTED"
            result.final_sim_time_s = self._state.simulation_time_s
            return result
        self._state.motion_active = True
        deadline = time.monotonic() + (max(timeout_s * 2.0, 1.0) if timeout_s > 0.0 else 0.0)

        while self._state.motion_active and time.monotonic() <= deadline:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.status = "CANCELED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            if self._state.shutdown_requested:
                goal_handle.abort()
                result.success = False
                result.status = "SHUTDOWN_REQUESTED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            if self._state.emergency_stopped:
                goal_handle.abort()
                result.success = False
                result.status = "EMERGENCY_STOPPED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            elapsed = max(self._state.simulation_time_s - started, 0.0)
            completion_ratio = 1.0 if timeout_s <= 0.0 else min(elapsed / timeout_s, 1.0)
            feedback = MoveToPose.Feedback()
            feedback.sim_time_s = self._state.simulation_time_s
            feedback.ros_time_s = self._state.simulation_time_s
            feedback.completion_ratio = completion_ratio
            feedback.stale_feedback = self._is_feedback_stale()
            goal_handle.publish_feedback(feedback)
            self._state.last_feedback_sim_time_s = self._state.simulation_time_s
            if completion_ratio >= 1.0:
                break
            time.sleep(0.02)

        canceled = goal_handle.is_cancel_requested or not self._state.motion_active
        self._state.motion_active = False
        if canceled:
            goal_handle.canceled()
            result.success = False
            result.status = "CANCELED"
        elif time.monotonic() > deadline:
            goal_handle.abort()
            result.success = False
            result.status = "TIMEOUT"
        else:
            goal_handle.succeed()
            result.success = True
            result.status = "SUCCEEDED"
        result.final_sim_time_s = self._state.simulation_time_s
        result.tcp_position_error_m = 0.0
        result.tcp_orientation_error_rad = 0.0
        return result

    def _execute_follow_joint_trajectory(self, goal_handle: Any) -> Any:
        request = goal_handle.request
        result = FollowJointTrajectory.Result()
        started = self._state.simulation_time_s
        timeout_s = float(request.timeout_s)
        violation = trajectory_joint_limit_violation(request.trajectory)
        if violation is not None:
            goal_handle.abort()
            result.success = False
            result.status = "JOINT_LIMIT_REJECTED"
            result.final_sim_time_s = self._state.simulation_time_s
            result.joint_tracking_rmse = 0.0
            self._publish_safety_event(
                request.header,
                "JOINT_LIMIT_REJECTED",
                json.dumps(violation, sort_keys=True),
                False,
            )
            return result
        if not self._state.backend_connected:
            goal_handle.abort()
            result.success = False
            result.status = "BACKEND_NOT_CONNECTED"
            result.final_sim_time_s = self._state.simulation_time_s
            return result
        self._state.motion_active = True
        deadline = time.monotonic() + (max(timeout_s * 2.0, 1.0) if timeout_s > 0.0 else 0.0)

        while self._state.motion_active and time.monotonic() <= deadline:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.status = "CANCELED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            if self._state.shutdown_requested:
                goal_handle.abort()
                result.success = False
                result.status = "SHUTDOWN_REQUESTED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            if self._state.emergency_stopped:
                goal_handle.abort()
                result.success = False
                result.status = "EMERGENCY_STOPPED"
                result.final_sim_time_s = self._state.simulation_time_s
                return result
            elapsed = max(self._state.simulation_time_s - started, 0.0)
            completion_ratio = 1.0 if timeout_s <= 0.0 else min(elapsed / timeout_s, 1.0)
            feedback = FollowJointTrajectory.Feedback()
            feedback.sim_time_s = self._state.simulation_time_s
            feedback.ros_time_s = self._state.simulation_time_s
            feedback.completion_ratio = completion_ratio
            feedback.stale_feedback = self._is_feedback_stale()
            goal_handle.publish_feedback(feedback)
            self._state.last_feedback_sim_time_s = self._state.simulation_time_s
            if completion_ratio >= 1.0:
                break
            time.sleep(0.02)

        canceled = goal_handle.is_cancel_requested or not self._state.motion_active
        self._state.motion_active = False
        if canceled:
            goal_handle.canceled()
            result.success = False
            result.status = "CANCELED"
        elif time.monotonic() > deadline:
            goal_handle.abort()
            result.success = False
            result.status = "TIMEOUT"
        else:
            goal_handle.succeed()
            result.success = True
            result.status = "SUCCEEDED"
        result.final_sim_time_s = self._state.simulation_time_s
        result.joint_tracking_rmse = 0.0
        return result

    def _is_feedback_stale(self) -> bool:
        stale = self._state.simulation_time_s - self._state.last_feedback_sim_time_s > 0.25
        if stale:
            self._state.feedback_stale_count += 1
        return stale


def main() -> None:
    rclpy.init()
    node = BigsmallSimBridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except ExternalShutdownException:
        node.get_logger().info("bigsmall_sim_bridge shutdown requested")
    except Exception as exc:
        if type(exc).__name__ != "RCLError":
            raise
        node.get_logger().info("bigsmall_sim_bridge shutdown requested")
    finally:
        executor.shutdown()
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
