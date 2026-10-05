"""Isaac 故障桥接器，把统一故障配置映射到 Isaac 场景。"""

from __future__ import annotations


def supported_faults() -> list[str]:
    return [
        "camera_noise",
        "occlusion",
        "object_slip",
        "collision_near_miss",
        "actuator_delay",
        "emergency_stop",
    ]
