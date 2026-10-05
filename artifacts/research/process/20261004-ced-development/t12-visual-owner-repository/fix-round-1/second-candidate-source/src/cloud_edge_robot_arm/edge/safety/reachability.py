"""可达性检查工具。

基于平面距离判断目标是否超过机械臂最大可达范围。
"""

from __future__ import annotations

from math import hypot


def check_reachability(x: float, y: float, max_reach_m: float) -> bool:
    planar_distance = hypot(x, y)
    return planar_distance <= max_reach_m
