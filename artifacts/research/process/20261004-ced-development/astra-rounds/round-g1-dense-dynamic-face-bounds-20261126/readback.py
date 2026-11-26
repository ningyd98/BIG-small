"""Cold-compare signed first-face intervals with the unchanged dense sensor packets."""

import argparse
import importlib.util
import sys
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

import numpy as np
from bounds import (
    ASSET,
    DENSE,
    OPTICAL,
    PLAN,
    PLAN_PATH,
    REFERENCE,
    RESULT,
    ROOT,
    require,
)
from scripts.graduation.perception_io import read, sha, write

OLD = ROOT / PLAN["previous_round"]
RAW = DENSE / "native"
NEEDLE = ROOT / PLAN["needle_native"]
SEAL = RAW / "seal.json"


def file_check(root, key):
    members = read(root / "seal.json")[key]
    require(
        {p.name for p in root.iterdir() if p.is_file()} == set(members) | {"seal.json"},
        "frozen native inventory changed",
    )
    for file, digest in members.items():
        path = (root / file).resolve()
        require(path.parent == root and sha(path) == digest, f"unbound native result {file}")


def original_rule():
    sys.path.insert(0, str(OLD))
    module = importlib.util.spec_from_file_location("prior_single_face_reader", OLD / "readback.py")
    require(module is not None and module.loader is not None, "prior single-face code unavailable")
    target = importlib.util.module_from_spec(module)
    module.loader.exec_module(target)
    return target


def check_binding(reference, geometry, checksum):
    require(
        reference["key"] == geometry["key"]
        and reference["shutter_checksum_sha256"] == geometry["source_checksum_sha256"] == checksum,
        "wrong original exposure binding",
    )


def radiometric(observed_z, expected_z, observed_rgb, expected_rgb):
    if observed_z <= 0 or not np.isfinite(observed_z):
        return "invalid_depth"
    if expected_z <= 0 or not np.isfinite(expected_z):
        return "invalid_reference"
    if abs(observed_z - expected_z) >= PLAN["band_m"]:
        return "depth_residual"
    if abs(observed_rgb.astype(int) - expected_rgb).max() > PLAN["rgb_max_dn"]:
        return "rgb_residual"
    return None


def controls():
    fake_ref = {"key": "frame", "shutter_checksum_sha256": "first checksum"}
    fake_geometry = {"key": "frame", "source_checksum_sha256": "other checksum"}
    try:
        check_binding(fake_ref, fake_geometry, "first checksum")
    except ValueError:
        mismatch = True
    else:
        mismatch = False
    black, six, seven = [np.repeat(value, 3) for value in (0, 6, 7)]
    reports = {
        "wrong_exposure_refused": mismatch,
        "four_mm_equality_refused": radiometric(0.008, 0.004, black, black) == "depth_residual",
        "below_four_mm_passes": radiometric(np.nextafter(0.008, 0.0), 0.004, black, black) is None,
        "seven_dn_refused": radiometric(1.0, 1.0, seven, black) == "rgb_residual",
        "six_dn_passes": radiometric(1.0, 1.0, six, black) is None,
        "missing_depth_refused": radiometric(0.0, 1.0, black, black) == "invalid_depth",
    }
    require(all(reports.values()), "frozen thresholds or identity control failed")
    return reports


def contained(lo, hi, depth):
    return max(abs(lo - depth), abs(hi - depth)) < PLAN["band_m"]


def point_diagnostic(ref_depth, ref_rgb, sensor, ray, uv):
    actual_rgb, actual_depth, valid = sensor
    u, v = uv
    seen = float(actual_depth[v, u])
    residual = seen - ref_depth
    decision = ray["reason"]
    if decision is None and not valid[v, u]:
        decision = "invalid_depth"
    if decision is None:
        decision = radiometric(seen, ref_depth, actual_rgb[v, u], ref_rgb)
    if decision is None:
        a, b = ray["axis_depth_interval_m"]
        if not contained(a, b, seen):
            decision = "geometry_outside_observation_band"
        elif not contained(a, b, ref_depth):
            decision = "geometry_outside_reference_band"
    return {
        "uv": list(uv),
        "new_reason": decision,
        "geometry_reason": ray["reason"],
        "observed_axial_m": seen,
        "sealed_reference_axial_m": ref_depth,
        "observation_minus_reference_m": float(residual),
    }


