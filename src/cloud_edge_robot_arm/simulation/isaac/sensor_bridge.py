from __future__ import annotations


def sensor_topics() -> list[str]:
    return [
        "/bigsmall/camera/color",
        "/bigsmall/camera/depth",
        "/bigsmall/camera/camera_info",
        "/bigsmall/contacts",
    ]
