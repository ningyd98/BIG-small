"""Independently score the sealed restricted-grid outputs and frozen sensitivity cases."""

import sys
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.perception_io import read, sha, write
from seeded_grid import HERE, OUT, PLAN, PLAN_PATH, ROOT, dependencies, require

PRIMARY = OUT / "prediction.json"


def before_readback():
    for relative, expected in PLAN["sha256"].items():
        item = (ROOT / relative).resolve()
        require(item.is_relative_to(ROOT) and sha(item) == expected, f"source changed {relative}")
    require(
        PRIMARY.read_bytes() == (OUT / "prediction.cold.json").read_bytes(),
        "cold predictions differ",
    )
    p = read(PRIMARY)
    require(
        p["plan_sha256"] == sha(PLAN_PATH)
        and p["handedness_plan_sha256"] == sha(HERE / "plan-handedness.json")
        and p["source_sha256"] == sha(HERE / "seeded_grid.py")
        and p["scope"] == PLAN["scope"]
        and p["refused_file_accesses"] == 3
        and p["unique_original_seeds"] == 11
        and len(p["dense"]) == 12
        and all(p["sampling_controls"].values()),
        "blind predictions or controls do not close",
    )
    for folder in (ROOT / PLAN["dense"] / "native", ROOT / PLAN["old_needle"]):
        entries = read(folder / "seal.json")["members"]
        require(
            {p.name for p in folder.iterdir() if p.is_file()} == set(entries) | {"seal.json"},
            "sealed native inventory changed",
        )
        require(
            all(sha(folder / name) == fingerprint for name, fingerprint in entries.items()),
            "sealed native data changed",
        )
    return p


def original_clear_regression(prior, old, old_stage, states, job_lookup, crossbar):
    stored = [r for r in old["rows"] if (r["archive"], r["step"]) == ("original", 1728)]
    require(len(stored) == 1, "qualified old CLEAR control missing")
    (measurement,) = [r for r in states.values() if (r["archive"], r["step"]) == ("original", 1728)]
    (original,) = [r for r in old_stage["dense"] if r["key"] == measurement["key"]]
    binding = job_lookup[measurement["key"]]
    require(
        original["original_frame_id"] == measurement["frame_id"] == binding["frame_id"]
        and original["original_checksum_sha256"]
        == measurement["checksum_sha256"]
        == binding["checksum_sha256"],
        "historical qualified CLEAR control detached",
    )
    metrics = prior.pose_metrics(
        original["pose"],
        np.asarray(measurement["world_object_center_m"]),
        np.asarray(measurement["world_object_rotation"]),
        crossbar,
    )
    require(metrics == stored[0]["candidate_metrics"], "prior 06/1728 physical regression differs")
    return {
        "center_error_m": metrics["center_error_m"],
        "full_geometry_at_zero_scale": stored[0]["geometry_sensitivity"]["snapshots"][0][
            "proved_first_faces"
        ],
        "hypothetical_full_set_scale_bracket": stored[0]["geometry_sensitivity"][
            "geometry_and_depth_scale_bracket"
        ],
    }


def needle_score(prior, geom, model, camera, source, forecasts):
    root = ROOT / PLAN["old_needle"]
    traces = {}
    for step in (120, 2112):
        pair = []
        for name in ("bare", "pin"):
            with np.load(root / f"step-{step}-4x-{name}.npz", allow_pickle=False) as data:
                pair.append(data["depth_m"])
        coords = np.argwhere(pair[0] - pair[1] > 0.008)
        require(len(coords) == 4, "real needle/positive native control changed")
        traces[step] = {"strong_pixels_uv": coords[:, ::-1].tolist()}
        if step == 2112:
            forecast = forecasts["pin"]
            traces[step]["new_marker_pose_available"] = forecast["reason"] is None
            if forecast["reason"] is None:
                state, pose = geom.camera_state(model, prior.supported_pose(source, forecast))
                scene = geom.SurfaceBounds(model, state, pose)
                eye, direction = geom.ray_directions(camera)
                result = []
                for v, u in coords:
                    nominal = scene.first_face(eye, direction(int(u), int(v)), factor=0.0)
                    measured = float(pair[1][v, u])
                    depth = nominal.get("nominal_m")
                    result.append(
                        {
                            "uv": [int(u), int(v)],
                            "nominal_geom": nominal.get("nominal_geom"),
                            "pin_axial_m": measured,
                            "nominal_axial_m": depth,
                            "measured_minus_nominal_m": None if depth is None else measured - depth,
                            "still_outside_nominal_4mm": depth is None
                            or abs(measured - depth) >= 0.004,
                        }
                    )
                traces[step]["point_estimate_residuals"] = result
                traces[step]["strong_returns_outside_nominal_4mm"] = sum(
                    p["still_outside_nominal_4mm"] for p in result
                )
    aligned = all(x["reason"] is None for x in forecasts.values())
    if aligned:
        keys = ("center_world_m", "rotation_object_to_world", "anchor_world_m", "method", "ids")
        aligned = all(forecasts["bare"]["pose"][k] == forecasts["pin"]["pose"][k] for k in keys)
    return {"historical_physical_pairs": traces, "pose_identical_between_t02_images": aligned}


