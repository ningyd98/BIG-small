"""Compare signed historical and training frames, all detector fields and scoped invariants."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PERFORMANCE = HERE.parent
ROOT = next(
    p for p in PERFORMANCE.parents if (p / "scripts/graduation/g1_visibility_replay.py").is_file()
)
READER = ROOT / "scripts/graduation/g1_visibility_replay.py"
SPEC = importlib.util.spec_from_file_location("frozen_replay_evidence", READER)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)
PLAN = "2022f2ee04f0252957788dfa381d3de530b459d3f795d5f97d11237ed862f471"
BASE = "7288cdc81e830f5282eb7d82d49d46d077e2593d0f96480960385463b850b9e9"
D02 = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/batches/train-current-grid-01"
D02_INDEX = "6beb09ca4f87a2e04760b0bbf79289cde31060f2514e1284e9eb2b82c32c22d3"


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def feature_controls(vision, frame, geometry, make):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    def raw(f, g=geometry):
        return vision.measure_frame(f, g)

    source = raw(frame)
    repeated = raw(frame)
    renamed = make(frame, 951)
    renamed_measurement = raw(renamed)
    camera = make(frame, 952, calibration_version="different-calibration-for-same-RGB")
    measured_camera = raw(camera)
    depth = replay.unpack(frame)[1]
    depth[:] = 0
    blank = make(frame, 953, depth=depth)
    changed = RGBDObservation.model_validate(
        {
            **blank.model_dump(),
            "frame_id": frame.frame_id,
            "observation_id": frame.observation_id,
            "checksum_sha256": "",
        }
    )
    measured_depth = raw(changed)
    # Keep the exact old claimed identity/digest but replace the depth AND its validity mask.
    forged = frame.model_copy(
        update={
            "depth_float32_base64": changed.depth_float32_base64,
            "valid_mask_base64": changed.valid_mask_base64,
        }
    )
    try:
        raw(forged)
    except ValueError as exc:
        forged_error = "RGB-D checksum mismatch" in str(exc)
    else:
        forged_error = False
    restored = raw(frame)
    excluded = {"frame_id", "observation_id", "checksum"}
    geometry_bytes_equal = canonical(
        {k: v for k, v in source.items() if k not in excluded}
    ) == canonical({k: v for k, v in renamed_measurement.items() if k not in excluded})
    return {
        "same_frame_repeated_twice": canonical(source)
        == canonical(repeated)
        == canonical(restored),
        "same_rgb_new_identity_bound": geometry_bytes_equal
        and source["checksum"] != renamed_measurement["checksum"]
        and renamed_measurement["frame_id"] == renamed.frame_id != frame.frame_id,
        "same_rgb_unsupported_calibration_rejected": not measured_camera["usable"]
        and measured_camera["reason"] == "registered_camera_mismatch",
        "same_claimed_identity_changed_depth_recomputed": changed.frame_id == frame.frame_id
        and source["usable"]
        and not measured_depth["usable"]
        and measured_depth["usable_ids"] == []
        and measured_depth["reason"] == "marker_metric_depth_unavailable"
        and measured_depth["checksum"] != source["checksum"],
        "forged_old_checksum_with_new_depth_rejected": forged_error,
        "same_rgb_sha256": hashlib.sha256(
            replay.base64.b64decode(frame.rgb_png_base64)
        ).hexdigest(),
        "original_checksum": frame.checksum_sha256,
        "renamed_checksum": renamed.checksum_sha256,
        "changed_depth_checksum": changed.checksum_sha256,
        "changed_calibration_checksum": camera.checksum_sha256,
    }


def capture(dataset, tree, out):
    """Supplement the unchanged official blind reader with the entire raw observer return."""
    tree, out = tree.resolve(), out.resolve()
    packets, sha = (
        (replay.PACKETS, replay.INDEX_SHA)
        if dataset == "historical"
        else (D02 / "scoring/pixels", D02_INDEX)
    )
    replay.restrict_worker(packets, tree, out)
    sys.path[:0] = [str(tree), str(tree / "src")]
    from scripts.graduation import g1_visibility_vision as vision
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.g1_formal_runtime import bind_scene

    replay.cv2.setNumThreads(1)
    bundles = replay.read(packets / "index.json", sha)
    frames = {}
    for token, b in bundles.items():
        previous = None
        with bind_scene(b["registered_scene"]):
            for i, row in enumerate(b["frames"]):
                replay.require(row["file"] == f"{i:04d}.json", "unexpected packet order")
                f = frame_from_row(packets / token, row, b["episode"], b["scene"], b["geometry"])
                replay.check_acquisition(f, frames, previous)
                frames[f.frame_id] = vision.measure_frame(f, b["geometry"])
                previous = f
    extra = {}
    if dataset == "historical":
        cases, originals, registrations, _ = replay.control_fixtures()
        for name, (_, frame, _) in cases.items():
            geo = registrations[
                "original" if name in {"unaltered-single", "one-print-no-depth"} else "dual"
            ]
            with bind_scene(frame.scene_id):
                extra[name] = vision.measure_frame(frame, geo)
        with bind_scene(originals["dual"].scene_id):
            extra["same-RGB-and-altered-identity-depth-calibration"] = feature_controls(
                vision, originals["dual"], registrations["dual"], replay.intervention
            )
    replay.write(
        out,
        {
            "dataset": dataset,
            "index_sha256": sha,
            "frames": frames,
            "controls": extra,
            "detector_files_sha256": {
                p: replay.sha(tree / p)
                for p in (
                    "scripts/graduation/g1_visibility_grid.py",
                    "scripts/graduation/g1_visibility_vision.py",
                )
            },
        },
    )


def differences(previous, current, path=()):
    """Retain all changed scalar values and types, including signed zero and float formatting."""
    if type(previous) is dict and type(current) is dict:
        for key in sorted(previous.keys() | current.keys()):
            if key not in previous or key not in current:
                yield {
                    "path": [*path, key],
                    "old": previous.get(key),
                    "new": current.get(key),
                    "old_present": key in previous,
                    "new_present": key in current,
                }
            else:
                yield from differences(previous[key], current[key], (*path, key))
    elif type(previous) is list and type(current) is list:
        if len(previous) != len(current):
            yield {"path": list(path), "old": previous, "new": current}
        else:
            for i, (a, b) in enumerate(zip(previous, current, strict=True)):
                yield from differences(a, b, (*path, i))
    elif type(previous) is not type(current) or canonical(previous) != canonical(current):
        yield {"path": list(path), "old": previous, "new": current}


def compare(name, old, fresh, all_differences):
    replay.require(
        old.keys() == fresh.keys(), f"{name}: frame or control identity population changed"
    )
    before, after = hashlib.sha256(), hashlib.sha256()
    counts = {
        "records": len(old),
        "identical_records": 0,
        "differing_record_ids": [],
        "scalar_differences": 0,
    }
    for key in sorted(old):
        a, b = (canonical((key, x[key])) + b"\n" for x in (old, fresh))
        before.update(a)
        after.update(b)
        if a == b:
            counts["identical_records"] += 1
        else:
            diff = list(differences(old[key], fresh[key]))
            replay.require(diff, f"{name}: unaccounted canonical byte difference")
            counts["scalar_differences"] += len(diff)
            counts["differing_record_ids"].append(key)
            all_differences.setdefault(name, {})[key] = diff
    return {
        **counts,
        "old_sorted_canonical_rows_sha256": before.hexdigest(),
        "new_sorted_canonical_rows_sha256": after.hexdigest(),
    }


def compare_all(private, old_tree, candidate_tree):
    plan = replay.read(PERFORMANCE / "plan.json", PLAN)
    inputs = plan["inputs_sha256"]

    def planned(path):
        return replay.read(path, inputs[path.relative_to(ROOT).as_posix()])

    parent = planned(replay.ROUND / "replay-release.public.json")

    def stored(name):
        p = replay.ROUND / name
        return replay.read(p, parent["input_artifacts_sha256"][p.relative_to(ROOT).as_posix()])

    def native(path, digest):
        output = replay.read(path, digest)
        return {r["frame_id"]: r for r in output}

    def detectors(tree):
        return {k: replay.sha(tree / k) for k in parent["detector_files_sha256"]}

    old_detector, new_detector = detectors(old_tree), detectors(candidate_tree)
    replay.require(
        replay.sha(old_tree / "runtime-build.json") == BASE
        and parent["detector_files_sha256"] == old_detector,
        "incorrect frozen baseline",
    )
    new_lock = replay.read(candidate_tree / "runtime-build.json", candidate_tree.parent.name)
    replay.require(
        new_lock["detector_files_sha256"] == new_detector
        and all(replay.sha(ROOT / k) == v for k, v in new_detector.items()),
        "incorrect candidate source",
    )
    seals = {}
    products = {}
    for dataset, directory, index_sha, expected, count in (
        ("historical", "blind", replay.INDEX_SHA, new_detector, 778),
        ("frozen-d02", "frozen-d02", D02_INDEX, old_detector, 75),
        ("candidate-d02", "candidate-d02", D02_INDEX, new_detector, 75),
    ):
        seal, data = replay.sealed_products(private / directory)
        replay.require(
            seal["detector_files_sha256"] == expected
            and seal["frames"] == count
            and seal["index_sha256"] == index_sha,
            "foreign independent blind seal",
        )
        seals[dataset] = {
            "seal": seal,
            "seal_sha256": replay.sha(private / directory / "seal.json"),
        }
        products[dataset] = data["frames"]
    results, diffs, hashes = {}, {}, {}
    results["historical_published_778"] = compare(
        "historical_published_778",
        stored("replay-blind-frames.public.json.gz")["frames"],
        products["historical"],
        diffs,
    )
    results["d02_blind_75"] = compare(
        "d02_blind_75", products["frozen-d02"], products["candidate-d02"], diffs
    )
    controls_report = replay.read(private / "report/replay-controls.public.json")
    controls_old = stored("replay-controls.public.json")
    results["official_controls_20"] = compare(
        "official_controls_20", controls_old["cases"], controls_report["cases"], diffs
    )
    replay.require(
        controls_report["all_control_witnesses"]
        and controls_report["false_positive_controls"] == 0
        and (controls_report["positive_controls"], controls_report["negative_controls"]) == (4, 16)
        and controls_report["stimuli_manifest_sha256"] == controls_old["stimuli_manifest_sha256"],
        "control qualification or physical stimulus changed",
    )
    for dataset, n in (("historical", 778), ("d02", 75)):
        old_path, fresh_path = (
            private / f"raw-{label}-{dataset}.json.gz" for label in ("old", "new")
        )
        old_measure, fresh_measure = (replay.read(p) for p in (old_path, fresh_path))
        hashes[dataset] = dict(
            old_sha256=replay.sha(old_path), candidate_sha256=replay.sha(fresh_path)
        )
        replay.require(
            old_measure["detector_files_sha256"] == old_detector
            and fresh_measure["detector_files_sha256"] == new_detector
            and len(old_measure["frames"]) == len(fresh_measure["frames"]) == n,
            "full current-frame comparison used a different detector or denominator",
        )
        section = f"{dataset}_all_detector_fields"
        results[section] = compare(section, old_measure["frames"], fresh_measure["frames"], diffs)
        if dataset == "historical":
            results["controls_all_detector_fields_plus_identity_collisions"] = compare(
                "controls_all_detector_fields_plus_identity_collisions",
                old_measure["controls"],
                fresh_measure["controls"],
                diffs,
            )
            boundary = fresh_measure["controls"]["same-RGB-and-altered-identity-depth-calibration"]
        else:
            raw_d02 = fresh_measure["frames"]
    # Independently confirm that the rerun represents the actual failed training acquisition.
    inst = D02 / "d02/instance"
    online = planned(inst / "online-vision.json")
    capture_index = planned(inst / "pixel-index.json")
    logged = {k: v["measurement"] for k, v in online["frames"].items()}
    unlogged = [row for row in capture_index["frames"] if row["frame_id"] not in logged]
    replay.require(
        len(logged) == 74
        and [r["label"] for r in unlogged] == ["terminal"]
        and unlogged[0]["frame_id"] == plan["terminal_capture"]["frame_id"],
        "unexpected unobserved online acquisition",
    )
    results["d02_original_online_full_74"] = compare(
        "d02_original_online_full_74", logged, {k: raw_d02[k] for k in logged}, diffs
    )
    old_score = planned(D02 / "score.json")
    first, second = (D02 / "scoring" / d for d in ("blind-one", "blind-two"))
    sig_a, sig_b = (
        replay.read(p / "seal.json", h)
        for p, h in zip((first, second), old_score["blind_seals_sha256"], strict=True)
    )
    replay.require(
        sig_a == sig_b and sig_a["index_sha256"] == D02_INDEX and sig_a["n_frames"] == 75,
        "archived independent native d02 records do not match",
    )
    token = replay.sha(inst / "pixel-index.json")
    native_old = native(first / (token + ".json"), sig_a["packets"][token])
    native_other = native(second / (token + ".json"), sig_b["packets"][token])
    replay.require(native_old == native_other, "archived native d02 rows differ")
    native_fresh = {
        k: {f: products["candidate-d02"][k][f] for f in row} for k, row in native_old.items()
    }
    results["d02_archived_native_published_75"] = compare(
        "d02_archived_native_published_75", native_old, native_fresh, diffs
    )
    # The frozen native scorer recomputed rigid points with its own matrix arithmetic.
    # Keep ALL cross-implementation float differences in the details even when tiny.
    nd = diffs.get("d02_archived_native_published_75", {})
    native_tolerance = all(
        type(d["old"]) is float
        and type(d["new"]) is float
        and {"top_m", "tcp_m", "center_m"}.intersection(d["path"])
        and abs(d["old"] - d["new"]) <= 1e-10
        for rows in nd.values()
        for d in rows
    )
    historical_report = replay.read(private / "report/replay-historical.public.json")
    gate = replay.read(private / "report/qualification.json")
    replay.require(
        gate["historical_sha256"] == replay.sha(private / "report/replay-historical.public.json")
        and gate["control_sha256"] == replay.sha(private / "report/replay-controls.public.json"),
        "qualification source changed",
    )
    exact = all(
        r["scalar_differences"] == 0
        for k, r in results.items()
        if k != "d02_archived_native_published_75"
    )
    collision_pass = all(v for v in boundary.values() if isinstance(v, bool))
    report = {
        "schema": "g1.visibility.deadline-semantic-equivalence.v1",
        "performance_plan_sha256": PLAN,
        "development_plan_sha256": replay.PLAN_SHA,
        "source_program_sha256": replay.sha(Path(__file__)),
        "unchanged_replay_program_sha256": replay.sha(READER),
        "baseline_build_sha256": BASE,
        "candidate_build_sha256": candidate_tree.parent.name,
        "old_detector_files_sha256": old_detector,
        "candidate_detector_files_sha256": new_detector,
        "blind_seals": seals,
        "raw_read_file_hashes": hashes,
        "sections": results,
        "d02_original_online_coverage": {
            "logged": len(logged),
            "captures": len(capture_index["frames"]),
            "unlogged_terminal": plan["terminal_capture"],
            "refused_feedback": plan["terminal_feedback"],
            "terminal_feedback_measurement": {
                k: raw_d02[plan["terminal_feedback"]["frame_id"]][k]
                for k in (
                    "observed_ids",
                    "usable_ids",
                    "usable",
                    "reason",
                    "selected_id",
                    "object_top_world_m",
                    "grasp_world_m",
                    "rejected_candidate_count",
                )
            },
        },
        "cache_collision_controls": boundary,
        "all_collision_controls_passed": collision_pass,
        "canonicalization": (
            "sorted JSON object keys, list order unchanged, finite numbers at "
            "Python round-trip precision, UTF-8 and LF. Frame and control IDs "
            "are part of each hashed record."
        ),
        "candidate_vs_frozen_all_exact": exact,
        "native_archived_float_tolerance_m": 1e-10,
        "native_archived_closure": native_tolerance,
        "historical_gates": historical_report["gates"],
        "software_equivalence_eligible": bool(
            exact and collision_pass and native_tolerance and gate["eligible"]
        ),
        "hardware_and_new_evaluation_runs": 0,
        "differences_file": "semantic-differences.public.json.gz",
    }
    diff_path = PERFORMANCE / report["differences_file"]
    replay.write(
        diff_path,
        {"schema": "g1.visibility.deadline-semantic-differences.v1", "all_changed_fields": diffs},
    )
    report["differences_file_sha256"] = replay.sha(diff_path)
    replay.write(PERFORMANCE / "semantic-equivalence.public.json", report)
    print(
        json.dumps(
            {
                "eligible": report["software_equivalence_eligible"],
                "records": {
                    k: (v["identical_records"], v["records"], v["scalar_differences"])
                    for k, v in results.items()
                },
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    cap = subs.add_parser("capture")
    cap.add_argument("dataset", choices=["historical", "d02"])
    cap.add_argument("tree", type=Path)
    cap.add_argument("output", type=Path)
    cmp = subs.add_parser("compare")
    cmp.add_argument("private", type=Path)
    cmp.add_argument("baseline_tree", type=Path)
    cmp.add_argument("candidate_tree", type=Path)
    args = parser.parse_args()
    if args.mode == "capture":
        capture(args.dataset, args.tree, args.output)
    else:
        compare_all(args.private, args.baseline_tree, args.candidate_tree)


if __name__ == "__main__":
    main()
