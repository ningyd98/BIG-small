from __future__ import annotations

from pathlib import Path


def test_phase9_1_moveit_boundary_source_covers_required_safety_checks() -> None:
    source = Path(
        "ros2_ws/src/bigsmall_robot_bridge/bigsmall_robot_bridge/moveit_boundary_node.py"
    ).read_text(encoding="utf-8")

    assert "MoveItPy" in source
    assert "PlanningSceneMonitor" in source
    assert "check_reachability" in source
    assert "check_joint_limits" in source
    assert "update_collision_scene" in source
    assert "planning_failure" in source
    assert "cancel_execution" in source
    assert "emergency_stop_boundary" in source
    assert "safety_clearance_id" in source
    assert "follow_joint_trajectory_client" in source
    assert "DIRECT_MOVEIT_EXECUTION_FORBIDDEN" in source


def test_phase9_1_moveit_boundary_package_installs_node() -> None:
    cmake = Path("ros2_ws/src/bigsmall_robot_bridge/CMakeLists.txt").read_text(encoding="utf-8")
    package = Path("ros2_ws/src/bigsmall_robot_bridge/package.xml").read_text(encoding="utf-8")

    assert "ament_python_install_package" in cmake
    assert "scripts/bigsmall_moveit_boundary_node" in cmake
    assert "<exec_depend>moveit_ros_planning_interface</exec_depend>" in package
    assert "<exec_depend>bigsmall_interfaces</exec_depend>" in package
