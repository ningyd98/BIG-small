from __future__ import annotations


def command_requires_safety_approval(command_type: str) -> bool:
    return command_type in {"move_to_pose", "follow_joint_trajectory", "gripper_command"}
