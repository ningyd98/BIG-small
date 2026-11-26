"""Measure the registered ID8 crossbar edge without sampling the opposite target."""

import argparse
import json
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations, product
from pathlib import Path

import cv2
import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "plan.json"
PLAN = read(PLAN_FILE)
OUT = ROOT / PLAN["output"]
SIGNS = np.array(list(product((-1, 1), repeat=3)))
CROSSBAR = "g1_dual_id8_crossbar"
TABLE = "table"
P = PLAN["thresholds"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def library(key):
    src = ROOT / PLAN[key]
    spec = spec_from_file_location(key, src)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checked_inputs():
    for relative, digest in PLAN["binding_sha256"].items():
        path = ROOT / relative
        require(path.resolve() == path and sha(path) == digest, f"input changed: {relative}")


def blind(allow):
    raw = ROOT / "experiments/results"

    def check(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            target = Path(os.fsdecode(args[0])).resolve()
            if target.is_relative_to(raw) and target not in allow:
                raise PermissionError(f"unregistered optical input: {target.name}")

    sys.addaudithook(check)
    for file in (
        raw / "g1-dense-registered-surface-20261126/capture-input.json",
        raw / "g1-dense-opposite-carrier-20261126/readback.json",
    ):
        try:
            file.read_bytes()
        except PermissionError:
            continue
        raise ValueError("unguarded prior physical or score read")


def project(points, meta):
    camera = np.asarray(meta["camera_to_world"]).reshape(4, 4)
    view = (points - camera[:3, 3]) @ camera[:3, :3]
    require(np.isfinite(view).all() and np.all(view[:, 2] > 0), "geometry projects behind camera")
    f = np.asarray(meta["intrinsics"])
    return view[:, :2] / view[:, 2, None] * f[:2] + f[2:]


def rectangle(mask, view, pad):
    h, w = mask.shape
    lo = np.maximum(np.floor(view.min(axis=0)).astype(int) - pad, 0)
    hi = np.minimum(np.ceil(view.max(axis=0)).astype(int) + pad + 1, [w, h])
    if np.all(lo < hi):
        mask[lo[1] : hi[1], lo[0] : hi[0]] = True


def geometry_mask(job, meta, scene):
    raw = np.zeros((meta["height"], meta["width"]), dtype=bool)
    pad = PLAN["mixed_guard_dense_px"]
    for u, v in job["pixels_original_uv"]:
        rectangle(raw, np.array([[4 * u - 1, 4 * v - 1], [4 * u + 4, 4 * v + 4]]), pad)
    # The needle control retains each predeclared strong subpixel width and the same mask in bare.
    if job["key"] == PLAN["use_keys"][-1]:
        rectangle(raw, np.array([[684, 489], [685, 490]]), pad)
    competitors = np.zeros_like(raw)
    for i, (name, c, r, h) in enumerate(
        zip(scene.names, scene.centers, scene.rotations, scene.half, strict=True)
    ):
        if name in {CROSSBAR, TABLE}:
            continue
        expanded = h + scene.uncertainty[i]
        uv = project(c + SIGNS * expanded @ r.T, meta)
        rectangle(competitors, uv, PLAN["competitor_expansion_dense_px"])
    return raw, competitors


def open_column(mask, u, coords):
    h, w = mask.shape
    if u < 0 or u >= w or coords[0] < 0 or coords[-1] >= h:
        return False
    return not mask[coords, u].any()


def geometry_schedule(job, meta, seed, scene):
    raw, other = geometry_mask(job, meta, scene)
    pose = seed["pose"]
    coarse_r, coarse_c = (
        np.asarray(pose[k]) for k in ("rotation_object_to_world", "center_world_m")
    )
    old_c, old_r = scene.center, scene.rotation
    shape = scene.model.geom(CROSSBAR)
    require(
        np.allclose(shape.pos, [0.0605, 0, 0.018], atol=1e-12, rtol=0)
        and np.allclose(shape.size, [0.0255, 0.004, 0.001], atol=1e-12, rtol=0),
        "crossbar is not frozen 51 mm rectangle",
    )
    y, z = float(shape.size[1]), float(shape.pos[2] + shape.size[2])
    axes = project(
        coarse_c + np.array([[shape.pos[0], y, z], [shape.pos[0], 0, z]]) @ coarse_r.T, meta
    )
    sign = int(np.sign(axes[0, 1] - axes[1, 1]))
    require(sign != 0, "crossbar +Y edge direction is ambiguous")
    segments = {}
    for group, (lo, hi) in PLAN["physical_segments_mm"].items():
        seen = set()
        legal, denied = [], []
        for mm in range(lo, hi + 1, PLAN["source_mm_stride"]):
            local = np.array([mm / 1000.0, y, z])
            estimate = project((coarse_c + coarse_r @ local)[None], meta)[0]
            u = int(round(estimate[0]))
            if u in seen:
                denied.append({"mm": mm, "u": u, "reason": "duplicate_integer_column"})
                continue
            seen.add(u)
            radius = scene.anchor_err + scene.basis @ abs(local - scene.anchor)
            uncertain = project(old_c + (local + SIGNS * radius) @ old_r.T, meta)
            low = min(estimate[1], float(uncertain[:, 1].min()))
            high = max(estimate[1], float(uncertain[:, 1].max()))
            rows = np.arange(int(np.floor(low)) - 2, int(np.ceil(high)) + 3)
            record = {"mm": mm, "u": u, "all_search_rows": rows.tolist()}
            if not open_column(raw, u, rows):
                denied.append(record | {"reason": "guarded_target_window_or_outside"})
            elif not open_column(other, u, rows):
                denied.append(record | {"reason": "registered_competing_geometry"})
            else:
                legal.append(record)
        span = max((r["mm"] for r in legal), default=0) - min((r["mm"] for r in legal), default=0)
        segments[group] = dict(legal=legal, denied=denied, legal_span_mm=span)
    return segments, sign, coarse_r, coarse_c


def supported(segment, name):
    return (
        len(segment["legal"]) >= P[f"{name}_columns"]
        and segment["legal_span_mm"] >= P[f"{name}_span_mm"]
    )


def plane_points(uv, meta, normal, pivot):
    f = np.asarray(meta["intrinsics"])
    tf = np.asarray(meta["camera_to_world"]).reshape(4, 4)
    ray = np.column_stack(((uv - f[2:]) / f[:2], np.ones(len(uv)))) @ tf[:3, :3].T
    denom = ray @ normal
    require(np.all(abs(denom) > 0.1), "grazing crossbar plane")
    z = ((pivot - tf[:3, 3]) @ normal) / denom
    return tf[:3, 3] + z[:, None] * ray, z


def transitions(depth, gray, near, far):
    good = np.isfinite(depth) & (depth > 0)
    inner = good & (abs(depth - near) < P["depth_band_m"])
    outer = good & (abs(depth - far) < P["depth_band_m"]) & (depth - near > P["outside_offset_m"])
    broad = gray[:-3] - gray[3:]
    step = gray[1:-2] - gray[2:-1]
    contrast = (
        (abs(broad) > P["contrast_inner_outer_dn"])
        & (abs(step) > P["contrast_adjacent_dn"])
        & (broad * step > 0)
    )
    fits = inner[:-3] & inner[1:-2] & outer[2:-1] & outer[3:] & contrast
    return np.flatnonzero(fits), np.sign(broad)


def native_edge(segment, meta, path, sign, r, c, shape):
    top = shape.pos + [0, 0, shape.size[2]]
    base = c + r @ top
    accepted, fails = [], []
    for record in segment["legal"]:
        ys = np.asarray(record["all_search_rows"])[::sign]
        uv = np.column_stack((np.full(len(ys), record["u"]), ys))
        x, y = uv.T
        _, near = plane_points(uv, meta, r[:, 2], base)
        _, far = plane_points(uv, meta, [0, 0, 1], [0, 0, 0])
        depth, rgb, valid = path
        if not valid[y, x].all():
            fails.append(record | {"reason": "invalid_pixel"})
            continue
        gray = cv2.cvtColor(rgb[y, x].reshape(-1, 1, 3), cv2.COLOR_RGB2GRAY)[:, 0].astype(float)
        found, polarity = transitions(depth[y, x], gray, near, far)
        if len(found) != 1:
            fails.append(record | {"reason": "nonunique_or_missing_dual_class_transition"})
            continue
        i = int(found[0])
        ends, _ = plane_points(uv[i + 1 : i + 3], meta, r[:, 2], base)
        metric = (ends - base) @ r
        accepted.append(
            record | {"ends_xy_m": metric[:, :2].tolist(), "polarity": int(polarity[i])}
        )
    return dict(
        legal=accepted,
        denied=fails,
        legal_span_mm=max((v["mm"] for v in accepted), default=0)
        - min((v["mm"] for v in accepted), default=0),
    )


def line_range(points):
    left = np.vstack([x["ends_xy_m"][0] for x in points])
    right = np.vstack([x["ends_xy_m"][1] for x in points])
    require(np.all(right[:, 1] > left[:, 1]), "crossbar +Y measurement orientation differs")
    a = np.r_[
        np.column_stack((-left[:, 0], -np.ones(len(left)))),
        np.column_stack((right[:, 0], np.ones(len(right)))),
    ]
    b = np.r_[-left[:, 1], right[:, 1]]
    indices = np.array(list(combinations(range(len(b)), 2)))
    matrix = a[indices]
    good = abs(np.linalg.det(matrix)) > 1e-10
    values = np.linalg.solve(matrix[good], b[indices[good]][..., None])[..., 0]
    return values[np.all(values @ a.T <= b + 1e-10, axis=1)]


def measured_pose(scheduled, meta, arrays, sign, r, c, shape, seed):
    fit, validation = (
        native_edge(scheduled[name], meta, arrays, sign, r, c, shape)
        for name in ("fit", "validation")
    )
    result = {"measured_fit": fit, "measured_validation": validation}
    if not (supported(fit, "fit") and supported(validation, "validation")):
        return result | {"reason": "insufficient_disjoint_measured_edges", "pose": None}
    fitpol = {x["polarity"] for x in fit["legal"]}
    valpol = {x["polarity"] for x in validation["legal"]}
    if len(fitpol) != 1 or fitpol != valpol:
        return result | {"reason": "unstable_rgb_polarity", "pose": None}
    possible = line_range(fit["legal"])
    if not len(possible):
        return result | {"reason": "empty_sampling_bracket", "pose": None}
    slope, offset = possible.mean(0)
    result["sampling_bracket_point_slope_intercept"] = [float(slope), float(offset)]
    result["sampling_bracket_min_max"] = [possible.min(0).tolist(), possible.max(0).tolist()]
    for item in validation["legal"]:
        endpoints = np.asarray(item["ends_xy_m"])
        residual = endpoints[:, 1] - slope * endpoints[:, 0] - offset
        if not residual[0] <= 0 <= residual[1]:
            return result | {"reason": "untouched_validation_bracket_missed", "pose": None}
    angle = np.arctan(slope)
    cos, sin = float(np.cos(angle)), float(np.sin(angle))
    rotation = r @ [[cos, -sin, 0], [sin, cos, 0], [0, 0, 1]]
    shift = offset - float(shape.size[1]) / cos
    center = c + r @ (shape.pos + [0, shift, 0]) - rotation @ shape.pos
    lever = np.asarray(seed["anchor_object_m"])
    pose = seed | {
        "center_world_m": center.tolist(),
        "rotation_object_to_world": rotation.tolist(),
        "anchor_world_m": (center + rotation @ lever).tolist(),
        "method": "id8_crossbar_other_long_edge_diagnostic",
    }
    return result | {"reason": None, "pose": pose}


def controls():
    mask = np.zeros((10, 10), bool)
    mask[4, 3] = True
    sample = np.array([1.339, 1.340, 1.4, 1.401])
    gray = np.array([100, 103, 136, 139])
    near, far = np.full(4, 1.34), np.full(4, 1.4)
    a, _ = transitions(sample, gray, near, far)
    a_reverse, _ = transitions(sample[::-1], gray[::-1], near, far)
    a_two, _ = transitions(np.tile(sample, 2), np.tile(gray, 2), np.tile(near, 2), np.tile(far, 2))
    result = {
        "one_guarded_pixel_rejects_whole_column": not open_column(mask, 3, np.arange(2, 7)),
        "outside_column_refused": not open_column(mask, 10, np.arange(2, 7)),
        "native_style_synthetic_transition_accepted": a.tolist() == [0],
        "reversed_depth_refused": len(a_reverse) == 0,
        "two_transitions_detected_for_rejection": len(a_two) == 2,
        "duplicate_only_columns_cannot_encode_span": not supported(
            {"legal": [0] * 8, "legal_span_mm": 0}, "fit"
        ),
    }
    require(all(result.values()), "edge controls failed")
    return result


def write_new(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("x", encoding="utf-8") as p:
        p.write(
            json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", choices=("prediction.json", "prediction.cold.json"))
    output = p.parse_args().output
    checked_inputs()
    original, bounds = library("source_reader"), library("prior_bounds")
    _, source = original.snapshot_sources()
    source = [v for v in source if v[0]["key"] in PLAN["use_keys"]]
    require(len(source) == 6, "six-frame denominator changed")
    seed_file = ROOT / PLAN["local_seed"]
    seeds = {r["dense_frame_id"]: r for r in read(seed_file)["dense"]}
    blind({OUT / output, ROOT / PLAN["asset"], *[row[2] for row in source]})
    model = mujoco.MjModel.from_xml_path(str(ROOT / PLAN["asset"]))
    result = []
    for job, meta, raw, frame_id in source:
        seed = seeds[frame_id]
        require(
            seed["key"] == job["key"]
            and seed["original_checksum_sha256"] == job["checksum_sha256"],
            "bound seed differs",
        )
        exposure_info = {
            "key": job["key"],
            "dense_frame_id": frame_id,
            "source_shutter_checksum": job["checksum_sha256"],
            "dense_raw_sha256": seed["dense_raw_sha256"],
            "model": meta.get("model"),
        }
        data, pose = bounds.camera_state(model, job)
        scene = bounds.SurfaceBounds(model, data, pose)
        scheduled, sign, r, c = geometry_schedule(job, meta, seed, scene)
        record = exposure_info | {
            "scheduled_segments": scheduled,
            "planned_raw_reads": False,
            "pose": None,
        }
        if not all(supported(scheduled[name], name) for name in ("fit", "validation")):
            result.append(record | {"reason": "insufficient_unmasked_geometry_columns"})
            continue
        require(sha(raw) == seed["dense_raw_sha256"], "raw dense frame changed")
        with np.load(raw, allow_pickle=False) as pack:
            arrays = pack["depth_m"], pack["rgb"], pack["valid"]
        score = measured_pose(
            scheduled, meta, arrays, sign, r, c, model.geom(CROSSBAR), seed["pose"]
        )
        result.append(record | score | {"planned_raw_reads": True})
    write_new(
        output,
        {
            "plan_sha256": sha(PLAN_FILE),
            "script_sha256": sha(Path(__file__).resolve()),
            "rows": result,
            "controls": controls(),
        },
    )


if __name__ == "__main__":
    main()
