"""Isolate final-plane refinement on the frozen reduced RGB windows."""

import argparse
import json
import subprocess
import sys
from collections import Counter
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "round-g1-rgb-edge-reduced-20261126"
sys.path.insert(0, str(PRIOR))
import read_reduced_fit as core  # noqa: E402

root, reader, require = core.root, core.reader, core.require
previous = core.previous
FROZEN = core.OUT
OUT = root / "experiments/results/g1-rgb-edge-plane-refit-20261126/development-01"
PLAN = reader.read(HERE / "plan.json")
old_fit = core.one_fit
old_audit = core.inspect_packet


def pin_inputs():
    core.pin_inputs()
    roots = {"prior": PRIOR, "native": root, "frozen": FROZEN}
    for key, expected in PLAN["sha256"].items():
        stem, name = key.split("/", 1)
        reader.pin(roots[stem] / name, expected)


def register():
    pin_inputs()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["head"], "wrong Astra baseline")
    packets, _ = core.packet_list()
    frozen = reader.read(FROZEN / "registration.json")
    require(packets == frozen["packets"] and len(packets) == PLAN["frames"], "source set differs")
    for entry in packets.values():
        reader.pin(root / entry["path"], entry["sha256"])
    core.check_geometry_controls()
    OUT.mkdir(exist_ok=False, parents=True)
    reader.write(
        OUT / "registration.json",
        {
            "packets": packets,
            "source_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "parent_registration_sha256": sha(FROZEN / "registration.json"),
        },
    )


def read_registration(expected):
    reg = reader.read(reader.pin(OUT / "registration.json", expected))
    require(
        reg["source_sha256"] == sha(Path(__file__))
        and reg["plan_sha256"] == sha(HERE / "plan.json"),
        "registered plane reader changed",
    )
    return reg


def cloud(state, uv):
    x, y = uv.T
    depth = state["depth"][y, x]
    require(np.all(np.isfinite(depth) & (depth > 0)), "invalid same-frame retained depth")
    rays = optics._rays(uv, *state["frame"].intrinsics)
    return state["eye"] + (rays * depth[:, None]) @ state["rotation"].T


def selected_cloud(state, fitted_columns):
    native_pixels, rgb = previous.original_pixels(state)
    use = np.isin(native_pixels[:, 0], fitted_columns[:, 0])
    require(
        np.array_equal(rgb[use], fitted_columns), "retained point did not come from native edge"
    )
    uv = native_pixels[use].copy()
    uv[:, 1] -= 2 * state["sign"]
    return uv, cloud(state, uv)


def refined(point, states, rgb, marker):
    frame = states[-1]["frame"]
    corners = np.asarray(marker["by_id"]["8"]["ordered_corners_px"])
    interior = optics._pixels(corners, frame.width, frame.height)
    require(interior is not None, "native interior point set changed")
    parts = [cloud(states[-1], interior)]
    ray_pixels = []
    for side in (-1, 1):
        pixel, world = selected_cloud(states[side], rgb[side])
        ray_pixels.append(pixel.tolist())
        parts.append(world)
    result = optics._fit_plane(np.vstack(parts))
    evidence = {"original_id8_interior_count": len(interior), "far_planar_pixels": ray_pixels}
    if result is None:
        return {"point": point, "status": "fallback_to_initial", **evidence}
    normal, _, inliers = result
    first_vector = np.asarray(point["rotation"])[:, 0]
    forward = first_vector - normal * (normal @ first_vector)
    norm = np.linalg.norm(forward)
    require(np.isfinite(norm) and norm > 1e-12, "degenerate refined forward vector")
    forward /= norm
    rotation = np.column_stack((forward, np.cross(normal, forward), normal))
    anchor = np.asarray(point["anchor_world_m"])
    center = anchor - rotation @ np.asarray(point["anchor_object_m"])
    old_normal = np.asarray(point["rotation"])[:, 2]
    angle = np.arctan2(np.linalg.norm(np.cross(old_normal, normal)), old_normal @ normal)
    return {
        "status": "refitted",
        "point": dict(point, center_m=center.tolist(), rotation=rotation.tolist()),
        "plane_inlier_count": int(inliers.sum()),
        "normal_delta_rad": float(angle),
        **evidence,
    }


def compare_plane(measured, states, rgb, side, columns, kind, *, marker):
    baseline = old_fit(measured, states, rgb, side, columns, kind)
    point = baseline["point"]
    computed = (
        refined(point, states, rgb, marker)
        if point is not None
        else {"status": "original_rgb_fit_refused", "point": None}
    )
    return dict(baseline, extension=computed)


def uncropped_controls(frame, marker, scene, certified):
    measured, states = previous.original_state(frame, marker, scene)
    rgb = {side: previous.original_pixels(states[side])[1] for side in (-1, 1)}
    require(
        all(core.strong_side(pixels) for pixels in rgb.values()),
        "original two-edge control lacks original points",
    )
    line, check = previous.fiducial_fit(states, rgb)
    require(check["same_native_metric_limits"], "original uncropped control does not fit")
    initial = previous.point_diagnostic(measured, states[-1], line[1])
    recomputed = refined(initial, states, rgb, marker)
    point = recomputed["point"]
    errors = {
        key: float(np.max(abs(np.asarray(point[key]) - np.asarray(certified[key]))))
        for key in ("center_m", "rotation", "anchor_world_m", "anchor_object_m")
    }
    require(
        max(errors.values()) <= PLAN["uncropped_control_max_m_or_matrix_abs"],
        "uncropped original edge and plane pose failed to reproduce",
    )
    return {
        "method": "id8_opposite_edges",
        "max_abs_errors": errors,
        "extended_plane": recomputed["status"],
    }


