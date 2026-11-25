"""Registered upright-box geometry and exact fixed-orientation sweep envelopes (metres)."""

from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

SIGNS = np.array(list(product((-1, 1), repeat=3)), dtype=float)
EPS = 1e-10


@dataclass
class Box:
    name: str
    c: np.ndarray
    h: np.ndarray
    r: np.ndarray

    def corners(self):
        return self.c + (SIGNS * self.h) @ self.r.T


def values(element, key, default):
    return np.fromstring(element.get(key, default), sep=" ")


def local_box(element):
    if element.get("type") != "box" or any(
        name in element.attrib
        for name in ("quat", "euler", "axisangle", "xyaxes", "zaxis", "fromto")
    ):
        raise ValueError("registration contains an unsupported oriented local shape")
    return Box(
        element.get("name"), values(element, "pos", "0 0 0"), values(element, "size", ""), np.eye(3)
    )


def parse_tool(path: Path):
    xml = ElementTree.parse(path)
    hand = xml.find(".//body[@name='panda_hand']")
    tcp = values(hand.find("site[@name='tcp']"), "pos", "0 0 0")
    palm = local_box(hand.find("geom[@name='hand']"))
    fingers = []
    for name, sign in (("left_finger", 1), ("right_finger", -1)):
        body = hand.find(f"body[@name='{name}']")
        joint = body.find("joint")
        assert not ({"quat", "euler", "axisangle", "xyaxes", "zaxis"} & set(body.attrib))
        assert joint.get("type") == "slide" and np.array_equal(
            values(joint, "axis", ""), [0, sign, 0]
        )
        b = local_box(body.find(f"geom[@name='{name}_geom']"))
        b.c = b.c + values(body, "pos", "0 0 0") - tcp
        fingers.append((b, sign, values(joint, "range", "")))
    palm.c = palm.c - tcp
    gaps = [sign * b.c[1] + rng[1] - b.h[1] for b, sign, rng in fingers]
    assert abs(gaps[0] - gaps[1]) < EPS
    obj = xml.find(".//body[@name='object']")
    default = xml.find("default/geom")
    attachments = []
    masses = []
    for elem in obj.findall("geom"):
        mass = float(elem.get("mass", "0"))
        if mass:
            masses.append((mass, values(elem, "pos", "0 0 0")))
        if elem.get("name") != "object_geom" and (
            int(elem.get("contype", default.get("contype", "1")))
            or int(elem.get("conaffinity", default.get("conaffinity", "1")))
        ):
            attachments.append(local_box(elem))
    actuators = [
        xml.find(f".//actuator/position[@joint='finger_{side}_joint']")
        for side in ("left", "right")
    ]
    return dict(
        palm=palm,
        fingers=fingers,
        opening=sum(gaps),
        attachments=attachments,
        target=local_box(obj.find("geom[@name='object_geom']")),
        mass=sum(m for m, _ in masses),
        com=sum(m * c for m, c in masses) / sum(m for m, _ in masses),
        registered_object_friction=float(
            obj.find("geom[@name='object_geom']")
            .get("friction", default.get("friction"))
            .split()[0]
        ),
        finger_slide_friction=[
            float(hand.find(f"body[@name='{name}']/geom").get("friction").split()[0])
            for name in ("left_finger", "right_finger")
        ],
        actuator_kp=[float(a.get("kp")) for a in actuators],
        pose_source="registered XML local transforms only",
    )


def axis_basis(axis):
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    if abs(axis[2]) > EPS:
        raise ValueError("closure axis must be horizontal")
    t = np.array([axis[1], -axis[0], 0.0])
    return np.column_stack((t, axis, [0.0, 0.0, 1.0]))


def yaw_basis(yaw):
    co, si = np.cos(yaw), np.sin(yaw)
    return np.array([[co, -si, 0.0], [si, co, 0.0], [0.0, 0.0, 1.0]])


def clearance(a, b):
    """Signed separating-axis bound; true distance can exceed the positive bound."""
    axes = np.vstack((a.r.T, b.r.T, np.cross(a.r.T[:, None, :], b.r.T[None, :, :]).reshape(-1, 3)))
    v = np.linalg.norm(axes, axis=1)
    axes = axes[v > EPS] / v[v > EPS, None]
    gaps = np.abs(axes @ (a.c - b.c)) - np.abs(axes @ a.r) @ a.h - np.abs(axes @ b.r) @ b.h
    return float(gaps.max())


def sweep_box(a, b):
    """Exact swept OBB for a translation parallel to one of the box axes."""
    assert np.allclose(a.r, b.r, atol=1e-10, rtol=0) and np.array_equal(a.h, b.h)
    shift = (b.c - a.c) @ a.r
    if np.count_nonzero(np.abs(shift) > EPS) > 1:
        raise ValueError("oblique translation needs a swept polytope or a segmented envelope")
    return replace(a, c=(a.c + b.c) / 2, h=a.h + np.abs(shift) / 2)


