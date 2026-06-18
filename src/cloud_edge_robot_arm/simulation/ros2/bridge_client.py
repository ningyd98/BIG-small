"""ROS2 仿真桥客户端，约束桥接调用而不触碰真实控制器。"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class Ros2BridgeStatus:
    status: str
    blockers: list[str]


class Ros2BridgeClient:
    def check_status(self) -> Ros2BridgeStatus:
        blockers: list[str] = []
        if importlib.util.find_spec("rclpy") is None:
            blockers.append("rclpy is not importable")
        return Ros2BridgeStatus(
            status="ROS_READY" if not blockers else "BLOCKED_BY_ENV",
            blockers=blockers,
        )
