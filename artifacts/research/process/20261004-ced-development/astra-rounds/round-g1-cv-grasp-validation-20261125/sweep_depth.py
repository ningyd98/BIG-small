"""Conservative per-pixel frustum overlap against a single current axial depth image."""

import numpy as np


class DepthView:
    def __init__(self, depth, valid, intrinsics, camera_to_world, band):
        self.depth = np.asarray(depth)
        self.valid = np.asarray(valid, dtype=bool) & np.isfinite(depth) & (depth > 0)
        self.k = intrinsics
        self.tf = np.asarray(camera_to_world, dtype=float).reshape(4, 4)
        self.band = band
        self.mixed = np.zeros_like(self.valid)
        for dim in (0, 1):
            lo, hi = (slice(None, -1), slice(1, None))
            a, b = (
                ((lo, slice(None)), (hi, slice(None)))
                if dim == 0
                else ((slice(None), lo), (slice(None), hi))
            )
            jump = (
                self.valid[a] & self.valid[b] & (np.abs(self.depth[a] - self.depth[b]) > 2 * band)
            )
            self.mixed[a] |= jump
            self.mixed[b] |= jump

    @staticmethod
    def _slabs(o, d, h):
        parallel = np.abs(d) < 1e-12
        denom = np.where(parallel, 1.0, d)
        v0 = (-h - o) / denom
        v1 = (h - o) / denom
        near = np.where(parallel, -np.inf, np.minimum(v0, v1)).max(axis=-1)
        far = np.where(parallel, np.inf, np.maximum(v0, v1)).min(axis=-1)
        valid = ~(parallel & (np.abs(o) > h)).any(axis=-1) & (far >= np.maximum(near, 0.0))
        return near, far, valid

    def assess(self, box):
        fx, fy, cx, cy = self.k
        rc = self.tf[:3, :3]
        origin = self.tf[:3, 3]
        corners = (box.corners() - origin) @ rc
        volume = float(8 * np.prod(box.h) * 1e9)
        if corners[:, 2].min() <= 0:
            return dict(
                state="UNKNOWN",
                counts={"outside": 1},
                unknown_volume_upper_mm3=volume,
                free_axial_margin_mm=None,
            )
        pixels = corners[:, :2] / corners[:, 2, None] * [fx, fy] + [cx, cy]
        lim0 = np.ceil(pixels.min(axis=0) - 0.5 - 1e-10).astype(int)
        lim1 = np.floor(pixels.max(axis=0) + 0.5 + 1e-10).astype(int)
        xy = np.array(self.depth.shape[::-1])
        outside = bool(np.any(lim0 < 0) | np.any(lim1 >= xy))
        lo = np.maximum(lim0, 0)
        hi = np.minimum(lim1, xy - 1)
        if np.any(hi < lo):
            return dict(
                state="UNKNOWN",
                counts={"outside": 1},
                unknown_volume_upper_mm3=volume,
                free_axial_margin_mm=None,
            )
        v, u = np.mgrid[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
        dirs = np.stack(((u - cx) / fx, (v - cy) / fy, np.ones(u.shape)), axis=-1)
        relative = rc.T @ box.r
        dirs = dirs @ relative
        local_origin = (origin - box.c) @ box.r
        # Every point in a pixel cone lies at most this far from its centre ray on
        # each local box axis, for any optical range up to the farthest vertex.
        lateral = (np.abs(relative[0]) / (2 * fx) + np.abs(relative[1]) / (2 * fy)) * corners[
            :, 2
        ].max()
        near, far, hit = self._slabs(local_origin, dirs, box.h + lateral)
        near = np.maximum(near, corners[:, 2].min())
        far = np.minimum(far, corners[:, 2].max())
        hit &= far >= near
        near0, far0, hit0 = self._slabs(local_origin, dirs, box.h)
        d = self.depth[v, u]
        valid = self.valid[v, u]
        mixed = self.mixed[v, u]
        front = hit & valid & ~mixed & (far < d - self.band)
        occupied = hit & valid & ~mixed & hit0 & (near0 <= d + self.band) & (far0 >= d - self.band)
        back = hit & valid & ~mixed & (near > d + self.band)
        unknown = hit & ~(front | occupied)
        counts = dict(
            free=int(front.sum()),
            occupied=int(occupied.sum()),
            behind=int(back.sum()),
            invalid=int((hit & ~valid).sum()),
            mixed=int((hit & valid & mixed).sum()),
            footprint_boundary=int((unknown & valid & ~mixed & ~back).sum()),
            outside=int(outside),
        )
        interval = np.zeros_like(d, dtype=float)
        np.subtract(far**3, near**3, out=interval, where=unknown)
        bound = float(min(volume, max(0.0, interval.sum() / (3 * fx * fy) * 1e9)))
        # For partially observed occupied cells, portions behind the front remain unknown.
        tail = occupied & (far > d + self.band)
        if tail.any():
            bound = min(
                volume,
                bound
                + float(np.sum(far[tail] ** 3 - (d[tail] + self.band) ** 3) / (3 * fx * fy) * 1e9),
            )
        if outside or not hit.any():
            bound = volume
        state = (
            "OCCUPIED"
            if occupied.any()
            else "UNKNOWN"
            if unknown.any() or outside or not hit.any()
            else "FREE"
        )
        return dict(
            state=state,
            counts=counts,
            unknown_volume_upper_mm3=bound,
            free_axial_margin_mm=float(np.min(d[front] - self.band - far[front]) * 1000)
            if front.any()
            else None,
        )
