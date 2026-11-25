"""Current fixed-wrist angle from a decoded print and independent long-baseline optical edges."""

import base64

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_angle_domain import contact_opportunity
from scripts.graduation.g1_complete_cv_angle_edges import plate_yaw
from scripts.graduation.g1_complete_cv_calibrate import BAND, axial


def board_center_row(depth, gray, expected, slope, half, z, columns, *, allow_print_margin=False):
    rows = []
    printed = {-1: [], 1: []}
    for x in columns:
        if x < 2 or x >= depth.shape[1] - 2:
            continue
        measured = []
        for sign in (-1, 1):
            boundary = expected[1] + slope * (x - expected[0]) + sign * half
            edges = []
            for v in range(round(boundary) - 3, round(boundary) + 4):
                if v < 3 or v >= depth.shape[0] - 3:
                    continue
                inner = v - sign
                outer = v
                if not (
                    abs(depth[inner, x] - z) <= 2 * BAND
                    and abs(depth[inner - sign, x] - z) <= 2 * BAND
                    and depth[outer, x] > z + 2 * BAND
                ):
                    continue
                # Bright quiet margin on this physical plate versus its measured
                # background. Use its current antialiased luminance crossing.
                bg, fg = float(gray[outer + sign, x]), float(gray[inner - sign, x])
                first, last = float(gray[outer, x]), float(gray[inner, x])
                if fg - bg < 24 or last - first < 8:
                    continue
                t = np.clip(((bg + fg) * 0.5 - first) / (last - first), 0, 1)
                edges.append(outer - sign * t)
            if len(edges) == 1:
                measured.append(edges[0])
                if allow_print_margin:
                    y = edges[0]
                    strip = int(round(y - sign * 0.14 * half))
                    ink = int(round(y - sign * 0.35 * half))
                    if (
                        abs(depth[strip, x] - z) <= 2 * BAND
                        and abs(depth[ink, x] - z) <= 2 * BAND
                        and float(gray[strip, x]) - float(gray[ink, x]) >= 45
                    ):
                        printed[sign].append((x, y))
        if len(measured) == 2 and abs((measured[1] - measured[0]) / 2 - half) < 0.8:
            rows.append([x, *measured])
    if len(rows) < 5:
        if not allow_print_margin:
            return None
        sign = max(printed, key=lambda s: len(printed[s]))
        sample = np.asarray(printed[sign])
        if len(sample) < 6 or np.ptp(sample[:, 0]) < 7:
            return None
        xx = sample[:, 0] - expected[0]
        fit = np.polyfit(xx, sample[:, 1], 1)
        residual = abs(sample[:, 1] - np.polyval(fit, xx))
        if residual.max() > 0.45 or abs(fit[0] - slope) > 0.08:
            return None
        return dict(
            center_row=float(fit[1] - sign * half),
            columns=len(sample),
            span_px=float(np.ptp(sample[:, 0])),
            edge_sign=sign,
            maximum_pair_residual_px=float(residual.max()),
            slope=float(fit[0]),
            supporting_ink_margin=True,
        )
    a = np.array(rows)
    if np.ptp(a[:, 0]) < 5:
        return None
    mid = a[:, 1:].mean(axis=1)
    fit = np.polyfit(a[:, 0] - expected[0], mid, 1)
    residual = abs(mid - np.polyval(fit, a[:, 0] - expected[0]))
    if residual.max() > 0.65 or abs(fit[0] - slope) > 0.10:
        return None
    return dict(
        center_row=float(fit[1]),
        columns=len(a),
        span_px=float(np.ptp(a[:, 0])),
        maximum_pair_residual_px=float(residual.max()),
        slope=float(fit[0]),
    )


