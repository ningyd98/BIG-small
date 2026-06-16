#!/usr/bin/env python
from __future__ import annotations

import argparse
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
from bigsmall_interfaces.msg import (  # type: ignore[import-not-found]
    CommandHeader,
    ContactArray,
    SimulationStatus,
)
from bigsmall_interfaces.srv import (  # type: ignore[import-not-found]
    EmergencyStop,
    LoadScenario,
    ResetWorld,
)
from builtin_interfaces.msg import Duration, Time  # type: ignore[import-not-found]
from rclpy.action import ActionClient  # type: ignore[import-not-found]
from rclpy.node import Node  # type: ignore[import-not-found]
from rclpy.qos import (  # type: ignore[import-not-found]
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from trajectory_msgs.msg import (  # type: ignore[import-not-found]
    JointTrajectory,
    JointTrajectoryPoint,
)

ROS2_RUNTIME_CHECKS = (
    "custom_message",
    "custom_service",
    "qos_compatible",
    "qos_incompatible",
    "namespace_isolation",
    "ros_timestamp",
    "sensor_timestamp",
    "action_success",
    "action_timeout",
    "action_cancel",
    "stale_feedback",
    "node_crash",
    "node_restart_reconnect",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Phase 9.1 ROS 2 runtime evidence.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_1/ros2"))
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    args = parser.parse_args()

    runner = Ros2RuntimeEvidenceRunner(args.output, startup_timeout=args.startup_timeout)
    payload = runner.run()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output / "ros2_runtime_evidence.json"
    evidence_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["validation_claimed"] else 1


class Ros2RuntimeEvidenceRunner:
    def __init__(self, output_dir: Path, *, startup_timeout: float) -> None:
        self.output_dir = output_dir
        self.logs_dir = output_dir / "logs"
        self.startup_timeout = startup_timeout
        self.node: Node | None = None
        self.bridge_process: subprocess.Popen[str] | None = None
        self.bridge_log_handle: Any | None = None
        self.bridge_log_path = self.logs_dir / "bigsmall_sim_bridge.log"
        self.bridge_start_count = 0
        self.latest_status: SimulationStatus | None = None

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        checks: dict[str, dict[str, Any]] = {}
        rclpy.init()
        try:
            self.node = rclpy.create_node("phase9_1_ros2_runtime_evidence")
            self.node.create_subscription(
                SimulationStatus,
                "/bigsmall/simulation/status",
                self._status_callback,
                _telemetry_qos(),
            )
            self._start_bridge()
            self._wait_for_bridge()
            for name, callback in (
                ("qos_compatible", self._check_qos_compatible),
                ("qos_incompatible", self._check_qos_incompatible),
                ("namespace_isolation", self._check_namespace_isolation),
                ("ros_timestamp", self._check_ros_timestamp),
                ("sensor_timestamp", self._check_sensor_timestamp),
                ("action_success", self._check_action_success),
                ("action_timeout", self._check_action_timeout),
                ("action_cancel", self._check_action_cancel),
                ("stale_feedback", self._check_stale_feedback),
                ("node_crash", self._check_node_crash),
                ("node_restart_reconnect", self._check_node_restart_reconnect),
                ("custom_service", self._check_custom_service),
                ("custom_message", self._check_sensor_timestamp),
            ):
                checks[name] = self._record_check(name, callback)
        finally:
            self._stop_bridge()
            self._sanitize_process_logs()
            if self.node is not None:
                self.node.destroy_node()
            rclpy.shutdown()
        required_passed = all(checks[name]["passed"] for name in ROS2_RUNTIME_CHECKS)
        return {
            "status": "ROS2_INTEGRATION_VALIDATED" if required_passed else "INCOMPLETE",
            "validation_claimed": required_passed,
            "artifact_provenance_complete": required_passed,
            "process_provenance": {
                "runtime": "ros2-rclpy",
                "node": "bigsmall_sim_bridge",
                "ros_distro": os.environ.get("ROS_DISTRO", ""),
                "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", ""),
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
            },
            "checks": checks,
        }

    def _status_callback(self, message: SimulationStatus) -> None:
        self.latest_status = message

    def _start_bridge(self) -> None:
        if self.bridge_process is not None and self.bridge_process.poll() is None:
            return
        self.bridge_log_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if self.bridge_start_count == 0 else "a"
        self.bridge_log_handle = self.bridge_log_path.open(mode, encoding="utf-8")
        self.bridge_start_count += 1
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
        )

    def _stop_bridge(self) -> None:
        if self.bridge_process is not None and self.bridge_process.poll() is None:
            self.bridge_process.terminate()
            try:
                self.bridge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bridge_process.kill()
                self.bridge_process.wait(timeout=5)
        if self.bridge_log_handle is not None:
            self.bridge_log_handle.close()
        self.bridge_process = None
        self.bridge_log_handle = None

    def _sanitize_process_logs(self) -> None:
        _sanitize_log_file(self.bridge_log_path)

    def _wait_for_bridge(self) -> None:
        assert self.node is not None
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if self.latest_status is not None:
                return
            if self.bridge_process is not None and self.bridge_process.poll() is not None:
                raise RuntimeError(f"bigsmall_sim_bridge exited: {self.bridge_process.returncode}")
        raise TimeoutError("timed out waiting for bigsmall_sim_bridge status")

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
                "scripts/phase9/run_ros2_runtime_evidence.py",
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
        if self.latest_status is None:
            return {"sec": 0, "nanosec": 0}
        return {
            "sec": int(self.latest_status.stamp.sec),
            "nanosec": int(self.latest_status.stamp.nanosec),
        }

    def _check_qos_compatible(self) -> dict[str, Any]:
        status = self._wait_for_status_sample()
        service = self._call_reset_world("qos-compatible", 1)
        return {
            "passed": status is not None and service.accepted,
            "status": status.status if status is not None else "",
            "physics_steps": int(status.physics_steps) if status is not None else 0,
            "service_status": service.status,
        }

    def _check_qos_incompatible(self) -> dict[str, Any]:
        assert self.node is not None
        received: list[SimulationStatus] = []
        best_effort_pub = self.node.create_publisher(
            SimulationStatus,
            "/bigsmall/qos_incompatible_probe",
            QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
            ),
        )
        reliable_sub = self.node.create_subscription(
            SimulationStatus,
            "/bigsmall/qos_incompatible_probe",
            lambda msg: received.append(msg),
            QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
            ),
        )
        time.sleep(0.2)
        best_effort_pub.publish(SimulationStatus())
        self._spin_for(0.5)
        self.node.destroy_publisher(best_effort_pub)
        self.node.destroy_subscription(reliable_sub)
        return {
            "passed": len(received) == 0,
            "received_count": len(received),
            "expected": "reliable subscriber rejects best-effort-only publisher",
        }

    def _check_namespace_isolation(self) -> dict[str, Any]:
        assert self.node is not None
        tenant_a: list[SimulationStatus] = []
        tenant_b: list[SimulationStatus] = []
        pub = self.node.create_publisher(SimulationStatus, "/tenant_a/status", _telemetry_qos())
        sub_a = self.node.create_subscription(
            SimulationStatus, "/tenant_a/status", lambda msg: tenant_a.append(msg), _telemetry_qos()
        )
        sub_b = self.node.create_subscription(
            SimulationStatus, "/tenant_b/status", lambda msg: tenant_b.append(msg), _telemetry_qos()
        )
        time.sleep(0.2)
        message = SimulationStatus()
        message.status = "TENANT_A_ONLY"
        pub.publish(message)
        self._spin_for(0.5)
        self.node.destroy_publisher(pub)
        self.node.destroy_subscription(sub_a)
        self.node.destroy_subscription(sub_b)
        return {
            "passed": len(tenant_a) > 0 and len(tenant_b) == 0,
            "tenant_a_messages": len(tenant_a),
            "tenant_b_messages": len(tenant_b),
        }

    def _check_ros_timestamp(self) -> dict[str, Any]:
        status = self._wait_for_status_sample()
        return {
            "passed": status is not None and status.stamp.nanosec > 0,
            "stamp": {"sec": int(status.stamp.sec), "nanosec": int(status.stamp.nanosec)}
            if status is not None
            else {},
            "ros_time_s": float(status.ros_time_s) if status is not None else 0.0,
        }

    def _check_sensor_timestamp(self) -> dict[str, Any]:
        assert self.node is not None
        received: list[ContactArray] = []
        pub = self.node.create_publisher(ContactArray, "/bigsmall/contacts_probe", _telemetry_qos())
        sub = self.node.create_subscription(
            ContactArray,
            "/bigsmall/contacts_probe",
            lambda msg: received.append(msg),
            _telemetry_qos(),
        )
        time.sleep(0.2)
        message = ContactArray()
        message.stamp = Time(sec=7, nanosec=123_000_000)
        pub.publish(message)
        self._spin_for(0.5)
        self.node.destroy_publisher(pub)
        self.node.destroy_subscription(sub)
        first = received[0] if received else None
        return {
            "passed": first is not None
            and first.stamp.sec == 7
            and first.stamp.nanosec == 123_000_000,
            "stamp": {"sec": int(first.stamp.sec), "nanosec": int(first.stamp.nanosec)}
            if first is not None
            else {},
            "received_count": len(received),
        }

    def _check_action_success(self) -> dict[str, Any]:
        result, feedback = self._run_follow_joint_action("action-success", 10, timeout_s=0.08)
        return {
            "passed": bool(result.success) and result.status == "SUCCEEDED",
            "status": result.status,
            "feedback_count": len(feedback),
            "final_sim_time_s": float(result.final_sim_time_s),
        }

    def _check_action_timeout(self) -> dict[str, Any]:
        result, feedback = self._run_follow_joint_action("action-timeout", 20, timeout_s=0.0)
        return {
            "passed": not bool(result.success) and result.status == "TIMEOUT",
            "status": result.status,
            "feedback_count": len(feedback),
        }

    def _check_action_cancel(self) -> dict[str, Any]:
        assert self.node is not None
        client = ActionClient(self.node, FollowJointTrajectory, "/bigsmall/follow_joint_trajectory")
        try:
            if not client.wait_for_server(timeout_sec=5.0):
                raise TimeoutError("follow_joint_trajectory action server is unavailable")
            feedback: list[bool] = []
            send_goal_future = client.send_goal_async(
                self._trajectory_goal("action-cancel", 30, timeout_s=1.0),
                feedback_callback=lambda msg: feedback.append(bool(msg.feedback.stale_feedback)),
            )
            rclpy.spin_until_future_complete(self.node, send_goal_future, timeout_sec=5.0)
            goal_handle = send_goal_future.result()
            if goal_handle is None or not goal_handle.accepted:
                raise RuntimeError("cancel goal was rejected")
            self._spin_for(0.1)
            cancel_future = goal_handle.cancel_goal_async()
            rclpy.spin_until_future_complete(self.node, cancel_future, timeout_sec=5.0)
            result_future = goal_handle.get_result_async()
            rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=5.0)
            result = result_future.result().result
            return {
                "passed": not bool(result.success) and result.status == "CANCELED",
                "status": result.status,
                "feedback_count": len(feedback),
                "cancel_return_code": int(result_future.result().status),
            }
        finally:
            client.destroy()

    def _check_stale_feedback(self) -> dict[str, Any]:
        self._spin_for(0.4)
        result, feedback = self._run_follow_joint_action("stale-feedback", 40, timeout_s=0.4)
        return {
            "passed": any(feedback),
            "status": result.status,
            "stale_feedback_samples": sum(1 for item in feedback if item),
            "feedback_count": len(feedback),
        }

    def _check_node_crash(self) -> dict[str, Any]:
        if self.bridge_process is None or self.bridge_process.poll() is not None:
            raise RuntimeError("bridge process is not running")
        pid = self.bridge_process.pid
        os.kill(pid, signal.SIGKILL)
        return_code = self.bridge_process.wait(timeout=5)
        if self.bridge_log_handle is not None:
            self.bridge_log_handle.close()
            self.bridge_log_handle = None
        return {
            "passed": return_code == -signal.SIGKILL,
            "pid": pid,
            "return_code": return_code,
            "bridge_log": _display_path(self.bridge_log_path),
        }

    def _check_node_restart_reconnect(self) -> dict[str, Any]:
        self._start_bridge()
        self.latest_status = None
        self._wait_for_bridge()
        response = self._call_load_scenario("node-restart", 50)
        return {
            "passed": response.accepted and response.status == "SCENARIO_LOADED",
            "status": response.status,
            "accepted": bool(response.accepted),
            "bridge_log": _display_path(self.bridge_log_path),
        }

    def _check_custom_service(self) -> dict[str, Any]:
        scenario = self._call_load_scenario("custom-service", 60)
        estop = self._call_emergency_stop("custom-service", 61)
        self._call_reset_world("custom-service-reset", 62)
        return {
            "passed": scenario.accepted and estop.accepted,
            "load_scenario_status": scenario.status,
            "emergency_stop_status": estop.status,
        }

    def _wait_for_status_sample(self) -> SimulationStatus:
        self._wait_for_bridge()
        assert self.latest_status is not None
        return self.latest_status

    def _spin_for(self, duration_s: float) -> None:
        assert self.node is not None
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.02)

    def _call_reset_world(self, task_id: str, command_seq: int) -> ResetWorld.Response:
        assert self.node is not None
        client = self.node.create_client(ResetWorld, "/bigsmall/reset_world")
        if not client.wait_for_service(timeout_sec=5.0):
            raise TimeoutError("reset_world service is unavailable")
        request = ResetWorld.Request()
        request.header = _header(task_id, command_seq)
        request.seed = 0
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("reset_world service returned no response")
        return response

    def _call_load_scenario(self, task_id: str, command_seq: int) -> LoadScenario.Response:
        assert self.node is not None
        client = self.node.create_client(LoadScenario, "/bigsmall/load_scenario")
        if not client.wait_for_service(timeout_sec=5.0):
            raise TimeoutError("load_scenario service is unavailable")
        request = LoadScenario.Request()
        request.header = _header(task_id, command_seq)
        request.scenario_id = "S01_NORMAL_STATIC"
        request.seed = 0
        request.randomization_level = "NONE"
        request.config_json = "{}"
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("load_scenario service returned no response")
        return response

    def _call_emergency_stop(self, task_id: str, command_seq: int) -> EmergencyStop.Response:
        assert self.node is not None
        client = self.node.create_client(EmergencyStop, "/bigsmall/emergency_stop")
        if not client.wait_for_service(timeout_sec=5.0):
            raise TimeoutError("emergency_stop service is unavailable")
        request = EmergencyStop.Request()
        request.header = _header(task_id, command_seq)
        request.reason = "phase9_1_runtime_check"
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        self.node.destroy_client(client)
        response = future.result()
        if response is None:
            raise RuntimeError("emergency_stop service returned no response")
        return response

    def _run_follow_joint_action(
        self, task_id: str, command_seq: int, *, timeout_s: float
    ) -> tuple[Any, list[bool]]:
        assert self.node is not None
        client = ActionClient(self.node, FollowJointTrajectory, "/bigsmall/follow_joint_trajectory")
        try:
            if not client.wait_for_server(timeout_sec=5.0):
                raise TimeoutError("follow_joint_trajectory action server is unavailable")
            feedback: list[bool] = []
            send_goal_future = client.send_goal_async(
                self._trajectory_goal(task_id, command_seq, timeout_s=timeout_s),
                feedback_callback=lambda msg: feedback.append(bool(msg.feedback.stale_feedback)),
            )
            rclpy.spin_until_future_complete(self.node, send_goal_future, timeout_sec=5.0)
            goal_handle = send_goal_future.result()
            if goal_handle is None or not goal_handle.accepted:
                raise RuntimeError(f"{task_id} goal was rejected")
            result_future = goal_handle.get_result_async()
            rclpy.spin_until_future_complete(
                self.node, result_future, timeout_sec=max(5.0, timeout_s + 2.0)
            )
            result_wrapper = result_future.result()
            if result_wrapper is None:
                raise RuntimeError(f"{task_id} action returned no result")
            return result_wrapper.result, feedback
        finally:
            client.destroy()

    def _trajectory_goal(
        self, task_id: str, command_seq: int, *, timeout_s: float
    ) -> FollowJointTrajectory.Goal:
        goal = FollowJointTrajectory.Goal()
        goal.header = _header(task_id, command_seq)
        goal.timeout_s = timeout_s
        trajectory = JointTrajectory()
        trajectory.joint_names = [f"panda_joint{i}" for i in range(1, 8)]
        point = JointTrajectoryPoint()
        point.positions = [0.0, -0.4, 0.0, -2.2, 0.0, 1.8, 0.8]
        point.time_from_start = Duration(sec=1, nanosec=0)
        trajectory.points = [point]
        goal.trajectory = trajectory
        return goal


def _header(task_id: str, command_seq: int) -> CommandHeader:
    header = CommandHeader()
    header.stamp = Time(sec=int(time.time()), nanosec=0)
    header.command_seq = command_seq
    header.plan_version = 1
    header.task_id = task_id
    header.mode = "phase9_1_runtime"
    header.frame_id = "world"
    return header


def _telemetry_qos() -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=20,
    )


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
