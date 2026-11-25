"""Optical bilateral closure domain for the registered original 70 mm workpiece and pads."""

import numpy as np

DESIGN_SHA256 = "99b85bbb122651f8d9e77c3b575c939593ffe3d3ccba39d2c0165f22289a277b"
WORKPIECE_HALF = 0.035
COM_Z = 0.00697725084
MASS_KG = 0.10126432
MIN_FRICTION = 0.8
MIN_NORMAL_PER_PAD_N = 2.0
ACCEL_M_S2 = 0.5


def _face_rectangle(pad_center, sign, toward, pad_axes, uncertainty):
    # Project both independent contact surfaces along the actual closing direction onto
    # their respective object faces. Clip a guaranteed inscribed rectangle from each
    # projected parallelogram. The object can rotate in the measured angle interval.
    centre = pad_center + toward * ((sign * WORKPIECE_HALF - pad_center[1]) / toward[1])
    projected = pad_axes - np.outer(toward, pad_axes[1] / toward[1])
    xz = projected[[0, 2]]
    inscribed = np.array([0.028, 0.035])
    divisor = float(max(abs(np.linalg.inv(xz)) @ inscribed))
    half = inscribed / max(1.0, divisor)
    lower = np.maximum(-WORKPIECE_HALF, centre[[0, 2]] - half + uncertainty)
    upper = np.minimum(WORKPIECE_HALF, centre[[0, 2]] + half - uncertainty)
    return lower, upper


def contact_opportunity(
    center,
    rotation,
    tcp,
    wrist,
    fingers,
    xyz_uncertainty,
    *,
    yaw_error_deg,
    yaw_uncertainty_deg,
    measured_rotation,
    support_height,
):
    """Use current camera and measured encoders. Mechanical force is an offline lower bound."""
    rot = np.asarray(rotation)
    hand = np.asarray(wrist)
    f = np.asarray(fingers)
    u = np.asarray(xyz_uncertainty)
    delta = np.asarray(tcp) - np.asarray(center)
    d = delta @ rot
    body_hand = rot.T @ hand
    toward = body_hand[:, 1]
    if not (
        np.all(np.isfinite([*d, *u, *f, yaw_error_deg, yaw_uncertainty_deg]))
        and np.all(u >= 0)
        and abs(toward[1]) > 0.98
        and len(f) == 2
    ):
        return dict(
            passes=False, reason="unmeasured_joint_closure_geometry", design_sha256=DESIGN_SHA256
        )
    # Norm includes the entire observation interval, not just the central estimate.
    worst = np.array(
        [abs(d[0] + 0.001) + u[0], abs(d[1]) + u[1], abs(d[2] - 0.010) + u[2], yaw_error_deg]
    )
    norm = float(np.sum((worst / np.array([0.012, 0.006, 0.015, 5.0])) ** 2))
    da = np.radians(yaw_uncertainty_deg)
    span = WORKPIECE_HALF * max(
        sum(abs(toward)), sum(abs(hand[:, 1] @ np.asarray(measured_rotation)))
    )
    span += WORKPIECE_HALF * (np.sin(da) + 1 - np.cos(da))
    offset = float(delta @ hand[:, 1])
    opening = f + 0.001 + np.array([offset, -offset]) - span - float(abs(toward) @ u)
    pad_axes = body_hand[:, [2, 0]] @ np.diag([0.028, 0.035])
    # Projection through each face adds the error from the maximum jaw travel, as
    # well as the registered support-centre and angular intervals from this frame.
    extent = WORKPIECE_HALF + max(f) + 0.009
    uxz = u[[0, 2]] + np.array([extent * (np.sin(da) + 1 - np.cos(da)), 0.0])
    floor = []
    overlaps = []
    margins = []
    moments = []
    centres = []
    for sign, encoder in zip((1.0, -1.0), f, strict=True):
        measured_pad = np.array([-0.005, sign * (0.009 + encoder), 0.0])
        zlow = (np.asarray(tcp) + hand @ measured_pad)[2] - abs(hand[2]) @ np.array(
            [0.035, 0.008, 0.028]
        )
        floor.append(float(zlow - support_height - u[2]))
        facing = measured_pad - np.array([0.0, sign * 0.008, 0.0])
        lo, hi = _face_rectangle(d + body_hand @ facing, sign, toward, pad_axes, uxz)
        span_xz = np.maximum(0.0, hi - lo)
        mid = (hi + lo) / 2
        com = np.array([0.0, COM_Z])
        margin = np.minimum(com - lo, hi - com)
        # The two opposed pads share the gravity/acceleration load. The conservative
        # normal-force floor and lower friction coefficient come from the registered
        # material and independent bilateral actuator measurements.
        load = MASS_KG * (9.81 + ACCEL_M_S2)
        residual = max(0.0, MIN_FRICTION * MIN_NORMAL_PER_PAD_N - load / 2)
        available = residual * min(span_xz) / 2
        required = load * abs(mid[0] - com[0]) + MASS_KG * ACCEL_M_S2 * abs(mid[1] - com[1])
        overlaps.append(span_xz.tolist())
        centres.append(mid.tolist())
        margins.append(float(min(margin)))
        moments.append([float(required), float(available)])
    enough_overlap = all(x >= 0.040 and z >= 0.032 for x, z in overlaps)
    com_supported = min(margins) >= 0.003
    enough_moment = all(available > required for required, available in moments)
    above_table = min(floor) >= 0.002
    enough_opening = min(opening) > 0 and min(f) >= 0.030 and max(f) <= 0.041
    decisions = [
        norm <= 1.0,
        yaw_error_deg <= 3.0,
        enough_overlap,
        com_supported,
        enough_moment,
        above_table,
        enough_opening,
    ]
    return dict(
        passes=bool(all(decisions)),
        design_sha256=DESIGN_SHA256,
        squared_combined_domain_radius=norm,
        inside_physical_combination=bool(norm <= 1),
        enough_overlap=enough_overlap,
        com_supported=com_supported,
        enough_moment=enough_moment,
        above_table=above_table,
        enough_opening=bool(enough_opening),
        robust_per_pad_gap_m=opening.tolist(),
        per_pad_xz_overlap_m=overlaps,
        per_pad_contact_center_xz_m=centres,
        per_pad_com_edge_margin_m=margins,
        per_pad_moment_demand_capacity_Nm=moments,
        per_pad_min_table_gap_m=floor,
    )
