"""ROS2 仿真安全限制检查工具，用关节边界拒绝越界轨迹。"""

from __future__ import annotations

import math
from typing import Any

PANDA_JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "panda_joint1": (-2.9671, 2.9671),
    "panda_joint2": (-1.8326, 1.8326),
    "panda_joint3": (-2.9671, 2.9671),
    "panda_joint4": (-3.1416, 0.0873),
    "panda_joint5": (-2.9671, 2.9671),
    "panda_joint6": (-0.0873, 3.8223),
    "panda_joint7": (-2.9671, 2.9671),
}


def trajectory_joint_limit_violation(trajectory: Any) -> dict[str, float | int | str] | None:
    joint_names = list(getattr(trajectory, "joint_names", []))
    checked_indexes = [
        (index, joint_name)
        for index, joint_name in enumerate(joint_names)
        if joint_name in PANDA_JOINT_LIMITS
    ]
    for point_index, point in enumerate(getattr(trajectory, "points", [])):
        positions = list(getattr(point, "positions", []))
        for joint_index, joint_name in checked_indexes:
            if joint_index >= len(positions):
                continue
            position = float(positions[joint_index])
            lower, upper = PANDA_JOINT_LIMITS[joint_name]
            if not math.isfinite(position) or position < lower or position > upper:
                return {
                    "joint_name": joint_name,
                    "point_index": point_index,
                    "position": position,
                    "lower": lower,
                    "upper": upper,
                }
    return None
