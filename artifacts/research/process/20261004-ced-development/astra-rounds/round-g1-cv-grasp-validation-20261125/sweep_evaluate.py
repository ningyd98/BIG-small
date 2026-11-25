"""Continuous swept hand volumes against registered solids and same-frame depth."""

import hashlib
import json
import math
from collections import Counter

import cv2
import numpy as np
from sweep_geometry import EPS, axis_basis, contact_patch, hand_sweeps, yaw_basis


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


class Scene:
    """Upright object and attachments share a rotation; cache all SAT projections."""

    def __init__(self, boxes, floor, view=None, known_static_volume=False):
        self.boxes = boxes
        self.floor = floor
        self.view = view
        self.known_static_volume = known_static_volume
        self._axes = {}
        self._rays = {}

    def distances(self, box):
        key = tuple(box.r.ravel())
        if key not in self._axes:
            a = box.r
            b = self.boxes[0].r
            assert all(np.array_equal(o.r, b) for o in self.boxes)
            axes = np.vstack((a.T, b.T, np.cross(a.T[:, None, :], b.T[None, :, :]).reshape(-1, 3)))
            n = np.linalg.norm(axes, axis=1)
            axes = axes[n > EPS] / n[n > EPS, None]
            centers = np.array([o.c for o in self.boxes]) @ axes.T
            radii = np.array([o.h for o in self.boxes]) @ np.abs(axes @ b).T
            self._axes[key] = (axes, centers, radii, np.abs(axes @ a))
        axes, centers, radii, local = self._axes[key]
        return (np.abs(centers - axes @ box.c) - radii - local @ box.h).max(axis=1)

    def depth(self, box):
        if self.view is None:
            return dict(
                state="FREE" if self.known_static_volume else "UNKNOWN",
                counts={},
                unknown_volume_upper_mm3=0.0
                if self.known_static_volume
                else 8 * np.prod(box.h) * 1e9,
                free_axial_margin_mm=None,
            )
        key = tuple(np.round(np.r_[box.c, box.h, box.r.ravel()], 12))
        if key not in self._rays:
            self._rays[key] = self.view.assess(box)
        return self._rays[key]


def evaluate(tool, center, tcp, yaw, angle, offset, scene):
    half = tool["target"].h
    patch = contact_patch(tool, tcp, center, half, yaw, angle, offset)
    a = yaw + angle
    axis = np.array([np.cos(a), np.sin(a), 0.0])
    phases = hand_sweeps(
        tool, tcp, axis, offset, patch["required_width_m"], patch["tcp_normal_offset_m"]
    )
    hits = []
    minimum = math.inf
    limiting = None
    counts = Counter()
    volume = 0.0
    largest_unknown = 0.0
    best_depth_margin = math.inf
    phase_evidence = []
    for phase, box in phases:
        distances = scene.distances(box)
        candidates = [("table", float(box.c[2] - np.abs(box.r[2]) @ box.h - scene.floor))]
        for index, value in enumerate(distances):
            name = scene.boxes[index].name
            permitted = (
                name == "object_geom"
                and phase == "close"
                and box.name != "hand"
                and patch["face_supported"]
                and patch["aperture_ok"]
                and abs(value) < EPS
            )
            if not permitted:
                candidates.append((name, float(value)))
        other, dist = min(candidates, key=lambda v: v[1])
        if dist < minimum:
            minimum = dist
            limiting = (phase, box.name, other)
        for name, d in candidates:
            if d <= EPS and not (
                name == "object_geom" and phase == "close" and box.name != "hand" and abs(d) < EPS
            ):
                hits.append((phase, box.name, name, d * 1000.0))
        d = scene.depth(box)
        counts.update(d["counts"])
        volume += d["unknown_volume_upper_mm3"]
        largest_unknown = max(largest_unknown, d["unknown_volume_upper_mm3"])
        if d["free_axial_margin_mm"] is not None:
            best_depth_margin = min(best_depth_margin, d["free_axial_margin_mm"])
        phase_evidence.append(
            (
                phase,
                box.name,
                round(dist * 1000, 4),
                d["state"],
                round(d["unknown_volume_upper_mm3"], 2),
                d["counts"],
            )
        )
    # When an occupied return has no contemporaneous external-vs-robot identity,
    # the present surface is known but its persistence along the future path is not.
    ray_states = [x[3] for x in phase_evidence]
    zlim = tool["com"]
    rot = yaw_basis(yaw)
    com = center + rot @ zlim
    basis = axis_basis(axis)
    com_t = float(basis[:, 0] @ (com - center))
    patch_t = patch["projected_patch_centroids_tz_m"][0][0]
    reasons = []
    if not patch["aperture_ok"]:
        reasons.append("nonpositive_aperture_margin")
    if not patch["face_supported"]:
        reasons.append("no_bilateral_finite_face_patch")
    if hits:
        reasons.append("registered_forbidden_contact")
    if reasons:
        status = "BLOCKED"
    elif "OCCUPIED" in ray_states:
        status = "UNKNOWN"
        reasons.append("current_return_in_sweep_identity_or_persistence_unconfirmed")
    elif "UNKNOWN" in ray_states:
        status = "UNKNOWN"
        reasons.append("required_volume_unobserved")
    else:
        status = "CLEAR"
    return dict(
        geometric_status="BLOCKED"
        if hits or not patch["face_supported"] or not patch["aperture_ok"]
        else "CLEAR",
        clearance=status,
        reasons=reasons,
        registered_min_sep_bound_mm=minimum * 1000,
        limiting_pair=limiting,
        hits=hits,
        unknown_volume_upper_mm3=volume,
        largest_component_unknown_upper_mm3=largest_unknown,
        ray_counts=dict(counts),
        free_ray_min_axial_margin_mm=best_depth_margin
        if math.isfinite(best_depth_margin)
        else None,
        phase_evidence=phase_evidence,
        patch=patch,
        mass_kg=tool["mass"],
        com_t_m=com_t,
        gravity_torque_about_patch_nm=(com_t - patch_t) * tool["mass"] * 9.81,
    )


