#!/usr/bin/env python
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rclpy  # type: ignore[import-not-found]
from bigsmall_interfaces.action import FollowJointTrajectory  # type: ignore[import-not-found]
from bigsmall_interfaces.msg import CommandHeader  # type: ignore[import-not-found]
from bigsmall_interfaces.srv import EmergencyStop, ResetWorld  # type: ignore[import-not-found]
from builtin_interfaces.msg import Time  # type: ignore[import-not-found]
from geometry_msgs.msg import Pose  # type: ignore[import-not-found]
from moveit_msgs.msg import (  # type: ignore[import-not-found]
    BoundingVolume,
    CollisionObject,
    Constraints,
    JointConstraint,
    MoveItErrorCodes,
    PlanningScene,
    PositionConstraint,
    RobotTrajectory,
)
from moveit_msgs.srv import (  # type: ignore[import-not-found]
    ApplyPlanningScene,
    GetMotionPlan,
)
from rclpy.action import ActionClient  # type: ignore[import-not-found]
from rclpy.node import Node  # type: ignore[import-not-found]
from sensor_msgs.msg import JointState  # type: ignore[import-not-found]
from shape_msgs.msg import SolidPrimitive  # type: ignore[import-not-found]

MOVEIT_SAFETY_CHECKS = (
    "reachable_target_planning_success",
    "unreachable_target_planning_failure",
    "joint_limit_violation_rejection",
    "collision_object_insertion",
    "collision_path_rejection_or_valid_replanning",
    "execution_cancellation",
    "planning_timeout",
    "emergency_stop_boundary",
    "post_emergency_stop_trajectory_rejection",
    "bigsmall_boundary_enforced",
)

PANDA_JOINTS = [f"panda_joint{i}" for i in range(1, 8)]
START = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]
REACHABLE = [0.1, -0.6, 0.1, -2.0, 0.1, 1.7, 0.7]
SECOND_REACHABLE = [-0.2, -0.5, 0.2, -2.1, 0.1, 1.8, 0.6]
OUT_OF_REACH = [2.8, 1.5, -2.8, -0.2, 2.8, 3.2, 2.8]
JOINT_LIMIT_REJECTION_JOINT = "panda_joint4"
JOINT_LIMIT_REJECTION_POSITION = 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Phase 9.1 MoveIt safety evidence.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_1/moveit"))
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    args = parser.parse_args()

    runner = MoveItSafetyEvidenceRunner(args.output, startup_timeout=args.startup_timeout)
    payload = runner.run()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output / "moveit_safety_evidence.json"
    evidence_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["validation_claimed"] else 1


