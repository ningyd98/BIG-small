"""Compare the frozen opposite-carrier estimates with independent archived physical labels."""

import sys
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha, write

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["out"]
DENSE = ROOT / PLAN["dense"]
INITIAL = ROOT / PLAN["local_out"] / "prediction.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sealed_predictions():
    for name, fingerprint in PLAN["sha256"].items():
        source = (ROOT / name).resolve()
        require(source.is_relative_to(ROOT) and sha(source) == fingerprint, f"input drift: {name}")
    primary = OUT / "prediction.json"
    cold = OUT / "prediction.cold.json"
    require(primary.read_bytes() == cold.read_bytes(), "cold blind predictions differ")
    reg = read(primary)
    require(
        reg["source_sha256"] == sha(HERE / "predict.py")
        and reg["plan_sha256"] == sha(PLAN_PATH)
        and reg["initial_prediction_sha256"] == sha(INITIAL)
        and reg["scope"] == PLAN["scope"]
        and all(reg["controls"].values())
        and reg["denied_label_accesses"] == 2,
        "forecast's source, controls or blindness differs",
    )
    for root in (DENSE / "native", ROOT / PLAN["needle"]):
        expected = read(root / "seal.json")["members"]
        require(
            {p.name for p in root.iterdir() if p.is_file()} == set(expected) | {"seal.json"},
            "wrong dense archive inventory",
        )
        require(
            all(sha(root / name) == digest for name, digest in expected.items()),
            "tampered native evidence",
        )
    return reg


def side_short(rows):
    return [
        {
            key: r[key]
            for key in (
                "side",
                "reason",
                "searched_columns",
                "columns_span_subgrid",
                "ink_supported_columns",
            )
            if key in r
        }
        | {"masked_columns": len(r.get("masked_columns", []))}
        for r in rows
    ]


def verdict(candidate, baseline, prior_geometry, new_geometry):
    if candidate is None or baseline is None or prior_geometry is None or new_geometry is None:
        return {
            "comparable": False,
            "improved_lateral_error": False,
            "point_geometry_kept": False,
            "hypothetical_scale_not_lower": False,
            "hypothetical_scale_higher": False,
        }
    old = prior_geometry["geometry_and_depth_scale_bracket"]
    new = new_geometry["geometry_and_depth_scale_bracket"]
    return {
        "comparable": True,
        "improved_lateral_error": candidate["id8_crossbar_worst_lateral_face_error_m"]
        < baseline["id8_crossbar_worst_lateral_face_error_m"],
        "point_geometry_kept": new_geometry["snapshots"][0]["proved_and_depth_compatible"] == 36,
        "hypothetical_scale_not_lower": (
            old is not None and new is not None and new["feasible_lower"] >= old["feasible_lower"]
        ),
        "hypothetical_scale_higher": (
            old is not None and new is not None and new["feasible_lower"] > old["feasible_lower"]
        ),
    }


