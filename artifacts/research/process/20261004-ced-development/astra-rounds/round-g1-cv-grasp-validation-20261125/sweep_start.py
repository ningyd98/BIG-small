"""Bound the pose-to-high nominal path from a synchronized robot observation."""

import math
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np
from sweep_geometry import Box, values


def quaternion_matrix(quat):
    quat = np.array(quat, dtype=float)
    norm = np.linalg.norm(quat[1:])
    return cv2.Rodrigues(quat[1:] * (2 * np.arctan2(norm, quat[0]) / norm if norm else 0.0))[0]


def kin(xml: Path, joints):
    root = ElementTree.parse(xml).find(".//body[@name='panda_link0']")
    rot = np.eye(3)
    center = np.zeros(3)
    body = root
    while body is not None:
        center += rot @ values(body, "pos", "0 0 0")
        joint = body.find("joint")
        if joint is not None:
            idx = int(joint.get("name")[5:]) - 1
            rot = rot @ cv2.Rodrigues(values(joint, "axis", "") * joints[idx])[0]
        if body.get("name") == "panda_hand":
            return center + rot @ values(body.find("site[@name='tcp']"), "pos", ""), rot
        body = body.find("body")
    raise ValueError("unsupported registered kinematic chain")


def robot_state(measured, frame, xml, tool):
    if measured is None:
        return dict(
            status="UNKNOWN",
            reason="synchronized_robot_measurement_unavailable",
            finger_interval_m=[[0.0, 0.04], [0.0, 0.04]],
        )
    if (
        measured.get("frame_id") != frame.frame_id
        or measured.get("checksum_sha256", measured.get("checksum")) != frame.checksum_sha256
    ):
        raise ValueError("robot measurement belongs to another image")
    if (
        measured.get("sim_time_s") is not None
        and abs(measured["sim_time_s"] - frame.sim_time_s) > 1e-10
    ):
        raise ValueError("robot measurement has a different simulation timestamp")
    q = np.asarray(measured["joint_positions_rad"], dtype=float)
    if q.shape != (7,) or not np.isfinite(q).all():
        raise ValueError("invalid arm joint measurement")
    p, rot = kin(xml, q)
    pos = np.asarray(measured.get("tcp_position_m", p), dtype=float)
    if pos.shape != (3,) or np.linalg.norm(pos - p) > 0.001:
        raise ValueError("robot measurement and FK disagree")
    if measured.get("tcp_quaternion_wxyz") is not None:
        quat = np.asarray(measured["tcp_quaternion_wxyz"], dtype=float)
        if quat.shape != (4,) or not np.isclose(np.linalg.norm(quat), 1.0):
            raise ValueError("invalid robot orientation")
        given = quaternion_matrix(quat)
        if np.max(np.abs(given - rot)) > 1e-4:
            raise ValueError("robot orientation disagrees with registered FK")
    if measured.get("finger_positions_m") is not None:
        f = np.asarray(measured["finger_positions_m"], dtype=float)
        if f.shape != (2,) or not np.isfinite(f).all():
            raise ValueError("invalid finger measurement")
        # Slight overtravel is possible near a compliant joint limit.
        intervals = [[float(x), float(x)] for x in f]
    elif measured.get("gripper_open") is True:
        intervals = [[0.035, 0.04], [0.035, 0.04]]
    else:
        intervals = [[0.0, 0.04], [0.0, 0.04]]
    return dict(
        status="MEASURED",
        reason="same-frame seven measured joints and registered FK",
        tcp_m=pos.tolist(),
        rotation=rot.tolist(),
        fk_position_residual_mm=float(1000 * np.linalg.norm(pos - p)),
        finger_interval_m=intervals,
    )


def nominal_to_high(state, tool, high, rotation, scene):
    if state["status"] != "MEASURED":
        return dict(status="UNKNOWN", reason=state["reason"], segments=0)
    p = np.asarray(state["tcp_m"])
    a = np.array(state["rotation"])
    b = rotation
    rel = cv2.Rodrigues(a.T @ b)[0].ravel()
    theta = np.linalg.norm(rel)
    components = [(tool["palm"], 0, [0.0, 0.0])]
    for (part, sign, rng), interval in zip(
        tool["fingers"], state["finger_interval_m"], strict=True
    ):
        # The moving-to-high envelope includes measured start widths and both fully open endpoints.
        components.append((part, sign, [min(interval[0], rng[1]), max(interval[1], rng[1])]))
    radius = max(
        np.linalg.norm(part.c) + np.linalg.norm(part.h) + max(map(abs, interval))
        for part, _, interval in components
    )
    translation = np.linalg.norm(high - p)
    maxtravel = translation + theta * radius
    steps = max(1, math.ceil(maxtravel / 0.001))
    pad = maxtravel / (2 * steps)
    worst = math.inf
    pair = None
    unknown = 0
    occup = 0
    for i in range(steps):
        t = (i + 0.5) / steps
        R = a @ cv2.Rodrigues(rel * t)[0]
        cc = p + t * (high - p)
        for part, sign, iv in components:
            cin = part.c.copy()
            cin[1] += sign * (iv[0] + iv[1]) * 0.5
            ext = part.h.copy()
            ext[1] += (iv[1] - iv[0]) * 0.5
            box = Box(part.name, cc + R @ cin, ext + pad, R)
            gaps = scene.distances(box)
            g = min(float(gaps.min()), float(box.c[2] - np.abs(R[2]) @ box.h - scene.floor))
            if g < worst:
                worst = g
                pair = (i, box.name)
            d = scene.depth(box)["state"]
            unknown += d == "UNKNOWN"
            occup += d == "OCCUPIED"
    return dict(
        status="POSSIBLE_OVERLAP"
        if worst <= 0
        else ("UNKNOWN" if unknown or occup else "NOMINALLY_CLEAR"),
        segments=steps,
        max_vertex_motion_mm=maxtravel / steps * 1000,
        remaining_radius_mm=pad * 1000,
        minimum_envelope_sat_or_floor_mm=worst * 1000,
        limiting_segment=pair,
        unknown_boxes=unknown,
        current_occupied_return_boxes=occup,
        reason="linear TCP and geodesic wrist orientation, actual controller trajectory unverified",
    )
