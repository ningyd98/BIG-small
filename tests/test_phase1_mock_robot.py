from __future__ import annotations

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def test_mock_robot_moves_grasps_places_and_records_history() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
    )

    assert robot.home().success is True
    assert robot.move_above("red_cube", z_offset_m=0.12).success is True
    assert robot.approach("red_cube").success is True
    assert robot.grasp("red_cube").success is True
    assert robot.lift(0.16).success is True
    assert robot.move_to_region("bin_a").success is True
    assert robot.place("bin_a").success is True
    assert robot.release().success is True
    assert robot.retreat(0.1).success is True

    assert robot.object_region("red_cube") == "bin_a"
    assert robot.state.gripper_open is True
    assert robot.state.tcp_pose.z >= robot.scene.minimum_safe_height_m
    assert [entry.skill for entry in robot.history][0] == "HOME"
    assert [entry.skill for entry in robot.history][-1] == "RETREAT"


def test_mock_robot_reports_structured_failures_without_raising() -> None:
    scene = MockScene.with_default_pick_place_scene()
    scene.objects["red_cube"].pose = Pose(x=10.0, y=10.0, z=0.02)
    robot = MockRobotAdapter(scene=scene, auto_connect=True, grasp_failures_remaining=1)

    unreachable = robot.move_above("red_cube", z_offset_m=0.12)
    first_grasp = robot.grasp("red_cube")
    robot.scene.objects["red_cube"].pose = Pose(x=0.2, y=0.0, z=0.02)
    robot.move_above("red_cube", z_offset_m=0.12)
    robot.approach("red_cube")
    second_grasp = robot.grasp("red_cube")

    assert unreachable.success is False
    assert unreachable.error is not None
    assert unreachable.error.code == "TARGET_UNREACHABLE"
    assert first_grasp.success is False
    assert first_grasp.error is not None
    assert first_grasp.error.code == "GRASP_FAILED"
    assert second_grasp.success is True
