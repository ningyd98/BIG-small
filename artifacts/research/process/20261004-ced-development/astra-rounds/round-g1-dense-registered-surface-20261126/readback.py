"""Cold-compare frozen optical reference patches to native returns and the real-pin control."""

import argparse
import math
from collections import Counter
from pathlib import Path

import numpy as np
from register import (
    ASSET,
    HEIGHT,
    HERE,
    NEEDLE_ARCHIVE,
    OPTICAL,
    OUT,
    PHYSICAL,
    PLAN,
    PLAN_PATH,
    SCALE,
    WIDTH,
    pins,
    require,
    seal,
)
from scripts.graduation.g1_complete_cv_carried_surface import compare_face_patch
from scripts.graduation.perception_io import read, sha, write

RAW = OUT / "native"
PREDICTED = OUT / "prediction.json"


def arrays(folder, record):
    path = (folder / record["file"]).resolve()
    require(path.parent == folder and sha(path) == record["file_sha256"], "sensor bytes differ")
    with np.load(path, allow_pickle=False) as archive:
        color, depth, valid = (archive[key] for key in ("rgb", "depth_m", "valid"))
    require(
        color.shape == (HEIGHT, WIDTH, 3)
        and color.dtype == np.uint8
        and depth.shape == valid.shape == (HEIGHT, WIDTH)
        and depth.dtype == np.dtype("<f4")
        and valid.dtype == np.uint8
        and np.isfinite(depth).all()
        and np.array_equal(depth > 0, valid.astype(bool)),
        "malformed native RGB-D array",
    )
    return color, depth, valid


def compare_registered_pixel(predicted, observed_rgb, observed_depth):
    points = []
    source_u, source_v = predicted["original_uv"]
    coordinates = [
        [source_u * SCALE + i, source_v * SCALE + j] for j in range(SCALE) for i in range(SCALE)
    ]
    require([p["uv"] for p in predicted["subpixels"]] == coordinates, "fixed subgrid differs")
    for point in predicted["subpixels"]:
        u, v = point["uv"]
        roi = np.s_[v - 1 : v + 2, u - 1 : u + 2]
        reference = np.asarray(point["depth_m"])
        expected_rgb = np.asarray(point["rgb"])
        interior = np.asarray(point["interior"])
        actual = observed_depth[roi]
        color = observed_rgb[roi]
        residual = actual - reference
        max_z = float(abs(residual).max())
        max_rgb = int(abs(color.astype(int) - expected_rgb).max())
        span = float(np.ptp(reference))
        failed = []
        if not np.all(interior) or point["center_face"] is None:
            failed.append("no_same_safe_interior_face")
        if not np.all(actual > 0):
            failed.append("invalid_observed_depth")
        if span >= PLAN["band_m"]:
            failed.append("mixed_reference_depth")
        if max_z >= PLAN["band_m"]:
            failed.append("depth_residual")
        if max_rgb > PLAN["rgb_max_dn"]:
            failed.append("rgb_residual")
        flag = compare_face_patch(actual, reference, color, expected_rgb, interior)
        require(flag == (not failed), "adapter changed the frozen face predicate")
        points.append(
            {
                "uv": [u, v],
                "parsed_center_face": point["center_face"],
                "qualified": flag,
                "failures": failed,
                "reference_center_m": float(reference[1, 1]),
                "observed_center_m": float(actual[1, 1]),
                "center_depth_residual_m": float(residual[1, 1]),
                "max_patch_depth_residual_m": max_z,
                "max_patch_rgb_residual_dn": max_rgb,
                "reference_patch_depth_span_m": span,
            }
        )
    faces = {tuple(p["parsed_center_face"]) for p in points if p["parsed_center_face"] is not None}
    accepted = sum(p["qualified"] for p in points)
    return {
        "original_uv": predicted["original_uv"],
        "qualified_subpixels": accepted,
        "explained": accepted == SCALE**2 and len(faces) == 1,
        "first_face_inventory": [list(face) for face in sorted(faces)],
        "per_point": points,
    }


def compare_prediction(predicted, raw):
    rgb, depth, _ = raw
    pixels = [compare_registered_pixel(p, rgb, depth) for p in predicted["pixels"]]
    require(pixels, "registered frame without a query pixel")
    return {
        "key": predicted["key"],
        "pixels": pixels,
        "all_original_points_explained": all(p["explained"] for p in pixels),
        "individual_dense_points_passed": sum(p["qualified_subpixels"] for p in pixels),
        "point_failure_counts": dict(
            Counter(flag for pixel in pixels for p in pixel["per_point"] for flag in p["failures"])
        ),
    }


