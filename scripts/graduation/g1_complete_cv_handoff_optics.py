"""Current 3-D pose of the registered G1 workpiece, including held and placed poses."""

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import axial

# Fit only to complete development trajectories. Unknown views retain no authorization.
CALIBRATION = {
    "both": {
        "anchor": [0.000716, 0.000488, 0.000419],
        "basis": [
            [0.001501, 0.001751, 0.002466],
            [0.001754, 0.001535, 0.011166],
            [0.002467, 0.011166, 0.001535],
        ],
    },
    "id8": {
        "anchor": [0.001055, 0.001094, 0.00055],
        "basis": [
            [0.001601, 0.01344, 0.016919],
            [0.013433, 0.001624, 0.019533],
            [0.016882, 0.019513, 0.001649],
        ],
    },
    "id8_opposite_edges": {
        "anchor": [0.001074, 0.001056, 0.000444],
        "basis": [
            [0.001516, 0.007734, 0.004664],
            [0.007733, 0.001545, 0.012403],
            [0.00467, 0.012403, 0.001545],
        ],
    },
    "id8_opposite_ink": {
        "anchor": [0.000811, 0.001202, 0.000471],
        "basis": [
            [0.001512, 0.006387, 0.005352],
            [0.006387, 0.001568, 0.014859],
            [0.005346, 0.014858, 0.001567],
        ],
    },
}


