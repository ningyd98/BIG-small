"""Short-horizon qualification at a continuous native stage return, from measured inputs only."""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Box, box_gap, box_gaps
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_visibility_trials import STAGES

DIRECT = {"GRASP", "RELEASE"}
ON_CUBE = {"GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE"}
PROFILE = Path(__file__).with_name("g1_complete_cv_handoff_profile.json")
# Each state must match a single measured incoming command and configuration.
# Group maxima share one ellipsoidal budget. Distances are in radians, metres and seconds.
GROUPS = (7, 7, 2, 2, 7, 7, 7, 2, 3, 9)
SCALES = (0.24, 0.22, 0.006, 0.040, 0.075, 0.040, 0.075, 0.004, 0.025, 0.17)


def authorized_pair(skill, first, second):
    return (
        skill in ON_CUBE
        and first in {"left_finger_geom", "right_finger_geom"}
        and second == "object_geom"
    )


def required_delays(skill):
    if skill in DIRECT:
        return {"pre", *map(str, range(241))}
    return set(map(str, range(9)))


def binding_error(h, skill, phase, frame):
    if not isinstance(h, dict) or skill not in STAGES[1:]:
        return "missing_native_stage_handoff"
    previous = STAGES[STAGES.index(skill) - 1]
    if h.get("source_skill") != previous or h.get("destination_skill") != skill:
        return "wrong_prior_native_stage"
    times = [h.get(k) for k in ("prior_end_step", "entry_step", "current_step")]
    seq = [h.get(k) for k in ("entry_command_seq", "last_command_seq")]
    if (
        not all(type(v) is int and v >= 0 for v in times + seq)
        or times[0] != times[1]
        or times[1] > times[2]
        or seq[0] > seq[1]
        or type(h.get("entry_gripper_open")) is not bool
    ):
        return "unbound_stage_clock_or_command"
    if phase == "PRE" and (
        times[1] != times[2]
        or seq[0] != seq[1]
        or h.get("entry_frame_id") != frame.frame_id
        or h.get("entry_checksum_sha256") != frame.checksum_sha256
        or h.get("effective_joint_target_rad") != h.get("entry_target_rad")
        or h.get("effective_finger_target_m") != h.get("entry_finger_target_m")
    ):
        return "stage_entry_source_or_drive_changed"
    return None


def nearby_rows(probe, uncertainty, references, scale, groups=None):
    norm = (abs(np.asarray(references) - probe) + uncertainty) / scale
    if groups is not None:
        norm = np.column_stack(
            [part.max(axis=1) for part in np.split(norm, np.cumsum(groups)[:-1], axis=1)]
        )
    return np.flatnonzero(np.sum(norm**2, axis=1) <= 1).tolist()


def features(q, dq, f, df, applied, goal, velocity, finger_target, tcp, wrist, center, rotation):
    return np.concatenate(
        (
            q,
            dq,
            f,
            df,
            applied - q,
            goal - q,
            velocity,
            finger_target,
            wrist.T @ (center - tcp),
            (wrist.T @ rotation).reshape(-1),
        )
    )


@lru_cache(maxsize=1)
def profile():
    if not PROFILE.is_file():
        return {}
    return json.loads(PROFILE.read_bytes())


@lru_cache(maxsize=2)
def geometry(model):
    return MotionGeometry(model)


