"""Candidate-specific native targets and a continuous envelope for directly moving to them."""

import math
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

PARENT = Path(__file__).resolve().parent.parent / "round-g1-cv-grasp-validation-20261125"
sys.path.insert(0, str(PARENT))
from sweep_evaluate import orientation_wxyz  # noqa: E402
from sweep_geometry import Box  # noqa: E402

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD  # noqa: E402


def mot_targets(central, rotation, object_delta):
    low = np.asarray(central) + np.asarray(rotation).reshape(3, 3) @ np.asarray(object_delta)
    high = low.copy()
    high[2] = max(0.16, low[2] + 0.10)
    return low, high


def wrist(axis, native):
    if native:
        if not np.allclose(np.asarray(axis), [0.0, 1.0, 0.0], rtol=0, atol=1e-9):
            raise ValueError("native wrist requires its signed world closure axis")
        return list(_DOWNWARD)
    return orientation_wxyz(axis)


def direct_envelope(state, tool, highs, goal_rot, scene):
    highs = np.array(highs)
    if state["status"] != "MEASURED":
        return dict(
            status="UNKNOWN",
            reason="initial same-frame arm/wrist/width unavailable",
            members=len(highs),
            segments=0,
            max_vertex_motion_mm=None,
            pieces={},
        )
    origin = np.asarray(state["tcp_m"])
    first = np.array(state["rotation"])
    rotvec = cv2.Rodrigues(first.T @ goal_rot)[0].ravel()
    components = [(tool["palm"], 0, [0.0, 0.0])]
    for (b, sign, rng), bounds in zip(tool["fingers"], state["finger_interval_m"], strict=True):
        components.append((b, sign, [min(bounds[0], rng[1]), max(bounds[1], rng[1])]))
    radius = max(
        np.linalg.norm(np.abs(b.c) + b.h) + max(abs(w) for w in interval)
        for b, _, interval in components
    )
    travel = np.max(np.linalg.norm(highs - origin, axis=1)) + np.linalg.norm(rotvec) * radius
    steps = max(1, math.ceil(travel / 0.001))
    pad = travel / (2 * steps)
    names = [b.name for b, _, _ in components]
    records = {
        n: dict(
            minimum_envelope_gap_mm=math.inf,
            limiting_pair=None,
            limiting_segment=None,
            unknown_volume_upper_mm3=0.0,
            largest_proven_free_box_volume_lower_mm3=0.0,
            known_free_boxes=0,
            ray_counts=Counter(),
            unknown_boxes=0,
            envelope_intersections=0,
            occupied_return_boxes=0,
            midpoint_hits=0,
        )
        for n in names
    }
    maximum_family_offset_mm = 0.0
    global_min = math.inf
    first_observation = None
    maximum_half_range = np.zeros(3)
    for i in range(steps):
        t = (i + 0.5) / steps
        R = first @ cv2.Rodrigues(rotvec * t)[0]
        # All candidate centre translations are represented explicitly, regardless of
        # whether max(minimum high, low + clearance) switches between endpoints.
        mids = origin + t * (highs - origin)
        reference = mids[0]
        local = (mids - reference) @ R
        lower = local.min(axis=0)
        upper = local.max(axis=0)
        half = (upper - lower) / 2
        maximum_half_range = np.maximum(maximum_half_range, half)
        route_c = reference + R @ ((upper + lower) / 2)
        maximum_family_offset_mm = max(
            maximum_family_offset_mm, float(np.max(np.linalg.norm(mids - route_c, axis=1)) * 1000)
        )
        for b, sign, iv in components:
            c = b.c.copy()
            c[1] += sign * (iv[0] + iv[1]) / 2
            h = b.h.copy()
            h[1] += (iv[1] - iv[0]) / 2
            box = Box(b.name, route_c + R @ c, h + half + pad, R)
            gaps = scene.distances(box)
            choices = [
                ("table", box.c[2] - np.abs(R[2]) @ box.h - scene.floor),
                *[(ob.name, g) for ob, g in zip(scene.boxes, gaps, strict=True)],
            ]
            other, d = min(choices, key=lambda item: item[1])
            r = records[b.name]
            if d * 1000 < r["minimum_envelope_gap_mm"]:
                r["minimum_envelope_gap_mm"] = float(d * 1000)
                r["limiting_pair"] = [b.name, other]
                r["limiting_segment"] = i
            global_min = min(global_min, d)
            if d <= 1e-10:
                r["envelope_intersections"] += 1
                if len(highs) == 1 and iv[1] - iv[0] < 1e-12:
                    exact = Box(b.name, route_c + R @ c, b.h, R)
                    if (
                        min(
                            scene.distances(exact).min(),
                            exact.c[2] - np.abs(R[2]) @ exact.h - scene.floor,
                        )
                        <= 0
                    ):
                        r["midpoint_hits"] += 1
            v = scene.depth(box)
            r["ray_counts"].update(v["counts"])
            r["unknown_volume_upper_mm3"] += v["unknown_volume_upper_mm3"]
            r["largest_proven_free_box_volume_lower_mm3"] = max(
                r["largest_proven_free_box_volume_lower_mm3"],
                v.get(
                    "free_volume_lower_mm3",
                    8 * np.prod(box.h) * 1e9 if v["state"] == "FREE" else 0.0,
                ),
            )
            r["known_free_boxes"] += v["state"] == "FREE"
            r["unknown_boxes"] += v["state"] == "UNKNOWN"
            r["occupied_return_boxes"] += v["state"] == "OCCUPIED"
            if first_observation is None and v["state"] != "FREE":
                first_observation = [i, b.name, v["state"]]
    actual = sum(s["midpoint_hits"] for s in records.values())
    if actual:
        status = "BLOCKED"
    elif global_min <= 1e-10 or first_observation:
        status = "UNKNOWN"
    else:
        status = "CLEAR"
    for q in records.values():
        q["ray_counts"] = dict(q["ray_counts"])
    return dict(
        status=status,
        predicted="linear TCP, geodesic rotation; observed physical route unavailable",
        members=len(highs),
        segments=steps,
        max_vertex_motion_mm=1000 * travel / steps,
        within_segment_pad_mm=1000 * pad,
        max_family_center_displacement_mm=maximum_family_offset_mm,
        family_extra_local_half_extent_upper_mm=(1000 * maximum_half_range).tolist(),
        minimum_union_gap_mm=1000 * global_min,
        actual_midpoint_hits=actual,
        pieces=records,
        first_unconfirmed_ray_box=first_observation,
        initial_position_m=origin.tolist(),
        initial_orientation_matrix=first.tolist(),
        goal_orientation_matrix=goal_rot.tolist(),
        initial_finger_ranges_m=state["finger_interval_m"],
        endpoint_minimum_m=highs.min(axis=0).tolist(),
        endpoint_maximum_m=highs.max(axis=0).tolist(),
    )
