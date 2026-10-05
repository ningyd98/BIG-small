"""ROS2 QoS 配置，统一仿真桥接的可靠性和队列策略。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Phase9QoSProfile:
    reliability: str
    durability: str
    history: str
    depth: int


def qos_profiles() -> dict[str, Phase9QoSProfile]:
    sensor = Phase9QoSProfile(
        reliability="best_effort", durability="volatile", history="keep_last", depth=5
    )
    telemetry = Phase9QoSProfile(
        reliability="reliable", durability="volatile", history="keep_last", depth=20
    )
    command = Phase9QoSProfile(
        reliability="reliable", durability="transient_local", history="keep_last", depth=10
    )
    return {
        "sensor": sensor,
        "telemetry": telemetry,
        "command": command,
        "emergency_stop": command,
        "clock": Phase9QoSProfile(
            reliability="reliable", durability="volatile", history="keep_last", depth=10
        ),
    }
