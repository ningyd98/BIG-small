"""Propagate each synchronized optical pose to the two finite finger faces."""

import argparse
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_angle_domain import (
    ACCEL_M_S2,
    COM_Z,
    MASS_KG,
    MIN_FRICTION,
    MIN_NORMAL_PER_PAD_N,
)
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha

PLAN = "af9abc72ffaa9b2b3d5e2e92fbcf99559b2f13411dacaa7d22955b1f6d3ce7b2"
RAW = ROOT / "experiments/results/g1-continuous-payload-observation-20261125"
CONTINUOUS = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / "round-g1-continuous-payload-observation-20261125"
)
STAGES = {"LIFT", "MOVE_TO_REGION", "PLACE"}


def signed_interval_product(left_low, left_high, right_low, right_high):
    values = np.stack(
        (left_low * right_low, left_low * right_high, left_high * right_low, left_high * right_high)
    )
    return values.min(axis=0), values.max(axis=0)


def enclosed_pad(pad, pose, side):
    """An inscribed rectangle of the pad projected along its closing axis onto the cube face."""
    radius = 0.035
    optical_rot = np.asarray(pose["rotation"])
    anchor = np.asarray(pose["anchor_world_m"])
    lever = np.asarray(pose["anchor_object_m"])
    anchor_error = np.asarray(pose["anchor_error_object_m"])
    basis_error = np.asarray(pose["basis_error_object"])
    face = pad.c - side * pad.h[1] * pad.r[:, 1]
    a = pad.r[:, 0] * pad.h[0]
    b = pad.r[:, 2] * pad.h[2]
    vertices = np.array([face - a - b, face + a - b, face + a + b, face - a + b])
    delta = (vertices - anchor) @ optical_rot
    estimated = delta + lever
    world_direction = pad.r[:, 1] * side
    direction = world_direction @ optical_rot
    direction_error = abs(direction) @ basis_error
    low, high = direction - direction_error, direction + direction_error
    if low[1] <= 0 <= high[1] or min(abs(low[1]), abs(high[1])) < 0.98:
        return None
    ratios = np.stack([v / w for v in (low, high) for w in (low[1], high[1])])
    # Relative to the measured marker anchor, for every corner the true transform
    # lies within the registered elementwise matrix bound and signed anchor interval.
    error = abs(delta) @ basis_error + anchor_error @ (np.eye(3) + basis_error)
    distance = side * radius - estimated[:, 1, None]
    distance_error = error[:, 1, None]
    extents = signed_interval_product(
        distance - distance_error,
        distance + distance_error,
        ratios.min(axis=0),
        ratios.max(axis=0),
    )
    projected = (estimated + distance * (direction / direction[1]))[:, [0, 2]]
    mins = (estimated - error + extents[0])[:, [0, 2]]
    maxs = (estimated + error + extents[1])[:, [0, 2]]
    deviation = np.maximum(projected - mins, maxs - projected)
    # Propagate the rectangular support error per axis. Every directional dot
    # product of this box bounds all projected corner perturbations.
    erode = deviation.max(axis=0)
    mid = projected.mean(axis=0)
    basis = np.column_stack(((projected[1] - projected[0]) / 2, (projected[3] - projected[0]) / 2))
    if abs(np.linalg.det(basis)) <= 1e-9:
        return None
    base = np.array([0.028, 0.035])
    half = np.maximum(0.0, base / max(1.0, float((abs(np.linalg.inv(basis)) @ base).max())) - erode)
    lower, upper = np.maximum(-radius, mid - half), np.minimum(radius, mid + half)
    span = np.maximum(upper - lower, 0.0)
    support = np.array([0.0, COM_Z])
    support_clearance = float(np.minimum(support - lower, upper - support).min())
    # A conditional comparison with the original independent force floor. A
    # projection of the pad is not a spatial measurement of normal force.
    force = MASS_KG * (9.81 + ACCEL_M_S2)
    slack = MIN_FRICTION * MIN_NORMAL_PER_PAD_N - force / 2
    torque_capacity = max(0.0, slack) * float(span.min()) / 2
    mid = (lower + upper) / 2
    required = force * abs(mid[0] - support[0]) + MASS_KG * ACCEL_M_S2 * abs(mid[1] - support[1])
    return dict(
        pad=pad.name,
        erode_object_axes_m=erode.tolist(),
        overlap_span_m=span.tolist(),
        guaranteed_rectangle_area_mm2=float(1e6 * np.prod(span)),
        com_edge_lower_m=support_clearance,
        torque_reserve_conditional_Nm=float(torque_capacity - required),
        original_min_geometry=bool(
            span[0] >= 0.040 and span[1] >= 0.032 and support_clearance >= 0.003
        ),
    )


def project(root, role, predictions):
    source = root / "physical-03" / role
    capture = read(source / "sensor-receipt.json")
    index = pinned(source / "rgbd-index.json", capture["index_sha256"])
    asset = pinned(
        CONTINUOUS / "continuous-diagnostic-registration.json",
        "7d0a9f809d958b5c413fd91fc85116c2448b58c1c46067adeaef0ad38293f711",
    )
    rig = (
        ROOT
        / "assets/robots/franka_panda"
        / "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
    )
    assert sha(rig) == asset["native_controller_asset_sha256"]
    model = Model(rig)
    rows = []
    for source, row in zip(index["rows"], predictions["records"], strict=True):
        robot = source["robot"]
        assert (
            row["frame_id"] == robot["frame_id"]
            and row["checksum_sha256"] == robot["checksum_sha256"]
        )
        if row["skill"] not in STAGES:
            continue
        pose = row["result"]["pose"]
        data = dict(
            frame_id=row["frame_id"],
            step=row["step"],
            skill=row["skill"],
            original_relation=row["result"]["relation"],
            projected_pads=[],
        )
        if pose is not None:
            q, f = robot["camera_joint_positions_rad"], robot["camera_finger_positions_m"]
            tcp, wrist, _ = model.forward(q)
            hand = model.hand_at(tcp, wrist, f)
            data["projected_pads"] = [
                enclosed_pad(pad, pose, sign)
                for pad, sign in zip(hand[1:], (1.0, -1.0), strict=True)
            ]
        rows.append(data)
    return rows


def main(root, output):
    plan = pinned(Path(__file__).with_name("plan.json"), PLAN)
    records, provenance = {}, {}
    for role in ("dense-fit-01", "dense-fit-02", "dense-fit-03"):
        p = root / (role + "-prediction-02.json")
        h = plan["input_sha256"][p.relative_to(ROOT).as_posix()]
        records[role] = project(root, role, pinned(p, h))
        provenance[p.relative_to(ROOT).as_posix()] = h
    write_once(
        output,
        dict(
            plan_sha256=PLAN,
            source_sha256=provenance,
            physical_labels_used=False,
            commands_authorized=0,
            projections=records,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(RAW, args.output)
