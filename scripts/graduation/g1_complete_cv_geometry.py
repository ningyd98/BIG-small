"""Registered geometry for the development arm and workpiece, independent of live physics."""

from dataclasses import dataclass
from itertools import product
from xml.etree import ElementTree as ET

import cv2
import numpy as np

DOWN = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
SIGNS = np.array(list(product((-1.0, 1.0), repeat=3)))


@dataclass(frozen=True)
class Box:
    name: str
    c: np.ndarray
    h: np.ndarray
    r: np.ndarray

    def corners(self):
        return self.c + (SIGNS * self.h) @ self.r.T

    def placed(self, origin, rotation):
        return Box(self.name, origin + rotation @ self.c, self.h, rotation @ self.r)


def visible_box(points, eye, box, tolerance):
    """Only camera-facing finite surface patches, with metric localization uncertainty."""
    p = (points - box.c) @ box.r
    camera = (eye - box.c) @ box.r
    front = (abs(camera) > box.h) & (abs(p * np.sign(camera) - box.h) <= tolerance)
    return (abs(p) <= box.h + tolerance).all(axis=1) & front.any(axis=1)


def box_gaps(a, centers, half_sizes, rotation):
    """Signed separating-axis distance lower bounds to equally oriented OBBs."""
    axes = np.vstack((a.r.T, rotation.T, np.cross(a.r.T[:, None], rotation.T).reshape(-1, 3)))
    lengths = np.linalg.norm(axes, axis=1)
    axes = axes[lengths > 1e-10] / lengths[lengths > 1e-10, None]
    gap = abs((centers - a.c) @ axes.T) - abs(axes @ a.r) @ a.h
    return (gap - half_sizes @ abs(axes @ rotation).T).max(axis=1)


def box_gap(a, b):
    return float(box_gaps(a, b.c[None], b.h[None], b.r)[0])


def translation_envelope(a, b):
    if not np.array_equal(a.r, b.r) or not np.array_equal(a.h, b.h):
        raise ValueError("fixed orientation and sizes required for a translation envelope")
    return Box(a.name, (a.c + b.c) / 2, a.h + abs((b.c - a.c) @ a.r) / 2, a.r)


def _v(node, name, default="0 0 0"):
    return np.fromstring(node.get(name, default), sep=" ")


def _box(node):
    if node.get("type") != "box" or set(node.attrib) & {"quat", "euler", "axisangle", "fromto"}:
        raise ValueError("unsupported local solid")
    return Box(node.get("name"), _v(node, "pos"), _v(node, "size"), np.eye(3))


class Model:
    def __init__(self, asset):
        root = ET.parse(asset).find("worldbody")
        obj = root.find("body[@name='object']")
        self.object = [_box(n) for n in obj.findall("geom") if float(n.get("mass", 0)) > 0]
        self.obj_c = np.array([b.c for b in self.object])
        self.obj_h = np.array([b.h for b in self.object])
        self.table = _box(root.find("geom[@name='table']"))
        region = root.find("body[@name='target_region']")
        self.region = _box(region.find("geom")).placed(_v(region, "pos"), np.eye(3))
        base = root.find("body[@name='panda_link0']")
        self.base = _v(base, "pos")
        self.base_size = _v(base.find("geom"), "size")
        self.chain = []
        body = base.find("body")
        while body.get("name") != "panda_hand":
            joint, geom = body.find("joint"), body.find("geom")
            self.chain.append(
                (
                    _v(body, "pos"),
                    _v(joint, "axis"),
                    _v(geom, "fromto").reshape(2, 3),
                    float(geom.get("size")),
                    geom.get("name"),
                )
            )
            body = body.find("body")
        self.hand_pos, self.hand_axis = _v(body, "pos"), _v(body.find("joint"), "axis")
        site = body.find("site[@name='tcp']")
        self.tcp = _v(site, "pos")
        self.site_radius = float(site.get("size"))
        self.hand = [_box(body.find("geom")).placed(-self.tcp, np.eye(3))]
        for name in ("left_finger", "right_finger"):
            finger = body.find(f"body[@name='{name}']")
            self.hand.append(
                _box(finger.find("geom")).placed(_v(finger, "pos") - self.tcp, np.eye(3))
            )
        if len(self.chain) != 6 or self.object[0].name != "object_geom":
            raise ValueError("unregistered arm or workpiece")

    def forward(self, joints):
        p, r = self.base.copy(), np.eye(3)
        links = []
        for angle, (trans, axis, ends, radius, name) in zip(joints[:6], self.chain, strict=True):
            p = p + r @ trans
            r = r @ cv2.Rodrigues(axis * angle)[0]
            links.append((name, p + ends @ r.T, radius))
        p += r @ self.hand_pos
        r = r @ cv2.Rodrigues(self.hand_axis * joints[6])[0]
        return p + r @ self.tcp, r, links

    def hand_at(self, tcp, rotation, fingers):
        centers = [b.c.copy() for b in self.hand]
        centers[1][1] += fingers[0]
        centers[2][1] -= fingers[1]
        return [
            Box(b.name, tcp + rotation @ c, b.h, rotation)
            for c, b in zip(centers, self.hand, strict=True)
        ]

    def hand_gaps(self, hand, center, rotation, fingers_may_touch=False):
        centers = center + self.obj_c @ rotation.T
        minimum, pair = float("inf"), None
        for index, box in enumerate(hand):
            gaps = box_gaps(box, centers, self.obj_h, rotation)
            if fingers_may_touch and index:
                gaps[0] = float("inf")
            i = int(np.argmin(gaps))
            if gaps[i] < minimum:
                minimum, pair = float(gaps[i]), [box.name, self.object[i].name]
        return dict(gap_m=minimum, pair=pair)

    def approach(self, center, rotation, low, opening):
        low = np.asarray(low, dtype=float)
        high = low.copy()
        high[2] = max(0.16, low[2] + 0.10)
        start = self.hand_at(high, DOWN, [opening, opening])
        end = self.hand_at(low, DOWN, [opening, opening])
        descent = [translation_envelope(a, b) for a, b in zip(start, end, strict=True)]
        result = self.hand_gaps(descent, center, rotation)
        # The full closing interval against the assembly is conservative. Only the
        # named cube can contact a fingertip during the actual closing operation.
        closed = self.hand_at(low, DOWN, [0.0, 0.0])
        closing = [translation_envelope(a, b) for a, b in zip(end, closed, strict=True)]
        close_result = self.hand_gaps(closing, center, rotation, fingers_may_touch=True)
        return min((result, close_result), key=lambda row: row["gap_m"])
