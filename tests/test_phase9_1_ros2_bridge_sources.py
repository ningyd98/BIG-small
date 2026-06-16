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