def by_query(pixels):
    samples = {}
    for pixel in pixels:
        for point in pixel["subpixels"]:
            u, v = point["uv"]
            for row, col in product(range(3), repeat=2):
                loc = (u + col - 1, v + row - 1)
                value = (point["depth_m"][row][col], tuple(point["rgb"][row][col]))
                require(
                    loc not in samples or value == samples[loc], "overlapping reference differs"
                )
                samples[loc] = value
    return samples


def compare_frame(reference, sensor, geometry, old):
    ray_at = {tuple(r["uv"]): r for r in geometry["rays"]}
    query = by_query(reference["pixels"])
    require(
        len(ray_at) == len(geometry["rays"]) and set(ray_at) == set(query),
        "prediction did not cover the complete deduplicated stencil",
    )
    results = {
        uv: point_diagnostic(depth, np.asarray(rgb), sensor, ray_at[uv], uv)
        for uv, (depth, rgb) in query.items()
    }
    pixels = []
    for p, o in zip(reference["pixels"], old["pixels"], strict=True):
        require(p["original_uv"] == o["original_uv"], "old pixel ordering differs")
        new_centers = []
        for point in p["subpixels"]:
            u, v = point["uv"]
            stencil = [(u + i, v + j) for j, i in product((-1, 0, 1), repeat=2)]
            reasons = [results[uv]["new_reason"] for uv in stencil if results[uv]["new_reason"]]
            group = defaultdict(list)
            if not reasons:
                for uv in stencil:
                    group[tuple(ray_at[uv]["signed_face"])].append(query[uv][0])
                if any(max(depth) - min(depth) >= PLAN["band_m"] for depth in group.values()):
                    reasons.append("same_face_depth_span")
            new_centers.append(
                {
                    "uv": [u, v],
                    "new_stencil_passed": not reasons,
                    "stencil_failure_counts": dict(Counter(reasons)),
                }
            )
        passes = sum(p["new_stencil_passed"] for p in new_centers)
        pixels.append(
            {
                "original_uv": p["original_uv"],
                "old_explained": o["explained"],
                "new_qualified_subpixels": passes,
                "explained": o["explained"] or passes == PLAN["scale"] ** 2,
                "centers": new_centers,
            }
        )
    return {
        "pixels": pixels,
        "all_explained": all(x["explained"] for x in pixels),
        "geometric_reason_counts": dict(Counter(x["reason"] or "proved" for x in ray_at.values())),
        "nearer_competing_geometries": dict(
            Counter(
                x["closest_competitor"]
                for x in ray_at.values()
                if x["reason"] == "competitor_overlap"
            )
        ),
        "rays": list(results.values()),
    }


def cases_out(source, actual, reference, geometry, old_module, old_archive):
    shots = {entry["key"]: entry for entry in actual["frames"]}
    earlier = {entry["key"]: entry for entry in old_archive["cases"]}
    results = []
    for job in source["jobs"]:
        case = job["key"]
        record = shots[case]
        projected = reference[case]
        require(
            record["source_frame_id"] == geometry[case]["source_frame_id"] == job["frame_id"]
            and record["source_time_s"] == job["time_s"]
            and record["source_checksum_sha256"] == job["checksum_sha256"],
            "actual optical recapture detached from its archived source",
        )
        check_binding(projected, geometry[case], record["source_checksum_sha256"])
        sensor = old_module.arrays(RAW, record)
        replayed = old_module.compare_prediction(projected, sensor)
        require(
            all(replayed[k] == earlier[case][k] for k in replayed),
            "frozen single-face predicate changed",
        )
        results.append(
            compare_frame(projected, sensor, geometry[case], replayed)
            | {k: job[k] for k in ("archive", "slot", "step", "original_status", "original_reason")}
            | {"old_frame_explained": replayed["all_original_points_explained"]}
        )
    return results


