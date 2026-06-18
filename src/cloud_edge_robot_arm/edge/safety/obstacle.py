"""障碍物距离检查。

用于计算 TCP/目标点到障碍物的安全余量，低于阈值时应拒绝或暂停。
"""

from __future__ import annotations

from math import hypot

from cloud_edge_robot_arm.edge.safety.models import Obstacle


def distance_to_obstacle(x: float, y: float, z: float, obstacle: Obstacle) -> float:
    return hypot(x - obstacle.x, y - obstacle.y)


def check_obstacle_clearance(
    x: float,
    y: float,
    z: float,
    obstacles: list[Obstacle],
    safety_distance: float,
) -> Obstacle | None:
    for obs in obstacles:
        dist = distance_to_obstacle(x, y, z, obs)
        if dist < obs.radius_m + safety_distance:
            return obs
    return None