def fixed_wrist_angle(frame, marker, geometry):
    if (
        not marker.get("usable")
        or marker.get("frame_id") != frame.frame_id
        or marker.get("checksum") != frame.checksum_sha256
        or marker.get("registration_id") != geometry["registration_id"]
        or marker.get("asset_sha256") != geometry["pose_marker"]["marked_asset_sha256"]
    ):
        return None
    sides = marker.get("by_id", {})
    ids = marker.get("usable_ids", [])
    if not ids or not all(str(i) in sides for i in ids):
        return None
    centers = {i: np.array(sides[str(i)]["marker_center_world_m"]) for i in ids}
    if set(ids) == {7, 8}:
        delta = centers[8] - centers[7]
        span = float(np.linalg.norm(delta))
        if abs(span - 0.26) > 0.008:
            return None
        return dict(
            yaw_deg=float(np.degrees(np.arctan2(delta[1], delta[0]))),
            method="two_decoded_registered_centers",
            uncertainty_deg=0.30,
            span_m=span,
        )
    i = ids[0]
    other = 8 if i == 7 else 7
    orientation = np.asarray(marker["rotation_object_to_world"]).reshape(3, 3)
    current = centers[i]
    distance = 0.26 if i == 7 else -0.26
    opposite = current + orientation[:, 0] * distance
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    # This estimate applies to the registered vertical primary camera only.
    if not np.array_equal(tf[:3, :3], np.diag([1.0, -1.0, -1.0])):
        return None
    fx, fy, cx, cy = frame.intrinsics
    p = (opposite - tf[:3, 3]) @ tf[:3, :3]
    uv = p[:2] / p[2] * [fx, fy] + [cx, cy]
    slope = -orientation[1, 0] / orientation[0, 0]
    half = fy * 0.05 / p[2] / abs(orientation[0, 0])
    columns = np.arange(np.ceil(uv[0] - 0.72 * half), np.floor(uv[0] + 0.72 * half) + 1, dtype=int)
    gray = cv2.imdecode(
        np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_GRAYSCALE
    )
    depth = axial(frame)
    edge = board_center_row(depth, gray, uv, slope, half, p[2], columns, allow_print_margin=True)
    if edge:
        other_y = tf[1, 3] - (edge["center_row"] - cy) * p[2] / fy
        sine = (other_y - current[1]) / distance
        if abs(sine) < 0.16:
            one = edge.get("supporting_ink_margin", False)
            return dict(
                yaw_deg=float(np.degrees(np.arcsin(sine))),
                method="one_id_and_opposite_print_margin"
                if one
                else "one_id_and_opposite_plate_edges",
                decoded_id=i,
                edge_plate_id=other,
                edge=edge,
                uncertainty_deg=0.55 if one else 0.30,
            )
    grid_yaw = float(np.degrees(np.arctan2(orientation[1, 0], orientation[0, 0])))
    side = sides[str(i)]
    surface_z = float((current - tf[:3, 3]) @ tf[:3, 2])
    footprint = float(geometry["development_dual"]["markers"][str(i)]["marker_size_m"])
    boundary = plate_yaw(
        gray,
        depth,
        side["ordered_corners_px"],
        surface_z,
        0.5 * footprint * fy / surface_z,
        0.05 * fy / surface_z,
    )
    if boundary:
        # Two observations of the same plate constrain one current angle. A
        # disagreement outside both calibrated error intervals stays unknown.
        measured = boundary["yaw_deg"]
        edge_error = 0.85 if boundary["supporting_sides"] >= 5 else 1.20
        low = max(measured - edge_error, grid_yaw - 1.8)
        high = min(measured + edge_error, grid_yaw + 1.8)
        if low > high:
            return None
        return dict(
            yaw_deg=(low + high) / 2,
            uncertainty_deg=(high - low) / 2,
            method="one_id_print_and_carrier_edges",
            decoded_id=i,
            grid_yaw_deg=grid_yaw,
            carrier=boundary,
            angle_interval_deg=[low, high],
        )
    return dict(
        yaw_deg=grid_yaw, method="single_full_decoded_grid", decoded_id=i, uncertainty_deg=1.8
    )


def angle_error_deg(yaw, uncertainty, wrist_rotation, *, closure):
    r = np.asarray(wrist_rotation)
    wrist = np.degrees(np.arctan2(-r[0, 1], r[1, 1])) if closure else 0.0
    return float(abs((yaw - wrist + 180) % 360 - 180) + uncertainty)


def grasp_patch(
    center,
    object_rotation,
    tcp,
    wrist_rotation,
    fingers,
    *,
    xy_uncertainty_m,
    measured_rotation=None,
):
    """Project the registered solid into each measured inner finger face separately."""
    r = np.asarray(wrist_rotation)
    rot = np.asarray(object_rotation)
    delta = np.asarray(tcp) - center
    offset = delta @ rot
    # The 70 mm workpiece and the 56 mm-wide pads are registered solid geometry.
    half_width = 0.035 * float(np.abs(r[:, 1] @ rot).sum())
    if measured_rotation is not None:
        half_width = max(half_width, 0.035 * float(np.abs(r[:, 1] @ measured_rotation).sum()))
    closing_offset = float(delta @ r[:, 1])
    # Finger base is +/-9 mm, pad half-width is 8 mm. Independent encoder
    # positions keep asymmetric openings instead of assuming equal finger strokes.
    gaps = (
        np.array([fingers[0] + 0.001 + closing_offset, fingers[1] + 0.001 - closing_offset])
        - half_width
    )
    ux, uy = np.broadcast_to(np.asarray(xy_uncertainty_m, dtype=float), (2,))
    close_uncertainty = float(abs(r[:, 1] @ rot) @ np.array([ux, uy, 0.00075]))
    narrow = float(np.min(gaps)) - close_uncertainty
    tangent_overlap = min(0.056, max(0.0, 0.035 + 0.028 - abs(offset[0]) - ux))
    vertical_overlap = (
        max(0.0, min(0.035, offset[2] + 0.04) - max(-0.035, offset[2] - 0.03)) - 0.00075
    )
    # The physical fixture requested +/-3 mm at its motion endpoint; undisturbed
    # native IK actually realized these signed offsets across the full angle grid.
    # Each rectangle fits inside the measured four-corner hull at every
    # qualified angle. The second diagnostic varies reach farther with a
    # smaller lateral offset. Both are tested with the same native actuator.
    boxes = ((-0.00379, 0.00129, 0.00274), (-0.00479, 0.00319, 0.00169))
    inside_center = any(
        low <= offset[0] - ux and offset[0] + ux <= hi and abs(offset[1]) + uy <= dy
        for low, hi, dy in boxes
    )
    return dict(
        actual_open_m=float(sum(fingers) + 0.002),
        required_open_m=2 * half_width,
        per_pad_clearance_m=gaps.tolist(),
        minimum_inside_gap_m=narrow,
        xy_uncertainty_m=[float(ux), float(uy)],
        tcp_offset_object_m=offset.tolist(),
        tangent_overlap_m=tangent_overlap,
        vertical_overlap_m=vertical_overlap,
        within_measured_center_offsets=bool(inside_center),
        within_measured_vertical_band=bool(
            0.0067 <= offset[2] - 0.00075 and offset[2] + 0.00075 <= 0.0141
        ),
        passes=bool(
            inside_center
            and narrow > 0
            and tangent_overlap >= 0.055
            and vertical_overlap >= 0.0503
            and 0.0067 <= offset[2] - 0.00075
            and offset[2] + 0.00075 <= 0.0141
        ),
    )


