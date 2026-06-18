"""Isaac 传感器桥接器，把仿真观测转换为统一 SensorFrame。"""

from __future__ import annotations


def sensor_topics() -> list[str]:
    return [
        "/bigsmall/camera/color",
        "/bigsmall/camera/depth",
        "/bigsmall/camera/camera_info",
        "/bigsmall/contacts",
    ]
