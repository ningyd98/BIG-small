"""Independent raw force/patch/hold scorer for the fixed-wrist diagnostic split."""

import argparse
import gzip
import itertools
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_angle import angle_error_deg
from scripts.graduation.g1_complete_cv_angle_domain import (
    ACCEL_M_S2,
    COM_Z,
    MASS_KG,
    contact_opportunity,
)
from scripts.graduation.g1_complete_cv_calibrate import digest, write


def qualified(before, uncertainty):
    c = np.asarray(before["cube_xyz_m"])
    exact = np.asarray(before["cube_rotation"]).reshape(3, 3)
    hand = np.asarray(before["wrist_rotation"]).reshape(3, 3)
    yaw = float(np.degrees(np.arctan2(exact[1, 0], exact[0, 0])))
    a = np.radians(yaw)
    upright = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])
    dy = np.radians(uncertainty)
    # The tightest permissible replay uses the two decoded plates, whose levers cancel.
    return contact_opportunity(
        c,
        upright,
        before["tcp_xyz_m"],
        hand,
        before["finger_joints_m"],
        [0.00075, 0.00075, 0.00075],
        yaw_error_deg=angle_error_deg(yaw, uncertainty, hand, closure=True),
        yaw_uncertainty_deg=float(np.degrees(dy)),
        measured_rotation=exact,
        support_height=0.0,
    )


def contact_margin(row):
    p = [np.asarray(k)[:, [0, 2]] for k in row["points_object_m"]]
    f = [np.asarray(k) for k in row["forces_N_and_mu"]]
    load = MASS_KG * (9.81 + ACCEL_M_S2)
    min_area = []
    cap = []
    need = []
    normal = []
    slip = []
    for points, forces in zip(p, f, strict=True):
        fn, ft, mu = forces.T
        normal.append(float(sum(fn)))
        slip.append(float(sum(np.minimum(0.8, mu) * fn - ft)))
        weights = fn / sum(fn)
        centre = weights @ points
        need.append(float(load * abs(centre[0]) + MASS_KG * ACCEL_M_S2 * abs(centre[1] - COM_Z)))
        # Two opposite residual shear forces on distinct measured support points provide
        # a pure couple. Uses the smaller actual tangential reserve of the two points.
        budget = np.maximum(0, np.minimum(mu, 0.8) * fn - ft)
        pairs = [
            min(budget[i], budget[j]) * np.linalg.norm(points[i] - points[j])
            for i, j in itertools.combinations(range(len(points)), 2)
        ]
        cap.append(float(max(pairs, default=0.0)))
        min_area.append(
            float(cv2.contourArea(cv2.convexHull(points.astype("float32"))))
            if len(points) >= 3
            else 0.0
        )
    return [min(normal), min(slip), min(np.array(cap) - np.array(need)), min(min_area)]