def needle_out(case, projected, geometry, old_module, old_archive):
    archive = read(NEEDLE / "index.json")["frames"]
    records = {r["model"]: r for r in archive if (r["step"], r["scale"]) == (2112, PLAN["scale"])}
    prior_result = old_module.old_needle(projected, geometry[case]["source_frame_id"])
    # Cold-read the old physical positive independently and retain the four known returns.
    for s in (120, 2112):
        require(
            prior_result[s]["strong_uv"] == old_archive["needle_controls"][str(s)]["strong_uv"],
            "archived native positive or needle return differs",
        )
    compared = {}
    for key in ("bare", "pin"):
        check_binding(projected, geometry[case], records[key]["original_checksum_sha256"])
        sensor = old_module.arrays(NEEDLE, records[key])
        old = prior_result[2112]["same_reference_results"][key]
        compared[key] = compare_frame(projected, sensor, geometry[case], old)
    strong = {tuple(uv) for uv in prior_result[2112]["strong_uv"]}
    candidates = compared["pin"]["pixels"][0]["centers"]
    refutations = [
        p for p in candidates if tuple(p["uv"]) in strong and not p["new_stencil_passed"]
    ]
    require(
        len(refutations) == len(strong) == 4 and not compared["pin"]["all_explained"],
        "native needle response escaped",
    )
    require(
        all(
            result["new_reason"] is not None
            for result in compared["pin"]["rays"]
            if tuple(result["uv"]) in strong
        ),
        "a true needle return individually escaped",
    )
    return {
        "physical_positive_uv": prior_result[120]["strong_uv"],
        "needle_four_uv": prior_result[2112]["strong_uv"],
        "needle_individual_strong_refutations": len(refutations),
        "compared": compared,
    }


def run(path):
    for relative, digest in PLAN["sha256"].items():
        item = (ROOT / relative).resolve()
        require(item.is_relative_to(ROOT) and sha(item) == digest, f"source differs: {relative}")
    file_check(RAW, "members")
    file_check(NEEDLE, "members")
    controls_ok = controls()
    model = read(RESULT)
    source = read(DENSE / "capture-input.json")
    actual = read(RAW / "index.json")
    pred = read(REFERENCE)
    old_archive = read(DENSE / "readback.json")
    require(
        model["plan_sha256"] == sha(PLAN_PATH)
        and model["optical_input_sha256"] == sha(OPTICAL) == source["optical_input_sha256"]
        and model["sealed_prediction_sha256"] == sha(REFERENCE) == actual["prediction_sha256"]
        and model["source_sha256"] == sha(Path(__file__).with_name("bounds.py"))
        and model["denied_file_controls"] == 2
        and model["proofs_lost_after_bound_expansion"] > 0
        and model["scope"] == PLAN["scope"]
        and actual["assembly_sha256"] == sha(ASSET),
        "blind prediction or uncertainty control differs",
    )
    geometry = {r["key"]: r for r in model["rows"]}
    reference = {r["key"]: r for r in pred["predictions"]}
    require(set(geometry) == set(reference), "blind predictions omitted a frame")
    prior = original_rule()
    results = cases_out(source, actual, reference, geometry, prior, old_archive)
    needle_key = source["needle_key"]
    needle = needle_out(needle_key, reference[needle_key], geometry, prior, old_archive)
    stops = [r for r in results if r["original_status"] == "BLOCKED"]
    require(
        len(stops) == 5
        and len(results) == 10
        and not any(x["old_frame_explained"] for x in stops)
        and sum(p["old_explained"] for r in stops for p in r["pixels"]) == 3
        and sum(len(r["pixels"]) for r in stops) == 10,
        "archived denominator or novel result differs",
    )
    write(
        path,
        {
            "schema": "g1.development.dense-signed-face-bounds.result.v1",
            "plan_sha256": sha(PLAN_PATH),
            "geometry_sha256": sha(RESULT),
            "native_seal_sha256": sha(SEAL),
            "controls": controls_ok,
            "proofs_lost_after_bound_expansion": model["proofs_lost_after_bound_expansion"],
            "cases": results,
            "controls_needle": needle,
            "old_explained_pixels": 3,
            "new_explained_pixels": sum(p["explained"] for r in stops for p in r["pixels"]),
            "new_complete_stops": sum(x["all_explained"] for x in stops),
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.output)
