"""Test a depth-only crossbar candidate on an untouched gray/depth segment."""

import argparse
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["output"]
THRESHOLDS = PLAN["thresholds"]
EPS = PLAN["polytope_margin"]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def check(mapping):
    for rel, h in mapping.items():
        p = ROOT / rel
        require(p.resolve(strict=True) == p and sha(p) == h, f"changed source: {rel}")


def split_module():
    path = ROOT / PLAN["old_split_module"]
    spec = spec_from_file_location("prior_split", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transitions(depth, near, far):
    good = np.isfinite(depth) & (depth > 0)
    close = good & (np.abs(depth - near) < THRESHOLDS["depth_band_m"])
    back = (
        good
        & (np.abs(depth - far) < THRESHOLDS["depth_band_m"])
        & (depth - near > THRESHOLDS["outside_offset_m"])
    )
    return np.flatnonzero(close[:-3] & close[1:-2] & back[2:-1] & back[3:])


def gather_depth(base, segment, meta, data, sign, r, c, shape):
    raw, valid = data
    pivot = c + r @ (shape.pos + [0, 0, shape.size[2]])
    legal, denied = [], []
    for record in segment["legal"]:
        y = np.asarray(record["all_search_rows"])[::sign]
        x = np.full(len(y), record["u"])
        uv = np.column_stack((x, y))
        if not valid[y, x].all():
            denied.append(record | {"reason": "invalid_permitted_search_pixel"})
            continue
        _, near = base.plane_points(uv, meta, r[:, 2], pivot)
        _, far = base.plane_points(uv, meta, [0, 0, 1], [0, 0, 0])
        values = raw[y, x]
        indices = transitions(values, near, far)
        if len(indices) != 1:
            denied.append(record | {"reason": "no_unique_directed_depth_transition"})
            continue
        i = int(indices[0])
        endpoints, _ = base.plane_points(uv[i + 1 : i + 3], meta, r[:, 2], pivot)
        metric = (endpoints - pivot) @ r
        require(metric[0, 1] < metric[1, 1], "wrong registered material edge direction")
        legal.append(
            record
            | {
                "ends_xy_m": metric[:, :2].tolist(),
                "four_pixels_uv": uv[i : i + 4].tolist(),
                "four_depth_samples_m": values[i : i + 4].astype(float).tolist(),
                "expected_top_axial_m": near[i : i + 4].tolist(),
                "expected_table_axial_m": far[i : i + 4].tolist(),
            }
        )
    span = max((v["mm"] for v in legal), default=0) - min((v["mm"] for v in legal), default=0)
    return {"legal": legal, "denied": denied, "legal_span_mm": span}


def clip(poly, normal, upper):
    if not len(poly):
        return poly
    vertices = []
    previous = poly[-1]
    distance = float(previous @ normal - upper)
    for current in poly:
        next_distance = float(current @ normal - upper)
        if (next_distance <= 0) != (distance <= 0):
            fraction = distance / (distance - next_distance)
            vertices.append(previous + fraction * (current - previous))
        if next_distance <= 0:
            vertices.append(current)
        previous, distance = current, next_distance
    return np.asarray(vertices).reshape(-1, 2)


def centroid(poly):
    if len(poly) < 3:
        return None
    shifted = poly - poly[0]
    following = np.roll(shifted, -1, axis=0)
    twice_areas = shifted[:, 0] * following[:, 1] - shifted[:, 1] * following[:, 0]
    total = twice_areas.sum()
    if total <= EPS:
        return None
    return poly[0] + ((shifted + following) * twice_areas[:, None]).sum(0) / (3 * total)


def outer_parameter_domain(r, c, geom, old):
    ref = np.asarray(old["rotation"])
    anchor = np.asarray(old["anchor_object_m"])
    anchor_world = np.asarray(old["anchor_world_m"])
    matrix_band = np.asarray(old["basis_error_object"])
    pivot_error = np.asarray(old["anchor_error_object_m"]) + matrix_band @ abs(geom.pos - anchor)
    center_offset = c + r @ geom.pos - (anchor_world + ref @ (geom.pos - anchor))
    lateral_limit = np.linalg.norm(pivot_error) + abs(center_offset @ r[:, 1])
    correction_limit = 2 * np.arcsin(min(1.0, np.linalg.norm(matrix_band) / (2 * np.sqrt(2))))
    old_to_seed = np.arccos(np.clip((np.trace(ref.T @ r) - 1) / 2, -1, 1))
    yaw = correction_limit + old_to_seed
    require(yaw < np.pi / 4, "old pose bound cannot constrain line slope")
    width = geom.size[1]
    slope = np.tan(yaw)
    lo = width - lateral_limit - EPS
    hi = width / np.cos(yaw) + lateral_limit + EPS
    return np.array([[-slope, lo], [slope, lo], [slope, hi], [-slope, hi]])


def line_hull(points, domain):
    polygon = domain
    for point in points:
        (x0, y0), (x1, y1) = point["ends_xy_m"]
        polygon = clip(polygon, np.array([-x0, -1]), -y0)
        polygon = clip(polygon, np.array([x1, 1]), y1)
    return polygon


def candidate_pose(parameters, seed, r, c, shape):
    slope, intercept = parameters
    angle = np.arctan(slope)
    co, si = np.cos(angle), np.sin(angle)
    new_r = r @ [[co, -si, 0], [si, co, 0], [0, 0, 1]]
    shift = intercept - shape.size[1] / co
    new_c = c + r @ (shape.pos + [0, shift, 0]) - new_r @ shape.pos
    lever = np.asarray(seed["anchor_object_m"])
    return seed | {
        "center_world_m": new_c.tolist(),
        "rotation_object_to_world": new_r.tolist(),
        "anchor_world_m": (new_c + new_r @ lever).tolist(),
        "method": "guarded_depth_crossbar_point_diagnostic",
    }


def predict_fit(base, prior, geom, old, seed, r, c, depth_support):
    result = {"depth_support": depth_support, "pose": None}
    if not base.supported(depth_support, "fit"):
        return result | {"reason": "insufficient_unique_depth_columns"}
    domain = outer_parameter_domain(r, c, geom, old)
    hull = line_hull(depth_support["legal"], domain)
    point = centroid(hull)
    result |= {
        "slope_intercept_polygon": hull.tolist(),
        "outer_parameter_rectangle": domain.tolist(),
    }
    if point is None:
        return result | {"reason": "sampling_polygon_empty_or_degenerate"}
    pose = candidate_pose(point, seed, r, c, geom)
    if not prior.pose_within_old_bound(pose, old):
        return result | {"reason": "sampling_centroid_outside_original_directional_pose_bound"}
    return result | {
        "reason": None,
        "pose": pose,
        "chosen_slope_intercept": point.tolist(),
        "candidate_vertices_within_original_pose_bound": [
            bool(prior.pose_within_old_bound(candidate_pose(v, seed, r, c, geom), old))
            for v in hull
        ],
    }


def predict_validation(base, fit, measured):
    evidence = {"gray_depth_validation": measured}
    if fit["pose"] is None:
        return evidence | {"qualified": False, "reason": "no_depth_fit"}
    chosen = np.asarray(fit["chosen_slope_intercept"])
    poly = np.asarray(fit["slope_intercept_polygon"])
    per_column = []
    for item in measured["legal"]:
        endpoints = np.asarray(item["ends_xy_m"])
        line_terms = np.column_stack((endpoints[:, 0], np.ones(2)))
        local = endpoints[:, 1] - line_terms @ chosen
        extrema = endpoints[:, 1, None] - line_terms @ poly.T
        per_column.append(
            {
                "mm": item["mm"],
                "centroid_inside": bool(local[0] <= EPS and local[1] >= -EPS),
                "all_polygon_inside": bool(max(extrema[0]) <= EPS and min(extrema[1]) >= -EPS),
            }
        )
    polarities = {x["polarity"] for x in measured["legal"]}
    basic = base.supported(measured, "validation") and len(polarities) == 1
    point_pass = basic and all(row["centroid_inside"] for row in per_column)
    full_pass = point_pass and all(row["all_polygon_inside"] for row in per_column)
    return evidence | {
        "sampled_validation_columns_pass": per_column,
        "minimum_support_pass": basic,
        "centroid_pass": point_pass,
        "qualified": full_pass,
        "reason": None
        if full_pass
        else (
            "gray_depth_validation_support_insufficient"
            if not basic
            else "sampling_polygon_not_fully_validated"
        ),
    }


def controls():
    near, far = np.full(4, 1.34), np.full(4, 1.4)
    trace = np.array([1.34, 1.341, 1.4, 1.399])
    rect = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    out = {
        "known_directed_depth_step": transitions(trace, near, far).tolist() == [0],
        "opposite_depth_step_rejected": len(transitions(trace[::-1], near, far)) == 0,
        "wrong_table_plane_rejected": len(transitions(trace, near, far + 0.02)) == 0,
        "multiple_directed_steps_identified": len(
            transitions(np.tile(trace, 2), np.tile(near, 2), np.tile(far, 2))
        )
        == 2,
        "known_clipped_area_centroid": np.allclose(centroid(clip(rect, [1, 0], 0.5)), [0.25, 0.5]),
        "empty_polygon_rejected": centroid(clip(rect, [1, 0], -1)) is None,
    }
    require(all(out.values()), "depth/interval control failed")
    return out


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("x", encoding="utf-8") as f:
        f.write(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )


def execute(name):
    check(PLAN["registered_sources"])
    checks = controls()
    prior = split_module()
    base, geo, _, source, seeds = prior.registered()
    p = read(ROOT / PLAN["old_prediction"])
    pair = {r["group"]: r for r in p["pairs"]}
    model = mujoco.MjModel.from_xml_path(str(ROOT / base.PLAN["asset"]))
    geom = model.geom(base.CROSSBAR)
    fit_file = "fit.cold.json" if name == "prediction.cold.json" else "fit.json"
    waves, permitted = [], []
    for family, entries in prior.sorted_pairs(source):
        old = pair[family]
        selection = old["selection"]["selected"]
        for i, (job, meta, file, frame) in enumerate(entries):
            require(
                frame == old["frames"][i]["frame_id"]
                and job["checksum_sha256"] == old["frames"][i]["episode_shutter_checksum"]
                and meta["file_sha256"] == old["frames"][i]["dense_raw_sha256"],
                "prior chosen exposure not bound",
            )
            seed = seeds[frame]
            record = dict(
                family=family,
                key=job["key"],
                dense_frame_id=frame,
                dense_raw_sha256=meta["file_sha256"],
                fixture=meta.get("model"),
                source_shutter_sha256=job["checksum_sha256"],
                fit=None,
            )
            waves.append(record)
            if selection is not None:
                _, transform = prior.stations(base, geo, model, entries[i], seed)
                scheduled = {
                    role: values[i]
                    for role, values in selection["actual_measurement_footprints"].items()
                }
                record["scheduled"] = scheduled
                permitted.append(
                    (job, meta, file, record, seed, transform, old["frames"][i]["measurement"])
                )
    base.blind({ROOT / base.PLAN["asset"], OUT / name, OUT / fit_file, *(r[2] for r in permitted)})
    for job, meta, file, record, seed, (sign, r, c), _before in permitted:
        require(sha(file) == record["dense_raw_sha256"], "changed native fit frame")
        with np.load(file, allow_pickle=False) as data:
            depth = gather_depth(
                base,
                record["scheduled"]["fit"],
                meta,
                (data["depth_m"], data["valid"]),
                sign,
                r,
                c,
                geom,
            )
        record["fit"] = predict_fit(base, prior, geom, job["optical"], seed["pose"], r, c, depth)
    save(fit_file, {"plan_sha256": sha(PLAN_PATH), "rows": waves})
    fit_sha = sha(OUT / fit_file)
    for _, meta, file, record, _, (sign, r, c), before in permitted:
        require(sha(file) == record["dense_raw_sha256"], "changed native validation frame")
        with np.load(file, allow_pickle=False) as data:
            arrays = data["depth_m"], data["rgb"], data["valid"]
        kept = base.native_edge(record["scheduled"]["validation"], meta, arrays, sign, r, c, geom)
        gray_fit = base.native_edge(record["scheduled"]["fit"], meta, arrays, sign, r, c, geom)
        require(
            kept == before["measured_validation"] and gray_fit == before["measured_fit"],
            "legacy gray/depth comparison differs",
        )
        record["validation"] = predict_validation(base, record["fit"], kept)
        record["legacy_gray_depth_fit_count"] = len(gray_fit["legal"])
    save(
        name,
        {
            "plan_sha256": sha(PLAN_PATH),
            "script_sha256": sha(Path(__file__).resolve()),
            "fit_before_validation_sha256": fit_sha,
            "controls": checks,
            "rows": waves,
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", choices=("prediction.json", "prediction.cold.json"))
    execute(p.parse_args().name)


if __name__ == "__main__":
    main()