def run():
    p = before_readback()
    initial, _ = dependencies()
    sys.path.insert(0, str(ROOT / PLAN["prior_round"]))
    import score as prior

    camera, subjects = initial.snapshot_sources()
    physical = {r["key"]: r for r in read(initial.DENSE / "capture-input.json")["jobs"]}
    jobs = {r["key"]: r for r in read(initial.OPTICAL)["jobs"]}
    nominal = {r["dense_frame_id"]: r for r in p["dense"]}
    shadows = {r["key"]: r for r in read(ROOT / prior.PLAN["first_geometry"])["rows"]}
    truth_t02 = read(ROOT / PLAN["original_t02_label"])["samples"][2112]
    crossbar = prior.dimensions("g1_dual_id8_crossbar")
    squares = prior.load_bounds()
    old_report = ROOT / PLAN["prior_output"]
    regression = original_clear_regression(
        prior,
        read(old_report / "physical-readback.json"),
        read(old_report / "prediction.json"),
        physical,
        jobs,
        crossbar,
    )
    targets = {
        (t["archive"], step): t["representative"]
        for t in prior.PLAN["targets"]
        for step in (t["clear"], t["stop"])
    }

    rows = []
    needle = {}
    with patch.multiple(
        mujoco,
        mj_step=prior.fail_if_step,
        mj_step1=prior.fail_if_step,
        mj_step2=prior.fail_if_step,
        Renderer=prior.fail_if_step,
        mjr_render=prior.fail_if_step,
    ):
        model = mujoco.MjModel.from_xml_path(str(initial.ASSET))
        for job, meta, path, frame_id in subjects:
            forecast = nominal[frame_id]
            key = job["key"]
            require(
                forecast["key"] == key
                and forecast["original_frame_id"] == job["frame_id"]
                and forecast["original_checksum_sha256"] == job["checksum_sha256"]
                and forecast["dense_raw_sha256"] == sha(path) == meta["file_sha256"],
                "blind marker estimate detached from its sensor packet",
            )
            if key in physical:
                data = physical[key]
                c = np.asarray(data["world_object_center_m"])
                r = np.asarray(data["world_object_rotation"])
                require(
                    data["frame_id"] == job["frame_id"]
                    and data["time_s"] == job["time_s"]
                    and data["checksum_sha256"] == job["checksum_sha256"],
                    "physical label does not bind to prior shutter",
                )
                identity = {k: data[k] for k in ("archive", "step", "slot", "original_status")}
            else:
                needle[meta["model"]] = forecast
                needle_job = job
                require(
                    job["time_s"] == truth_t02["sim_time_s"], "needle and physical clocks differ"
                )
                c = np.asarray(truth_t02["object_geom_position_m"])
                r = np.asarray(truth_t02["object_geom_rotation_row_major"]).reshape(3, 3)
                identity = {"archive": "t02", "step": 2112, "fixture": meta["model"]}

            result = identity | {
                "forecast_reason": forecast["reason"],
                "rejected_footprint": forecast.get("rejected_footprint"),
                "prior_metrics": prior.pose_metrics(job["optical"], c, r, crossbar),
                "candidate_metrics": None,
                "ray_sensitivity": None,
            }
            if forecast["reason"] is None:
                require(
                    forecast["detected"] == [8]
                    and forecast["word_does_not_determine_handedness"]
                    and all(x["excluded_pixel_overlap"] == 0 for x in forecast["samples"]),
                    "candidate lost the conditional witness",
                )
                result["candidate_metrics"] = prior.pose_metrics(forecast["pose"], c, r, crossbar)
                result["selected_marker_depth_points"] = forecast["retained_depth_count"]
                result["physical_source_color_taps"] = forecast["sampler"]["unique_source_pixels"]
                result["heldout_grid_rms_px"] = forecast["grid_support"]["heldout_rms_px"]
                target = (identity["archive"], identity["step"])
                if target in targets:
                    with np.load(path, allow_pickle=False) as data:
                        dense_depth = data["depth_m"]
                    result["ray_sensitivity"] = prior.margin_results(
                        squares,
                        model,
                        camera,
                        job,
                        forecast,
                        shadows[key],
                        dense_depth,
                        targets[target],
                    )
            rows.append(result)
        require(set(needle) == {"bare", "pin"}, "old pin contrast missing")
        needle_result = needle_score(prior, squares, model, camera, needle_job, needle)
    ordinary = [r for r in rows if r["archive"] != "t02"]
    stops = [r for r in ordinary if r["original_status"] == "BLOCKED"]
    require(len(stops) == 5 and len(ordinary) == 10, "ordinary archived denominator changed")
    write(
        OUT / "readback.json",
        {
            "schema": "g1.development.local-grid-id8-result.v1",
            "rows": rows,
            "prediction_sha256": sha(PRIMARY),
            "shared_old_clear_regression": regression,
            "measurable_dense_frames": sum(r["candidate_metrics"] is not None for r in rows),
            "measurable_stop_frames": sum(r["candidate_metrics"] is not None for r in stops),
            "physical_needle_control": needle_result,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    run()
