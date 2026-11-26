"""Cold-check the two fixed physical edge segments without opening ungated images."""

import argparse

import mujoco
from crossbar import (
    HERE,
    OUT,
    PLAN,
    PLAN_FILE,
    checked_inputs,
    geometry_schedule,
    library,
    require,
    supported,
    write_new,
)
from scripts.graduation.perception_io import ROOT, read, sha


def summarize_sections(row):
    return {
        group: {
            "columns": len(segment["legal"]),
            "span_mm": segment["legal_span_mm"],
        }
        for group, segment in row.items()
    }


def readback(digest):
    file = OUT / "prediction.json"
    require(sha(file) == sha(OUT / "prediction.cold.json") == digest, "cold predictions differ")
    p = read(file)
    require(
        p["plan_sha256"] == sha(PLAN_FILE)
        and p["script_sha256"] == sha(HERE / "crossbar.py")
        and all(p["controls"].values()),
        "adjusted plan, script, or control",
    )
    checked_inputs()
    for rel, h in PLAN["external_readback_sources"].items():
        require(sha(ROOT / rel) == h, f"detached old score {rel}")
    prior_file = next(
        key for key in PLAN["external_readback_sources"] if key.endswith(".public.json")
    )
    original = read(ROOT / prior_file)
    old_scores = {(r["archive"], r["step"]): r for r in original["rows"] if r["archive"] != "t02"}
    expected = {
        "c15c7e9cd2ccaf30": ("original", 1728),
        "cb65235cb49fb670": ("original", 1736),
        "758cb679d689585c": ("slower", 1824),
        "ab449c835779e86a": ("slower", 1832),
    }
    original_reader, geometry = library("source_reader"), library("prior_bounds")
    _, source = original_reader.snapshot_sources()
    by_frame = {
        frame: (job, meta) for job, meta, _, frame in source if job["key"] in PLAN["use_keys"]
    }
    seeds = {r["dense_frame_id"]: r for r in read(ROOT / PLAN["local_seed"])["dense"]}
    model = mujoco.MjModel.from_xml_path(str(ROOT / PLAN["asset"]))
    rows, needle = [], {}
    for row in p["rows"]:
        frame = row["dense_frame_id"]
        job, meta = by_frame[frame]
        require(
            row["source_shutter_checksum"] == job["checksum_sha256"]
            and row["dense_raw_sha256"] == meta["file_sha256"],
            "detached frame in prediction",
        )
        data, pose = geometry.camera_state(model, job)
        geometry_result, _, _, _ = geometry_schedule(
            job, meta, seeds[frame], geometry.SurfaceBounds(model, data, pose)
        )
        require(geometry_result == row["scheduled_segments"], "geometry schedule differs")
        can_read = all(supported(geometry_result[name], name) for name in ("fit", "validation"))
        require(can_read == row["planned_raw_reads"], "frame access exceeds geometry")
        require(row["pose"] is None, "unexpected pose requires independent target scoring")
        entry = {
            "key": row["key"],
            "frame_id": frame,
            "opened_rgbd": row["planned_raw_reads"],
            "reason": row["reason"],
            "geometric_support": summarize_sections(geometry_result),
            "new_pose_and_ray_score": None,
        }
        if row["key"] in expected:
            family, tick = expected[row["key"]]
            require(not can_read, "four endpoint frames exceed the no-pixel validation scope")
            old = old_scores[(family, tick)]
            field = "id8_crossbar_worst_lateral_face_error_m"
            entry.update(
                {
                    "archive": family,
                    "step": tick,
                    "previous_errors_mm": {
                        key: (old[key][field] * 1000 if old[key] is not None else None)
                        for key in (
                            "original_320_metrics",
                            "dense_single_id8_metrics",
                            "new_metrics",
                        )
                    },
                }
            )
        else:
            require(can_read and row["model"] in {"bare", "pin"}, "needle control lost")
            needle[row["model"]] = [row["measured_fit"], row["measured_validation"]]
            entry.update(
                {
                    "archive": "old_t02",
                    "step": 2112,
                    "model": row["model"],
                    "measured_support": summarize_sections(
                        {"fit": row["measured_fit"], "validation": row["measured_validation"]}
                    ),
                }
            )
        rows.append(entry)
    require(
        len(rows) == 6 and set(needle) == {"bare", "pin"} and needle["bare"] == needle["pin"],
        "registered needle measurements or denominator differ",
    )
    old_witness = read(
        ROOT / "experiments/results/g1-lift-pixel-stop-envelope-20261126/needle-witness.json"
    )
    require(
        old_witness["native_optical_alias"]["bare_and_pin_RGB_depth_mask_identical"]
        and old_witness["old_no_pin_stop_with_pin_geometry"]["first_intersection_stop_step"] == 176,
        "old needle proof changed",
    )
    return {
        "forecast_sha256": digest,
        "rows": rows,
        "positive_candidate": False,
        "old_control": {
            "identical_blind_pin_and_bare_observations": True,
            "inherited_strong_unregistered_near_returns": 4,
            "old_geometric_first_overlap_step": 176,
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prediction-sha", required=True)
    write_new("readback.json", readback(p.parse_args().prediction_sha))


if __name__ == "__main__":
    main()