def load_support(tool, center, tcp, yaw, axis_angle, offset, patch):
    """Quasistatic feasibility at registered face corners under a conservative friction pyramid."""
    if not patch["face_supported"] or not patch["aperture_ok"]:
        return {"status": "no_finite_face"}
    half = tool["target"].h
    n = np.array([np.cos(axis_angle), np.sin(axis_angle), 0.0])
    t = np.array([n[1], -n[0], 0.0])
    z = np.array([0.0, 0.0, 1.0])
    normal_half = float(np.abs(n) @ half)
    tan_half = float(np.abs(t) @ half)
    world_com = tool["com"]
    mg = 9.81 * tool["mass"]
    goal = np.r_[0.0, 0.0, mg, np.cross(world_com, [0.0, 0.0, mg])]
    generators = []
    groups = []
    normal_capacity = []
    mu = min(tool["finger_slide_friction"] + [tool.get("registered_object_friction", 0.8)])
    for side, (finger, sign, _rng) in enumerate(tool["fingers"]):
        fp = offset + patch["tcp_tangent_offset_m"] + finger.c[2]
        pz = tcp[2] - center[2] - finger.c[0]
        tang = (max(-tan_half, fp - finger.h[2]), min(tan_half, fp + finger.h[2]))
        levels = (max(-half[2], pz - finger.h[0]), min(half[2], pz + finger.h[0]))
        q = patch["contact_joint_positions_m"][side]
        normal_capacity.append(float(tool["actuator_kp"][side] * max(0.0, q)))
        for u in tang:
            for zz in levels:
                radius = sign * normal_half * n + u * t + zz * z
                for direction in (t, -t, z, -z):
                    force = -sign * n + mu * direction
                    generators.append(np.r_[force, np.cross(radius, force)])
                    groups.append(side)
    eq = np.array(generators).T
    ub = np.array([[g == s for g in groups] for s in (0, 1)], dtype=float)
    A = np.vstack((eq, -eq, ub))
    rhs = np.r_[goal, -goal, normal_capacity]
    result, x = cv2.solveLP(-np.ones((1, eq.shape[1])), np.column_stack((A, rhs)), 1e-9)
    good = result >= 0 and x is not None
    if good:
        x = x.ravel()
        good = bool(
            np.isfinite(x).all()
            and x.min() >= -1e-7
            and np.max(abs(eq @ x - goal)) <= 1e-7
            and np.all(ub @ x <= np.asarray(normal_capacity) + 1e-7)
        )
    return dict(
        status="nominal_static_equilibrium" if good else "not_supported_by_static_model",
        mu=mu,
        registered_mass_kg=tool["mass"],
        registered_com_object_m=tool["com"].tolist(),
        gravity_n=mg,
        stationary_position_servo_nominal_capacity_n=normal_capacity,
        required_normal_each_n=(ub @ x).tolist() if good else None,
        measured_bilateral_load=False,
        dynamic_holding_qualified=False,
    )


def orientation_wxyz(axis):
    # Local mechanical +x points down, +y closes, +z is tangent.
    b = axis_basis(axis)
    rv = cv2.Rodrigues(np.column_stack((-b[:, 2], b[:, 1], b[:, 0])))[0].ravel()
    a = np.linalg.norm(rv)
    return np.r_[np.cos(a / 2), (np.sin(a / 2) / a if a else 0.5) * rv].tolist()


def qualify(row, bounds, high_status):
    if row["clearance"] == "BLOCKED":
        return "BLOCKED", list(row["reasons"])
    reasons = list(row["reasons"])
    if high_status != "NOMINALLY_CLEAR":
        reasons.append("initial_route_unconfirmed")
    possible = [bounds.get(k) for k in ("tracking_mm", "stopping_mm", "object_pose_mm", "depth_mm")]
    if any(e is None or not math.isfinite(e) or e < 0 for e in possible):
        reasons.append("incomplete_motion_or_object_bound")
    elif sum(possible) >= row["registered_min_sep_bound_mm"]:
        reasons.append("no_positive_bounded_margin")
    if row["clearance"] != "CLEAR" and not reasons:
        reasons.append("uncertified_current_volume")
    return ("UNKNOWN", reasons) if reasons else ("CLEAR", [])
