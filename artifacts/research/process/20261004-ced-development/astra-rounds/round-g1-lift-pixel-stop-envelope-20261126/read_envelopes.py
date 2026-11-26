"""Compare sealed whole-pixel viewing volumes and original LIFT stop envelopes."""

import argparse
import itertools
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import BAND
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, _covers
from scripts.graduation.g1_complete_cv_payload import source_support_evidence
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
TOL = PLAN["separation_tolerance_m"]
ANGLES = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]])
XYZ = np.eye(3)
CORNERS = np.array(list(itertools.product((0, 1), repeat=3)))
TRIPLETS = np.array(list(itertools.combinations(range(12), 3)))
VIEWS = ("panel-primary", "panel-start")
PRIOR = HERE.parent / "round-g1-lift-stop-geometry-20261126" / "diagnose.py"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned(root, name, digest):
    path = root / name
    resolved = path.resolve(strict=True)
    require(resolved == path and resolved.is_relative_to(root), f"redirected input {path}")
    require(sha(path) == digest, f"source changed: {path}")
    return path


def read_scope():
    def check(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            name = str(args[0])
            if any(
                part in name
                for part in (
                    "offline-physics",
                    "offline-truth",
                    "frame-labels",
                    "dense-registered-surface-20261126/capture",
                    "same-view-needle-sampling-20261126/capture",
                    "physically_added_tip",
                    "original-stops-01",
                    "cvfix-e01",
                    "cvfix-e02",
                )
            ):
                raise PermissionError("witness input denied before prediction seal")

    sys.addaudithook(check)
    for name in ("offline-physics.json", "original-stops-01/t02/observed-2112.npz"):
        try:
            Path(name).read_bytes()
        except PermissionError:
            continue
        raise ValueError("witness denial control failed")


def validate_capture(name, case):
    folder = ROOT / PLAN["captures"][name]
    seal = read(folder / "seal.json")
    members = seal["sealed_sha256"]
    require(len(members) == PLAN["seal_members"][name], "capture member count")
    for key in (
        "clearance-gate.json",
        "optical-allocation.json",
        "rgbd-index.json",
        "sensor-receipt.json",
        "native-commands.json",
    ):
        rel = f"{case}/{key}"
        pinned(folder, rel, members[rel])
    registration = read(pinned(folder, "registration.json", seal["registration_sha256"]))
    return folder, registration, members


def load_prior():
    spec = spec_from_file_location("sealed_first_stop_readback", PRIOR)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ancestor_support(cert, checks, tick):
    (grasp,) = [row for row in checks if (row["skill"], row["phase"]) == ("GRASP", "PRE")]
    current = grasp["current"]["payload_observation"]
    pose = current["pose"]
    require(
        grasp["status"] == "CLEAR"
        and pose["method"] in {"both", "id8_opposite_edges", "id8_opposite_ink"}
        and pose["frame_id"] == grasp["frame_id"]
        and pose["checksum_sha256"] == grasp["checksum_sha256"],
        "source support pose provenance",
    )
    center, rotation = np.asarray(pose["center_m"]), np.asarray(pose["rotation"])
    body = cert.model.object[0].placed(center, rotation)
    floor = cert.model.table.c[2] + cert.model.table.h[2]
    anchor = (
        center[:2]
        if current["evidence"]["support_surface_visible"]
        and abs(body.corners()[:, 2].min() - floor) <= 2 * BAND
        else None
    )
    result = None
    for row in checks:
        if row["skill"] != "LIFT" or row["step"] > tick:
            continue
        current = row["current"]
        observed = current["payload_observation"]
        result = source_support_evidence(observed, anchor, cert.model, cert.source_support)
        if "source_table_support" in current:
            require(result == current["source_table_support"], "support history differs")
        if (
            observed["evidence"]["cube_bottom_interval_m"][0]
            > cert.source_support["max_current_gap_m"]
        ):
            anchor = None
        if row["step"] == tick:
            return result
    raise ValueError("requested support tick missing")


def stop_boxes(cert, gate, robot, target, support, traverse):
    observed = gate["current"]["payload_observation"]
    require(
        observed["pose"]["frame_id"] == gate["frame_id"]
        and observed["pose"]["checksum_sha256"] == gate["checksum_sha256"],
        "unbound payload pose",
    )
    collected = {}
    allow_table = support["qualified"]

    def volume(box, pad):
        require(
            box.name not in collected
            and np.array_equal(box.r, XYZ)
            and np.array_equal(pad, np.zeros(3)),
            "changed volume callback",
        )
        points = box.corners()
        checked = points.copy()
        permitted_table = box.name == "object_geom" and allow_table
        if permitted_table:
            checked[:, 2] = np.maximum(checked[:, 2], cert.model.table.c[2] + cert.model.table.h[2])
        coverage = {
            key: _covers(checked, *cert.maps[key], 2 * BAND if permitted_table else 0.0)
            for key in VIEWS
        }
        collected[box.name] = {
            "bounds_m": [points.min(0).tolist(), points.max(0).tolist()],
            "checked_bounds_m": [checked.min(0).tolist(), checked.max(0).tolist()],
            "covered_by": coverage,
        }
        return traverse or any(coverage.values())

    measured = [
        np.asarray(robot[key])
        for key in (
            "joint_positions_rad",
            "finger_positions_m",
            "joint_velocities_rad_s",
            "finger_velocities_m_s",
        )
    ]
    result = cert.payload_gate.check(
        "LIFT",
        *measured,
        robot["handoff"],
        observed,
        volume,
        allow_grasp_station_contact=allow_table,
        native_target=target,
    )
    return result, collected


def envelope(cert, gate, robot, target, support):
    actual, prefix = stop_boxes(cert, gate, robot, target, support, False)
    saved = gate["current"].get("short_motion")
    if saved is not None:
        require(actual == saved, f"original short motion differs at {gate['step']}")
    reason = actual["reason"]
    complete = reason is None and tuple(prefix) == tuple(cert.motion.names)
    boxes = prefix
    if reason == "payload_horizon_outside_registered_volume":
        full, boxes = stop_boxes(cert, gate, robot, target, support, True)
        require(
            tuple(boxes)[: len(prefix)] == tuple(prefix)
            and all(boxes[k] == row for k, row in prefix.items()),
            "volume prefix changed",
        )
        complete = full["reason"] is None and tuple(boxes) == tuple(cert.motion.names)
    return {
        "reason_before_volume_traversal": reason,
        "registered_volume": prefix,
        "complete": complete,
        "boxes": boxes,
        "source_table_support": support,
        "short_motion": actual,
    }


def pixel_cone(camera, pixel, optical_far):
    require(
        len(pixel) == 2
        and 0 <= pixel[0] < camera["width"]
        and 0 <= pixel[1] < camera["height"]
        and optical_far > 0,
        "outside camera",
    )
    fx, fy, cx, cy = camera["intrinsics"]
    transform = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    origin, rotation = transform[:3, 3], transform[:3, :3]
    slopes = (pixel + ANGLES - [cx, cy]) / [fx, fy]
    directions = np.column_stack((slopes, np.ones(4))) @ rotation.T
    points = np.vstack((origin, origin + optical_far * directions))
    width, height, forward = rotation.T
    lo, hi = slopes.min(0), slopes.max(0)
    normals = np.array(
        [
            -width + lo[0] * forward,
            width - hi[0] * forward,
            -height + lo[1] * forward,
            height - hi[1] * forward,
            -forward,
            forward,
        ]
    )
    limits = normals @ origin + np.array([0, 0, 0, 0, 0, optical_far])
    edges = np.vstack((directions, width, height))
    return points, normals, limits, edges


def vertices_inside(normals, limits):
    matrices = normals[TRIPLETS]
    good = abs(np.linalg.det(matrices)) > 1e-10
    points = np.linalg.solve(matrices[good], limits[TRIPLETS[good]][..., None])[..., 0]
    return points[np.all(points @ normals.T <= limits + 1e-10, axis=1)]


def compare_cone(cone, bounds):
    points, normals, limits, edges = cone
    lo, hi = np.asarray(bounds)
    require(np.isfinite([lo, hi]).all() and np.all(lo <= hi), "invalid envelope bounds")
    box = np.where(CORNERS, hi, lo)
    axes = np.vstack((XYZ, normals, np.cross(edges[:, None], XYZ).reshape(-1, 3)))
    norms = np.linalg.norm(axes, axis=1)
    axes = axes[norms > 1e-12] / norms[norms > 1e-12, None]
    first, second = points @ axes.T, box @ axes.T
    margins = np.r_[second.min(0) - first.max(0), first.min(0) - second.max(0)]
    best = int(margins.argmax())
    margin = float(margins[best])
    if margin > TOL:
        axis = axes[best % len(axes)] * (1 if best < len(axes) else -1)
        return {"relation": "disjoint", "separating_axis_world": axis.tolist(), "gap_m": margin}
    all_normals = np.vstack((normals, XYZ, -XYZ))
    all_limits = np.r_[limits, hi, -lo]
    witnesses = vertices_inside(all_normals, all_limits)
    return {
        "relation": "intersects" if len(witnesses) else "uncertain",
        "witness_world_m": witnesses[0].tolist() if len(witnesses) else None,
        "largest_axis_gap_m": margin,
    }


def classify(results, complete):
    overlap = any(v["relation"] == "intersects" for v in results.values())
    if overlap:
        return "envelope_intersection_only" if complete else "partial_body_intersection"
    if complete and results and all(v["relation"] == "disjoint" for v in results.values()):
        return "complete_envelope_disjoint"
    return "insufficient_evidence"


def geometry_controls():
    camera = {
        "width": 3,
        "height": 3,
        "intrinsics": [1, 1, 1, 1],
        "camera_to_world": XYZ_4.reshape(-1).tolist(),
    }
    cone = pixel_cone(camera, [1, 1], 10)
    inner = compare_cone(cone, [[0.45, 0.45, 1], [0.48, 0.48, 1.1]])
    far = compare_cone(cone, [[0.9, 0.9, 2], [0.95, 0.95, 2.1]])
    outside = compare_cone(cone, [[1, 0, 1], [1.1, 0.1, 1.1]])
    touch = compare_cone(cone, [[0.5, 0, 1], [0.6, 0.1, 1]])
    wider = compare_cone(cone, [[0.45, 0, 1], [1.1, 0.1, 1.1]])
    controls = {
        "clear_spatial_gap": outside["relation"] == "disjoint",
        "pixel_corner_hits_without_center": inner["relation"] == "intersects",
        "occluded_depth_retained": far["relation"] == "intersects",
        "touch_is_not_disjoint": touch["relation"] != "disjoint",
        "enlarged_box_cannot_add_separation": wider["relation"] != "disjoint",
        "missing_named_body_not_complete": classify({"body": outside}, False)
        == "insufficient_evidence",
    }
    require(all(controls.values()), "failed geometry control")
    return controls


XYZ_4 = np.eye(4)


def checked_pair(prior, name, slot, clear_tick, stop_tick, pixels):
    case = f"g1-lift-grid-{slot}"
    folder, registration, members = validate_capture(name, case)
    source = folder / case
    checks = read(source / "clearance-gate.json")["checks"]
    index = read(source / "rgbd-index.json")
    for row in index["rows"]:
        if (row["skill"], row["phase"]) == ("LIFT", "FEEDBACK") and row["robot"][
            "physics_step"
        ] in {clear_tick, stop_tick}:
            path = f"{case}/{row['file']}"
            require(members[path] == row["file_sha256"], "raw packet missing from capture seal")
    selected = {
        "case": case,
        "previous_clear": clear_tick,
        "first_stop": stop_tick,
        "pixels": pixels,
        "status": "BLOCKED" if pixels else "UNKNOWN",
        "reason": "unregistered_near_surface"
        if pixels
        else "payload_horizon_outside_registered_volume",
    }
    allocation = read(source / "optical-allocation.json")
    cal = ROOT / PLAN["calibration"]
    cert = LocalClearance(
        allocation["geometry"],
        ROOT / PLAN["asset"],
        cal,
        calibration_sha256=PLAN["predict_sha256"][f"{PLAN['calibration']}/manifest.json"],
        isolated_scene=True,
    )
    require(
        allocation["geometry"]["camera"] == registration["camera"]
        and allocation["asset_sha256"] == registration["asset_sha256"] == cert.asset_sha,
        "capture camera or asset not registered",
    )
    lift = [r for r in checks if r["skill"] == "LIFT"]
    (entry,) = [r for r in lift if r["phase"] == "PRE"]
    (entry_robot,) = [
        r["robot"] for r in index["rows"] if r["robot"]["frame_id"] == entry["frame_id"]
    ]
    xyz = entry_robot["tcp_position_m"]
    target = np.array([xyz[0], xyz[1], max(0.16, xyz[2] + 0.1)])
    require(
        all(
            np.array_equal(r["current"]["commanded_target_xyz_m"], target)
            for r in lift
            if r["status"] == "CLEAR"
        ),
        "registered fixed LIFT command not reproduced",
    )
    frames = []
    for gate, robot, _frame in prior.paired_frames(folder, registration, selected):
        support = ancestor_support(cert, checks, gate["step"])
        row = envelope(cert, gate, robot, target, support)
        camera = registration["camera"]
        tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
        far = 1 + max(
            (
                max((np.where(CORNERS, *np.asarray(box["bounds_m"])[::-1]) - tf[:3, 3]) @ tf[:3, 2])
                for box in row["boxes"].values()
            ),
            default=0,
        )
        comparisons = []
        for pixel in pixels:
            cone = pixel_cone(camera, pixel, far)
            bodies = {
                key: compare_cone(cone, value["bounds_m"]) for key, value in row["boxes"].items()
            }
            comparisons.append(
                {
                    "pixel": pixel,
                    "classification": classify(bodies, row["complete"]),
                    "bodies": bodies,
                }
            )
        frames.append(
            {
                "step": gate["step"],
                "frame_id": gate["frame_id"],
                "checksum_sha256": gate["checksum_sha256"],
                "original_status": gate["status"],
                "original_reason": gate["reason"],
                "target_xyz_m": target.tolist(),
                "optical_axial_limit_m": [0.0, far],
                "envelope": row,
                "comparisons": comparisons,
            }
        )
    return {"archive": name, "case": case, "frames": frames}


def predict():
    read_scope()
    for name, digest in PLAN["predict_sha256"].items():
        pinned(ROOT, name, digest)
    prior = load_prior()
    controls = geometry_controls()
    rows = [checked_pair(prior, *case) for case in PLAN["cases"]]
    volume = checked_pair(prior, *PLAN["volume_control"], [])
    before, after = (r["envelope"] for r in volume["frames"])
    require(
        before["source_table_support"]["qualified"]
        and not after["source_table_support"]["qualified"]
        and after["short_motion"]["limiting_body"] == "object_geom"
        and abs(after["short_motion"]["minimum_gap_m"] - 0.001111) < 1e-6,
        "original volume negative control failed",
    )
    require(
        sum(len(f["comparisons"]) for row in rows for f in row["frames"]) == 20, "coverage changed"
    )
    return {
        "plan_sha256": sha(HERE / "plan.json"),
        "controls": controls,
        "rows": rows,
        "volume_control": volume,
    }


def save(name, result):
    OUT.mkdir(exist_ok=True, parents=True)
    with (OUT / name).open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pass_name", choices=("prediction.json", "prediction.cold.json"))
    save(parser.parse_args().pass_name, predict())


if __name__ == "__main__":
    main()