def old_needle(predicted, expected_frame_id):
    frames = read(NEEDLE_ARCHIVE / "index.json")["frames"]
    pairs = {}
    for step in (120, 2112):
        items = [r for r in frames if (r["step"], r["scale"]) == (step, SCALE)]
        bare, pin = [next(r for r in items if r["model"] == mode) for mode in ("bare", "pin")]
        require(
            len(items) == 2
            and bare["seed"] == pin["seed"]
            and bare["camera_to_world"] == pin["camera_to_world"]
            and bare["intrinsics"] == pin["intrinsics"]
            and bare["original_checksum_sha256"] == pin["original_checksum_sha256"],
            "needle control metadata differs",
        )
        if step == 2112:
            require(
                bare["original_frame_id"] == pin["original_frame_id"] == expected_frame_id,
                "needle pair not linked to the original prediction",
            )
        a, b = arrays(NEEDLE_ARCHIVE, bare), arrays(NEEDLE_ARCHIVE, pin)
        delta = a[1] - b[1]
        uv = np.argwhere(delta > PLAN["needle_threshold_m"])
        require(
            np.array_equal(a[2], b[2])
            and len(uv) == 4
            and all([int(u) // SCALE, int(v) // SCALE] == [171, 122] for v, u in uv),
            "native positive/negative control did not reproduce four over-threshold pixels",
        )
        pairs[step] = {
            "maximum_bare_minus_pin_m": float(delta.max()),
            "strong_uv": [[int(u), int(v)] for v, u in uv],
        }
        if step == 2112:
            paired_results = {
                key: compare_prediction(predicted, raw) for key, raw in (("bare", a), ("pin", b))
            }
            point_rows = {
                tuple(p["uv"]): p for p in paired_results["pin"]["pixels"][0]["per_point"]
            }
            pairs[step]["points_with_actual_needle_signal"] = [
                point_rows[tuple(x)] for x in pairs[step]["strong_uv"]
            ]
            pairs[step]["same_reference_results"] = paired_results
    require(
        not pairs[2112]["same_reference_results"]["pin"]["all_original_points_explained"],
        "actual needle was explained",
    )
    return pairs


def run(out):
    pins()
    seal(RAW, "members")
    seal(NEEDLE_ARCHIVE, "members")
    pred, index, source, optics = map(read, (PREDICTED, RAW / "index.json", PHYSICAL, OPTICAL))
    jobs = {item["key"]: item for item in optics["jobs"]}
    predicted = {item["key"]: item for item in pred["predictions"]}
    actual = {item["key"]: item for item in index["frames"]}
    require(
        sha(OPTICAL) == index["optical_input_sha256"] == pred["optical_input_sha256"]
        and sha(PREDICTED) == index["prediction_sha256"]
        and sha(PHYSICAL) == index["capture_input_sha256"]
        and sha(PLAN_PATH) == source["plan_sha256"] == optics["plan_sha256"]
        and sha(ASSET) == index["assembly_sha256"] == optics["assembly_sha256"]
        and sha(HERE / "predict.py") == pred["source_sha256"]
        and sha(HERE / "capture.py") == index["source_sha256"]
        and pred["blocked_file_controls"] == 2
        and pred["physics_steps"] == index["physics_steps"] == 0
        and len(actual) == len(index["frames"]) == PLAN["max_new_captures"]
        and set(actual) == {j["key"] for j in source["jobs"]}
        and set(jobs) == set(predicted) == set(actual) | {source["needle_key"]}
        and len(predicted)
        == PLAN["max_reference_projections"]
        == pred["rgb_passes"]
        == pred["depth_passes"],
        "raw closure or optical prediction staging differs",
    )
    old = old_needle(predicted[source["needle_key"]], jobs[source["needle_key"]]["frame_id"])
    results = []
    for job in source["jobs"]:
        key = job["key"]
        p, a = predicted[key], actual[key]
        camera = source["camera"]
        require(
            p["shutter_checksum_sha256"] == a["source_checksum_sha256"] == job["checksum_sha256"]
            and a["source_frame_id"] == job["frame_id"]
            and a["source_time_s"] == job["time_s"]
            and a["seed"] == job["seed"]
            and a["noise_std_m"] == PLAN["noise_std_m"]
            and a["camera_to_world"] == camera["camera_to_world"]
            and a["msaa"] == 4
            and a["renderer"] == pred["renderer"]
            and (a["width"], a["height"]) == (WIDTH, HEIGHT)
            and np.allclose(
                a["intrinsics"],
                [
                    camera["intrinsics"][0] * SCALE,
                    camera["intrinsics"][1] * SCALE,
                    (WIDTH - 1) / 2,
                    (HEIGHT - 1) / 2,
                ],
                atol=1e-12,
                rtol=0,
            )
            and [item["original_uv"] for item in p["pixels"]] == jobs[key]["pixels_original_uv"],
            "native/optical packet, geometry or camera mismatch",
        )
        scored = compare_prediction(p, arrays(RAW, a))
        estimated = jobs[key]["optical"]
        relative = np.asarray(estimated["rotation"]).T @ np.asarray(job["world_object_rotation"])
        angle = math.degrees(math.acos(np.clip((np.trace(relative) - 1) / 2, -1.0, 1.0)))
        results.append(
            scored
            | {
                name: job[name]
                for name in ("archive", "slot", "step", "original_status", "original_reason")
            }
            | {
                "optical_pose_difference_m": float(
                    np.linalg.norm(np.asarray(estimated["center_m"]) - job["world_object_center_m"])
                ),
                "optical_rotation_difference_deg": angle,
                "camera_call_wall_ms": a["camera_call_wall_ms"],
                "reference_rgb_depth_wall_ms": p["reference_rgb_depth_wall_ms"],
            }
        )
    write(
        out,
        {
            "schema": "g1.development.dense-registered-surface.results.v1",
            "baseline": PLAN["baseline"],
            "plan_sha256": sha(PLAN_PATH),
            "native_seal_sha256": sha(RAW / "seal.json"),
            "prediction_sha256": sha(PREDICTED),
            "capture_count": len(actual),
            "predict_reference_rgb_passes": pred["rgb_passes"],
            "predict_reference_depth_passes": pred["depth_passes"],
            "cases": results,
            "needle_controls": old,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.output)
