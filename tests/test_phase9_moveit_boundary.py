from __future__ import annotations

from cloud_edge_robot_arm.simulation.isaac.robot_controller import command_requires_safety_approval


def test_phase9_moveit_trajectory_execution_requires_bigsmall_safety_boundary() -> None:
    assert command_requires_safety_approval("follow_joint_trajectory")
    assert not command_requires_safety_approval("read_joint_states")
