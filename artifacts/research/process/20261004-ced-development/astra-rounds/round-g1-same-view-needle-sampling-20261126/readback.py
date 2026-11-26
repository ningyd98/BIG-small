"""Cold-read the sealed native comparisons and join actual differences to geometric rays."""

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from rays import HERE, OUT, PLAN, PLAN_PATH, original_inputs, require
from scripts.graduation.perception_io import read, sha, write

RAW = OUT / "capture-01"


def arrays(record):
    path = RAW / record["file"]
    require(path.parent == RAW and sha(path) == record["file_sha256"], "native array differs")
    with np.load(path, allow_pickle=False) as data:
        rgb, depth, valid = (data[key] for key in ("rgb", "depth_m", "valid"))
    shape = (record["height"], record["width"])
    require(
        rgb.shape == shape + (3,)
        and rgb.dtype == np.uint8
        and depth.shape == valid.shape == shape
        and depth.dtype == np.dtype("<f4")
        and valid.dtype == np.uint8
        and np.array_equal(depth > 0, valid.astype(bool)),
        "native plane shape, type or validity differs",
    )
    return rgb, depth, valid


def summarize(rows, geom, camera, source, old):
    bare, pin = [next(row for row in rows if row["model"] == key) for key in ("bare", "pin")]
    scale, step = bare["scale"], bare["step"]
    width, height = (d * scale for d in PLAN["original_dimensions"])
    require(
        pin["step"] == step
        and pin["scale"] == scale
        and all(
            bare[key] == pin[key]
            for key in (
                "original_frame_id",
                "original_checksum_sha256",
                "state_sha256",
                "source_time_s",
                "width",
                "height",
                "calibration_version",
                "intrinsics",
                "camera_to_world",
                "renderer",
                "msaa",
                "seed",
                "noise_std_m",
            )
        )
        and (bare["width"], bare["height"]) == (width, height)
        and bare["source_time_s"] == source["time_s"]
        and bare["original_frame_id"] == source["original_frame_id"] == geom["original_frame_id"]
        and bare["original_checksum_sha256"]
        == source["original_checksum_sha256"]
        == geom["original_checksum_sha256"]
        and bare["camera_to_world"] == camera["camera_to_world"]
        and bare["seed"] == PLAN["noise_seed_offset"] + step
        and bare["noise_std_m"] == PLAN["noise_std_m"]
        and bare["renderer"] == old["gpu"]
        and bare["msaa"] == 4
        and np.allclose(
            bare["intrinsics"],
            [
                camera["intrinsics"][0] * scale,
                camera["intrinsics"][1] * scale,
                (width - 1) / 2,
                (height - 1) / 2,
            ],
            atol=1e-12,
            rtol=0,
        ),
        "pose, optics, timing or noise differs across models",
    )
    rgb0, z0, valid0 = arrays(bare)
    rgb1, z1, valid1 = arrays(pin)
    require(np.array_equal(valid0, valid1), "different mask changes the zipped RNG stream")
    delta = z0 - z1
    rgb_changed = int(np.count_nonzero(np.any(rgb0 != rgb1, axis=2)))
    location = {
        (s["pixel_uv"][0], s["pixel_uv"][1]): s for s in geom["rays"] if s["scale"] == scale
    }
    near, far = geom["clip_near_far_m"]
    require(
        all(
            near < h["axial_m"] < far
            for row in location.values()
            for h in row["first"].values()
            if h["axial_m"] is not None
        ),
        "a geometric first surface is outside the camera clip range",
    )
    difference = []
    for v, u in np.argwhere(delta != 0):
        row = location[(int(u), int(v))]
        stop_ticks = row["intersecting_stop_ticks"]
        difference.append(
            {
                "native_pixel_uv": [int(u), int(v)],
                "original_cell_uv": [int(u) // scale, int(v) // scale],
                "original_coordinate_uv": row["original_coordinate_uv"],
                "bare_axis_depth_m": float(z0[v, u]),
                "pin_axis_depth_m": float(z1[v, u]),
                "bare_minus_pin_m": float(delta[v, u]),
                "center_ray": row["classification"],
                "earliest_future_collision_intersection_tick": min(stop_ticks, default=None),
                "future_collision_intersection_count": len(stop_ticks),
            }
        )
    peak = float(abs(delta).max())
    if scale == 1:
        match = source["old_match"]
        require(
            len(difference) == match["different_depth_pixels"]
            and abs(peak - match["peak_depth_delta_m"]) < 1e-6,
            "frozen standard-layout control did not reproduce",
        )
    ray_counts = Counter(
        r["classification"] for r in location.values() if r["classification"] != "outside_pin"
    )
    count = sum(s["bare_minus_pin_m"] > PLAN["diagnostic_threshold_m"] for s in difference)
    meeting_first = sum(
        176 in s["intersecting_stop_ticks"] and s["classification"] == "visible"
        for s in location.values()
    )
    return {
        "step": step,
        "scale": scale,
        "width": width,
        "height": height,
        "depth_changed": len(difference),
        "rgb_changed": rgb_changed,
        "peak_absolute_depth_change_m": peak,
        "positive_deltas_over_8_mm": count,
        "ray_counts_through_pin": dict(ray_counts),
        "visible_rays_intersecting_first_collision_state": meeting_first,
        "changed_depth_witnesses": difference,
        "static_camera_call_wall_ms": [row["capture_ns"] / 1e6 for row in (bare, pin)],
        "historical_rgb_changed_at_original_resolution": (
            source["old_match"]["different_rgb_pixels"] if scale == 1 else None
        ),
    }


def cold_read(out):
    camera, sources, old = original_inputs()
    rays_path = OUT / "rays.json"
    cpu = read(rays_path)
    reader = RAW / "seal.json"
    sealed = read(reader)["members"]
    require(
        set(sealed) | {"seal.json"} == {p.name for p in RAW.iterdir() if p.is_file()}
        and all(sha(RAW / path) == expected for path, expected in sealed.items()),
        "native evidence seal differs",
    )
    registration = read(RAW / "registration.json")
    index = read(RAW / "index.json")
    require(
        registration["driver_sha256"] == sha(HERE / "capture.py")
        and registration["plan_sha256"] == sha(PLAN_PATH) == cpu["source_plan_sha256"]
        and registration["cpu_sha256"] == sha(rays_path)
        and registration["original_optics"] == camera
        and registration["width_height_scales"] == PLAN["grids"]
        and index["new_physics_steps"] == cpu["physics_steps"] == 0,
        "unbound capture index, geometry or registration",
    )
    frames = index["frames"]
    registered = [
        (step, scale, mode)
        for scale in PLAN["grids"]
        for step in PLAN["steps"].values()
        for mode in ("bare", "pin")
    ]
    require(
        [(r["step"], r["scale"], r["model"]) for r in frames] == registered
        and len(set(r["frame_id"] for r in frames)) == len(frames) == PLAN["gpu_capture_limit"],
        "wrong number or order of native captures",
    )
    result = []
    for step, source in sources.items():
        for scale in PLAN["grids"]:
            pair = [r for r in frames if (r["step"], r["scale"]) == (step, scale)]
            result.append(summarize(pair, cpu["steps"][str(step)], camera, source, old))
    stop = cpu["steps"][str(PLAN["steps"]["refusal"])]
    collision = {
        "sample_count": len(stop["collision_states"]),
        "first_tick": min(stop["collision_states"]),
        "projection_uv_and_axial_bounds": stop["collision_uv_and_depth_bounds"],
    }
    write(
        out,
        {
            "schema": "g1.development.same-view-needle-sampling.result.v1",
            "baseline": PLAN["baseline"],
            "cpu_sha256": sha(rays_path),
            "capture_seal_sha256": sha(reader),
            "plan_sha256": sha(PLAN_PATH),
            "rows": result,
            "observed_brake_overlap": collision,
            "native_capture_count": len(frames),
            "native_physics_steps": 0,
            "new_control_commands": 0,
            **{
                key: PLAN[key]
                for key in (
                    "formal",
                    "whole_system",
                    "independent_formal_scoring",
                    "hardware",
                    "remote",
                )
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    cold_read(args.output)
