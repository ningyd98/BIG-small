"""Estimate in-plane yaw from both black-print and white-carrier silhouette edges."""

import numpy as np


def plate_yaw(gray, depth, corners, z, marker_half_px, plate_half_px):
    center = np.mean(corners, axis=0)
    v = np.asarray(corners)[1] - np.asarray(corners)[0]
    theta = np.arctan2(-v[1], v[0])
    # Registered upward-facing prints present nearly horizontal edges in this workcell.
    if abs(theta) > np.radians(10):
        return None
    slopes, spans, residuals, normals = [], [], [], []
    for n in range(2):
        t = 1 - n
        normal_slope = (1 if n == 0 else -1) * np.tan(theta)
        for half, inside_lighter in ((marker_half_px, False), (plate_half_px, True)):
            tangents = np.arange(
                int(np.ceil(center[t] - 0.78 * half)), int(np.floor(center[t] + 0.78 * half)) + 1
            )
            for sign in (-1, 1):
                base = (
                    center[n] + normal_slope * (tangents - center[t]) + sign * half / np.cos(theta)
                )
                # Native pixel centres. Search a short perpendicular profile from
                # interior to exterior at each independent tangent coordinate.
                normal = np.rint(base).astype(int)[:, None] + sign * np.arange(-3, 4)
                across = np.broadcast_to(tangents[:, None], normal.shape)
                xx, yy = (normal, across) if n == 0 else (across, normal)
                if (
                    np.any(xx < 0)
                    or np.any(yy < 0)
                    or np.any(xx >= gray.shape[1])
                    or np.any(yy >= gray.shape[0])
                ):
                    return None
                val = gray[yy, xx].astype(float)
                axial = depth[yy, xx]
                if inside_lighter:
                    val = -val
                lo = np.min(val[:, 1:3], axis=1)
                hi = np.max(val[:, 4:6], axis=1)
                level = (lo + hi) / 2
                step = np.diff(val[:, 1:6], axis=1)
                cross = (
                    (val[:, 1:5] <= level[:, None]) & (val[:, 2:6] > level[:, None]) & (step > 8)
                )
                i = np.argmax(cross, axis=1) + 1
                ix = np.arange(len(i))
                ok = (cross.sum(axis=1) == 1) & (hi - lo > 38) & (abs(axial[:, 1] - z) < 0.010)
                if inside_lighter:
                    ok &= axial[:, 5] > z + 0.008
                else:
                    ok &= abs(axial[:, 5] - z) < 0.010
                if ok.sum() < 7 or np.ptp(tangents[ok]) < 7:
                    continue
                fraction = np.clip(
                    (level - val[ix, i]) / np.maximum(val[ix, i + 1] - val[ix, i], 1.0e-8), 0, 1
                )
                locations = normal[ix, i] + sign * fraction
                x = tangents[ok].astype(float)
                y = locations[ok]
                a, b = np.polyfit(x - x.mean(), y, 1)
                error = abs(y - (a * (x - x.mean()) + b))
                if error.max() > 0.45 or abs(a - normal_slope) > 0.12:
                    continue
                slopes.append(float(a * (1 if n == 0 else -1)))
                spans.append(float(np.sum((x - x.mean()) ** 2)))
                residuals.append(float(error.max()))
                normals.append(n)
    if len(slopes) < 3 or len(set(normals)) != 2:
        return None
    estimate = np.average(slopes, weights=spans)
    return dict(
        yaw_deg=float(np.degrees(np.arctan(estimate))),
        supporting_sides=len(slopes),
        slope_range=(min(slopes), max(slopes)),
        max_line_residual_px=max(residuals),
    )
