"""Current measured loaded/released solids against complete native eight-tick and stop paths."""

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Box

AXES = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
STAGES = ("LIFT", "MOVE_TO_REGION", "PLACE", "RETREAT")
SPEED_CLASSES = (0.075, 0.15, 0.25, 0.4)
GROUPS = (7, 7, 2, 2, 7, 2, 3, 9)
SCALES = np.repeat((0.24, 0.25, 0.006, 0.04, 0.09, 0.006, 0.033, 0.22), GROUPS)


def permits_relation(stage, relation):
    return (
        (stage in ("LIFT", "MOVE_TO_REGION", "PLACE") and relation == "held")
        or (stage == "RETREAT" and relation == "supported_and_separated")
        or (stage == "RELEASE" and relation in ("held", "releasing", "supported_and_separated"))
    )


def positive_support(vertices, velocity, initial, axes):
    # Endpoints and inner Bezier controls of the cubic matching native endpoint
    # positions and velocities bound the entire recorded span.
    scaled = velocity / (3 * 240)
    delta = vertices - initial
    nodes = np.concatenate((delta, delta[:-1] + scaled[:-1], delta[1:] - scaled[1:]))
    return np.array(
        [
            np.maximum(0.0, (nodes[:, j].reshape(-1, 3) @ axes.T).max(0))
            for j in range(vertices.shape[1])
        ]
    )


def snapshot(mg, q, dq, c, r):
    omega = (r @ dq[:, 12:15, None])[:, :, 0]
    world, v = mg.vertex_velocities(
        q[:, :7], q[:, 7:9], dq[:, :7], dq[:, 7:9], c, r, dq[:, 9:12], omega
    )
    arm = world[:, : mg.load_start] - c[:, None, None]
    rel = arm @ r[:, None]
    rv = (
        v[:, : mg.load_start] - dq[:, None, None, 9:12] - np.cross(omega[:, None, None], arm)
    ) @ r[:, None]
    return world, v, rel, rv


def object_matrix(q):
    w, x, y, z = q[:, 12:].T
    return np.stack(
        (
            1 - 2 * (y * y + z * z),
            2 * (x * y - z * w),
            2 * (x * z + y * w),
            2 * (x * y + z * w),
            1 - 2 * (x * x + z * z),
            2 * (y * z - x * w),
            2 * (x * z - y * w),
            2 * (y * z + x * w),
            1 - 2 * (x * x + y * y),
        ),
        axis=1,
    ).reshape(-1, 3, 3)


def state_features(mg, q, dq, ctrl, c, r):
    _, _, tcp, w = mg.poses(q[:, :7], q[:, 7:9])
    return np.concatenate(
        (
            q[:, :7],
            dq[:, :7],
            q[:, 7:9],
            dq[:, 7:9],
            ctrl[:, :7] - q[:, :7],
            ctrl[:, 7:9] - q[:, 7:9],
            ((c - tcp)[:, None, :] @ w)[:, 0, :],
            (w.transpose(0, 2, 1) @ r).reshape(-1, 9),
        ),
        axis=1,
    )


def direction_compatible(vector, reference, quiet):
    vector = np.asarray(vector, dtype=float)
    speeds = np.linalg.norm(reference, axis=1)
    velocity = np.linalg.norm(vector)
    if velocity <= quiet:
        return speeds <= quiet
    return (speeds > quiet) & (reference @ vector >= np.cos(np.radians(18)) * speeds * velocity)


def tcp_directions(mg, states):
    q, f = states[:, :7], states[:, 14:16]
    measured = mg.poses(q, f)[2]
    rate = 240 * (mg.poses(q + states[:, 7:14] / 240, f)[2] - measured)
    drive = mg.poses(q + states[:, 18:25], f)[2] - measured
    return rate, drive


def match(probe, err, reference, eligible):
    scaled = (abs(reference - probe) + err) / SCALES
    distances = np.stack(
        [block.max(axis=1) for block in np.split(scaled, np.cumsum(GROUPS)[:-1], axis=1)], axis=1
    )
    norms = (distances**2).sum(1)
    # Workpiece uncertainty and all actuator groups consume the same joint budget.
    norms = np.where(eligible, norms, np.inf)
    return int(norms.argmin()) if len(norms) and norms.min() <= 1 else None