def audit(frame, marker, scene, identity, step, excluded):
    with patch.object(core, "one_fit", partial(compare_plane, marker=marker)):
        row = old_audit(frame, marker, scene, identity, step, excluded)
    certified = row["original"]
    if not excluded and certified and certified["method"] == "id8_opposite_edges":
        row["uncropped_control"] = uncropped_controls(frame, marker, scene, certified)
    return row


def predict(reg, name):
    with (
        patch.object(core, "OUT", OUT),
        patch.object(core, "load_registration", read_registration),
        patch.object(core, "inspect_packet", audit),
    ):
        core.predict(reg, name)


def evaluate(point, truth):
    result = core.measure_error(point, truth)
    gap = optics.CALIBRATION["id8_opposite_edges"]
    relative = np.asarray(point["rotation"]).T @ np.asarray(truth["rotation"])
    basis = abs(relative - np.eye(3)) / np.asarray(gap["basis"])
    result.update(
        pitch_ratio=float(max(basis[0, 2], basis[2, 0])),
        yaw_ratio=float(max(basis[0, 1], basis[1, 0])),
        roll_ratio=float(max(basis[1, 2], basis[2, 1])),
    )
    return result


def label(item):
    return "inside" if item["covered_by_existing_diagnostic_range"] else "outside"


def score(registration_hash, expected):
    pin_inputs()
    reg = read_registration(registration_hash)
    first, second = (
        reader.pin(OUT / f"predictions-{name}.json", expected).read_bytes()
        for name in ("first", "second")
    )
    require(first == second, "plane sensitivity predictions differ")
    prediction = json.loads(first)
    require(
        prediction["registration_sha256"] == registration_hash
        and prediction["label_access_denied"],
        "prediction provenance differs",
    )
    initial = reader.read(FROZEN / "predictions-first.json")["rows"]
    labels = core.physical_labels()
    rows = prediction["rows"]
    require(set(rows) == set(reg["packets"]) == set(initial), "registered source set changed")
    counts = Counter()
    reduced_kinds = Counter()
    groups = {g: Counter() for g in core.PLAN["counts"]}
    uncropped = []
    comparisons = []
    natural = []
    for key, row in rows.items():
        whole = row.pop("uncropped_control", None)
        if whole:
            uncropped.append(whole)
        extensions = [model.pop("extension") for model in row["models"]]
        require(row == initial[key], f"frozen observations or pair positions differ: {key}")
        group = key.split("/")[0]
        for before, extension in zip(row["models"], extensions, strict=True):
            require(before["point"] is not None, "previous estimate unexpectedly missing")
            old = evaluate(before["point"], labels[key])
            new = evaluate(extension["point"], labels[key])
            transition = f"{label(old)}_to_{label(new)}"
            counts[transition] += 1
            counts["refit_" + extension["status"]] += 1
            reduced_kinds[before["kind"]] += 1
            groups[group][transition] += 1
            if before["matches_t02_support"]:
                counts["target_support_" + transition] += 1
            detail = {
                "frame": key,
                "frame_id": row["frame_id"],
                "step": row["physics_step"],
                "weak_columns": before["weak_columns"],
                "side": before["side"],
                "kind": before["kind"],
                "matches_t02_support": before["matches_t02_support"],
                "transition": transition,
                "retained_samples": extension.get("far_planar_pixels"),
                "before": old,
                "after": new,
                "extended_plane": extension["status"],
                "normal_delta_rad": extension.get("normal_delta_rad"),
            }
            comparisons.append(detail)
            if before["kind"] == "natural":
                natural.append(detail)
    require(
        reduced_kinds == PLAN["models"] and uncropped, "pair count or uncropped positive absent"
    )
    require(
        counts["outside_to_outside"] + counts["outside_to_inside"] == 549,
        "paired baseline no longer reproduces 549 outside",
    )
    complete_recovery = not any(
        counts[key]
        for key in ("inside_to_outside", "outside_to_outside", "refit_fallback_to_initial")
    )
    reader.write(
        OUT / "readback.json",
        {
            "registration_sha256": registration_hash,
            "predictions_sha256": expected,
            "uncropped_control_count": len(uncropped),
            "uncropped_control_max_abs": max(max(x["max_abs_errors"].values()) for x in uncropped),
            "masked_and_natural_counts": reduced_kinds,
            "counts": counts,
            "groups": groups,
            "natural_results": natural,
            "comparisons": comparisons,
            "limits": PLAN["limits"],
            "full_recovery_on_frozen_set": complete_recovery,
            "eligible_for_online_or_relational_replay": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        register()
    elif args.mode == "predict":
        require(args.argument in ("first", "second"), "prediction process not registered")
        predict(args.registration_sha, args.argument)
    else:
        score(args.registration_sha, args.argument)