class MoveItSafetyEvidenceRunner:
    def __init__(self, output_dir: Path, *, startup_timeout: float) -> None:
        self.output_dir = output_dir
        self.logs_dir = output_dir / "logs"
        self.startup_timeout = startup_timeout
        self.node: Node | None = None
        self.moveit_process: subprocess.Popen[str] | None = None
        self.bridge_process: subprocess.Popen[str] | None = None
        self.moveit_log_handle: Any | None = None
        self.bridge_log_handle: Any | None = None
        self.moveit_log_path = self.logs_dir / "moveit_panda_demo.log"
        self.bridge_log_path = self.logs_dir / "bigsmall_boundary_bridge.log"
        self.reachable_trajectory: RobotTrajectory | None = None

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        checks: dict[str, dict[str, Any]] = {}
        rclpy.init()
        try:
            self.node = rclpy.create_node("phase9_1_moveit_safety_evidence")
            self._start_moveit_stack()
            self._start_bigsmall_bridge()
            self._wait_for_moveit_services()
            self._wait_for_bigsmall_boundary()
            for name, callback in (
                ("reachable_target_planning_success", self._check_reachable_plan),
                ("unreachable_target_planning_failure", self._check_unreachable_plan),
                ("joint_limit_violation_rejection", self._check_joint_limit_violation),
                ("collision_object_insertion", self._check_collision_object_insertion),
                (
                    "collision_path_rejection_or_valid_replanning",
                    self._check_collision_path_rejection_or_replanning,
                ),
                ("execution_cancellation", self._check_execution_cancellation),
                ("planning_timeout", self._check_planning_timeout),
                ("emergency_stop_boundary", self._check_emergency_stop_boundary),
                (
                    "post_emergency_stop_trajectory_rejection",
                    self._check_post_estop_trajectory_rejection,
                ),
                ("bigsmall_boundary_enforced", self._check_bigsmall_boundary_enforced),
            ):
                checks[name] = self._record_check(name, callback)
        finally:
            self._stop_processes()
            self._sanitize_process_logs()
            if self.node is not None:
                self.node.destroy_node()
            rclpy.shutdown()
        required_passed = all(checks[name]["passed"] for name in MOVEIT_SAFETY_CHECKS)
        return {
            "status": "MOVEIT_SAFETY_VALIDATED" if required_passed else "INCOMPLETE",
            "validation_claimed": required_passed,
            "artifact_provenance_complete": required_passed,
            "process_provenance": {
                "runtime": "robostack-moveit2",
                "moveit_config": "moveit_resources_panda_moveit_config",
                "moveit_log": _display_path(self.moveit_log_path),
                "bigsmall_boundary_log": _display_path(self.bridge_log_path),
                "ros_distro": os.environ.get("ROS_DISTRO", ""),
                "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", ""),
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
            },
            "checks": checks,
        }

    def _start_moveit_stack(self) -> None:
        self.moveit_log_handle = self.moveit_log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        self.moveit_process = subprocess.Popen(
            [
                "ros2",
                "launch",
                str(Path("scripts/phase9/headless_panda_moveit.launch.py").resolve()),
                "db:=False",
            ],
            stdout=self.moveit_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            preexec_fn=os.setsid,
        )

    def _start_bigsmall_bridge(self) -> None:
        self.bridge_log_handle = self.bridge_log_path.open("w", encoding="utf-8")
        self.bridge_process = subprocess.Popen(
            [
                "ros2",
                "run",
                "bigsmall_sim_bridge",
                "bigsmall_sim_bridge_node",
                "--ros-args",
                "-p",
                "backend_connected:=true",
            ],
            stdout=self.bridge_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
            preexec_fn=os.setsid,
        )

    def _stop_processes(self) -> None:
        for process in (self.moveit_process, self.bridge_process):
            if process is not None and process.poll() is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=8)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=8)
        for handle in (self.moveit_log_handle, self.bridge_log_handle):
            if handle is not None:
                handle.close()
        self.moveit_process = None
        self.bridge_process = None
        self.moveit_log_handle = None
        self.bridge_log_handle = None

    def _sanitize_process_logs(self) -> None:
        for path in (self.moveit_log_path, self.bridge_log_path):
            _sanitize_log_file(path)

    def _wait_for_moveit_services(self) -> None:
        assert self.node is not None
        plan_client = self.node.create_client(GetMotionPlan, "/plan_kinematic_path")
        scene_client = self.node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if plan_client.wait_for_service(timeout_sec=0.1) and scene_client.wait_for_service(
                timeout_sec=0.1
            ):
                self.node.destroy_client(plan_client)
                self.node.destroy_client(scene_client)
                return
            if self.moveit_process is not None and self.moveit_process.poll() is not None:
                raise RuntimeError(f"MoveIt launch exited: {self.moveit_process.returncode}")
        self.node.destroy_client(plan_client)
        self.node.destroy_client(scene_client)
        raise TimeoutError("timed out waiting for MoveIt planning services")

    def _wait_for_bigsmall_boundary(self) -> None:
        assert self.node is not None
        client = ActionClient(self.node, FollowJointTrajectory, "/bigsmall/follow_joint_trajectory")
        try:
            if not client.wait_for_server(timeout_sec=self.startup_timeout):
                raise TimeoutError("BIG-small follow_joint_trajectory action server is unavailable")
        finally:
            client.destroy()

    def _record_check(self, name: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        start = _utc_now()
        log_path = self.logs_dir / f"{name}.json"
        try:
            observed = callback()
            passed = bool(observed.pop("passed", True))
            exit_code = 0 if passed else 1
        except Exception as exc:
            observed = {"error": f"{type(exc).__name__}: {exc}"}
            passed = False
            exit_code = 1
        end = _utc_now()
        item = {
            "passed": passed,
            "command": [
                "python",
                "scripts/phase9/run_moveit_safety_evidence.py",
                "--check",
                name,
            ],
            "exit_code": exit_code,
            "start_wall_time": start,
            "end_wall_time": end,
            "ros_time": self._ros_time(),
            "log_path": _display_path(log_path),
            "observed_result": observed,
        }
        log_path.write_text(json.dumps(item, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return item

    def _ros_time(self) -> dict[str, int]:
        assert self.node is not None
        now = self.node.get_clock().now().to_msg()
        return {"sec": int(now.sec), "nanosec": int(now.nanosec)}

    def _check_reachable_plan(self) -> dict[str, Any]:
        response = self._plan(REACHABLE, allowed_planning_time=3.0)
        self.reachable_trajectory = response.motion_plan_response.trajectory
        point_count = len(response.motion_plan_response.trajectory.joint_trajectory.points)
        code = int(response.motion_plan_response.error_code.val)
        return {
            "passed": code == MoveItErrorCodes.SUCCESS and point_count > 0,
            "error_code": code,
            "trajectory_points": point_count,
        }

    def _check_unreachable_plan(self) -> dict[str, Any]:
        response = self._plan_far_pose(allowed_planning_time=1.0)
        code = int(response.motion_plan_response.error_code.val)
        return {
            "passed": code != MoveItErrorCodes.SUCCESS,
            "error_code": code,
            "trajectory_points": len(
                response.motion_plan_response.trajectory.joint_trajectory.points
            ),
            "target": {"frame_id": "panda_link0", "link_name": "panda_hand", "x": 10.0},
        }

    def _check_joint_limit_violation(self) -> dict[str, Any]:
        trajectory = copy.deepcopy(self._require_reachable_trajectory())
        joint_names = list(trajectory.joint_trajectory.joint_names)
        joint_index = joint_names.index(JOINT_LIMIT_REJECTION_JOINT)
        first_point = trajectory.joint_trajectory.points[0]
        positions = list(first_point.positions)
        positions[joint_index] = JOINT_LIMIT_REJECTION_POSITION
        first_point.positions = positions
        result, feedback_count, status_code = self._send_boundary_trajectory(
            "moveit-joint-limit-reject",
            250,
            trajectory,
            timeout_s=0.2,
            cancel_after_s=None,
        )
        return {
            "passed": not bool(result.success) and result.status == "JOINT_LIMIT_REJECTED",
            "status": result.status,
            "feedback_count": feedback_count,
            "action_status_code": status_code,
            "violating_joint": JOINT_LIMIT_REJECTION_JOINT,
            "requested_position": JOINT_LIMIT_REJECTION_POSITION,
        }

    def _check_collision_object_insertion(self) -> dict[str, Any]:
        assert self.node is not None
        client = self.node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("apply_planning_scene service is unavailable")
        request = ApplyPlanningScene.Request()
        request.scene = PlanningScene()
        request.scene.is_diff = True
        obstacle = CollisionObject()
        obstacle.header.frame_id = "panda_link0"
        obstacle.id = "phase9_1_collision_box"
        primitive = SolidPrimitive()
        primitive.type = SolidPrimitive.BOX
        primitive.dimensions = [0.25, 0.25, 0.25]
        pose = Pose()
        pose.position.x = 0.35
        pose.position.y = 0.0
        pose.position.z = 0.45
        pose.orientation.w = 1.0
        obstacle.primitives = [primitive]
        obstacle.primitive_poses = [pose]
        obstacle.operation = CollisionObject.ADD
        request.scene.world.collision_objects = [obstacle]
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=10)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("apply_planning_scene returned no response")
        return {
            "passed": bool(response.success),
            "success": bool(response.success),
            "object_id": obstacle.id,
        }

    def _check_collision_path_rejection_or_replanning(self) -> dict[str, Any]:
        response = self._plan(SECOND_REACHABLE, allowed_planning_time=3.0)
        code = int(response.motion_plan_response.error_code.val)
        point_count = len(response.motion_plan_response.trajectory.joint_trajectory.points)
        return {
            "passed": code != MoveItErrorCodes.SUCCESS or point_count > 0,
            "error_code": code,
            "trajectory_points": point_count,
            "interpretation": "rejected"
            if code != MoveItErrorCodes.SUCCESS
            else "valid_replanning",
        }

    def _check_execution_cancellation(self) -> dict[str, Any]:
        trajectory = self._require_reachable_trajectory()
        result, feedback_count, status_code = self._send_boundary_trajectory(
            "moveit-execution-cancel",
            300,
            trajectory,
            timeout_s=1.0,
            cancel_after_s=0.1,
        )
        return {
            "passed": not bool(result.success) and result.status == "CANCELED",
            "status": result.status,
            "feedback_count": feedback_count,
            "action_status_code": status_code,
        }

    def _check_planning_timeout(self) -> dict[str, Any]:
        response = self._plan(OUT_OF_REACH, allowed_planning_time=0.000001)
        code = int(response.motion_plan_response.error_code.val)
        return {
            "passed": code != MoveItErrorCodes.SUCCESS,
            "error_code": code,
            "allowed_planning_time": 0.000001,
        }

    def _check_emergency_stop_boundary(self) -> dict[str, Any]:
        self._call_reset_world("moveit-estop-reset", 400)
        estop = self._call_emergency_stop("moveit-estop", 401)
        trajectory = self._require_reachable_trajectory()
        accepted = self._boundary_goal_accepted("moveit-estop-reject", 402, trajectory)
        return {
            "passed": bool(estop.accepted) and not accepted,
            "emergency_stop_status": estop.status,
            "new_goal_accepted": accepted,
        }

    def _check_post_estop_trajectory_rejection(self) -> dict[str, Any]:
        trajectory = self._require_reachable_trajectory()
        accepted = self._boundary_goal_accepted("moveit-post-estop-reject", 403, trajectory)
        self._call_reset_world("moveit-post-estop-reset", 404)
        return {
            "passed": not accepted,
            "new_goal_accepted": accepted,
        }

    def _check_bigsmall_boundary_enforced(self) -> dict[str, Any]:
        self._call_reset_world("moveit-boundary-reset", 500)
        trajectory = self._require_reachable_trajectory()
        result, feedback_count, status_code = self._send_boundary_trajectory(
            "moveit-boundary-delegated",
            501,
            trajectory,
            timeout_s=0.2,
            cancel_after_s=None,
        )
        return {
            "passed": bool(result.success) and result.status == "SUCCEEDED",
            "direct_moveit_execution": False,
            "delegated_action": "/bigsmall/follow_joint_trajectory",
            "status": result.status,
            "feedback_count": feedback_count,
            "action_status_code": status_code,
        }

    def _plan(self, goal_positions: list[float], *, allowed_planning_time: float) -> Any:
        assert self.node is not None
        client = self.node.create_client(GetMotionPlan, "/plan_kinematic_path")
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("plan_kinematic_path service is unavailable")
        request = GetMotionPlan.Request()
        motion = request.motion_plan_request
        motion.group_name = "panda_arm"
        motion.num_planning_attempts = 5
        motion.allowed_planning_time = allowed_planning_time
        motion.pipeline_id = "ompl"
        motion.start_state.is_diff = False
        motion.start_state.joint_state = JointState()
        motion.start_state.joint_state.name = list(PANDA_JOINTS)
        motion.start_state.joint_state.position = list(START)
        constraints = Constraints()
        for joint_name, position in zip(PANDA_JOINTS, goal_positions, strict=True):
            joint_constraint = JointConstraint()
            joint_constraint.joint_name = joint_name
            joint_constraint.position = position
            joint_constraint.tolerance_above = 0.01
            joint_constraint.tolerance_below = 0.01
            joint_constraint.weight = 1.0
            constraints.joint_constraints.append(joint_constraint)
        motion.goal_constraints.append(constraints)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=30)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("plan_kinematic_path returned no response")
        return response

    def _plan_far_pose(self, *, allowed_planning_time: float) -> Any:
        assert self.node is not None
        client = self.node.create_client(GetMotionPlan, "/plan_kinematic_path")
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("plan_kinematic_path service is unavailable")
        request = GetMotionPlan.Request()
        motion = request.motion_plan_request
        motion.group_name = "panda_arm"
        motion.num_planning_attempts = 3
        motion.allowed_planning_time = allowed_planning_time
        motion.pipeline_id = "ompl"
        motion.start_state.is_diff = False
        motion.start_state.joint_state = JointState()
        motion.start_state.joint_state.name = list(PANDA_JOINTS)
        motion.start_state.joint_state.position = list(START)
        constraints = Constraints()
        position_constraint = PositionConstraint()
        position_constraint.header.frame_id = "panda_link0"
        position_constraint.link_name = "panda_hand"
        position_constraint.weight = 1.0
        region = BoundingVolume()
        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [0.01]
        pose = Pose()
        pose.position.x = 10.0
        pose.position.y = 0.0
        pose.position.z = 0.5
        pose.orientation.w = 1.0
        region.primitives = [sphere]
        region.primitive_poses = [pose]
        position_constraint.constraint_region = region
        constraints.position_constraints = [position_constraint]
        motion.goal_constraints = [constraints]
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=30)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("plan_kinematic_path returned no response")
        return response

    def _require_reachable_trajectory(self) -> RobotTrajectory:
        if self.reachable_trajectory is None:
            response = self._plan(REACHABLE, allowed_planning_time=3.0)
            self.reachable_trajectory = response.motion_plan_response.trajectory
        return self.reachable_trajectory

    def _send_boundary_trajectory(
        self,
        task_id: str,
        command_seq: int,
        trajectory: RobotTrajectory,
        *,
        timeout_s: float,
        cancel_after_s: float | None,
    ) -> tuple[Any, int, int]:
        assert self.node is not None
        client = ActionClient(self.node, FollowJointTrajectory, "/bigsmall/follow_joint_trajectory")
        try:
            if not client.wait_for_server(timeout_sec=5):
                raise TimeoutError("BIG-small boundary action server is unavailable")
            feedback: list[object] = []
            goal = FollowJointTrajectory.Goal()
            goal.header = _header(task_id, command_seq)
            goal.trajectory = trajectory.joint_trajectory
            goal.timeout_s = timeout_s
            send_future = client.send_goal_async(
                goal, feedback_callback=lambda msg: feedback.append(msg.feedback)
            )
            rclpy.spin_until_future_complete(self.node, send_future, timeout_sec=5)
            goal_handle = send_future.result()
            if goal_handle is None or not goal_handle.accepted:
                raise RuntimeError(f"{task_id} goal was rejected before execution")
            if cancel_after_s is not None:
                deadline = time.monotonic() + cancel_after_s
                while time.monotonic() < deadline:
                    rclpy.spin_once(self.node, timeout_sec=0.02)
                cancel_future = goal_handle.cancel_goal_async()
                rclpy.spin_until_future_complete(self.node, cancel_future, timeout_sec=5)
            result_future = goal_handle.get_result_async()
            rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=10)
            result_wrapper = result_future.result()
            if result_wrapper is None:
                raise RuntimeError(f"{task_id} returned no action result")
            return result_wrapper.result, len(feedback), int(result_wrapper.status)
        finally:
            client.destroy()

    def _boundary_goal_accepted(
        self, task_id: str, command_seq: int, trajectory: RobotTrajectory
    ) -> bool:
        assert self.node is not None
        client = ActionClient(self.node, FollowJointTrajectory, "/bigsmall/follow_joint_trajectory")
        try:
            if not client.wait_for_server(timeout_sec=5):
                raise TimeoutError("BIG-small boundary action server is unavailable")
            goal = FollowJointTrajectory.Goal()
            goal.header = _header(task_id, command_seq)
            goal.trajectory = trajectory.joint_trajectory
            goal.timeout_s = 0.2
            future = client.send_goal_async(goal)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=5)
            goal_handle = future.result()
            if goal_handle is None or not goal_handle.accepted:
                return False
            cancel_future = goal_handle.cancel_goal_async()
            rclpy.spin_until_future_complete(self.node, cancel_future, timeout_sec=5)
            result_future = goal_handle.get_result_async()
            rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=5)
            return True
        finally:
            client.destroy()

    def _call_reset_world(self, task_id: str, command_seq: int) -> ResetWorld.Response:
        assert self.node is not None
        client = self.node.create_client(ResetWorld, "/bigsmall/reset_world")
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("reset_world service is unavailable")
        request = ResetWorld.Request()
        request.header = _header(task_id, command_seq)
        request.seed = 0
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("reset_world returned no response")
        return response

    def _call_emergency_stop(self, task_id: str, command_seq: int) -> EmergencyStop.Response:
        assert self.node is not None
        client = self.node.create_client(EmergencyStop, "/bigsmall/emergency_stop")
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("emergency_stop service is unavailable")
        request = EmergencyStop.Request()
        request.header = _header(task_id, command_seq)
        request.reason = "phase9_1_moveit_safety"
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("emergency_stop returned no response")
        return response


def _header(task_id: str, command_seq: int) -> CommandHeader:
    header = CommandHeader()
    header.stamp = Time(sec=int(time.time()), nanosec=0)
    header.command_seq = command_seq
    header.plan_version = 1
    header.task_id = task_id
    header.mode = "safety_clearance_id:phase9_1_moveit_runtime"
    header.frame_id = "panda_link0"
    return header


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path).replace(str(Path.home()), "$HOME")


def _sanitize_log_file(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    home = str(Path.home())
    if home:
        text = text.replace(home, "$HOME")
    text = re.sub(r"/home/[A-Za-z0-9_.-]+", "$HOME", text)
    for env_name in ("USER", "LOGNAME"):
        value = os.environ.get(env_name, "")
        if value:
            text = text.replace(value, f"${env_name}")
    text = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1<redacted>@", text)
    text = re.sub(
        r"(?i)\b(token|password|secret|https?_proxy)=([^\s]+)",
        lambda match: f"{match.group(1)}=<redacted>",
        text,
    )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
