"""Object-local occupied boxes and intersections with the two existing support attachments."""

from itertools import combinations, product

import numpy as np

TOL_M = 1e-12
SIGNS = np.array(list(product((-1.0, 1.0), repeat=3)))
ARMS = ("left_finger_geom", "right_finger_geom", "hand")


def axes(rotation):
    a = np.eye(3)
    b = rotation.T
    normal = np.concatenate((a, b, np.cross(a[:, None, :], b[None, :, :]).reshape(9, 3)))
    lengths = np.linalg.norm(normal, axis=1)
    good = lengths > 1e-10
    return normal[good] / lengths[good, None], np.flatnonzero(good)


def local_box(model, data, name):
    obj = data.geom("object_geom")
    r = obj.xmat.reshape(3, 3)
    body = data.geom(name)
    box = model.geom(name)
    return r.T @ (body.xpos - obj.xpos), r.T @ body.xmat.reshape(3, 3), box.size.copy()


def describe(box):
    center, rotation, half = box
    corners = center + (SIGNS * half) @ rotation.T
    return {
        "center_m": center.tolist(),
        "local_from_box_rotation_row_major": rotation.ravel().tolist(),
        "half_m": half.tolist(),
        "corners_m": corners.tolist(),
        "axis_aligned_enclosing_bounds_m": [
            corners.min(axis=0).tolist(),
            corners.max(axis=0).tolist(),
        ],
    }


def intersect(box, lo, hi):
    """Enumerate all vertices satisfying both closed polyhedra, including zero-thickness faces."""
    center, rotation, half = box
    normals = np.concatenate((np.eye(3), -np.eye(3), rotation.T, -rotation.T))
    offsets = np.r_[hi, -lo, rotation.T @ center + half, -rotation.T @ center + half]
    vertices = []
    for idx in combinations(range(12), 3):
        a = normals[list(idx)]
        if abs(np.linalg.det(a)) <= 1e-10:
            continue
        q = np.linalg.solve(a, offsets[list(idx)])
        if np.max(normals @ q - offsets) <= TOL_M and not any(
            np.linalg.norm(q - p) <= 1e-10 for p in vertices
        ):
            vertices.append(q)
    if not vertices:
        return {
            "vertices_m": [],
            "positive_3d_volume": False,
            "volume_m3": 0.0,
            "min_m": None,
            "max_m": None,
        }
    points = np.array(sorted(vertices, key=tuple))
    rank = np.linalg.matrix_rank(points - points[0], tol=TOL_M)
    volume = 0.0
    if rank == 3:
        interior = points.mean(axis=0)
        counted = set()
        for n, h in zip(normals, offsets, strict=True):
            face_ids = tuple(np.flatnonzero(np.abs(points @ n - h) <= 1e-11))
            if len(face_ids) < 3 or face_ids in counted:
                continue
            polygon = points[list(face_ids)]
            origin = polygon.mean(axis=0)
            edges = polygon - origin
            basis = edges[np.argmax(np.linalg.norm(edges, axis=1))]
            basis = basis / np.linalg.norm(basis)
            ordered = edges[np.argsort(np.arctan2(edges @ np.cross(n, basis), edges @ basis))]
            area = 0.5 * abs(np.sum(np.cross(ordered, np.roll(ordered, -1, axis=0)) @ n))
            volume += area * abs(h - n @ interior) / 3
            counted.add(face_ids)
    return {
        "vertices_m": points.tolist(),
        "positive_3d_volume": bool(rank == 3 and volume > 0),
        "volume_m3": volume,
        "min_m": points.min(axis=0).tolist(),
        "max_m": points.max(axis=0).tolist(),
    }


def face(a, b):
    lo = np.maximum(a[0], b[0])
    hi = np.minimum(a[1], b[1])
    known = np.flatnonzero(np.abs(hi - lo) <= TOL_M)
    if len(known) != 1 or np.min(hi - lo) < -TOL_M:
        raise ValueError("compiled support has no single finite joining face")
    n = int(known[0])
    hi[n] = lo[n] = (lo[n] + hi[n]) * 0.5
    if min(np.delete(hi - lo, n)) <= 0:
        raise ValueError("zero attachment face area")
    return lo, hi


def zones(model, offset):
    result = {}

    def bounds(name):
        g = model.geom(name)
        if not np.array_equal(g.quat, [1.0, 0.0, 0.0, 0.0]):
            raise ValueError("registered attachment box is rotated")
        return g.pos - g.size, g.pos + g.size

    for code, axis in ((7, 1), (8, 0)):
        stem = f"g1_dual_id{code}_"
        beam = bounds(stem + "crossbar")
        post = bounds(stem + "upright")
        plate = bounds(stem + "plate")
        prefix = f"{offset}/id{code}/"
        result[prefix + "original_beam"] = beam
        result[prefix + "root_face"] = face(bounds("object_geom"), beam)
        result[prefix + "pillar_connection_face"] = face(beam, post)
        result[prefix + "plate_connection_face"] = face(post, plate)
        source_lo, source_hi = (a.copy() for a in beam)
        source_hi[axis] = 0.071
        result[prefix + "retained_beam_35_to_71_mm"] = (source_lo, source_hi)
        if offset == 30:
            extra_lo, extra_hi = (a.copy() for a in beam)
            extra_lo[axis] = 0.071
            result[prefix + "extension_71_to_86_mm"] = (extra_lo, extra_hi)
    return result


def separation(box, zone_centers, zone_half):
    center, rotation, half = box
    dirs, ids = axes(rotation)
    dist = (
        np.abs((zone_centers - center) @ dirs.T)
        - (zone_half @ np.abs(dirs).T)
        - (np.abs(dirs @ rotation) @ half)
    )
    idx = np.argmax(dist, axis=1)
    return dist[np.arange(len(idx)), idx], ids[idx]
