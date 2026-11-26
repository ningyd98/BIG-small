"""Cold-check candidate poses against withheld rays, physical labels, and the old pin."""

import argparse
import sys
from contextlib import contextmanager
from unittest.mock import patch

import mujoco
import numpy as np
from fit_depth import (
    HERE,
    OUT,
    PLAN,
    PLAN_PATH,
    candidate_pose,
    check,
    require,
    save,
    split_module,
)
from scripts.graduation.perception_io import ROOT, read, sha


def one(iterator):
    (result,) = list(iterator)
    return result


def old_file(suffix):
    return ROOT / one(p for p in PLAN["isolated_sources"] if p.endswith(suffix))


@contextmanager
def geometry_only():
    def prohibited(*_args, **_kwargs):
        raise RuntimeError("offline depth readback may not render or integrate")

    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        yield


def sampling_outer_rays(
    base, bounds, earlier, model, camera, job, state, family_pose, seed, geometry, transform
):
    fit = family_pose["fit"]
    _, coarse_r, coarse_c = transform
    geom = model.geom(base.CROSSBAR)
    eye, ray = bounds.ray_directions(camera)
    active = []
    all_hits = []
    for params, admissible in zip(
        fit["slope_intercept_polygon"],
        fit["candidate_vertices_within_original_pose_bound"],
        strict=True,
    ):
        new_pose = candidate_pose(params, seed["pose"], coarse_r, coarse_c, geom)
        synthetic = family_pose | {"pose": new_pose}
        data, pose = bounds.camera_state(model, earlier.supported_pose(job, synthetic))
        scene = bounds.SurfaceBounds(model, data, pose)
        hit = []
        for x, y in geometry:
            result = scene.first_face(eye, ray(x, y), 0)
            hit.append(result.get("nominal_geom"))
        if admissible:
            active.append(hit)
        all_hits.append(hit)
    ids = {
        "sampled_vertices": len(all_hits),
        "sampled_vertices_that_satisfy_original_bounds": len(active),
        "outer_vertices_with_distinct_geom_count": sum(
            len(set(x)) > 1 for x in zip(*all_hits, strict=True)
        ),
        "admissible_vertices_with_distinct_geom_count": sum(
            len(set(x)) > 1 for x in zip(*active, strict=True)
        ),
        "captured_state_time_s": state["time_s"],
    }
    return ids


