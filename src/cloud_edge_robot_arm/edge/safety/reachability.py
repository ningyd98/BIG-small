from __future__ import annotations

from math import hypot


def check_reachability(x: float, y: float, max_reach_m: float) -> bool:
    planar_distance = hypot(x, y)
    return planar_distance <= max_reach_m
