from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PoseLike(Protocol):
    position: object
    orientation: object


@dataclass(frozen=True)
class TimeStampedPose:
    frame_id: str
    pose: PoseLike
    simulation_time_s: float
    ros_time_s: float
    sensor_timestamp_s: float


def world_to_ros_pose(
    *,
    pose: PoseLike,
    frame_id: str,
    simulation_time_s: float,
    ros_time_s: float,
    sensor_timestamp_s: float,
) -> TimeStampedPose:
    """Convert a world-frame simulator pose to a ROS-frame stamped pose envelope."""

    return TimeStampedPose(
        frame_id=frame_id,
        pose=pose,
        simulation_time_s=float(simulation_time_s),
        ros_time_s=float(ros_time_s),
        sensor_timestamp_s=float(sensor_timestamp_s),
    )


def ros_pose_to_world(
    *,
    pose: PoseLike,
    frame_id: str,
    simulation_time_s: float,
    ros_time_s: float,
    sensor_timestamp_s: float,
) -> TimeStampedPose:
    """Convert a ROS-frame pose envelope back to simulator world-frame semantics."""

    return TimeStampedPose(
        frame_id=frame_id,
        pose=pose,
        simulation_time_s=float(simulation_time_s),
        ros_time_s=float(ros_time_s),
        sensor_timestamp_s=float(sensor_timestamp_s),
    )