def equivalent_needle(forecasts):
    keys = ("center_world_m", "rotation_object_to_world", "anchor_world_m", "method", "ids")
    bare, pin = forecasts["bare"]["fit"], forecasts["pin"]["fit"]
    return all(bare["pose"][k] == pin["pose"][k] for k in keys) and (
        bare["slope_intercept_polygon"] == pin["slope_intercept_polygon"]
        and bare["depth_support"] == pin["depth_support"]
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prediction-sha", required=True)
    digest = p.parse_args().prediction_sha
    prediction = OUT / "prediction.json"
    require(
        sha(prediction) == sha(OUT / "prediction.cold.json") == digest, "cold predictions differ"
    )
    result = read(prediction)
    f = OUT / "fit.json"
    require(
        sha(f) == sha(OUT / "fit.cold.json") == result["fit_before_validation_sha256"],
        "fit was not independently sealed before validation",
    )
    require(
        result["script_sha256"] == sha(HERE / "fit_depth.py")
        and result["plan_sha256"] == sha(PLAN_PATH)
        and all(result["controls"].values()),
        "cold output provenance drifted",
    )
    check(PLAN["isolated_sources"])
    old = split_module()
    base, bounds, camera, enrolled, seed = old.registered()
    marker = old_file("/score.py")
    sys.path.insert(0, str(marker.parent))
    import score as earlier

    prior = read(old_file("/opposite-carrier.public.json"))
    physical = {row["key"]: row for row in read(old_file("/capture-input.json"))["jobs"]}
    all_rays = {row["key"]: row for row in read(old_file("/geometry.json"))["rows"]}
    geom = earlier.dimensions("g1_dual_id8_crossbar")
    model = mujoco.MjModel.from_xml_path(str(ROOT / base.PLAN["asset"]))
    scores, needle = [], {}
    known_inputs = {x[3]: x for x in enrolled}
    with geometry_only():
        for row in result["rows"]:
            if row["fit"] is None:
                require(row["family"] == "original06", "unexpected geometry exclusion")
                scores.append(
                    {"family": row["family"], "key": row["key"], "outcome": "unopened_by_geometry"}
                )
                continue
            point = row["fit"]["pose"]
            require(
                point is not None,
                "record first-stage point rejection independently before evaluation",
            )
            job, meta, raw, ident = info = known_inputs[row["dense_frame_id"]]
            require(
                sha(raw) == meta["file_sha256"] == row["dense_raw_sha256"]
                and job["checksum_sha256"] == row["source_shutter_sha256"],
                "warded candidate and scoring input differ",
            )
            if row["family"] == "old_t02":
                needle[row["fixture"]] = row
                continue
            label = physical[row["key"]]
            require(
                label["frame_id"] == job["frame_id"]
                and label["checksum_sha256"] == job["checksum_sha256"]
                and label["time_s"] == job["time_s"],
                "physical label and exposure differ",
            )
            previous = one(
                r for r in prior["rows"] if r["archive"] == "slower" and r["step"] == label["step"]
            )
            recorded = all_rays[row["key"]]
            require(recorded["source_frame_id"] == job["frame_id"], "withheld rays are shifted")
            pred = row | {"pose": point}
            physical_score = earlier.pose_metrics(
                point,
                np.asarray(label["world_object_center_m"]),
                np.asarray(label["world_object_rotation"]),
                geom,
            )
            with np.load(raw, allow_pickle=False) as source:
                depth = source["depth_m"]
            sensitivity = earlier.margin_results(
                bounds,
                model,
                camera,
                job,
                pred,
                recorded,
                depth,
                [749, 473],
            )
            coords = [v["uv"] for v in recorded["rays"]]
            _, transform = old.stations(base, bounds, model, info, seed[ident])
            coverage = sampling_outer_rays(
                base,
                bounds,
                earlier,
                model,
                camera,
                job,
                label,
                row,
                seed[ident],
                coords,
                transform,
            )
            scores.append(
                {
                    "family": row["family"],
                    "step": label["step"],
                    "physical_comparison": physical_score,
                    "validation_qualified": row["validation"]["qualified"],
                    "baseline": {
                        k: previous[k]
                        for k in ("original_320_metrics", "dense_single_id8_metrics", "new_metrics")
                    },
                    "sensitivity": sensitivity,
                    "polygon_extrapolation": coverage,
                }
            )
        require(
            set(needle) == {"bare", "pin"} and equivalent_needle(needle), "pin changes candidate"
        )
        pin = needle["pin"]
        job, _, raw, _ = known_inputs[pin["dense_frame_id"]]
        bare = needle["bare"]
        _, _, original_raw, _ = known_inputs[bare["dense_frame_id"]]
        with (
            np.load(raw, allow_pickle=False) as found,
            np.load(original_raw, allow_pickle=False) as baseline,
        ):
            pin_depth, bare_depth = found["depth_m"], baseline["depth_m"]
        controls = np.argwhere(bare_depth - pin_depth > 0.008)
        require(len(controls) == 4, "old strong needle pixel count changed")
        registration = pin | {"pose": pin["fit"]["pose"]}
        native, pose = bounds.camera_state(model, earlier.supported_pose(job, registration))
        scene = bounds.SurfaceBounds(model, native, pose)
        eye, ray = bounds.ray_directions(camera)
        returns = []
        for yy, xx in controls:
            where = scene.first_face(eye, ray(int(xx), int(yy)), 0)
            nominal = where["nominal_m"]
            residual = float(pin_depth[yy, xx] - nominal)
            require(where["nominal_geom"] == "table" and residual < -0.004, "needle lost rejection")
            returns.append({"uv": [int(xx), int(yy)], "relative_depth_m": residual})
    save(
        "readback.json",
        {
            "prediction_sha256": digest,
            "rows": scores,
            "needle": {"same_admissible_input_output": True, "still_rejected": returns},
            "no_online_qualification": True,
        },
    )


if __name__ == "__main__":
    main()
