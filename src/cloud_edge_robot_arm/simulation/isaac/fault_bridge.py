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