def world_interval_separation(arm, arm_pad, load, load_pad):
    # The two signed displacements are kept separate on each world axis.
    arm_lo = arm.min(0) - arm_pad[1::2]
    arm_hi = arm.max(0) + arm_pad[0::2]
    load_lo = load.min(0) - load_pad[1::2]
    load_hi = load.max(0) + load_pad[0::2]
    return float(np.maximum(load_lo - arm_hi, arm_lo - load_hi).max())


def source_support_evidence(observation, source_xy, model, profile):
    """A held block can meet only its observed, originally authorized tabletop support."""
    denied = dict(qualified=False)
    if not observation or observation.get("relation") != "held" or source_xy is None:
        return denied
    pose = observation.get("pose") or {}
    evidence = observation.get("evidence") or {}
    bounds = np.asarray(evidence.get("support_table_bounds_xy_m"), dtype=float)
    interval = np.asarray(evidence.get("cube_bottom_interval_m"), dtype=float)
    counts = np.asarray(evidence.get("real_table_quadrant_samples"))
    if (
        evidence.get("support_surface_visible") is not True
        or interval.shape != (2,)
        or not np.isfinite(interval).all()
        or not (interval[0] <= interval[1] <= profile["max_current_gap_m"])
        or (
            interval[0] < -0.004
            and observation.get("allow_registered_block_table_contact") is not True
        )
        or interval[1] < -0.001
        or counts.shape != (4,)
        or np.min(counts) < 6
        or evidence.get("support_plane_m") != model.table.c[2] + model.table.h[2]
        or bounds.shape != (2, 2)
        or not np.allclose(
            bounds,
            [model.table.c[:2] - model.table.h[:2], model.table.c[:2] + model.table.h[:2]],
            atol=1e-8,
            rtol=0,
        )
    ):
        return denied
    offset = evidence.get("support_plane_residual_m")
    if offset is None or not np.isfinite(offset) or abs(offset) > 0.001:
        return denied
    center = np.asarray(pose["center_m"])
    rotation = np.asarray(pose["rotation"])
    centre_error = pose["center_error_m"]
    xy = np.linalg.norm(center[:2] - source_xy) + centre_error
    if xy > profile["source_xy_local_max_m"]:
        return denied
    # Bound tilt from the measured normal column, independent of uncertain yaw.
    normal_xy = rotation[:2, 2]
    delta = abs(rotation[:2]) @ np.asarray(pose["basis_error_object"])[:, 2]
    tilt = np.arcsin(min(1.0, np.linalg.norm(abs(normal_xy) + delta)))
    if tilt > profile["max_tilt_rad"]:
        return denied
    half = abs(rotation[:2]) @ model.object[0].h + centre_error + profile["xy_reserve_m"]
    desk_margin = float(
        np.minimum(center[:2] - half - bounds[0], bounds[1] - center[:2] - half).min()
    )
    if desk_margin <= 0:
        return denied
    return dict(
        qualified=True,
        registered_pair=["object_geom", "table"],
        current_bottom_interval_m=interval.tolist(),
        start_xy_offset_with_error_m=float(xy),
        current_tilt_upper_rad=float(tilt),
        checked_table_edge_clearance_m=desk_margin,
        measured_stop_branches=profile.get("branches"),
    )


def target_compatible(stage, target, tcp, entry_tcp, region):
    if target is None or target.shape != (3,) or not np.isfinite(target).all():
        return False
    if stage in ("LIFT", "RETREAT"):
        return bool(
            np.linalg.norm(target[:2] - entry_tcp[:2]) <= 0.001 and target[2] >= tcp[2] - 0.001
        )
    if not (abs(target[:2] - region.c[:2]) <= region.h[:2]).all():
        return False
    if stage == "PLACE":
        return bool(target[2] <= tcp[2] + 0.005)
    return stage == "MOVE_TO_REGION"


