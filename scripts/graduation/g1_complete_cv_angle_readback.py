"""Recompute current-camera target yaw, marker centres and geometric uncertainty on sealed clips."""

import argparse
import gzip
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_angle import (
    angle_error_deg,
    fixed_wrist_angle,
)
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def rz(degrees):
    a = np.radians(degrees)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])


def read_angles(base, out, details):
    # The control study precedes the handoff repair. Bind its actual closure criterion.
    frozen = (
        base
        / "builds/9ed09852049be122ae5ff684af8d89e20012dcae7486db44e93421e075d57caf"
        / "runtime-source/scripts/graduation/g1_complete_cv_angle.py"
    )
    if digest(frozen) != "46caba60c926be12445bd7bf71f44295129864941edb2c943363a5a134be4b8b":
        raise ValueError("frozen closure reader changed")
    spec = importlib.util.spec_from_file_location("frozen_angle_qualification", frozen)
    old_angle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_angle)
    domain = json.loads(
        gzip.decompress((base / "mount-optics-02/capture-gpu/compiled.json.gz").read_bytes())
    )["geometry"]
    wr = json.loads(
        gzip.decompress(
            (base / "mount-qualification-01/angles-centers-grid/close-001.json.gz").read_bytes()
        )
    )
    near = next(row for row in reversed(wr) if row["phase"] == "OPEN_SETTLE")
    groups = [
        "optical-control-gpu-01",
        "angle-optical-holdout-01",
        "angle-optical-validation-02",
        "angle-optical-aligned-03",
    ]
    reports = {}
    full = {}
    for group in groups:
        p = base / group
        idx = json.loads((p / "index.json").read_bytes())
        records = []
        for item in idx["raw"]:
            if item["kind"] != "yaw":
                continue
            file = p / item["file"]
            if digest(file) != item["file_sha256"]:
                raise ValueError("corrupt optical clip " + str(file))
            frame = RGBDObservation.model_validate_json(gzip.decompress(file.read_bytes()))
            marker = measure_frame(frame, domain)
            estimate = fixed_wrist_angle(frame, marker, domain)
            if not estimate:
                raise ValueError("optical uncertainty", str(file))
            ids = marker["usable_ids"]
            truth = np.asarray(
                item["center"] if "center" in item else [0.45 + item["dx"], item["dy"], 0.035]
            )
            real = rz(item["angle_deg"])
            current = rz(estimate["yaw_deg"])
            origins = []
            direct = []
            for code in map(str, ids):
                b = np.asarray(marker["by_id"][code]["marker_center_world_m"])
                lever = np.asarray(
                    domain["development_dual"]["markers"][code]["object_T_marker"]
                ).reshape(4, 4)[:3, 3]
                origins.append(b - current @ lever)
                direct.append(abs((b - truth - real @ lever) @ real).tolist())
            center = np.mean(origins, axis=0)
            error = (center - truth) @ current
            ua = np.radians(estimate["uncertainty_deg"])
            lever = 0.0 if len(ids) == 2 else 0.13
            bounds = 0.00075 + np.array([lever * (1 - np.cos(ua)), lever * np.sin(ua), 0])
            # Registered cube corner positions are scored only here using diagnostic pose.
            corner_ratios = []
            corner_errors = []
            for x in (-0.035, 0.035):
                for y in (-0.035, 0.035):
                    corner = np.array([x, y, 0.035])
                    diff = abs((center + current @ corner - truth - real @ corner) @ current)
                    limits = bounds + np.array(
                        [
                            abs(x) * (1 - np.cos(ua)) + abs(y) * np.sin(ua),
                            abs(y) * (1 - np.cos(ua)) + abs(x) * np.sin(ua),
                            0,
                        ]
                    )
                    corner_ratios.append(float(max(diff / limits)))
                    corner_errors.append(diff.tolist())
            close = item["pose"] in ("open-near", "near-centered")
            wrist = np.asarray(item.get("wrist_rotation", near["wrist_rotation"])).reshape(3, 3)
            observed = angle_error_deg(
                estimate["yaw_deg"], estimate["uncertainty_deg"], wrist, closure=False
            )
            reject = None
            if close:
                _, _, reject = old_angle.grasp_readiness(
                    frame,
                    marker,
                    domain,
                    np.asarray(marker["object_center_world_m"]),
                    np.asarray(marker["rotation_object_to_world"]).reshape(3, 3),
                    np.asarray(item["tcp"]),
                    wrist,
                    np.asarray(item["fingers"]),
                    closure=True,
                )
            records.append(
                dict(
                    file=item["file"],
                    raw_sha256=item["file_sha256"],
                    pose=item["pose"],
                    ids=ids,
                    truth_yaw=item["angle_deg"],
                    method=estimate["method"],
                    uncertainty=estimate["uncertainty_deg"],
                    yaw=estimate["yaw_deg"],
                    error_deg=abs(estimate["yaw_deg"] - item["angle_deg"]),
                    yaw_qualified=bool(observed <= 3),
                    closure_checked=close,
                    closure_reject=reject,
                    centered=bool(
                        "dx" in item
                        and item["dx"] == item["dy"] == 0
                        or item["pose"] == "near-centered"
                    ),
                    direct_marker_abs_error_object_m=direct,
                    center_error_estimated_axes_m=error.tolist(),
                    center_bound_estimated_axes_m=bounds.tolist(),
                    cube_corner_max_ratio=max(corner_ratios),
                    cube_corner_max_abs_m=np.max(corner_errors, axis=0).tolist(),
                )
            )

        def stats(rows):
            accepted = [r for r in rows if r["yaw_qualified"]]
            return dict(
                n=len(rows),
                max_error_deg=max(r["error_deg"] for r in rows),
                in_angle_bound=sum(r["error_deg"] <= r["uncertainty"] for r in rows),
                center_inside_bound=sum(
                    bool(
                        np.all(
                            abs(np.array(r["center_error_estimated_axes_m"]))
                            <= r["center_bound_estimated_axes_m"]
                        )
                    )
                    for r in rows
                ),
                cube_corners_all_inside_bound=sum(r["cube_corner_max_ratio"] <= 1 for r in rows),
                maximum_direct_marker_abs_xyz_mm=(
                    1000
                    * np.max(
                        [a for r in rows for a in r["direct_marker_abs_error_object_m"]], axis=0
                    )
                ).tolist(),
                max_center_abs_xyz_mm=(
                    1000
                    * np.max(np.abs([r["center_error_estimated_axes_m"] for r in rows]), axis=0)
                ).tolist(),
                max_cube_corner_abs_xyz_mm=(
                    1000 * np.max([r["cube_corner_max_abs_m"] for r in rows], axis=0)
                ).tolist(),
                outside_3deg_incorrectly_accepted=sum(abs(r["truth_yaw"]) > 3 for r in accepted),
                conservative_stops_inside_2_25_deg=sum(
                    not r["yaw_qualified"] and abs(r["truth_yaw"]) <= 2.25 for r in rows
                ),
                entire_centered_near_grasp_accepted=sum(
                    r["closure_checked"] and r["centered"] and not r["closure_reject"] for r in rows
                ),
                centered_near_grasp_cases=sum(r["closure_checked"] and r["centered"] for r in rows),
            )

        methods = defaultdict(list)
        poses = defaultdict(list)
        for r in records:
            methods[r["method"]].append(r)
            poses[r["pose"]].append(r)
        reports[group] = dict(
            index_sha256=digest(p / "index.json"),
            summary=stats(records),
            by_method={k: stats(v) for k, v in methods.items()},
            by_pose={k: stats(v) for k, v in poses.items()},
        )
        full[group] = records
    write(details, full)
    write(
        out,
        dict(
            groups=reports,
            records_sha256=digest(details),
            geometry_sha256=digest(base / "mount-optics-02/capture-gpu/compiled.json.gz"),
            truth_path=(
                "latent diagnostic fixture pose enters only scorer "
                "after same current optical measurement"
            ),
            formal_runs=0,
            independent_slots=0,
        ),
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("base", type=Path)
    a.add_argument("out", type=Path)
    a.add_argument("details", type=Path)
    v = a.parse_args()
    read_angles(v.base, v.out, v.details)