def grasp_readiness(
    frame, marker, geometry, center, object_rotation, tcp, wrist_rotation, fingers, *, closure
):
    """Current optical orientation, and the actual bilateral contact opportunity before closure."""
    estimate = fixed_wrist_angle(frame, marker, geometry)
    if estimate is None:
        return None, None, "unmeasured_grasp_face_orientation"
    yaw = estimate["yaw_deg"]
    uncertainty = estimate["uncertainty_deg"]
    error = angle_error_deg(yaw, uncertainty, wrist_rotation, closure=closure)
    angle = dict(
        estimate,
        upper_error_deg=error,
        wrist_yaw_deg=float(np.degrees(np.arctan2(-wrist_rotation[0, 1], wrist_rotation[1, 1])))
        if closure
        else 0.0,
    )
    if error > 3.0:
        return angle, None, "angle_outside_observed_bilateral_grasp_domain"
    if not closure:
        return angle, None, None
    # Only a registered near-upright tabletop grasp uses lateral reconstruction.
    # Use current measured identity and the registered lever arm to suppress
    # the long-baseline centre error of the raw single-marker yaw.
    theta = np.radians(yaw)
    c, s = np.cos(theta), np.sin(theta)
    upright = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    observations = []
    for i in marker["usable_ids"]:
        code = str(i)
        origin = np.asarray(marker["by_id"][code]["marker_center_world_m"])
        lever = np.asarray(
            geometry["development_dual"]["markers"][code]["object_T_marker"]
        ).reshape(4, 4)[:3, 3]
        observations.append(origin - upright @ lever)
    refined = np.mean(observations, axis=0)
    # The decoded-centre localization and angular lever-arm terms are separate.
    # In the two-ID case the opposite lever arms cancel before uncertainty propagation.
    half_angle = np.radians(uncertainty)
    # In object axes a rotational error contributes first-order transverse
    # displacement and second-order longitudinal displacement of this lever.
    lever = 0.0 if len(observations) == 2 else 0.130
    xy_uncertainty = np.array(
        [0.00075 + lever * (1 - np.cos(half_angle)), 0.00075 + lever * np.sin(half_angle)]
    )
    patch = grasp_patch(
        refined,
        upright,
        tcp,
        wrist_rotation,
        fingers,
        xy_uncertainty_m=xy_uncertainty,
        measured_rotation=object_rotation,
    )
    patch.update(
        optical_center_world_m=refined.tolist(),
        original_center_world_m=np.asarray(center).tolist(),
        marker_upright_zz=float(np.asarray(object_rotation)[2, 2]),
    )
    opportunity = contact_opportunity(
        refined,
        upright,
        tcp,
        wrist_rotation,
        fingers,
        [*xy_uncertainty, 0.00075],
        yaw_error_deg=error,
        yaw_uncertainty_deg=uncertainty,
        measured_rotation=object_rotation,
        support_height=float(geometry["support_height_m"]),
    )
    patch["previous_center_height_gate"] = patch["passes"]
    patch["bilateral_contact_domain"] = opportunity
    patch["passes"] = opportunity["passes"]
    tabletop_center = float(geometry["support_height_m"]) + float(
        geometry["object_half_extent_m"][2]
    )
    if abs(refined[2] - tabletop_center) > 0.004:
        return angle, patch, "unknown_tabletop_support_for_upright_closure"
    return (
        angle,
        patch,
        None if patch["passes"] else "insufficient_measured_bilateral_opening_or_overlap",
    )