class PayloadClearance:
    def __init__(self, motion, profile, source_profile=None):
        self.motion = motion
        self.axes = np.asarray(profile["axes"])
        self.source_classes = {
            key: (np.asarray(row["world"]) * 1.25 + 0.0005, row["windows"])
            for key, row in (source_profile or {}).get("classes", {}).items()
        }
        self.data = {}
        for stage, entry in profile["phases"].items():
            reference = np.array(entry["references"])
            self.data[stage] = dict(
                references=reference,
                vectors=tcp_directions(motion, reference),
                classes={
                    bound: dict(
                        world=np.asarray(row["world"]) * 1.25 + 0.0005,
                        relative=np.asarray(row["relative"]) * 1.25
                        + 0.0005 * abs(self.axes).sum(1),
                        windows=row["windows"],
                        traces=row["traces"],
                    )
                    for bound, row in entry["classes"].items()
                },
            )

    def check(
        self,
        stage,
        q,
        f,
        dq,
        df,
        h,
        observed,
        volume_check,
        *,
        allow_grasp_station_contact,
        native_target,
    ):
        if not isinstance(observed, dict) or not permits_relation(stage, observed.get("relation")):
            return dict(reason="unqualified_current_payload_relation")
        pose = observed.get("pose")
        if not isinstance(pose, dict):
            return dict(reason="missing_directional_payload_pose")
        c = np.asarray(pose["center_m"])
        rot = np.asarray(pose["rotation"])
        anchor = np.asarray(pose["anchor_object_m"])
        e = np.asarray(pose["anchor_error_object_m"])
        basis = np.asarray(pose["basis_error_object"])
        if (
            c.shape != (3,)
            or rot.shape != (3, 3)
            or anchor.shape != (3,)
            or e.shape != (3,)
            or basis.shape != (3, 3)
            or not np.isfinite(np.concatenate((c, rot.ravel(), anchor, e, basis.ravel()))).all()
            or np.any(e < 0)
            or np.any(basis < 0)
            or not np.allclose(rot.T @ rot, np.eye(3), atol=1e-5)
        ):
            return dict(reason="invalid_directional_payload_pose")
        if not isinstance(h, dict):
            return dict(reason="missing_active_payload_drive")
        active = np.asarray(h.get("effective_joint_target_rad"), float)
        jaw = np.asarray(h.get("effective_finger_target_m"), float)
        if active.shape != (7,) or jaw.shape != (2,) or not np.isfinite(np.r_[active, jaw]).all():
            return dict(reason="missing_active_payload_drive")
        mg = self.motion
        model = mg.model
        state = state_features(
            mg, np.r_[q, f][None], np.r_[dq, df][None], np.r_[active, jaw][None], c[None], rot[None]
        )[0]
        center, orient, tcp, wrist = mg.solids(q[None], f[None], c[None], rot[None])
        entry = np.asarray(h.get("entry_joint_positions_rad"), float)
        if entry.shape != (7,) or not np.isfinite(entry).all():
            return dict(reason="missing_payload_command_origin")
        origin = mg.poses(entry[None], f[None])[2][0]
        if not target_compatible(stage, native_target, tcp[0], origin, model.region):
            return dict(reason="command_outside_registered_payload_path")
        wrist_axes = abs(wrist[0].T @ rot)
        state_error = np.zeros_like(state)
        state_error[-12:-9] = wrist_axes @ (e + basis @ abs(anchor))
        state_error[-9:] = (wrist_axes @ basis).ravel()
        row = self.data[stage]
        rate, drive = tcp_directions(mg, state[None])
        rates, drives = row["vectors"]
        eligible = direction_compatible(rate[0], rates, 0.0025) & direction_compatible(
            drive[0], drives, 0.00025
        )
        matched = match(state, state_error, row["references"], eligible)
        if matched is None:
            return dict(reason="payload_state_outside_continuous_training_domain")
        speed = float(abs(dq).max())
        keys = [str(k) for k in SPEED_CLASSES if speed <= k and str(k) in row["classes"]]
        allowance = row["classes"][keys[0] if keys else "all"]
        if speed > abs(row["references"][:, 7:14]).max() + 0.002:
            return dict(reason="payload_speed_outside_qualified_range")
        vertices = mg.vertices(center, orient)[0]
        floor = model.table.c[2] + model.table.h[2]
        result = dict(
            relation=observed["relation"],
            reference=matched,
            speed_class=keys[0] if keys else "all",
            calibrated_windows=allowance["windows"],
            fitted_trajectories=allowance["traces"],
            physics_ticks=8,
            brake_ticks=240,
        )
        gaps = []
        names = []
        local_corners = np.stack([o.corners() for o in model.object])
        local_error = e + abs(local_corners - anchor) @ basis.T
        floor_uncertainty = (local_error @ abs(rot[2])).max(1)
        world_pad = allowance["world"]
        if stage == "LIFT" and allow_grasp_station_contact and self.source_classes:
            source_keys = [
                str(k) for k in SPEED_CLASSES if speed <= k and str(k) in self.source_classes
            ]
            source_key = source_keys[0] if source_keys else "all"
            world_pad, windows = self.source_classes[source_key]
            result["registered_source_windows"] = windows
            result["registered_source_speed_class"] = source_key
        object_xyz = local_error.max(axis=1) @ abs(rot).T
        load_world_pad = world_pad[mg.load_start :] + np.repeat(object_xyz, 2, axis=1)
        for j, name in enumerate(mg.names):
            extra = 0.0 if j < mg.load_start else float(floor_uncertainty[j - mg.load_start])
            gap = float(vertices[j, :, 2].min() - floor - world_pad[j, 5] - extra)
            permitted = name == "object_geom" and allow_grasp_station_contact
            if permitted:
                continue
            names.append([name, "table"])
            gaps.append(gap)
        # Compare the robot and all load solids in the *same observed object frame*.
        # The only contacts permitted between them are the registered grasp fingers
        # against the named cube while that physical load remains held.
        arm = (vertices[: mg.load_start] - c) @ rot
        anchor_world = c + rot @ anchor
        arm_from_anchor = (vertices[: mg.load_start] - anchor_world) @ rot
        current_err = (abs(arm_from_anchor) @ basis + (1.0 * np.eye(3) + basis).T @ e).max(axis=1)
        target_radius = abs(self.axes) @ model.obj_h.T
        target_lower = self.axes @ model.obj_c.T - target_radius
        for j, body in enumerate(mg.names[: mg.load_start]):
            if j < mg.hand_start:
                # A long moment arm can amplify load-angle error for distal links
                # in the moving load frame. Their separately qualified world
                # enclosures always include observed arm and object displacements.
                gap = np.array(
                    [
                        world_interval_separation(vertices[j], world_pad[j], load, pad)
                        for load, pad in zip(vertices[mg.load_start :], load_world_pad, strict=True)
                    ]
                )
            else:
                uncertain = abs(self.axes) @ current_err[j]
                hand_upper = (arm[j] @ self.axes.T).max(0) + uncertain + allowance["relative"][j]
                gap = (target_lower - hand_upper[:, None]).max(0)
            if observed["relation"] == "held" and body in ("left_finger_geom", "right_finger_geom"):
                gap[0] = float("inf")
            k = int(np.argmin(gap))
            names.append([body, model.object[k].name])
            gaps.append(float(gap[k]))
        i = int(np.argmin(gaps))
        result.update(
            minimum_gap_m=gaps[i],
            limiting_pair=names[i],
            finger_table_lower_m={
                n: gaps[k]
                for k, (n, other) in enumerate(names)
                if other == "table" and n in ("left_finger_geom", "right_finger_geom")
            },
        )
        if gaps[i] <= 0:
            return result | dict(reason="loaded_eight_tick_and_stop_envelope_meets_solid")
        for j, name in enumerate(mg.names):
            pad = world_pad[j] if j < mg.load_start else load_world_pad[j - mg.load_start]
            low = vertices[j].min(axis=0) - pad[1::2]
            high = vertices[j].max(axis=0) + pad[0::2]
            enclosure = Box(name, (low + high) / 2, (high - low) / 2, np.eye(3))
            if not volume_check(enclosure, np.zeros(3)):
                return result | dict(
                    reason="payload_horizon_outside_registered_volume", limiting_body=name
                )
        return result | dict(reason=None)