def handoff_motion(
    frame,
    marker,
    h,
    skill,
    phase,
    q,
    f,
    dq,
    df,
    center,
    rot,
    model,
    *,
    optical=None,
    volume_check=None,
):
    if skill == STAGES[0]:
        return None
    issue = binding_error(h, skill, phase, frame)
    if issue:
        return dict(reason=issue)
    if h["current_step"] > h["entry_step"]:
        return None
    evidence = dict(
        source=h["source_skill"],
        skill=skill,
        physical_step=h["entry_step"],
        command_seq=h["entry_command_seq"],
        plan="continuous_native_handoff",
        physics_ticks=240 if skill in DIRECT else 8,
        brake_ticks=240,
    )
    data = profile()
    stage = data.get("stages", {}).get(skill)
    if not stage or data.get("qualified") is not True:
        return evidence | dict(reason="unqualified_physical_handoff_profile")
    if (
        not optical
        or not callable(volume_check)
        or marker.get("frame_id") != frame.frame_id
        or marker.get("checksum") != frame.checksum_sha256
        or optical.get("frame_id") != frame.frame_id
        or optical.get("checksum_sha256") != frame.checksum_sha256
    ):
        return evidence | dict(reason="no_current_handoff_pose_interval")
    center = np.asarray(optical["center_m"], dtype=float)
    rot = np.asarray(optical["rotation"], dtype=float)
    poserr = float(optical["center_error_m"])
    roterr = float(optical["rotation_error_rad"])
    if (
        center.shape != (3,)
        or rot.shape != (3, 3)
        or not np.isfinite(center).all()
        or not np.allclose(rot.T @ rot, np.eye(3), atol=1e-5)
        or np.linalg.det(rot) < 0.999
        or not (0 <= poserr < 0.02 and 0 <= roterr < 0.20)
    ):
        return evidence | dict(reason="invalid_current_handoff_pose_interval")
    measured = [q, dq, f, df]
    keys = (
        "entry_joint_positions_rad",
        "entry_joint_velocities_rad_s",
        "entry_finger_positions_m",
        "entry_finger_velocities_m_s",
    )
    if not all(np.array_equal(a, h[k]) for a, k in zip(measured, keys, strict=True)):
        return evidence | dict(reason="handoff_encoder_changed_at_identical_step")
    arms = [
        np.asarray(h[k], dtype=float)
        for k in (
            "entry_target_rad",
            "entry_effective_arm_goal_rad",
            "entry_native_arm_velocity_rad_s",
        )
    ]
    finger_set = np.asarray(h["entry_finger_target_m"], dtype=float)
    if any(v.shape != (7,) for v in arms) or finger_set.shape != (2,):
        return evidence | dict(reason="missing_native_handoff_drive")
    mg = geometry(model)
    c, r, tcp, wrist = mg.solids(q[None], f[None], center[None], rot[None])
    state = features(q, dq, f, df, *arms, finger_set, tcp[0], wrist[0], center, rot)
    anchor = np.asarray(optical["anchor_object_m"], dtype=float)
    anchor_error = np.asarray(optical["anchor_error_object_m"], dtype=float)
    basis_error = np.asarray(optical["basis_error_object"], dtype=float)
    if (
        anchor.shape != (3,)
        or anchor_error.shape != (3,)
        or basis_error.shape != (3, 3)
        or not np.isfinite(anchor).all()
        or not np.isfinite(basis_error).all()
        or not np.isfinite(anchor_error).all()
        or np.any(basis_error < 0)
        or np.any(anchor_error < 0)
    ):
        return evidence | dict(reason="missing_directional_pose_uncertainty")
    wrist_axes = abs(wrist[0].T @ rot)
    error = np.zeros_like(state)
    error[-12:-9] = wrist_axes @ (anchor_error + basis_error @ abs(anchor))
    error[-9:] = (wrist_axes @ basis_error).ravel()
    candidates = [v for v in stage["references"] if h["entry_gripper_open"] is v["open"]]
    if not candidates or not np.isfinite(state).all():
        return evidence | dict(reason="unmeasured_handoff_state")
    selection = nearby_rows(
        state,
        error,
        [v["features"] for v in candidates],
        np.repeat(SCALES, GROUPS),
        GROUPS,
    )
    if not selection:
        return evidence | dict(reason="outside_continuous_handoff_state_domain")
    solids = {n: Box(n, c[0, i], mg.sizes[i], r[0, i]) for i, n in enumerate(mg.names)}
    solids["table"] = model.table
    for local in model.object:
        box = solids[local.name]
        # Bound every physical corner about the decoded anchor in the observed body axes.
        # This preserves e.g. a tight vertical interval when a single ID is weak in yaw.
        local_pad = (anchor_error + abs(local.corners() - anchor) @ basis_error.T).max(axis=0)
        solids[local.name] = Box(box.name, box.c, box.h + local_pad, box.r)
    same_pair = np.asarray(stage["pair_closing_m"])
    minimum, limiting = np.inf, None
    for (a, b), closing in zip(stage["pairs"], same_pair, strict=True):
        if authorized_pair(skill, a, b):
            continue
        gap = box_gap(solids[a], solids[b]) - closing
        if gap < minimum:
            minimum, limiting = gap, [a, b]
    # Link capsules are enclosed by these boxes, with every measured corner-motion
    # reserve from the complete uninterrupted span and every possible stop.
    pads = {n: np.asarray(v) for n, v in stage["body_pad_xyz_m"].items()}
    floor = model.table.c[2] + model.table.h[2]
    load = [solids[b.name] for b in model.object]
    load_centers = np.asarray([v.c for v in load])
    load_halves = np.asarray([v.h for v in load])
    load_allowance = np.array([np.linalg.norm(pads[v.name]) for v in load])
    for name in mg.names[: mg.hand_start]:
        box = solids[name]
        grown = Box(name, box.c, box.h + abs(box.r.T) @ pads[name], box.r)
        table_gap = grown.c[2] - abs(grown.r[2]) @ grown.h - floor
        gaps = box_gaps(grown, load_centers, load_halves, rot) - load_allowance
        i = int(np.argmin(gaps))
        if min(table_gap, gaps[i]) < minimum:
            minimum = min(table_gap, gaps[i])
            limiting = [name, "table" if table_gap < gaps[i] else load[i].name]
    evidence.update(
        minimum_gap_m=float(minimum),
        limiting_pair=limiting,
        matching_trajectories=len(selection),
        validated_stop_delays=stage["delays"],
    )
    if minimum <= 0:
        return evidence | dict(reason="continuous_handoff_or_stop_meets_solid")
    for name in mg.names:
        if not volume_check(solids[name], pads[name]):
            return evidence | dict(reason="handoff_outside_calibrated_volume", limiting_body=name)
    return evidence | dict(reason=None)
