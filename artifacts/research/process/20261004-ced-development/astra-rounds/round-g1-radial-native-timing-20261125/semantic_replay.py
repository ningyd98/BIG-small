"""Seal current-only measurements before joining three d02 runs and the registered +15 mm static screen."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

ROUND = Path(__file__).resolve().parent
ROOT = next(p for p in ROUND.parents if (p / "scripts/graduation/g1_visibility_replay.py").is_file())
PREVIOUS = ROUND.parent / "round-g1-visibility-feedback-deadline-20261125"
MECHANICAL = ROUND.parent / "round-g1-visibility-approach-geometry-20261125"
REFERENCE_SCRIPT = PREVIOUS / "diagnostics/semantic_replay.py"
spec = importlib.util.spec_from_file_location("deadline_evidence", REFERENCE_SCRIPT)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
replay = prior.replay
BASE = ROOT / "experiments/results/g1-visibility-pose-repair-20261124"
PLAN = "567e992a68593aecb32e73a3c3cd5bd9dc4a73d2c8ef2adb5146b91abc944171"
BASELINE = "36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf"
OLD_TREE = BASE / "builds" / BASELINE / "runtime-source"
DETECTORS = ("scripts/graduation/g1_visibility_grid.py", "scripts/graduation/g1_visibility_vision.py")
BATCHES = {"train-current-grid-01": 75, "train-feedback-deadline-01": 130, "train-radial15-01": 130}
STATIC = ("candidate_clean", "candidate_matched_noise")
READ, WRITE, CHECK, SHA = replay.read, replay.write, replay.require, replay.sha


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def geometry_identity(g):
    """The registration portions deciding actual sensor, dictionary, poses, and targets."""
    return {**{k: g[k] for k in ("asset_path", "registration_id", "camera", "pose_marker", "marker_family",
                                  "marker_to_object", "object_to_tcp", "object_half_extent_m", "tool_to_tcp")},
            "dual": {k: g["development_dual"][k] for k in ("markers", "scene_asset_sha256", "agreement_m",
                                                          "prefer_id", "structure_mass_kg", "camera_sha256")}}


def prepare(private, static_packets):
    from scripts.graduation import g1_visibility_radial

    plan = READ(ROUND / "plan.json", PLAN)
    sources = dict(plan["inputs_sha256"])
    for path, value in sources.items():
        CHECK(SHA(ROOT / path) == value, "plan input changed: " + path)
    def locked(path, expected=None):
        digest = SHA(path)
        CHECK(expected is None or expected == digest, "source changed: " + str(path))
        sources[rel(path)] = digest
        return READ(path, digest)

    base_source = locked(OLD_TREE / "runtime-build.json", BASELINE)
    prior_gate = locked(PREVIOUS / "replay-release.public.json")
    prior_equivalence = locked(PREVIOUS / "semantic-equivalence.public.json",
                               "c68745d4b506675e70a1242529b803f2859b69fbd9ea63a9ce77819c85dd5038")
    CHECK(base_source["detector_files_sha256"] == prior_gate["detector_files_sha256"], "wrong baseline detector")
    static_summary = locked(MECHANICAL / "screen-optical-15-summary.public.json")
    static_file = MECHANICAL / "screen-optical-15.public.json.gz"
    static = locked(static_file, "87150ea9f7479cc7a61bf27454438007f1b0515f80e8e519ce4af2c5b32458d0")
    CHECK(len(static["frames"]) == 22 and all(s["qualified"] for s in static["frames"]), "static gate changed")
    pixel_root = private / "packets"
    pixel_root.mkdir(parents=True, exist_ok=False)
    dyn_index = {}
    (pixel_root / "dynamic").mkdir()
    labels = {}
    for batch, count in BATCHES.items():
        path = BASE / "batches" / batch
        instance = path / "d02/instance"
        original = locked(instance / "pixel-index.json")
        allocation = locked(path / "d02/allocation.json", original["allocation_sha256"])
        score = locked(path / "score.json")
        packet_source = path / "scoring/pixels"
        pix = locked(packet_source / "index.json", score["pixel_index_sha256"])
        token, bundle = next(iter(pix.items()))
        CHECK(len(pix) == 1 and token == SHA(instance / "pixel-index.json") and
              bundle["geometry"] == allocation["geometry"] and len(bundle["frames"]) == len(original["frames"]) == count,
              "scored packet and native acquisition diverge")
        (pixel_root / "dynamic" / token).mkdir()
        for old, plain in zip(original["frames"], bundle["frames"], strict=True):
            CHECK(all(old[k] == plain[k] for k in replay.IDENTITY), "original frame tuple differs")
            source = instance / old["file"]
            CHECK(SHA(source) == plain["file_sha256"] == SHA(packet_source / token / plain["file"]), "raw byte mismatch")
            dest = pixel_root / "dynamic" / token / plain["file"]
            shutil.copyfile(source, dest)
            labels[plain["frame_id"]] = {"batch": batch, "label": old["label"], **plain}
        dyn_index[token] = bundle
        for name in ("online-audit", "online-vision", "run", "acquisition-seal"):
            locked(instance / (name + ".json"))
        for i, side in enumerate(("blind-one", "blind-two")):
            folder = path / "scoring" / side
            seal = locked(folder / "seal.json", score["blind_seals_sha256"][i])
            locked(folder / (token + ".json"), seal["packets"][token])
    WRITE(pixel_root / "dynamic/index.json", dyn_index)
    keys = {batch: next(v["geometry"] for t, v in dyn_index.items()
                       if labels[v["frames"][0]["frame_id"]]["batch"] == batch) for batch in BATCHES}
    real_geometry = keys["train-radial15-01"]
    static_geometry = g1_visibility_radial.geometry_for_screen(keys["train-feedback-deadline-01"], 15)
    geometry = geometry_identity(real_geometry)
    static_identity = geometry_identity(static_geometry)
    encoding_differences = list(prior.differences(static_identity, geometry))
    CHECK(geometry == static_identity and all(
          set((type(d["old"]), type(d["new"]))) == {int, float}
          and d["old"] == d["new"] and any(k in d["path"] for k in ("object_T_marker", "marker_to_object"))
          for d in encoding_differences),
          "static registration differs from real radial acquisition")
    CHECK(real_geometry["development_dual"]["radial_offset_mm"] == 15 and
          SHA(OLD_TREE / real_geometry["asset_path"]) == real_geometry["pose_marker"]["marked_asset_sha256"],
          "wrong source or distance")
    lock_static = {}
    for mode in STATIC:
        out = pixel_root / mode
        out.mkdir()
        items = {}
        for event in static["frames"]:
            seal = event[mode]
            p = static_packets / seal["packet_file"]
            frame = READ(p, seal["packet_sha256"])
            CHECK(frame["checksum_sha256"] == seal["frame_checksum"] and
                  frame["calibration_version"] == geometry["camera"]["calibration_version"], "static checksum/registration changed")
            tok = hashlib.sha256((mode + frame["episode_id"]).encode()).hexdigest()
            items.setdefault(tok, []).append((event, seal, p, frame))
        index = {}
        for tok, group in items.items():
            grouped = sorted(group, key=lambda x: (x[0]["step"], x[3]["captured_at"]))
            target = out / tok
            target.mkdir()
            pix = []
            for i, (event, seal, src, frame) in enumerate(grouped):
                name = f"{i:04d}.json"
                shutil.copyfile(src, target / name)
                pix.append({"file": name, "file_sha256": seal["packet_sha256"], "checksum_sha256": seal["frame_checksum"],
                            "frame_id": frame["frame_id"], "physics_step": event["step"]})
                lock_static[frame["frame_id"]] = {"case": event["case"], "role": event["role"], "mode": mode,
                    "step": event["step"], "source_packet_file": seal["packet_file"], "file_sha256": seal["packet_sha256"]}
            f = grouped[0][3]
            index[tok] = {"frames": pix, "geometry": real_geometry, "scene": f["scene_id"], "episode": f["episode_id"],
                          "registered_scene": f["scene_id"], "mode": "dual"}
        WRITE(out / "index.json", index)
    report = {"schema": "g1.radial-native-software-inputs.v1", "timing_plan_sha256": PLAN,
              "baseline_runtime_build_sha256": BASELINE, "input_artifacts_sha256": sources, "geometry_identity": geometry,
              "static_screen_descriptor_sha256": prior.digest(static_geometry), "actual_radial_descriptor_sha256": prior.digest(real_geometry),
              "static_qualified_summary_sha256": SHA(MECHANICAL / "screen-optical-15-summary.public.json"),
              "equal_numeric_transform_entries_with_int_float_spelling": encoding_differences,
              "old_complete_historical_bytes_sha256": prior_equivalence["raw_read_file_hashes"]["historical"]["candidate_sha256"],
              "index_sha256": {k: SHA(pixel_root / k / "index.json") for k in ("dynamic", *STATIC)},
              "static_packets": lock_static, "dynamic_packets": labels}
    WRITE(private / "inputs.json", report)
    print({k:len(v) for k,v in (("dynamic",labels),("static",lock_static))}, flush=True)


def capture(packets, index_sha, tree, output):
    """The subprocess can only open the anonymous current packets and frozen dependencies."""
    tree, output, packets = (p.resolve() for p in (tree, output, packets))
    replay.restrict_worker(packets, tree, output)
    sys.path[:0] = [str(tree), str(tree / "src")]
    from scripts.graduation import g1_visibility_vision as vision
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.g1_formal_runtime import bind_scene

    replay.cv2.setNumThreads(1)
    sources = {k: SHA(tree / k) for k in DETECTORS}
    frames = {}
    for token, b in READ(packets / "index.json", index_sha).items():
        geom = b["geometry"]
        CHECK(b["scene"] == b["registered_scene"], "wrong registered scene")
        previous = None
        with bind_scene(b["scene"]):
            for i, row in enumerate(b["frames"]):
                CHECK(row["file"] == f"{i:04d}.json" and set(row) == {*replay.IDENTITY, "file"}, "unexpected packet fields/order")
                f = frame_from_row(packets / token, row, b["episode"], b["scene"], geom)
                replay.check_acquisition(f, frames, previous)
                CHECK(f.model_dump(mode="json", include=set(geom["camera"])) == geom["camera"], "wrong actual camera")
                m = vision.measure_frame(f, geom)
                CHECK(m["registration_id"] == geom["registration_id"] and m["asset_sha256"] == geom["pose_marker"]["marked_asset_sha256"]
                      and m["frame_id"] == f.frame_id and m["checksum"] == f.checksum_sha256, "wrong result source binding")
                independent = {str(k): replay.independent_pose(geom, k, m["by_id"][str(k)]) for k in m["usable_ids"]}
                if len(independent) == 2:
                    distance = math.dist(independent["7"]["tcp_m"], independent["8"]["tcp_m"])
                    CHECK(abs(distance - m["target_disagreement_m"]) <= 1e-10 and (distance <= 0.010 or not m["usable"]),
                          "dual disagreement bypass")
                frames[f.frame_id] = {"measurement": m, "per_id": independent, "time": f.sim_time_s,
                                      "captured_at": f.captured_at.isoformat(), **{k: row[k] for k in replay.IDENTITY}}
                previous = f
    dependencies = {Path(m.__file__).resolve() for k,m in sys.modules.items()
                    if k.startswith(("scripts.", "cloud_edge_robot_arm")) and getattr(m,"__file__",None)}
    CHECK(all(p.is_relative_to(tree) for p in dependencies), "foreign import")
    CHECK(sources == {k: SHA(tree/k) for k in DETECTORS}, "observer source changed during read")
    WRITE(output, {"frames": frames, "index_sha256": index_sha, "detector_files_sha256": sources,
                   "imported_files_sha256": {p.relative_to(tree).as_posix():SHA(p) for p in sorted(dependencies)}})


if __name__ == "__main__":
    cmd, *argv = sys.argv[1:]
    if cmd == "prepare":
        prepare(*map(Path,argv))
    elif cmd == "capture":
        capture(Path(argv[0]), argv[1], Path(argv[2]), Path(argv[3]))

