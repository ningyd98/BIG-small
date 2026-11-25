"""Current image, encoder and clock evidence for the relation between the hand, block and table."""

import base64
import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import BAND, axial
from scripts.graduation.g1_complete_cv_geometry import SIGNS, Model, box_gap
from scripts.graduation.g1_complete_cv_handoff_optics import (
    _fit_plane,
    _pixels,
    _rays,
    directional_error,
    measured_pose,
)
from scripts.graduation.g1_complete_cv_optical_identity import OpticalIdentity


def frozen_red_geometry(tree, asset_path):
    """Load the print fitter through this isolated runtime's verified source catalogue."""
    from scripts.graduation.g1_complete_cv_red_geometry import RedInkGeometry
    from scripts.graduation.perception_io import pinned

    lock = tree / "runtime-build.json"
    if not lock.is_file():
        return None
    generation = tree.parent.name
    library = "scripts/graduation/g1_complete_cv_red_ink.so"
    expected = pinned(lock, generation)["runtime_files_sha256"].get(library)
    if expected:
        return RedInkGeometry(asset_path, tree / library, expected)
    return None


@lru_cache(maxsize=1)
def _profile():
    return json.loads(Path(__file__).with_name("g1_complete_cv_relation_profile.json").read_bytes())


@lru_cache(maxsize=2)
def _model(path):
    return Model(path)


def _window(frame, world, radius):
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    local = (world - tf[:3, 3]) @ tf[:3, :3]
    uv = local[:2] / local[2] * frame.intrinsics[:2] + frame.intrinsics[2:]
    u, v = np.rint(uv).astype(int)
    x0 = max(0, u - radius)
    x1 = min(frame.width, u + radius + 1)
    y0 = max(0, v - radius)
    y1 = min(frame.height, v + radius + 1)
    y, x = np.mgrid[y0:y1, x0:x1]
    return x, y


def _cloud(frame, x, y, depth):
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    uv = np.column_stack((x.ravel(), y.ravel()))
    rays = _rays(uv, *frame.intrinsics) @ tf[:3, :3].T
    return (tf[:3, 3] + rays * depth[y, x].reshape(-1, 1)).reshape((*x.shape, 3))


