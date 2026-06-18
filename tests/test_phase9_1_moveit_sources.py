"""Phase 9.1 ROS2/Isaac/MoveIt 边界回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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


def test_phase9_1_moveit_safety_runner_captures_collision_and_timeout_evidence() -> None:
    source = Path("scripts/phase9/run_moveit_safety_evidence.py").read_text(encoding="utf-8")

    for token in (
        "baseline_plan",
        "collision_object",
        "planning_scene_confirmed",
        "replanned_or_rejected",
        "collision_free",
        "trajectory_delta",
        "moveit_error_code",
        "planning_start_wall_time",
        "planning_end_wall_time",
        "normal_budget_success",
        "timeout_budget_result",
        "timeout_attempts",
        "timeout_budget_candidates_ms",
        "log_integrity",
        "FORBIDDEN_LOG_MARKERS",
    ):
        assert token in source


def test_phase9_1_moveit_safety_runner_handles_normalized_planning_scene_objects() -> None:
    source = Path("scripts/phase9/run_moveit_safety_evidence.py").read_text(encoding="utf-8")

    assert "_effective_collision_object_pose" in source
    assert "planning_scene_object" in source
