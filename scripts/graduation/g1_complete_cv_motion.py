"""Measured eight-physics-tick forecast and post-stop envelopes for a fixed development arm."""

from itertools import product
from math import gcd

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import SIGNS, Box


def enclose(box, vertex_sets, world_pad):
    local = (np.concatenate(vertex_sets) - box.c) @ box.r
    lower, upper = local.min(axis=0), local.max(axis=0)
    return Box(
        box.name,
        box.c + box.r @ ((lower + upper) / 2),
        (upper - lower) / 2 + abs(box.r).T @ world_pad,
        box.r,
    )


def support_axes():
    vectors = [
        v
        for v in product(range(-3, 4), repeat=3)
        if gcd(*v) == 1 and (v.count(0) > 0 or max(map(abs, v)) == 1)
    ]
    vectors = np.array(vectors, float)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def upper_support(vertices, axes, residual):
    projected = vertices @ axes.T
    between_ticks = 0.5 * abs(np.diff(projected, axis=0)).max(axis=(0, 1))
    return projected.max(axis=(0, 1)) + residual + between_ticks


def _rot(axis, theta):
    x, y, z = axis
    cross = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    a = theta[:, None, None]
    return np.eye(3) + np.sin(a) * cross + (1.0 - np.cos(a)) * (cross @ cross)


class MotionGeometry:
    def __init__(self, model):
        self.model = model
        self.axes = []
        self.centers = []
        self.sizes = []
        self.names = []
        for _, _, ends, radius, name in model.chain:
            axis = ends[1] - ends[0]
            length = np.linalg.norm(axis)
            a = axis / length
            ref = np.array([0.0, 1.0, 0.0]) if abs(a[1]) < 0.8 else np.array([1.0, 0.0, 0.0])
            b = np.cross(a, ref)
            b /= np.linalg.norm(b)
            self.axes.append(np.column_stack((a, b, np.cross(a, b))))
            self.centers.append(ends.mean(axis=0))
            self.sizes.append(np.array([length / 2 + radius, radius, radius]))
            self.names.append(name)
        self.names += [b.name for b in [*model.hand, *model.object]]
        self.load_start = len(model.chain) + len(model.hand)
        self.hand_start = len(model.chain)
        self.sizes = np.array(
            [*self.sizes, *[b.h for b in model.hand], *[b.h for b in model.object]]
        )

    def poses(self, q, fingers):
        n = len(q)
        r = np.broadcast_to(np.eye(3), (n, 3, 3))
        p = np.broadcast_to(self.model.base, (n, 3))
        c, rmat = [], []
        for i, (trans, axis, _, _, _) in enumerate(self.model.chain):
            p = p + r @ trans
            r = r @ _rot(axis, q[:, i])
            c.append(p + r @ self.centers[i])
            rmat.append(r @ self.axes[i])
        p = p + r @ self.model.hand_pos
        r = r @ _rot(self.model.hand_axis, q[:, 6])
        tcp = p + r @ self.model.tcp
        for i, b in enumerate(self.model.hand):
            cc = np.broadcast_to(b.c, (n, 3)).copy()
            if i:
                cc[:, 1] += (1 if i == 1 else -1) * fingers[:, i - 1]
            c.append(tcp + (r @ cc[:, :, None])[:, :, 0])
            rmat.append(r)
        return np.stack(c, axis=1), np.stack(rmat, axis=1), tcp, r

    def solids(self, q, fingers, obj_center, obj_rot):
        c, r, tcp, wrist = self.poses(q, fingers)
        loads = obj_center[:, None, :] + self.model.obj_c @ obj_rot.transpose(0, 2, 1)
        c = np.concatenate((c, loads), axis=1)
        r = np.concatenate((r, np.broadcast_to(obj_rot[:, None], (*loads.shape[:2], 3, 3))), axis=1)
        return c, r, tcp, wrist

    def vertices(self, c, r):
        return c[:, :, None, :] + (SIGNS * self.sizes[:, None, :]) @ r.transpose(0, 1, 3, 2)

    def forecast(self, q, f, dq, df, center, rot, dt, loaded):
        qq = q + dq * dt
        ff = f + df * dt
        # Supplied finger motion is bounded by the original physical slide range
        # with the measured overtravel retained at the starting frame.
        ff = np.clip(ff, np.minimum(f, 0.0), np.maximum(f, 0.04))
        c, r, tcp, wrist = self.poses(qq, ff)
        _, _, before, initial = self.poses(q, f)
        if loaded:
            rr = wrist @ initial.transpose(0, 2, 1)
            center = tcp + (rr @ (center - before)[:, :, None])[:, :, 0]
            rot = rr @ rot
        loads = center[:, None, :] + self.model.obj_c @ rot.transpose(0, 2, 1)
        c = np.concatenate((c, loads), axis=1)
        r = np.concatenate((r, np.broadcast_to(rot[:, None], (*loads.shape[:2], 3, 3))), axis=1)
        return c, r

    def envelopes(self, q, f, dq, df, center, rot, skill, profile, *, with_vertices=False):
        loaded = skill in ("LIFT", "MOVE_TO_REGION", "PLACE")
        q, f, dq, df, center, rot = (np.asarray(x)[None] for x in (q, f, dq, df, center, rot))
        ticks = np.arange(9)[:, None] / 240.0
        q, f, dq, df, center, rot = (np.repeat(x, 9, axis=0) for x in (q, f, dq, df, center, rot))
        c, r = self.forecast(q, f, dq, df, center, rot, ticks, loaded)
        vertices = self.vertices(c, r)
        # A linear-angular FK deviation between consecutive physical ticks is
        # covered conservatively by half the maximum adjacent corner movement.
        pad = (
            np.asarray(profile["normal"])
            + np.asarray(profile["stop"])
            + 0.5 * abs(np.diff(vertices, axis=0)).max(axis=(0, 2))
        )
        boxes = []
        for i, name in enumerate(self.names):
            b = Box(name, c[0, i], self.sizes[i], r[0, i])
            boxes.append(enclose(b, vertices[:, i], pad[i]))
        return (boxes, vertices) if with_vertices else boxes