def run():
    result = sealed_predictions()
    sys.path.insert(0, str(ROOT / PLAN["local_round"]))
    import evaluate as local

    initial, _ = local.dependencies()
    import score as earlier

    camera, entries = initial.snapshot_sources()
    pin = read(INITIAL)
    baseline = {p["dense_frame_id"]: p for p in pin["dense"]}
    predictions = {r["dense_frame_id"]: r for r in result["predictions"]}
    require(
        set(predictions) == set(baseline) and len(predictions) == 12, "forecast denominator changed"
    )
    archived = read(ROOT / PLAN["local_out"] / "readback.json")
    historical = {(r["archive"], r["step"], r.get("fixture")): r for r in archived["rows"]}
    labels = {r["key"]: r for r in read(DENSE / "capture-input.json")["jobs"]}
    original = read(ROOT / local.PLAN["original_t02_label"])["samples"][2112]
    geometry = {r["key"]: r for r in read(ROOT / earlier.PLAN["first_geometry"])["rows"]}
    shape = earlier.dimensions("g1_dual_id8_crossbar")
    bounds = earlier.load_bounds()
    target = {
        (t["archive"], step): t["representative"]
        for t in earlier.PLAN["targets"]
        for step in (t["clear"], t["stop"])
    }
    rows = []
    candidate_needle = {}
    with patch.multiple(
        mujoco,
        mj_step=earlier.fail_if_step,
        mj_step1=earlier.fail_if_step,
        mj_step2=earlier.fail_if_step,
        Renderer=earlier.fail_if_step,
        mjr_render=earlier.fail_if_step,
    ):
        model = mujoco.MjModel.from_xml_path(str(initial.ASSET))
        for job, meta, path, frame in entries:
            ref, new = baseline[frame], predictions[frame]
            key = job["key"]
            require(
                key == ref["key"] == new["key"]
                and job["checksum_sha256"]
                == ref["original_checksum_sha256"]
                == new["source_shutter_checksum"]
                and sha(path) == ref["dense_raw_sha256"] == new["dense_raw_sha256"],
                "optical estimates detached from the fixed capture",
            )
            if key in labels:
                truth = labels[key]
                require(
                    truth["checksum_sha256"] == job["checksum_sha256"]
                    and truth["frame_id"] == job["frame_id"]
                    and truth["time_s"] == job["time_s"],
                    "ordinary physical label pose clock changed",
                )
                center = np.asarray(truth["world_object_center_m"])
                rotation = np.asarray(truth["world_object_rotation"])
                ids = {k: truth[k] for k in ("archive", "step", "original_status")}
            else:
                needle_job = job
                candidate_needle[meta["model"]] = new
                require(
                    job["time_s"] == original["sim_time_s"], "old needle physical clock changed"
                )
                center = np.asarray(original["object_geom_position_m"])
                rotation = np.asarray(original["object_geom_rotation_row_major"]).reshape(3, 3)
                ids = {"archive": "t02", "step": 2112, "fixture": meta["model"]}
            old = historical[(ids["archive"], ids["step"], ids.get("fixture"))]
            ref_score = earlier.pose_metrics(ref["pose"], center, rotation, shape)
            require(
                ref_score == old["candidate_metrics"],
                "single-ID8 baseline like-for-like score drifted",
            )
            new_score, sensitivity = None, None
            if new["reason"] is None:
                new_score = earlier.pose_metrics(new["pose"], center, rotation, shape)
                selector = (ids["archive"], ids["step"])
                if selector in target:
                    with np.load(path, allow_pickle=False) as packed:
                        depth = packed["depth_m"]
                    sensitivity = earlier.margin_results(
                        bounds,
                        model,
                        camera,
                        job,
                        new,
                        geometry[key],
                        depth,
                        target[selector],
                    )
            rows.append(
                ids
                | {
                    "reason": new["reason"],
                    "original_320_metrics": old["prior_metrics"],
                    "dense_single_id8_metrics": ref_score,
                    "new_metrics": new_score,
                    "side_diagnostics": side_short(new["side_results"]),
                    "dense_single_id8_sensitivity": old["ray_sensitivity"],
                    "candidate_sensitivity": sensitivity,
                    "goal_conditions": verdict(
                        new_score, ref_score, old["ray_sensitivity"], sensitivity
                    ),
                }
            )
        require(set(candidate_needle) == {"bare", "pin"}, "old pin comparison is incomplete")
        needle = local.needle_score(earlier, bounds, model, camera, needle_job, candidate_needle)
    target_stop = [
        r for r in rows if (r["archive"], r["step"]) in {("original", 1736), ("slower", 1832)}
    ]
    require(len(target_stop) == 2 and len(rows) == 12, "crossbar case denominator differs")
    conditions = [row["goal_conditions"] for row in target_stop]
    progress = (
        all(
            c["comparable"]
            and c["improved_lateral_error"]
            and c["point_geometry_kept"]
            and c["hypothetical_scale_not_lower"]
            for c in conditions
        )
        and any(c["hypothetical_scale_higher"] for c in conditions)
        and needle["pose_identical_between_t02_images"]
        and needle["historical_physical_pairs"][2112].get("strong_returns_outside_nominal_4mm") == 4
    )
    write(
        OUT / "readback.json",
        {
            "schema": "g1.development.dense-opposite-surface-result.v1",
            "forecast_sha256": sha(OUT / "prediction.json"),
            "plan_sha256": sha(PLAN_PATH),
            "scope": PLAN["scope"],
            "physical_needle_control": needle,
            "rows": rows,
            "cleared_next_stand_alone_calibration_precondition": progress,
        },
    )


if __name__ == "__main__":
    run()
