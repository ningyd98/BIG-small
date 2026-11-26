"""Separate archived ID8 plate travel into object translation and rotation."""

import argparse
from pathlib import Path

import numpy as np
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import ROOT, read, sha, write

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
WINDOW = PLAN["window"]
OUT = REPO / PLAN["output"]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def rotation_angle(a, b):
    cosine = (np.trace(a.T @ b) - 1) / 2
    return float(np.degrees(np.arccos(np.clip(cosine, -1, 1))))


def archive(path, motion, expected):
    with np.load(path, allow_pickle=False) as stop:
        q, dq = stop["q"], stop["qvel"]
        names = stop["pair_names"].tolist()
        counts = stop["contact_counts"]
        ctrl = stop["ctrl"]
    require(
        q.shape == (241, 16)
        and dq.shape == (241, 15)
        and ctrl.shape == (241, 9)
        and counts.shape == (241, len(names))
        and np.isfinite(q).all()
        and np.isfinite(dq).all()
        and np.isfinite(ctrl).all(),
        "stop archive is incomplete",
    )
    part = motion.names.index(WINDOW["part"])
    origin, orientation = q[:, 9:12], object_matrix(q)
    world, velocity, _, _ = snapshot(motion, q, dq, origin, orientation)
    _, _, tcp, wrist = motion.solids(q[:, :7], q[:, 7:9], origin, orientation)
    points = world[:, part]
    descent = points[0, :, 2] - points[:, :, 2]
    stop_tick, corner = np.unravel_index(descent.argmax(), descent.shape)
    endpoint = float(descent[stop_tick, corner])
    translation_z = float(origin[0, 2] - origin[stop_tick, 2])
    relative = points[:, corner, 2] - origin[:, 2]
    rotation_z = float(relative[0] - relative[stop_tick])
    require(abs(endpoint - translation_z - rotation_z) < 1e-14, "rigid vertex sum differs")
    envelope = float(positive_support(world, velocity, world[0], AXES)[part, 5])
    require(abs(expected - envelope) < 1e-12, "freeze envelope cannot be reproduced")
    table = counts[:, names.index(["object_geom", "table"])] > 0
    left = counts[:, names.index(["left_finger_geom", "object_geom"])] > 0
    right = counts[:, names.index(["object_geom", "right_finger_geom"])] > 0
    in_tcp = (wrist.transpose(0, 2, 1) @ (origin - tcp)[..., None])[..., 0]
    relative_r = wrist.transpose(0, 2, 1) @ orientation
    offset = (points[0, corner] - origin[0]) @ orientation[0]
    return {
        "archive_sha256": sha(path),
        "worst_stop_tick": int(stop_tick),
        "corner_index": int(corner),
        "corner_m_in_workpiece_frame": offset.tolist(),
        "maximum_endpoint_z_m": endpoint,
        "workpiece_origin_down_m": translation_z,
        "same_corner_rotation_down_m": rotation_z,
        "original_fitter_excess_over_endpoint_m": envelope - endpoint,
        "original_fitter_bound_m": envelope,
        "frozen_allowance_m": WINDOW["fixed_allowance_m"],
        "envelope_excess_m": envelope - WINDOW["fixed_allowance_m"],
        "workpiece_rotation_from_stop_start_deg": rotation_angle(
            orientation[0], orientation[stop_tick]
        ),
        "first_table_contact_after_stop": int(np.flatnonzero(table)[0]) if table.any() else None,
        "contact_at_peak": {
            "left": bool(left[stop_tick]),
            "right": bool(right[stop_tick]),
            "table": bool(table[stop_tick]),
        },
        "TCP_down_at_peak_m": float(tcp[0, 2] - tcp[stop_tick, 2]),
        "workpiece_in_TCP_change_at_peak_m": (in_tcp[stop_tick] - in_tcp[0]).tolist(),
        "workpiece_in_TCP_rotation_change_at_peak_deg": rotation_angle(
            relative_r[0], relative_r[stop_tick]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen runtime")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for name, expected in PLAN["sha256"].items():
        require(sha(REPO / name) == expected, f"sealed input changed: {name}")
    scene = ROOT / "assets/robots/franka_panda"
    asset = scene / "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
    motion = MotionGeometry(Model(asset))
    paths = {k: REPO / v for k, v in PLAN["inputs"].items()}
    result = {
        "baseline": archive(paths["baseline"], motion, 0.002777251732861987),
        "feedback_init": archive(paths["feedback_init"], motion, 0.0026587198318027455),
        "source_sha256": sha(Path(__file__)),
        "plan_sha256": sha(HERE / "plan.json"),
        "new_physical_steps": 0,
        "new_exposures": 0,
    }
    OUT.mkdir(exist_ok=True)
    write(OUT / f"{args.reader}.json", result)


if __name__ == "__main__":
    main()