def _pixels(corners, width, height):
    uv = np.asarray(corners)
    lo = np.floor(uv.min(axis=0)).astype(int)
    hi = np.ceil(uv.max(axis=0)).astype(int)
    if min(lo) < 1 or hi[0] >= width - 1 or hi[1] >= height - 1:
        return None
    mask = np.zeros((hi[1] - lo[1] + 1, hi[0] - lo[0] + 1), np.uint8)
    cv2.fillConvexPoly(mask, np.rint(uv - lo).astype(np.int32), 255)
    yy, xx = np.nonzero(
        cv2.erode(mask, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    )
    if len(xx) < 55:
        return None
    return np.column_stack((xx + lo[0], yy + lo[1]))


def _rays(uv, fx, fy, cx, cy):
    return np.column_stack(((uv[:, 0] - cx) / fx, (uv[:, 1] - cy) / fy, np.ones(len(uv))))


def _fit_plane(cloud):
    pivot = cloud.mean(axis=0)
    local = cloud - pivot
    mat = np.column_stack((local[:, :2], np.ones(len(local))))
    use = np.ones(len(local), bool)
    for _ in range(3):
        coef, _, rank, _ = np.linalg.lstsq(mat[use], local[use, 2], rcond=None)
        if rank != 3:
            return None
        residual = local[:, 2] - mat @ coef
        use = abs(residual - np.median(residual)) <= 0.0028
        if np.count_nonzero(use) < 0.90 * len(use):
            return None
    n = np.array([-coef[0], -coef[1], 1.0])
    n /= np.linalg.norm(n)
    return n, pivot + np.array([0.0, 0.0, coef[2]]), use


def _opposite_edges(frame, depth, normal, pivot, anchor, forward, distance, tf):
    # Intersect native camera rays with the measured metric plane before comparing the
    # metric 100 mm carrier width. Both depth transitions and the actual quiet/ink border
    # are tested. A foreground occluder cannot establish an exterior edge.
    import base64

    gray = cv2.imdecode(
        np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_GRAYSCALE
    )
    eye = tf[:3, 3]
    rotation = tf[:3, :3]
    fy = frame.intrinsics[1]

    def project(world):
        local = (world - eye) @ rotation
        return local[:, :2] / local[:, 2, None] * frame.intrinsics[:2] + frame.intrinsics[2:]

    across = np.cross(normal, forward)
    opposite = anchor + distance * forward
    metric = []
    edge_counts = []
    near_samples = []
    for side in (-1, 1):
        ends = np.vstack([opposite + side * 0.05 * across + t * forward for t in (-0.037, 0.037)])
        projected = project(ends)
        if abs(projected[1, 0] - projected[0, 0]) < 8:
            return None
        lo, hi = np.sort(projected[:, 0])
        ux = np.arange(int(np.ceil(lo)), int(np.floor(hi)) + 1)
        slope = (projected[1, 1] - projected[0, 1]) / (projected[1, 0] - projected[0, 0])
        expected = projected[0, 1] + (ux - projected[0, 0]) * slope
        sign = int(np.sign(np.mean(expected) - project(opposite[None, :])[0, 1]))
        if not sign:
            return None
        width = abs((ends.mean(axis=0) - eye) @ rotation[:, 2])
        half = 0.05 * fy / width
        rad = max(4, int(np.ceil(0.016 * fy / width)))
        yy = np.rint(expected).astype(int)[:, None] + np.arange(-rad, rad + 1)
        xx = np.broadcast_to(ux[:, None], yy.shape)
        if (
            xx.min() < 1
            or xx.max() >= frame.width - 1
            or yy.min() < 3
            or yy.max() >= frame.height - 3
        ):
            return None

        def pred(uv):
            rays = _rays(uv, *frame.intrinsics) @ rotation.T
            return ((pivot - eye) @ normal) / (rays @ normal)

        plane = pred(np.column_stack((xx.ravel(), yy.ravel()))).reshape(xx.shape)
        match = (
            (abs(depth[yy - sign, xx] - plane) < 0.004)
            & (abs(depth[yy - 2 * sign, xx] - plane) < 0.004)
            & (depth[yy, xx] > plane + 0.006)
            & (depth[yy + sign, xx] > plane + 0.006)
        )
        fg = gray[yy - 2 * sign, xx].astype(float)
        bg = gray[yy + sign, xx].astype(float)
        last = gray[yy - sign, xx].astype(float)
        first = gray[yy, xx].astype(float)
        match &= (fg - bg > 22) & (last - first > 9)
        usable = match.sum(axis=1) == 1
        if usable.sum() < 4:
            edge_counts.append(0)
            continue
        ii, jj = np.nonzero(match & usable[:, None])
        yv = yy[ii, jj]
        xv = xx[ii, jj]
        interpol = np.clip(
            ((fg[ii, jj] + bg[ii, jj]) * 0.5 - first[ii, jj]) / (last[ii, jj] - first[ii, jj]), 0, 1
        )
        edge_uv = np.column_stack((xv, yv - sign * interpol))
        rr = _rays(edge_uv, *frame.intrinsics) @ rotation.T
        world = eye + rr * pred(edge_uv)[:, None]
        h = world - (anchor + distance * forward)
        along = h @ forward
        transverse = h @ across - side * 0.05
        strip = np.rint(yv - sign * half * 0.14).astype(int)
        ink = np.rint(yv - sign * half * 0.36).astype(int)
        view = (
            (abs(depth[strip, xv] - plane[ii, jj]) < 0.004)
            & (abs(depth[ink, xv] - plane[ii, jj]) < 0.004)
            & (gray[strip, xv].astype(float) - gray[ink, xv].astype(float) > 42)
        )
        if np.ptp(xv) < 4:
            edge_counts.append(0)
            continue
        # Measured edge pixels refer to the actual native plane samples inside that edge.
        puv = np.column_stack((xv, yv - 2 * sign))
        near_samples.extend(
            eye + (_rays(puv, *frame.intrinsics) * depth[puv[:, 1], puv[:, 0], None]) @ rotation.T
        )
        edge_counts.append(len(xv))
        metric.extend(zip(along, transverse, [side] * len(xv), view, strict=True))
    if not metric:
        return None
    points = np.array(metric)
    if min(edge_counts) >= 5:
        kind = "opposite_edges"
    else:
        points = points[points[:, 3] > 0]
        if len(points) < 6 or np.ptp(points[:, 0]) < 0.023:
            return None
        kind = "opposite_ink"
    t = points[:, 0]
    y = points[:, 1]
    slope, y0 = np.polyfit(t, y, 1)
    if np.max(abs(y - (slope * t + y0))) > 0.0019 or abs(slope) > 0.075 or abs(y0) > 0.016:
        return None
    # The observed strip constrains the lateral component of the actual marker-center
    # baseline. The known length supplies its longitudinal component on the same plane.
    baseline = np.sign(distance) * np.sqrt(max(distance**2 - y0**2, 0)) * forward + y0 * across
    return baseline / distance, kind, np.asarray(near_samples)


def measured_pose(frame, marker, geometry):
    """Reconstruct a dense metric common plane and its printed, in-plane orientation."""
    if not (
        marker.get("usable")
        and marker.get("frame_id") == frame.frame_id
        and marker.get("checksum") == frame.checksum_sha256
        and marker.get("asset_sha256") == geometry["pose_marker"]["marked_asset_sha256"]
        and marker.get("registration_id") == geometry["registration_id"]
        and sorted(marker.get("observed_ids", [])) == sorted(marker.get("usable_ids", []))
    ):
        return None
    ids = tuple(marker["usable_ids"])
    if ids not in ((7,), (8,), (7, 8)):
        return None
    info = geometry["development_dual"]
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    if frame.model_dump(mode="json", include=set(geometry["camera"])) != geometry["camera"]:
        return None
    surface = axial(frame)
    parts = []
    corners = []
    levers = []
    for code in ids:
        side = marker["by_id"][str(code)]
        uv = np.asarray(side["ordered_corners_px"])
        interior = _pixels(uv, frame.width, frame.height)
        if interior is None:
            return None
        xx, yy = interior.T
        z = surface[yy, xx]
        if not np.all(np.isfinite(z) & (z > 0)):
            return None
        points = (_rays(interior, *frame.intrinsics) * z[:, None]) @ tf[:3, :3].T + tf[:3, 3]
        parts.append(points)
        corners.append(uv)
        levers.append(
            np.asarray(info["markers"][str(code)]["object_T_marker"]).reshape(4, 4)[:3, 3]
        )
    fit = _fit_plane(np.concatenate(parts))
    if not fit:
        return None
    normal, pivot, use = fit
    if any(np.max(abs((points.mean(axis=0) - pivot) @ normal)) > 0.0012 for points in parts):
        return None
    topo = []
    for raw in corners:
        rays = _rays(np.vstack((raw, raw.mean(axis=0))), *frame.intrinsics) @ tf[:3, :3].T
        denom = rays @ normal
        if np.any(abs(denom) < 0.1):
            return None
        scale = ((pivot - tf[:3, 3]) @ normal) / denom
        topo.append(tf[:3, 3] + rays * scale[:, None])
    anchors = np.array([v[-1] for v in topo])
    if len(anchors) == 2:
        span = anchors[1] - anchors[0]
        if abs(np.linalg.norm(span) - 0.260) > 0.006:
            return None
        forward = span
        method = "both"
    else:
        points = topo[0]
        forward = (points[1] - points[0] + points[2] - points[3]) / 2
        if abs(np.linalg.norm(forward) - 0.075) > 0.007:
            return None
        method = "id" + str(ids[0])
    forward -= normal * (normal @ forward)
    forward /= np.linalg.norm(forward)
    if len(ids) == 1:
        opposite = _opposite_edges(
            frame, surface, normal, pivot, anchors[0], forward, 0.26 if ids[0] == 7 else -0.26, tf
        )
        if opposite:
            forward, kind, distant = opposite
            extended = _fit_plane(np.vstack([*parts, distant]))
            if extended:
                normal, pivot, use = extended
            forward -= normal * (normal @ forward)
            forward /= np.linalg.norm(forward)
            method = method + "_" + kind
    rotation = np.column_stack((forward, np.cross(normal, forward), normal))
    anchor = anchors.mean(axis=0)
    lever = np.mean(levers, axis=0)
    return dict(
        center_world_m=(anchor - rotation @ lever).tolist(),
        rotation_object_to_world=rotation.tolist(),
        anchor_world_m=anchor.tolist(),
        anchor_object_m=lever.tolist(),
        ids=list(ids),
        method=method,
        dense_plane_samples=int(sum(len(v) for v in parts)),
        plane_inliers=int(use.sum()),
        frame_id=frame.frame_id,
        checksum_sha256=frame.checksum_sha256,
    )


def rigid_pose(frame, marker, geometry):
    if (
        frame.source != "mujoco_camera"
        or frame.scene_id != geometry["development_dual"]["scene_id"]
    ):
        return None
    result = measured_pose(frame, marker, geometry)
    # Single-board orientation without independent carrier support missed its
    # registered matrix bound on an unseen trajectory. That view has no qualification.
    if result is None or result["method"] not in {"both", "id8_opposite_edges", "id8_opposite_ink"}:
        return None
    profile = CALIBRATION[result["method"]]
    centre_error = np.asarray(profile["anchor"]) + np.asarray(profile["basis"]) @ abs(
        np.asarray(result["anchor_object_m"])
    )
    angle = 2 * np.arcsin(min(1.0, np.linalg.norm(profile["basis"]) / (2 * np.sqrt(2))))
    result.update(
        anchor_error_object_m=profile["anchor"],
        basis_error_object=profile["basis"],
        center_error_m=float(np.linalg.norm(centre_error)),
        rotation_error_rad=float(angle),
        center_m=result["center_world_m"],
        rotation=result["rotation_object_to_world"],
    )
    return result


def directional_error(pose, local_points, world_direction):
    """Bound signed distance along the given world direction for each body-fixed point."""
    unit = np.asarray(world_direction, dtype=float)
    if (
        unit.shape != (3,)
        or not np.all(np.isfinite(unit))
        or abs(np.linalg.norm(unit) - 1.0) > 1e-6
    ):
        raise ValueError("unit world direction required")
    lever = abs(np.atleast_2d(local_points) - np.asarray(pose["anchor_object_m"]))
    extent = (
        np.asarray(pose["anchor_error_object_m"]) + lever @ np.asarray(pose["basis_error_object"]).T
    )
    return extent @ abs(unit @ np.asarray(pose["rotation_object_to_world"]))