def red_face_pose(frame, marker, geometry, rgb, depth, base=None):
    """The real red top face and independently decoded ink sample a common metric plane."""
    original = base or measured_pose(frame, marker, geometry)
    if not original:
        return None, None
    rot = np.asarray(original["rotation_object_to_world"])
    center = np.asarray(original["center_world_m"])
    x, y = _window(frame, center + rot[:, 2] * 0.035, 16)
    if not x.size:
        return None, None
    cloud = _cloud(frame, x, y, depth)
    local = (cloud - center) @ rot
    r, g, b = rgb[y, x].astype(float).transpose(2, 0, 1)
    red = (r > 1.25 * g + 7) & (r > 1.25 * b + 7) & (abs(local[:, :, :2]).max(axis=2) < 0.042)
    ink_offset = 0.00005
    top = red & (abs(local[:, :, 2] - 0.035) < BAND)
    pts = cloud[top]
    if len(pts) < 12:
        return None, None
    span = np.ptp(local[top, :2], axis=0)
    if max(span) < 0.053 or min(span) < 0.003:
        return None, None
    code = original["ids"]
    interior = []
    for k in code:
        raw = _pixels(marker["by_id"][str(k)]["ordered_corners_px"], frame.width, frame.height)
        if raw is None:
            return None, None
        interior.append(_cloud(frame, raw[:, 0], raw[:, 1], depth))
    # Balance the spatially separated surfaces; the small visible portion of the red face
    # may comprise two real columns yet span the full width of the block.
    fit = _fit_plane(
        np.concatenate(
            [
                *interior,
                np.tile(
                    pts + rot[:, 2] * ink_offset,
                    (max(1, min(8, sum(map(len, interior)) // len(pts))), 1),
                ),
            ]
        )
    )
    if not fit:
        return None, None
    normal, pivot, _ = fit
    top_res = (pts - pivot) @ normal + ink_offset
    if np.quantile(abs(top_res), 0.9) > 0.0024 or np.max(abs(top_res)) >= BAND:
        return None, None
    forward = rot[:, 0] - normal * (rot[:, 0] @ normal)
    forward /= np.linalg.norm(forward)
    orientation = np.column_stack((forward, np.cross(normal, forward), normal))
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    eye = tf[:3, 3]
    anchors = []
    for k in code:
        uv = np.mean(marker["by_id"][str(k)]["ordered_corners_px"], axis=0)[None, :]
        ray = (_rays(uv, *frame.intrinsics) @ tf[:3, :3].T)[0]
        anchors.append(eye + ray * ((pivot - eye) @ normal) / (ray @ normal))
    anchor = np.mean(anchors, axis=0)
    lever = np.asarray(original["anchor_object_m"])
    c = anchor - orientation @ lever
    # Distinct native depth returns spanning a registered side (a real rim), plus
    # boundaries of the red face in image space. Avoid treating mixed boundary depth
    # as a Euclidean corner of the block.
    mask = (
        red
        & (np.max(abs(local[:, :, :2]), axis=2) > 0.027)
        & (local[:, :, 2] < 0.028)
        & (local[:, :, 2] > -0.042)
    )
    rim_lines = []
    normal_depth = ((cloud - pivot) @ normal) + ink_offset
    active = red & (abs(normal_depth) < BAND)
    for col in np.flatnonzero(active.sum(axis=0) >= 8):
        hits = np.nonzero(active[:, col])[0]
        a, b = hits[0], hits[-1]
        if a < 1 or b >= len(y) - 1 or b - a < 10 or len(hits) < 0.70 * (b - a + 1):
            continue
        if normal_depth[a - 1, col] >= -0.006 or normal_depth[b + 1, col] >= -0.006:
            continue
        uv = np.array([[x[a, col], y[a, col] - 0.5], [x[b, col], y[b, col] + 0.5]])
        rr = _rays(uv, *frame.intrinsics) @ tf[:3, :3].T
        points = eye + rr * (((pivot - eye) @ normal - ink_offset) / (rr @ normal))[:, None]
        rim_lines.append(points.tolist())
    evidence = dict(
        red_top_samples=int(top.sum()),
        red_top_span_m=span.tolist(),
        red_face_p90_residual_m=float(np.quantile(abs(top_res), 0.9)),
        red_side_samples=int(mask.sum()),
        red_side_span_m=float(np.ptp(local[mask, 2])) if mask.any() else 0.0,
        red_side_low_m=float(local[mask, 2].min()) if mask.any() else None,
        exposed_top_rim_lines_world_m=rim_lines,
    )
    raw = dict(
        original,
        method="id8_and_red_top",
        center_world_m=c.tolist(),
        rotation_object_to_world=orientation.tolist(),
        anchor_world_m=anchor.tolist(),
    )
    return raw, evidence


def _certify(raw):
    cert = _profile().get("single_id8_red_print")
    if not raw or raw["ids"] != [8] or not cert or not cert["enabled"]:
        return None
    basis = np.asarray(cert["basis"])
    anchor = np.asarray(cert["anchor"])
    return dict(
        raw,
        basis_error_object=basis.tolist(),
        anchor_error_object_m=anchor.tolist(),
        center_m=raw["center_world_m"],
        rotation=raw["rotation_object_to_world"],
        center_error_m=float(
            np.linalg.norm(anchor + basis @ abs(np.asarray(raw["anchor_object_m"])))
        ),
        rotation_error_rad=float(2 * np.arcsin(np.linalg.norm(basis) / (2 * np.sqrt(2)))),
    )


def transverse_edges(face, pose, jaw):
    """Extend two measured ends of the same visible top strip to the two extreme pad directions."""
    if not face or not face["exposed_top_rim_lines_world_m"]:
        return None
    r = np.asarray(pose["rotation_object_to_world"])
    c = np.asarray(pose["center_world_m"])
    j = jaw @ r
    if abs(j[1]) < 0.997 or r[2, 2] < 0.998:
        return None
    extent = 0.035 * np.sum(abs(j))
    edges = []
    for line in np.asarray(face["exposed_top_rim_lines_world_m"]):
        obj = (line - c) @ r
        sign = np.sign(obj[:, 1])
        if (
            sign.prod() != -1
            or (abs(abs(obj[:, 1]) - 0.035) > 0.006).any()
            or (abs(obj[:, 0]) > 0.042).any()
        ):
            continue
        local = np.column_stack((obj[:, 0], sign * 0.035, np.full(2, 0.035)))
        extreme = line @ jaw + np.sign(j[1] * sign) * extent - local @ j
        edges.append(sorted(extreme))
    if not edges or np.ptp(edges, axis=0).max() > 0.0025:
        return None
    return np.median(edges, axis=0)


def _substrate(frame, rgb, depth, geometry, pose):
    c = np.asarray(pose["center_m"])
    rot = np.asarray(pose["rotation"])
    rig = _model(geometry["asset_path"])
    reg = rig.region
    # The green optical surface is four millimetres higher than the collision
    # table. Independently sample the exposed real grey table in all quadrants.
    x, y = _window(frame, c, 42)
    pts = _cloud(frame, x, y, depth)
    z = pts[:, :, 2]
    delta = pts[:, :, :2] - c[:2]
    rad = np.linalg.norm(delta, axis=2)
    real = rig.table.c[2] + rig.table.h[2]
    green_h = reg.c[2] + reg.h[2]
    inside = (abs(pts[:, :, :2] - reg.c[:2]) < reg.h[:2] - 0.009).all(axis=2)
    outside = (abs(pts[:, :, :2] - reg.c[:2]) > reg.h[:2] + 0.009).any(axis=2)
    table_inside = (abs(pts[:, :, :2] - rig.table.c[:2]) < rig.table.h[:2] - 0.007).all(axis=2)
    r, g, b = rgb[y, x].astype(float).transpose(2, 0, 1)
    gray = (np.maximum.reduce([r, g, b]) - np.minimum.reduce([r, g, b]) <= 7) & (r >= 25)
    green = (g > r * 1.22 + 8) & (g > b * 1.12 + 6)
    ring = (rad >= 0.045) & (rad <= 0.204)
    table = ring & outside & table_inside & gray & (abs(z - real) < BAND)
    region = ring & inside & green & (abs(z - green_h) < BAND)

    def quadrant(mask):
        return [
            int((mask & ((delta[:, :, 0] >= 0) == sx) & ((delta[:, :, 1] >= 0) == sy)).sum())
            for sx in (False, True)
            for sy in (False, True)
        ]

    tq = quadrant(table)
    gq = quadrant(region)
    eligible = min(tq) >= 6
    table_error = float(np.median(z[table]) - real) if eligible else None
    dest = bool(
        (
            abs(c[:2] - reg.c[:2]) + abs(rot[:2]) @ rig.object[0].h + pose["center_error_m"]
            < reg.h[:2]
        ).all()
    )
    corner = SIGNS * rig.object[0].h
    hz = c[2] + corner @ rot[2]
    unc = directional_error(pose, corner, np.array([0.0, 0.0, 1.0]))
    observation_floor = real + (table_error or 0.0)
    return dict(
        support_surface_visible=bool(eligible and abs(table_error) < 0.001),
        support_plane_m=real,
        support_plane_residual_m=table_error,
        real_table_quadrant_samples=tq,
        green_region_quadrant_samples=gq,
        registered_destination_visible=bool(dest and min(gq) >= 3),
        cube_bottom_interval_m=[
            float(np.min(hz - unc) - observation_floor),
            float(np.min(hz + unc) - observation_floor),
        ],
        nominal_cube_bottom_m=float(np.min(hz) - observation_floor),
        support_table_bounds_xy_m=[
            (rig.table.c[:2] - rig.table.h[:2]).tolist(),
            (rig.table.c[:2] + rig.table.h[:2]).tolist(),
        ],
        visible_green_plane_height_m=float(green_h),
    )


def stable_support(rows):
    if len(rows) < 31:
        return False
    rows = rows[-31:]
    steps = [r["step"] for r in rows]
    if (
        steps[-1] - steps[0] != 240
        or any(b - a != 8 for a, b in zip(steps[:-1], steps[1:], strict=True))
        or len({r["frame_id"] for r in rows}) != 31
    ):
        return False
    xyz = np.asarray([r["center_m"] for r in rows])
    rr = np.asarray([r["rotation"] for r in rows])
    bottom = np.asarray([r["bottom_m"] for r in rows])
    # Compare the full spread to the original placement tolerance.
    return bool(
        np.linalg.norm(np.ptp(xyz, axis=0)) <= 0.004
        and np.max(np.linalg.norm(rr - rr[0], axis=(1, 2))) <= 0.042
        and np.ptp(bottom) <= 0.003
    )


def advance_history(history, physics_step):
    """A missing interval or a reordered packet breaks both observation chains."""
    prior = history.get("last_step")
    if prior is not None and not (0 <= physics_step - prior <= 8):
        history["recent_held"] = None
        history["support"].clear()
        if physics_step < prior:
            return False
    history["last_step"] = physics_step
    return True


def record_support(window, current):
    """Keep one physically timed observation per dwell tick."""
    if window:
        delta = current["step"] - window[-1]["step"]
        if delta == 0:
            return
        if delta != 8:
            window.clear()
    window.append(current)
    del window[:-31]


def payload_observation(
    frame,
    marker,
    geometry,
    robot_packet,
    skill,
    phase,
    *,
    identity,
    physics_step,
    optical,
    history,
    red_geometry=None,
):
    evidence = {}
    result = dict(
        relation="unknown", pose=None, allow_registered_block_table_contact=False, evidence=evidence
    )

    def failed(reason):
        if isinstance(history, dict):
            history.update(support=[], recent_held=None)
        evidence["reason"] = reason
        return result

    if (
        type(identity) is not OpticalIdentity
        or not identity.matches(frame, marker, geometry, physics_step)
        or robot_packet.get("physics_step") != physics_step
        or robot_packet.get("frame_id") != frame.frame_id
        or robot_packet.get("checksum_sha256") != frame.checksum_sha256
        or robot_packet.get("sim_time_s") != frame.sim_time_s
    ):
        return failed("unbound_current_frame_or_exposure")
    if not isinstance(history, dict):
        return failed("missing_per_instance_optical_history")
    key = (identity.allocation_sha256, identity.episode_id)
    if history.get("key") != key:
        history.clear()
        history.update(key=key, support=[], recent_held=None)
    if not advance_history(history, physics_step):
        return failed("non_monotonic_payload_observation")
    depth = axial(frame)
    rgb = cv2.imdecode(
        np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
    )
    if rgb is None or not np.isfinite(depth).all():
        return failed("missing_current_depth")
    rgb = rgb[:, :, ::-1]
    if optical and (
        optical.get("frame_id") != frame.frame_id
        or optical.get("checksum_sha256") != frame.checksum_sha256
    ):
        return failed("foreign_or_stale_certified_pose")
    refined, face = red_face_pose(frame, marker, geometry, rgb, depth, optical)
    if optical is None and refined is not None and red_geometry is not None:
        registered = red_geometry.refine(frame, refined, rgb, depth)
        if registered is not None:
            optical = _certify(
                dict(
                    refined,
                    **registered,
                    method=registered["fit_evidence"]["method"],
                )
            )
    result["pose"] = optical
    if not optical:
        return failed("missing_independent_3d_block_pose")
    evidence.update(_substrate(frame, rgb, depth, geometry, optical))
    evidence["red_physical_face"] = face
    rig = _model(geometry["asset_path"])
    joint = robot_packet.get("camera_joint_positions_rad")
    f = robot_packet.get("camera_finger_positions_m")
    if np.shape(joint) != (7,) or np.shape(f) != (2,) or not np.isfinite(np.r_[joint, f]).all():
        return failed("missing_exposure_encoders")
    tcp, r, _ = rig.forward(joint)
    hand = rig.hand_at(tcp, r, f)
    c = np.asarray(optical["center_m"])
    rot = np.asarray(optical["rotation"])
    block = rig.object[0].placed(c, rot)
    pad_gaps = [box_gap(p, block) for p in hand[1:]]
    jaw = r[:, 1]
    centre_offset = float((c - tcp) @ jaw)
    width = abs(jaw @ rot) @ block.h
    gap = [float(f[0] + 0.001 - centre_offset - width), float(f[1] + 0.001 + centre_offset - width)]
    err = float(np.max(directional_error(optical, SIGNS * block.h, jaw)))
    edges = transverse_edges(face, optical, jaw)
    measured_gap = None
    if edges is not None and _profile().get("independent_rim"):
        ep = np.asarray(_profile()["independent_rim"]["error_m"])
        # Both ends of the same top strip independently locate its middle. Propagate
        # the registered cube's measured 3-D orientation back to both outside faces.
        # The outward error on each extreme was calibrated as a pair, including the
        # current orientation and image sampling error, on complete physical curves.
        centre_projection = float(np.mean(edges))
        outer = centre_projection + np.array([-width, width])
        middle_error = np.asarray(_profile()["independent_rim"]["midpoint_outward_m"])
        lower = max(edges[0] - ep[0], outer[0] - middle_error[0])
        upper = min(edges[1] + ep[1], outer[1] + middle_error[1])
        # The whole registered block lies between the two measured outer limits.
        # Each current inner pad face must be beyond its respective limit.
        w = tcp @ jaw
        measured_gap = [
            float(w + f[0] + 0.001 - upper),
            float(lower - (w - f[1] - 0.001)),
        ]
    tangent = np.asarray([(c - tcp) @ hand[0].r[:, i] for i in (0, 2)])
    # Different axes of the downward wrist correspond to block height and tangency.
    closed = robot_packet.get("last_accepted_gripper_open") is False
    opened = robot_packet.get("last_accepted_gripper_open") is True
    command_step = robot_packet.get("last_accepted_gripper_command_step")
    stamp = robot_packet.get("previous_native_return_step")
    known_command = type(command_step) is int and 0 <= command_step <= physics_step
    known_return = type(stamp) is int and 0 <= stamp <= physics_step
    prior = robot_packet.get("previous_native_successful_skill")
    evidence.update(
        actual_inner_face_gaps_m=gap,
        finger_box_gap_m=pad_gaps,
        finger_axis_uncertainty_m=err,
        encoder_finger_positions_m=list(f),
        relative_tcp_wrist_axes_m=tangent.tolist(),
    )
    relative = (c - tcp) @ r
    relative_rotation = r.T @ rot
    last = history["recent_held"]
    observed_grasp_return = prior == "GRASP" and stamp == physics_step
    follows_hand = bool(
        last is not None
        and 0 <= physics_step - last["step"] <= 8
        and np.linalg.norm(relative - last["relative"]) <= 0.005
        and np.linalg.norm(relative_rotation - last["rotation"]) <= 0.07
    )
    preload = bool(
        closed
        and known_command
        and known_return
        and (observed_grasp_return or follows_hand)
        and prior in ("GRASP", "LIFT", "MOVE_TO_REGION", "PLACE")
        and min(f) > 0.021
        and max(f) < 0.039
        and max(abs(np.asarray(gap))) <= max(0.0025, err + 0.0008)
        and max(gap) <= 0
        and max(pad_gaps) <= 0
        and max(abs(tangent)) < 0.030
        and abs(centre_offset) < 0.0032
    )
    optical_pad_gap = (
        min(gap) - err if measured_gap is None else max(min(gap) - err, min(measured_gap))
    )
    separated = bool(opened and known_command and min(f) > 0.035 and optical_pad_gap > 0.00025)
    evidence["lower_transverse_gap_current_rims_m"] = measured_gap
    low, high = evidence["cube_bottom_interval_m"]
    table = bool(
        evidence["support_surface_visible"]
        and low <= 0.0012
        and high >= -0.0015
        and abs(evidence["nominal_cube_bottom_m"]) < 0.0024
    )
    side = bool(face and face["red_side_samples"] >= 3 and face["red_side_low_m"] < 0.010)
    upright = bool(rot[2, 2] > 0.9994)
    supported = bool(table and side and upright and evidence["registered_destination_visible"])
    if preload:
        if last is None or last["step"] < physics_step:
            history["recent_held"] = dict(
                step=physics_step, relative=relative, rotation=relative_rotation
            )
        result["relation"] = "held"
    else:
        history["recent_held"] = None
    # At release entry the still-closing command proves that the fingers have not
    # separated. A native return is provenance only; geometry must agree independently.
    if (
        skill == "RELEASE"
        and supported
        and prior in ("PLACE", "RELEASE")
        and known_return
        and (preload or (opened and known_command))
    ):
        result["relation"] = "releasing"
    result["allow_registered_block_table_contact"] = bool(table and (preload or supported))
    window = history["support"]
    if supported and separated and known_return and prior in ("RELEASE", "RETREAT"):
        current = dict(
            step=physics_step,
            frame_id=frame.frame_id,
            center_m=c.tolist(),
            rotation=rot.tolist(),
            bottom_m=evidence["nominal_cube_bottom_m"],
        )
        record_support(window, current)
        if stable_support(window):
            result["relation"] = "supported_and_separated"
    else:
        window.clear()
    evidence.update(
        stable_observation_count=len(window),
        observed_support_and_rim=supported,
        observed_two_finger_separation=separated,
        compatible_with_bilateral_holding=preload,
    )
    return result