def get_case(job):
    directory, record = job
    raw = directory / (record["id"] + ".json.gz")
    if (
        digest(raw) != record["clip_sha256"]
        or digest(directory / (record["id"] + "-commands.json.gz")) != record["command_sha256"]
    ):
        raise ValueError("native clip/command integrity failure")
    rows = json.loads(gzip.decompress(raw.read_bytes()))
    if any(b["step"] != a["step"] + 1 for a, b in zip(rows[:-1], rows[1:], strict=True)):
        raise ValueError("step gap " + record["id"])
    pre = next(row for row in reversed(rows) if row["phase"] == "settle")
    lifts = [r for r in rows if r["phase"] == "lift"]
    hold = lifts[-120:]
    close = [r for r in rows if r["phase"] == "close"]
    min_height = min((r["cube_bottom_m"] - pre["cube_bottom_m"] for r in hold), default=0.0)
    both = len(hold) == 120 and all(min(r["normal_force_N"]) > 0 for r in hold)
    forbidden = sum(bool(r["forbidden_pairs"]) for r in rows)
    actual = bool(
        record["lifted"] and record["closed"] and both and min_height >= 0.05 and not forbidden
    )
    if actual != record["eligible"]:
        raise ValueError("independent lift score mismatch")
    gate = qualified(pre, 0.3)
    if both:
        force, friction, torque, area = np.min([contact_margin(r) for r in hold], axis=0).tolist()
    else:
        force = friction = torque = area = None
    baseline = close[-1] if close else pre
    slip = max(
        (
            float(
                np.linalg.norm(np.array(r["xyz_error_object_m"]) - baseline["xyz_error_object_m"])
            )
            for r in lifts
        ),
        default=0.0,
    )
    tip = max(
        (float(np.degrees(np.arccos(np.clip(r["cube_rotation"][8], -1, 1)))) for r in lifts),
        default=0.0,
    )
    return dict(
        id=record["id"],
        group=record["design"]["group"],
        design=record["design"],
        pre=gate,
        admitted=gate["passes"],
        physical_success=actual,
        both_hold=both,
        minimum_lift_m=min_height,
        forbidden=forbidden,
        min_active_per_pad_force_N=force,
        min_measured_patch_area_m2=area,
        min_available_friction_after_shear_N=friction,
        min_measured_couple_reserve_after_gravity_Nm=torque,
        max_lift_slip_m=slip,
        max_upright_tilt_deg=tip,
        reason=record["error"],
        raw_sha256=record["clip_sha256"],
    )


def report(base, out, private):
    folders = [base / "handoff-grasp-fit-01", base / "handoff-grasp-unseen-01"]
    jobs = []
    for p in folders:
        index = json.loads((p / "index.json").read_bytes())
        if digest(p / "prospective.json") != index["prospective"]:
            raise ValueError("source proposal mismatch")
        jobs.extend((p, row) for row in index["rows"])
    with ProcessPoolExecutor(max_workers=4) as executors:
        results = list(executors.map(get_case, jobs))
    grouped = defaultdict(list)
    for d in results:
        grouped[d["group"]].append(d)
    summary = {}
    for label, rows in grouped.items():
        passes = [r for r in rows if r["admitted"]]
        summary[label] = dict(
            total=len(rows),
            physically_held=sum(r["physical_success"] for r in rows),
            admitted=len(passes),
            admitted_but_physically_failed=[r["id"] for r in passes if not r["physical_success"]],
            physically_held_while_rejected=sum(
                r["physical_success"] and not r["admitted"] for r in rows
            ),
            measured_minima={
                key: min((r[key] for r in passes if r[key] is not None), default=None)
                for key in [
                    "minimum_lift_m",
                    "min_active_per_pad_force_N",
                    "min_measured_patch_area_m2",
                    "min_available_friction_after_shear_N",
                    "min_measured_couple_reserve_after_gravity_Nm",
                ]
            },
            maximum_real_lift_slip_m=max((r["max_lift_slip_m"] for r in passes), default=None),
            maximum_tilt_deg=max((r["max_upright_tilt_deg"] for r in passes), default=None),
            forbidden_in_admitted=sum(r["forbidden"] for r in passes),
            physical_guard_stops=dict(Counter(e for r in rows for e in r["reason"])),
        )
    write(private, results)
    write(
        out,
        dict(
            split=summary,
            per_trajectory_sha256=digest(private),
            source_sha256={p.name: digest(p / "index.json") for p in folders},
            pose_input_in_fixture=(
                "known position scores physical opportunity; frozen real RGB-D optical "
                "uncertainty is tested separately. Raw normal/contact forces are never "
                "online inputs."
            ),
            force_and_moment=(
                "120 consecutive held steps; actual per-pad effective contact hulls, fn and shear "
                "available at conservative mu<=0.8. Pure couple uses one matched pair of opposing "
                "residual shear forces on each side. Slip includes initial lift tracking."
            ),
            independent_slots=0,
            formal_runs=0,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("base", "out", "private"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    report(a.base, a.out, a.private)