def world_parts(tool, tcp, basis, opening):
    out = []
    for b, sign, rng in [(tool["palm"], 0, [0.0, 0.0]), *tool["fingers"]]:
        if sign:
            width = opening if np.isscalar(opening) else opening[0 if sign == 1 else 1]
            q = width / 2 - (sign * b.c[1] - b.h[1])
            assert rng[0] - EPS <= q <= rng[1] + EPS
        else:
            q = 0.0
        c = np.array([b.c[2], b.c[1] + sign * q, -b.c[0]])
        out.append(Box(b.name, tcp + basis @ c, b.h[[2, 1, 0]], basis))
    return out


def hand_sweeps(tool, tcp, axis, offset, width, normal_offset=0.0):
    basis = axis_basis(axis)
    tcp = np.asarray(tcp)
    high = tcp.copy()
    high[2] = max(0.16, tcp[2] + 0.10)
    initial = world_parts(tool, high, basis, tool["opening"])
    high_offset = high + basis[:, 0] * offset
    low = tcp + basis[:, 0] * offset
    poses = [
        initial,
        world_parts(tool, high_offset, basis, tool["opening"]),
        world_parts(tool, low, basis, tool["opening"]),
        world_parts(
            tool,
            low,
            basis,
            [min(width - 2 * sgn * normal_offset, tool["opening"]) for sgn in (1, -1)],
        ),
    ]
    return [
        (phase, sweep_box(a, b))
        for phase, start, end in zip(
            ("high_shift", "descend", "close"), poses[:-1], poses[1:], strict=True
        )
        for a, b in zip(start, end, strict=True)
    ]


def contact_patch(tool, tcp, center, half, yaw, axis_angle, offset):
    """axis_angle is the closure angle from object-local x; offset along face tangent."""
    half = np.asarray(half)
    axis = np.array([np.cos(axis_angle), np.sin(axis_angle)])
    tangent = np.array([axis[1], -axis[0]])
    width = float(2 * np.abs(axis) @ half[:2])
    tang_half = float(np.abs(tangent) @ half[:2])
    angle_error = np.arctan2(np.min(np.abs(axis)), np.max(np.abs(axis)))
    aligned = angle_error < 1e-9
    world_angle = yaw + axis_angle
    world_axis = np.array([np.cos(world_angle), np.sin(world_angle), 0.0])
    world_tangent = np.array([world_axis[1], -world_axis[0], 0.0])
    dn = float(world_axis @ (tcp - center))
    dt = float(world_tangent @ (tcp - center))
    offset += dt
    sides = []
    centroids = []
    for b, _, _ in tool["fingers"]:
        u = offset + b.c[2]
        lo = max(-tang_half, u - b.h[2])
        hi = min(tang_half, u + b.h[2])
        z = tcp[2] - b.c[0]
        zd = max(center[2] - half[2], z - b.h[0])
        zu = min(center[2] + half[2], z + b.h[0])
        sides.append((max(0.0, hi - lo) * 1000, max(0.0, zu - zd) * 1000))
        centroids.append(((lo + hi) / 2, (zd + zu) / 2))
    overlap = np.min(sides, axis=0)
    return dict(
        required_width_m=width,
        margin_mm=(tool["opening"] - width) * 1000,
        aperture_ok=bool(width + 2 * abs(dn) < tool["opening"] - EPS),
        tcp_tangent_offset_m=dt,
        tcp_normal_offset_m=dn,
        minimum_open_side_margin_mm=(tool["opening"] / 2 - width / 2 - abs(dn)) * 1000,
        contact_joint_positions_m=[
            width / 2 - sg * dn - (sg * f.c[1] - f.h[1]) for f, sg, _ in tool["fingers"]
        ],
        face_alignment_error_deg=float(np.degrees(angle_error)),
        face_supported=bool(aligned and np.all(overlap >= [14 - 1e-7, 10 - 1e-7])),
        projected_tangent_overlap_limit_m=tang_half
        + min(b.h[2] for b, _, _ in tool["fingers"])
        - 0.014,
        face_patch_each_side_mm=sides,
        overlap_mm=overlap.tolist(),
        contact_area_each_mm2=[x * z if aligned else 0.0 for x, z in sides],
        projected_patch_centroids_tz_m=centroids,
        face_contact_nominal="plane" if aligned else "edge_or_corner",
    )


def world_assembly(tool, center, yaw):
    rot = yaw_basis(yaw)
    return [
        Box(b.name, center + rot @ b.c, b.h, rot @ b.r)
        for b in [tool["target"], *tool["attachments"]]
    ]
