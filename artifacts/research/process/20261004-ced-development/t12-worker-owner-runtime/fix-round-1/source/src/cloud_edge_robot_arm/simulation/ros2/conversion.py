"""ROS2 消息转换工具，确保仿真数据和内部模型字段一致。"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.models import ContactSnapshot, JointStateSnapshot


def joint_state_to_message(snapshot: JointStateSnapshot) -> dict[str, object]:
    return {
        "header": {"stamp": snapshot.sim_time_s, "frame_id": "robot_base"},
        "name": snapshot.names,
        "position": snapshot.positions,
        "velocity": snapshot.velocities,
        "effort": snapshot.efforts,
    }


def pose_to_message(pose: Pose, *, stamp: float, frame_id: str = "world") -> dict[str, object]:
    return {
        "header": {"stamp": stamp, "frame_id": frame_id},
        "pose": {
            "position": {"x": pose.x, "y": pose.y, "z": pose.z},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    }


def contacts_to_message(contacts: list[ContactSnapshot]) -> dict[str, object]:
    return {
        "contacts": [
            {
                "geom1": contact.geom1,
                "geom2": contact.geom2,
                "impulse": contact.impulse,
                "expected": contact.expected,
                "illegal": contact.illegal,
                "stamp": contact.sim_time_s,
            }
            for contact in contacts
        ]
    }
