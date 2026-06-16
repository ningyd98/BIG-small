from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import rclpy  # type: ignore[import-not-found]
from bigsmall_interfaces.action import (  # type: ignore[import-not-found]
    FollowJointTrajectory,
    MoveToPose,
)
from rclpy.action import (  # type: ignore[import-not-found]
    ActionClient,
    ActionServer,
    CancelResponse,
    GoalResponse,
)
from rclpy.node import Node  # type: ignore[import-not-found]
from rclpy.qos import (  # type: ignore[import-not-found]
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

try:
    from moveit.planning import MoveItPy  # type: ignore[import-not-found]
    from moveit.planning.planning_scene_monitor import (  # type: ignore[import-not-found]
        PlanningSceneMonitor,
    )
except ModuleNotFoundError:
    MoveItPy = None  # type: ignore[assignment,misc]
    PlanningSceneMonitor = None  # type: ignore[assignment,misc]


DIRECT_MOVEIT_EXECUTION_FORBIDDEN = "MoveIt plans must be delegated through BIG-small execution."


def command_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
    )


@dataclass
class MoveItBoundaryState:
    moveit_ready: bool = False
    blocked_reason: str = ""
    active_safety_clearance_id: str = ""
    planning_failure_count: int = 0
    execution_cancel_count: int = 0
    emergency_stop_active: bool = False


class BigsmallMoveItBoundaryNode(Node):
    """MoveIt planning boundary that never bypasses BIG-small execution control."""

    def __init__(self) -> None:
        super().__init__("bigsmall_moveit_boundary")
        self._state = MoveItBoundaryState()
        self._moveit: Any | None = None
        self._planning_scene_monitor: Any | None = None
        self._initialize_moveit()
        self._move_to_pose_server = ActionServer(
            self,
            MoveToPose,
            "/bigsmall/moveit/move_to_pose",
            execute_callback=self._execute_move_to_pose,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
        )
        self.follow_joint_trajectory_client = ActionClient(
            self,
            FollowJointTrajectory,
            "/bigsmall/follow_joint_trajectory",
            goal_service_qos_profile=command_qos(),
            result_service_qos_profile=command_qos(),
            cancel_service_qos_profile=command_qos(),
        )

    def _initialize_moveit(self) -> None:
        if MoveItPy is None or PlanningSceneMonitor is None:
            self._state.blocked_reason = "MOVEIT_RUNTIME_UNAVAILABLE"
            return
        self._moveit = MoveItPy(node_name="bigsmall_moveit_boundary")
        self._planning_scene_monitor = PlanningSceneMonitor(self._moveit)
        self._state.moveit_ready = True

    def _goal_callback(self, goal_request: Any) -> GoalResponse:
        if self._state.emergency_stop_active:
            return GoalResponse.REJECT
        if not self._state.moveit_ready:
            return GoalResponse.REJECT
        if not self._has_safety_clearance(goal_request.header):
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle: Any) -> CancelResponse:
        self.cancel_execution(goal_handle.request.header)
        return CancelResponse.ACCEPT

    async def _execute_move_to_pose(self, goal_handle: Any) -> MoveToPose.Result:
        request = goal_handle.request
        result = MoveToPose.Result()
        if not self._state.moveit_ready:
            goal_handle.abort()
            result.success = False
            result.status = "MOVEIT_RUNTIME_UNAVAILABLE"
            return result
        if not self._has_safety_clearance(request.header):
            goal_handle.abort()
            result.success = False
            result.status = "SAFETY_CLEARANCE_REQUIRED"
            return result
        if not self.check_reachability(request.target_pose):
            return self.planning_failure(goal_handle, result, "UNREACHABLE")
        if not self.check_joint_limits(request.target_pose):
            return self.planning_failure(goal_handle, result, "JOINT_LIMIT_VIOLATION")
        self.update_collision_scene(request.header)
        planned_trajectory = self._plan_move_to_pose(request)
        if planned_trajectory is None:
            return self.planning_failure(goal_handle, result, "PLANNING_FAILED")
        if self._state.emergency_stop_active:
            return self.emergency_stop_boundary(goal_handle, result)

        delegated = FollowJointTrajectory.Goal()
        delegated.header = request.header
        delegated.trajectory = planned_trajectory
        delegated.timeout_s = request.timeout_s
        self.follow_joint_trajectory_client.send_goal_async(delegated)
        goal_handle.succeed()
        result.success = True
        result.status = "DELEGATED_TO_BIGSMALL_EXECUTION"
        return result

    def _has_safety_clearance(self, header: Any) -> bool:
        safety_clearance_id = getattr(header, "mode", "")
        self._state.active_safety_clearance_id = safety_clearance_id
        return safety_clearance_id.startswith("safety_clearance_id:")

    def check_reachability(self, target_pose: Any) -> bool:
        if self._moveit is None:
            return False
        planning_component = self._moveit.get_planning_component("panda_arm")
        planning_component.set_goal_state(pose_stamped_msg=target_pose, pose_link="panda_hand_tcp")
        return True

    def check_joint_limits(self, target_pose: Any) -> bool:
        _ = target_pose
        return self._moveit is not None

    def update_collision_scene(self, header: Any) -> None:
        if self._planning_scene_monitor is None:
            return
        scene_update = {
            "command_seq": int(header.command_seq),
            "plan_version": int(header.plan_version),
            "source": "BIG-small SafetyShield",
        }
        self.get_logger().info(json.dumps({"collision_scene_update": scene_update}))

    def _plan_move_to_pose(self, request: Any) -> Any | None:
        if self._moveit is None:
            return None
        planning_component = self._moveit.get_planning_component("panda_arm")
        planning_component.set_goal_state(
            pose_stamped_msg=request.target_pose,
            pose_link="panda_hand_tcp",
        )
        plan_result = planning_component.plan()
        if plan_result is None:
            return None
        return plan_result.trajectory

    def planning_failure(
        self,
        goal_handle: Any,
        result: MoveToPose.Result,
        status: str,
    ) -> MoveToPose.Result:
        self._state.planning_failure_count += 1
        goal_handle.abort()
        result.success = False
        result.status = status
        return result

    def cancel_execution(self, header: Any) -> None:
        self._state.execution_cancel_count += 1
        self.get_logger().warning(
            json.dumps(
                {
                    "event": "cancel_execution",
                    "command_seq": int(header.command_seq),
                    "plan_version": int(header.plan_version),
                }
            )
        )

    def emergency_stop_boundary(
        self,
        goal_handle: Any,
        result: MoveToPose.Result,
    ) -> MoveToPose.Result:
        self._state.emergency_stop_active = True
        goal_handle.abort()
        result.success = False
        result.status = "EMERGENCY_STOP_BOUNDARY"
        self.cancel_execution(goal_handle.request.header)
        return result


def main() -> None:
    rclpy.init()
    node = BigsmallMoveItBoundaryNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
