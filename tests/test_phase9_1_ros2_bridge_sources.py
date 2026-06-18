"""Phase 9.1 ROS2/Isaac/MoveIt 边界回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path


def test_phase9_1_ros2_sim_bridge_source_preserves_runtime_boundaries() -> None:
    source = Path(
        "ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/sim_bridge_node.py"
    ).read_text(encoding="utf-8")

    assert "import rclpy" in source
    assert "QoSProfile" in source
    assert "ReliabilityPolicy.RELIABLE" in source
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in source
    assert "/clock" in source
    assert "/bigsmall/simulation/status" in source
    assert "command_seq" in source
    assert "DUPLICATE_REJECTED" in source
    assert "simulation_time_s" in source
    assert "wall_time_s" in source


def test_phase9_1_ros2_sim_bridge_source_covers_actions_cancel_and_reconnect() -> None:
    source = Path(
        "ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/sim_bridge_node.py"
    ).read_text(encoding="utf-8")

    assert "ActionServer" in source
    assert "MoveToPose" in source
    assert "FollowJointTrajectory" in source
    assert "/bigsmall/move_to_pose" in source
    assert "/bigsmall/follow_joint_trajectory" in source
    assert "cancel_callback" in source
    assert "timeout_s" in source
    assert "feedback_stale_count" in source
    assert "node_restart_generation" in source
    assert "bridge_session_id" in source
    assert "RECONNECT_READY" in source
    assert "backend_connected" in source
    assert "BACKEND_NOT_CONNECTED" in source


def test_phase9_1_ros2_frame_conversion_source_keeps_time_domains_explicit() -> None:
    source = Path(
        "ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/frame_conversion.py"
    ).read_text(encoding="utf-8")

    assert "world_to_ros_pose" in source
    assert "ros_pose_to_world" in source
    assert "simulation_time_s" in source
    assert "ros_time_s" in source
    assert "sensor_timestamp_s" in source
    assert "frame_id" in source


def test_phase9_1_ros2_sim_bridge_package_installs_node() -> None:
    cmake = Path("ros2_ws/src/bigsmall_sim_bridge/CMakeLists.txt").read_text(encoding="utf-8")
    package = Path("ros2_ws/src/bigsmall_sim_bridge/package.xml").read_text(encoding="utf-8")

    assert "ament_python_install_package" in cmake
    assert "scripts/bigsmall_sim_bridge_node" in cmake
    assert "<exec_depend>rclpy</exec_depend>" in package
    assert "<exec_depend>bigsmall_interfaces</exec_depend>" in package


def test_phase9_1_ros2_sim_bridge_has_ordered_shutdown_path() -> None:
    source = Path(
        "ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/sim_bridge_node.py"
    ).read_text(encoding="utf-8")

    stop_body = source.split("    def _stop(", maxsplit=1)[1].split(
        "    def _reset_world", maxsplit=1
    )[0]
    goal_body = source.split("    def _goal_callback(", maxsplit=1)[1].split(
        "    def _cancel_callback", maxsplit=1
    )[0]
    main_body = source.split("def main() -> None:", maxsplit=1)[1]

    assert "self._state.shutdown_requested = True" in stop_body
    assert "self._state.motion_active = False" in stop_body
    assert "GoalResponse.REJECT" in goal_body
    assert "ExternalShutdownException" in source
    assert "RCLError" in source
    assert main_body.index("executor.shutdown()") < main_body.index("node.close()")
    assert main_body.index("node.close()") < main_body.index("node.destroy_node()")
    assert main_body.index("node.destroy_node()") < main_body.index("rclpy.shutdown()")
