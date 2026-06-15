from __future__ import annotations

from cloud_edge_robot_arm.simulation.isaac.protocol import IsaacCommand

_TRAJECTORY_SKILLS = {
    "MOVE_ABOVE",
    "APPROACH",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RETREAT",
}

_GRIPPER_SKILLS = {"GRASP", "RELEASE"}
_SENSOR_SKILLS = {"OBSERVE", "LOCATE_OBJECT", "VERIFY_RESULT"}


def command_requires_safety_approval(command_type: str) -> bool:
    return command_type in {"move_to_pose", "follow_joint_trajectory", "gripper_command"}


def skill_to_isaac_command(
    skill_name: str,
    payload: dict[str, object],
    *,
    command_seq: int,
    safety_approval_id: str,
) -> IsaacCommand:
    normalized = skill_name.upper()
    command_payload: dict[str, object] = {
        "skill": normalized,
        "parameters": payload,
        "safety_approval_id": safety_approval_id,
    }
    if normalized == "HOME":
        command_type = "follow_joint_trajectory"
    elif normalized in _TRAJECTORY_SKILLS:
        command_type = "follow_joint_trajectory"
    elif normalized in _GRIPPER_SKILLS:
        command_type = "gripper_command"
    elif normalized in _SENSOR_SKILLS:
        command_type = "sensor_request"
    elif normalized == "SAFE_STOP":
        command_type = "emergency_stop"
    else:
        raise ValueError(f"unsupported Isaac skill: {skill_name}")
    return IsaacCommand(
        command_type=command_type,
        payload=command_payload,
        command_seq=command_seq,
    )
