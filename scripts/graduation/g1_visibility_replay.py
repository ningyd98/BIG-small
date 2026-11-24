"""Read current RGB-D frames twice, seal estimates, then score against independent G1 truth."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[2]
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
ROUND = ROUNDS / "round-g1-visibility-pose-repair-20261124"
DIAG = ROUNDS / "round-g1-formal-failure-observation-20261124"
RAW = ROOT / "experiments/results/g1-formal-paired-20261124"
PACKETS = RAW / "scoring-q6lm7_gt/packets"
PLAN_SHA = "9fe2d5f7a514a62ebdac454107360f9077a71feb9809b6e93e02a4c8e15c3ef7"
INDEX_SHA = "cf467aea0431903800857fb40b71fc01fe28f34e8d2f0be46227c4144d71a939"
IDENTITY = ("frame_id", "checksum_sha256", "physics_step", "file_sha256")
LIMIT_M = 0.010


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path, expected=None):
    if expected is not None:
        require(sha(path) == expected, f"input SHA256 changed: {path}")
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def write(path, value):
    raw = (
        json.dumps(
            value,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            indent=None if path.suffix == ".gz" else 2,
            separators=(",", ":") if path.suffix == ".gz" else None,
        ).encode()
        + b"\n"
    )
    with path.open("xb") as out:
        if path.suffix == ".gz":
            with gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as stream:
                stream.write(raw)
        else:
            out.write(raw)


def check_acquisition(frame, frame_ids, last):
    require(frame.frame_id not in frame_ids, "duplicate acquisition identity")
    if last is not None:
        require(
            frame.captured_at > last.captured_at and frame.sim_time_s >= last.sim_time_s,
            "acquisition clock repeated or reversed",
        )


def attachment(geometry, code):
    if "development_dual" in geometry:
        marker = geometry["development_dual"]["markers"][str(code)]
        raw, size = marker["object_T_marker"], marker["marker_size_m"]
    else:
        require(code == geometry["pose_marker"]["marker_id"], "unregistered single print")
        raw, size = geometry["marker_to_object"], geometry["pose_marker"]["marker_size_m"]
    return np.reshape(raw, (4, 4)), size


def independent_pose(geometry, code, side):
    transform, _ = attachment(geometry, code)
    marker = np.eye(4)
    marker[:3, :3] = np.reshape(side["rotation_marker_to_world"], (3, 3))
    marker[:3, 3] = side["marker_center_world_m"]
    obj = marker @ np.linalg.inv(transform)
    top = (obj @ [0, 0, geometry["object_half_extent_m"][2], 1])[:3]
    tcp = (obj @ np.reshape(geometry["object_to_tcp"], (4, 4)))[:3, 3]
    result = {"center_m": obj[:3, 3], "top_m": top, "tcp_m": tcp}
    for field, key in (
        ("object_center_world_m", "center_m"),
        ("object_top_world_m", "top_m"),
        ("grasp_world_m", "tcp_m"),
    ):
        require(
            np.allclose(result[key], side[field], rtol=0, atol=1e-10),
            "reported object/grasp differs from independent rigid transform",
        )
    return {k: v.tolist() for k, v in result.items()}


def measure(frame, geometry):
    from scripts.graduation.g1_visibility_vision import measure_frame

    observation = measure_frame(frame, geometry)
    require(
        observation["frame_id"] == frame.frame_id
        and observation["checksum"] == frame.checksum_sha256,
        "detector source binding differs",
    )
    ids = observation["observed_ids"]
    valid = observation["usable_ids"]
    selected = observation["selected_id"]
    registered = (
        {int(k) for k in geometry["development_dual"]["markers"]}
        if "development_dual" in geometry
        else {geometry["pose_marker"]["marker_id"]}
    )
    require(set(valid) <= registered and set(valid) <= set(ids), "unregistered usable print")
    per_id = {str(i): independent_pose(geometry, i, observation["by_id"][str(i)]) for i in valid}
    if observation["usable"]:
        require(
            valid
            and selected == min(valid)
            and len(ids) == len(set(ids))
            and set(ids) <= registered,
            "accepted identity or arbitration violation",
        )
        for key, field in (("top_m", "object_top_world_m"), ("tcp_m", "grasp_world_m")):
            require(
                np.allclose(per_id[str(selected)][key], observation[field], rtol=0, atol=1e-10),
                "selected target differs from independent rigid transform",
            )
    else:
        require(
            selected is None
            and all(
                observation[field] is None
                for field in ("object_center_world_m", "object_top_world_m", "grasp_world_m")
            ),
            "rejected acquisition supplied a target",
        )
    if len(valid) == 2:
        distance = math.dist(per_id["7"]["tcp_m"], per_id["8"]["tcp_m"])
        require(
            math.isclose(distance, observation["target_disagreement_m"], rel_tol=0, abs_tol=1e-10)
            and (not observation["usable"] or distance <= LIMIT_M),
            "dual disagreement bypass or mismatch",
        )
    return {
        **{
            k: observation[k]
            for k in (
                "observed_ids",
                "usable_ids",
                "selected_id",
                "reason",
                "usable",
                "target_disagreement_m",
                "by_id",
                "candidates",
            )
        },
        "per_id": per_id,
        "top_m": observation["object_top_world_m"],
        "tcp_m": observation["grasp_world_m"],
    }


def restrict_worker(packets, runtime, output):
    """Limit research-data access before importing project code in each fresh process."""
    workspace = next((p for p in ROOT.parents if (p / ".venv").is_dir()), ROOT)
    libraries = [Path(p).resolve() for p in sys.path if "site-packages" in p]
    writes = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def guard(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if args[2] & writes:
            if path != output:
                raise PermissionError(f"blind write outside exclusive product: {path}")
            return
        if path.is_relative_to(packets):
            name = path.relative_to(packets).as_posix()
            if name == "index.json" or re.fullmatch(r"[0-9a-f]{64}/[0-9]{4}\.json", name):
                return
            raise PermissionError(f"unexpected blind packet file: {path}")
        if path == SOURCE or any(path.is_relative_to(p) for p in libraries):
            return
        if path.is_relative_to(runtime):
            name = path.relative_to(runtime)
            if (
                name.parts
                and name.parts[0] in ("scripts", "src")
                and path.suffix in (".py", ".pyc")
            ):
                return
            if (
                name.parts
                and name.parts[0] in ("configs", "assets")
                and path.suffix in (".json", ".yaml", ".xml")
            ):
                return
        if any(path.is_relative_to(p) for p in (ROOT, workspace, runtime, output.parent)):
            raise PermissionError(f"blind read outside registered source and packets: {path}")

    sys.addaudithook(guard)


def worker(packets, index_sha, output, runtime):
    packets, output, runtime = (p.resolve() for p in (packets, output, runtime))
    restrict_worker(packets, runtime, output)
    sys.path[:0] = [str(runtime), str(runtime / "src")]
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.g1_formal_runtime import bind_scene

    cv2.setNumThreads(1)
    from scripts.graduation import g1_visibility_vision

    detector_at_start = {
        Path(m.__file__).resolve(): sha(Path(m.__file__).resolve())
        for n, m in sys.modules.items()
        if n.startswith("scripts.graduation.g1_visibility_") and getattr(m, "__file__", None)
    }
    require(
        Path(g1_visibility_vision.__file__).resolve() in detector_at_start, "candidate not loaded"
    )
    reader_at_start = sha(SOURCE)
    bundles = read(packets / "index.json", index_sha)
    frames, episodes = {}, set()
    for token, bundle in bundles.items():
        fields = {"episode", "scene", "geometry", "mode", "frames"}
        require(
            re.fullmatch(r"[0-9a-f]{64}", token)
            and set(bundle) in (fields, fields | {"registered_scene"}),
            "foreign input to blind reader",
        )
        geometry, scene, episode = (bundle[k] for k in ("geometry", "scene", "episode"))
        require(
            scene == bundle.get("registered_scene", scene) and episode and episode not in episodes,
            "foreign scene or repeated episode",
        )
        mode = "dual" if "development_dual" in geometry else "original"
        require(
            bundle["mode"] == mode and bundle["frames"], "incorrect installation or empty frame set"
        )
        episodes.add(episode)
        previous = None
        with bind_scene(scene):
            for i, row in enumerate(bundle["frames"]):
                require(
                    set(row) == {*IDENTITY, "file"} and row["file"] == f"{i:04d}.json",
                    "unexpected packet or acquisition order",
                )
                frame = frame_from_row(packets / token, row, episode, scene, geometry)
                check_acquisition(frame, frames, previous)
                require(
                    frame.model_dump(mode="json", include=set(geometry["camera"]))
                    == geometry["camera"],
                    "packet camera differs from registered camera",
                )
                frames[frame.frame_id] = {
                    **{k: row[k] for k in IDENTITY},
                    "episode": episode,
                    "packet_set": token,
                    "packet_ordinal": i,
                    "mode": mode,
                    "captured_at": frame.captured_at.isoformat(),
                    "time": frame.sim_time_s,
                    **measure(frame, geometry),
                }
                previous = frame
    sources = {
        Path(m.__file__).resolve()
        for name, m in sys.modules.items()
        if name.startswith(("scripts.", "cloud_edge_robot_arm")) and getattr(m, "__file__", None)
    }
    require(
        sources and all(p.is_relative_to(runtime) for p in sources), "foreign project dependency"
    )
    source_hashes = {p.relative_to(runtime).as_posix(): sha(p) for p in sorted(sources)}
    detector = {
        p: h
        for p, h in source_hashes.items()
        if Path(p).name.startswith("g1_visibility_") and Path(p).name != SOURCE.name
    }
    require("scripts/graduation/g1_visibility_vision.py" in detector, "missing candidate source")
    require(
        reader_at_start == sha(SOURCE)
        and all(sha(path) == h for path, h in detector_at_start.items()),
        "candidate or reader changed during measurement",
    )
    write(
        output,
        {
            "schema": "g1.visibility.blind-rgbd.v1",
            "index_sha256": index_sha,
            "worker_sha256": sha(SOURCE),
            "project_sources_sha256": source_hashes,
            "detector_files_sha256": detector,
            "episodes": len(episodes),
            "frames": frames,
        },
    )


def lock_packets(packets, index_sha):
    bundles = read(packets / "index.json", index_sha)
    ids, count, total = set(), 0, 0
    for token, bundle in bundles.items():
        require(re.fullmatch(r"[0-9a-f]{64}", token), "unexpected bundle token")
        for i, row in enumerate(bundle["frames"]):
            require(
                row["file"] == f"{i:04d}.json" and row["frame_id"] not in ids,
                "duplicate or unordered packet during pre-lock",
            )
            path = packets / token / row["file"]
            require(
                path.resolve().is_relative_to(packets.resolve())
                and sha(path) == row["file_sha256"],
                "anonymous input changed before blind measurement",
            )
            total += path.stat().st_size
            ids.add(row["frame_id"])
            count += 1
    require(count > 0, "empty input lock")
    return {
        "schema": "g1.visibility.blind-input-lock.v1",
        "index_sha256": index_sha,
        "frames_byte_verified": count,
        "episodes": len(bundles),
        "total_frame_bytes": total,
    }


def blind(packets, index_sha, output, runtime):
    require(not output.resolve().is_relative_to(packets.resolve()), "output overlaps input packets")
    output.mkdir(parents=True, exist_ok=False)
    write(output / "input-lock.json", lock_packets(packets, index_sha))
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    children = []
    for name in ("one", "two"):
        path = output / (name + ".json.gz")
        cmd = [
            sys.executable,
            "-I",
            "-B",
            str(SOURCE),
            "worker",
            str(packets.resolve()),
            index_sha,
            str(path.resolve()),
            "--runtime",
            str(runtime.resolve()),
        ]
        proc = subprocess.Popen(
            cmd, cwd=runtime, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        children.append((name, proc, path))
    receipts = []
    for name, proc, path in children:
        stdout, stderr = proc.communicate()
        receipt = {
            "pid": proc.pid,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "product_sha256": sha(path) if proc.returncode == 0 else None,
        }
        write(output / (name + ".receipt.json"), receipt)
        receipts.append(receipt)
    require(
        all(r["exit_code"] == 0 for r in receipts), "blind process failed, see exclusive receipts"
    )
    digests = [r["product_sha256"] for r in receipts]
    require(
        len({r["pid"] for r in receipts}) == 2
        and digests[0] == digests[1]
        and children[0][2].read_bytes() == children[1][2].read_bytes(),
        "independent blind products differ",
    )
    data = read(children[0][2], digests[0])
    write(
        output / "seal.json",
        {
            "schema": "g1.visibility.pre-join.v1",
            "plan_sha256": PLAN_SHA,
            "reader_sha256": sha(SOURCE),
            "index_sha256": index_sha,
            "input_lock_sha256": sha(output / "input-lock.json"),
            "pids": [r["pid"] for r in receipts],
            "exit_codes": [r["exit_code"] for r in receipts],
            "worker_sha256": digests,
            "detector_files_sha256": data["detector_files_sha256"],
            "episodes": data["episodes"],
            "frames": len(data["frames"]),
            "products_identical": True,
        },
    )


def identity_in_print(geometry, truth, code, corners):
    """Independently project the true printed square after both pixel products are sealed."""
    mount, size = attachment(geometry, code)
    obj = np.eye(4)
    obj[:3, :3] = np.reshape(truth["object_geom_rotation_row_major"], (3, 3))
    obj[:3, 3] = truth["object_geom_position_m"]
    cam = geometry["camera"]
    camera_marker = np.linalg.inv(np.reshape(cam["camera_to_world"], (4, 4))) @ obj @ mount
    half = size / 2
    shape = np.array(
        [[-half, half, 0, 1], [half, half, 0, 1], [half, -half, 0, 1], [-half, -half, 0, 1]]
    )
    xyz = (camera_marker @ shape.T).T
    require(min(xyz[:, 2]) > 0, "true marker behind registered camera")
    fx, fy, cx, cy = cam["intrinsics"]
    quad = xyz[:, :2] / xyz[:, 2, None] * [fx, fy] + [cx, cy]
    center = np.mean(np.reshape(corners, (4, 2)), axis=0)
    return cv2.pointPolygonTest(quad.astype("float32"), tuple(center), False) >= 0


def truth_errors(geometry, sample, result):
    rot = np.reshape(sample["object_geom_rotation_row_major"], (3, 3))
    center = np.asarray(sample["object_geom_position_m"])
    top = center + rot[:, 2] * sample["object_half_extent_m"][2]
    tcp = center + rot @ np.reshape(geometry["object_to_tcp"], (4, 4))[:3, 3]
    expected = {"top_m": top, "center_m": center, "tcp_m": tcp}
    errors = {}
    for code, p in result["per_id"].items():
        errors[code] = {
            k.replace("_m", "_error_mm"): 1000 * math.dist(v, expected[k]) for k, v in p.items()
        }
    registered = (
        set(geometry["development_dual"]["markers"]) if "development_dual" in geometry else {"7"}
    )
    identities = {}
    for c in result["candidates"]:
        code = str(c["id"])
        match = code in registered and identity_in_print(
            geometry, sample, c["id"], c["ordered_corners_px"]
        )
        identities.setdefault(code, []).append(match)
    require(
        sorted(int(k) for k, v in identities.items() for _ in v) == sorted(result["observed_ids"]),
        "detector candidate and observed populations differ",
    )
    return {
        "truth_top_world_m": top.tolist(),
        "truth_center_world_m": center.tolist(),
        "truth_tcp_world_m": tcp.tolist(),
        "per_id": errors,
        "identity_matches_projected_print": identities,
        "correct_registered_id": bool(identities) and all(all(v) for v in identities.values()),
        "selected_top_error_mm": errors[str(result["selected_id"])]["top_error_mm"]
        if result["usable"]
        else None,
    }


def conflict_demonstrated(result):
    if (
        result["usable"]
        or result["selected_id"] is not None
        or result["usable_ids"] != [7, 8]
        or result["observed_ids"] != [7, 8]
        or result["reason"] != "dual_marker_grasp_conflict"
    ):
        return False
    distance = math.dist(result["per_id"]["7"]["tcp_m"], result["per_id"]["8"]["tcp_m"])
    return distance > LIMIT_M and math.isclose(
        distance, result["target_disagreement_m"], rel_tol=0, abs_tol=1e-10
    )


def summarize(rows):
    valid = [r for r in rows if r["usable"]]
    previous = [r for r in rows if r["previously_usable"]]
    errors = [r["selected_top_error_mm"] for r in valid]
    sides = defaultdict(list)
    for row in rows:
        for code, measurements in row["per_id"].items():
            sides[code].append(measurements["top_error_mm"])
    return {
        "frames": len(rows),
        "valid": len(valid),
        "previously_valid": len(previous),
        "previously_valid_retained": sum(
            r["usable"] and r["correct_registered_id"] for r in previous
        ),
        "wrong_accepted_id": sum(not r["correct_registered_id"] for r in valid),
        "outside_10mm": sum(e > LIMIT_M * 1000 for e in errors),
        "valid_selected_top_error_p90_mm": float(np.quantile(errors, 0.9)) if errors else None,
        "valid_selected_top_error_max_mm": max(errors, default=None),
        "per_id_top_error_mm": {
            k: {"measured": len(v), "p90": float(np.quantile(v, 0.9)), "max": max(v)}
            for k, v in sides.items()
        },
    }


def sealed_products(directory):
    seal = read(directory / "seal.json")
    require(
        seal["plan_sha256"] == PLAN_SHA
        and seal["products_identical"]
        and seal["exit_codes"] == [0, 0]
        and len(set(seal["pids"])) == 2
        and len(set(seal["worker_sha256"])) == 1,
        "missing independent blind proof",
    )
    lock = read(directory / "input-lock.json", seal["input_lock_sha256"])
    require(
        lock["index_sha256"] == seal["index_sha256"]
        and lock["frames_byte_verified"] == seal["frames"],
        "pre-measurement input population changed",
    )
    hashes = [sha(directory / (name + ".json.gz")) for name in ("one", "two")]
    require(hashes == seal["worker_sha256"], "sealed worker bytes changed before truth join")
    one = read(directory / "one.json.gz", hashes[0])
    require(
        one["index_sha256"] == seal["index_sha256"]
        and one["worker_sha256"] == seal["reader_sha256"]
        and seal["detector_files_sha256"] == one["detector_files_sha256"],
        "pixel seal mismatch",
    )
    return seal, one


def join_historical(directory, output):
    seal, data = sealed_products(directory)
    require(
        seal["index_sha256"] == INDEX_SHA
        and seal["frames"] == len(data["frames"]) == 778
        and seal["episodes"] == 8,
        "historical replay denominator differs",
    )
    plan = read(ROUND / "plan.json", PLAN_SHA)

    def planned(path):
        return read(path, plan["inputs_sha256"][path.relative_to(ROOT).as_posix()])

    previous = planned(DIAG / "pixels-frames.public.json.gz")["frames"]
    timelines = planned(DIAG / "episode-timelines.public.json")["cases"]
    manifest = planned(RAW / "originals-manifest.json")["files"]
    bundles = read(PACKETS / "index.json", INDEX_SHA)
    fresh = data["frames"]
    require(
        previous.keys() == fresh.keys() and len(timelines) == 8, "old and fresh frame sets differ"
    )
    joined, anchors, by_arm, by_slot = {}, {}, defaultdict(list), {}
    for case in timelines:
        slot = case["id"]
        instance = RAW / "trials" / slot / "instance"

        def source(name, base=instance):
            path = base / name
            return read(path, manifest[path.relative_to(RAW).as_posix()]["sha256"])

        truth = source("offline-truth.json")
        index = source("pixel-index.json")
        acquisition = source("acquisition-seal.json")
        token = acquisition["index_sha256"]
        require(
            token == sha(instance / "pixel-index.json")
            and acquisition["truth_sha256"] == sha(instance / "offline-truth.json")
            and truth["allocation_sha256"] == index["allocation_sha256"]
            and truth["episode"] == index["episode"] == case["episode"]
            and truth["scene"] == index["scene"] == bundles[token]["scene"],
            "truth and pixel acquisition disagree",
        )
        geometry = bundles[token]["geometry"]
        rows = []
        for ordinal, annotation in enumerate(index["frames"]):
            key = annotation["frame_id"]
            old, new = previous[key], fresh[key]
            require(
                key not in joined
                and old["packet_ordinal"] == new["packet_ordinal"] == ordinal
                and old["packet_set"] == new["packet_set"] == token
                and all(new[k] == old[k] == annotation[k] for k in IDENTITY),
                "reordered or mismatched captured identity",
            )
            step = annotation["physics_step"]
            sample = truth["samples"][step]
            require(
                sample["episode_id"] == new["episode"] == truth["episode"]
                and sample["physics_step"] == step
                and math.isclose(sample["sim_time_s"], new["time"], rel_tol=0, abs_tol=1e-8),
                "foreign pose or time at post-seal join",
            )
            row = {
                "slot": slot,
                "mode": case["arm"],
                **{k: new[k] for k in IDENTITY},
                "previously_usable": old["usable"],
                "previous_selected_id": old["selected_id"],
                "previous_usable_ids": old["usable_ids"],
                "previous_reason": old["reason"],
                "previous_disagreement_mm": None
                if old["target_disagreement_m"] is None
                else 1000 * old["target_disagreement_m"],
                **{
                    k: new[k]
                    for k in ("observed_ids", "usable_ids", "selected_id", "usable", "reason")
                },
                "disagreement_mm": None
                if new["target_disagreement_m"] is None
                else 1000 * new["target_disagreement_m"],
                **truth_errors(geometry, sample, new),
            }
            joined[key] = row
            rows.append(row)
        by_arm[case["arm"]].extend(rows)
        by_slot[slot] = summarize(rows)
        anchors[slot] = {}
        for role in ("last_accepted", "first_refused"):
            anchor = case["anchors"][role]
            frame = joined[anchor["frame_id"]]
            require(
                frame["slot"] == slot
                and frame["physics_step"] == anchor["physics_step"]
                and frame["previously_usable"] == (role == "last_accepted"),
                "misjoined refusal anchor",
            )
            anchors[slot][role] = frame
    require(joined.keys() == fresh.keys(), "unjoined captured frames")
    groups = {arm: summarize(rows) for arm, rows in by_arm.items()}
    stops = [a["first_refused"] for a in anchors.values()]
    conflicts = [s for s in stops if s["previous_reason"] == "dual_marker_grasp_conflict"]
    recovered = sum(
        bool(s["usable"] and s["correct_registered_id"] and s["selected_top_error_mm"] <= 10)
        for s in stops
    )
    conflict_pass = len(conflicts) == 2 and all(
        s["usable_ids"] == [7, 8]
        and s["usable"]
        and 0 <= s["disagreement_mm"] <= 10
        and all(p["top_error_mm"] <= 10 for p in s["per_id"].values())
        for s in conflicts
    )
    conditions = {
        "first_refusals": recovered == 8,
        "two_conflicts_both_codes_correct": conflict_pass,
        "each_original_valid_retained_with_correct_id": all(
            v["previously_valid_retained"] == v["previously_valid"] for v in groups.values()
        ),
        "no_wrong_accepted_id": all(v["wrong_accepted_id"] == 0 for v in groups.values()),
        "each_arm_p90_at_most_10mm": all(
            v["valid_selected_top_error_p90_mm"] is not None
            and v["valid_selected_top_error_p90_mm"] <= 10
            for v in groups.values()
        ),
    }
    write(
        output / "replay-joined-frames.public.json.gz",
        {
            "schema": "g1.visibility.post-seal-truth.v1",
            "prejoin_sha256": sha(directory / "seal.json"),
            "frames": joined,
        },
    )
    summary = {
        "schema": "g1.visibility.historical-replay.v1",
        "plan_sha256": PLAN_SHA,
        "historical_frames": len(joined),
        "originals_manifest_sha256": sha(RAW / "originals-manifest.json"),
        "legacy_frames_sha256": sha(DIAG / "pixels-frames.public.json.gz"),
        "timeline_sha256": sha(DIAG / "episode-timelines.public.json"),
        "index_sha256": INDEX_SHA,
        "worker_sha256": seal["worker_sha256"],
        "prejoin_sha256": sha(directory / "seal.json"),
        "per_frame_sha256": sha(output / "replay-joined-frames.public.json.gz"),
        "first_refusals_recovered": recovered,
        "first_refusals_total": len(stops),
        "gates": conditions,
        "all_historical_gates": all(conditions.values()),
        "groups": groups,
        "slots": by_slot,
        "anchors": anchors,
    }
    write(output / "replay-historical.public.json", summary)
    return summary


def unpack(frame):
    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as image:
        rgb = np.array(image)
    shape = (frame.height, frame.width)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(shape)
    mask = np.frombuffer(frame.valid_mask_bytes(), dtype="uint8").reshape(shape)
    return rgb, depth.copy(), mask.copy()


def intervention(frame, ordinal, rgb=None, depth=None, mask=None, **fields):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    if rgb is not None:
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")
        fields["rgb_png_base64"] = base64.b64encode(buf.getvalue()).decode()
    if depth is not None:
        fields["depth_float32_base64"] = base64.b64encode(
            depth.astype("<f4", copy=False).tobytes()
        ).decode()
        if mask is None:
            mask = (depth > 0).astype("uint8")
        fields["valid_mask_base64"] = base64.b64encode(mask.tobytes()).decode()
    identifier = hashlib.sha256(f"{frame.frame_id}_{ordinal}".encode()).hexdigest()[:32]
    return RGBDObservation.model_validate(
        {
            **frame.model_dump(),
            **fields,
            "frame_id": "rgbd-" + identifier,
            "observation_id": "",
            "checksum_sha256": "",
        }
    )


def dictionary_patterns():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return [cv2.aruco.generateImageMarker(dictionary, i, 6) > 0 for i in range(50)]


def control_fixtures():
    from scripts.graduation.dynamic_vision_score import frame_from_row

    # SHA-pinned, real, simultaneous exposures in normal launch poses.
    bins = read(PACKETS / "index.json", INDEX_SHA)
    tokens = {
        "dual": "7fafc0d324efc8c94b94866b8ae876dd28f6b023231a3bfa41d63e26f451f289",
        "original": "58ca705f2d40968d71022c01e4b1a931742a545c16f2b224771649914be2964c",
    }
    bases = {}
    for arm, token in tokens.items():
        b = bins[token]
        bases[arm] = frame_from_row(
            PACKETS / token, b["frames"][0], b["episode"], b["scene"], b["geometry"]
        )
    frame, single = bases["dual"], bases["original"]
    arrays = unpack(frame)
    rgb, depth, mask = arrays
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    direct, decoded, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(gray)
    require(
        decoded is not None and set(decoded.ravel()) == {7, 8},
        "control source lacks two direct prints",
    )
    boxes = {}
    for code, quad in zip(decoded.ravel(), direct, strict=True):
        points = quad.reshape(4, 2)
        lo, hi = (
            np.floor(points.min(axis=0)).astype(int) - 3,
            np.ceil(points.max(axis=0)).astype(int) + 4,
        )
        boxes[int(code)] = tuple(map(int, [*lo, *hi]))
    x, y, x1, y1 = boxes[8]
    dx = 39
    source, dest = np.s_[y:y1, x:x1], np.s_[y:y1, x + dx : x1 + dx]
    swapped = [a.copy() for a in arrays]
    for original, changed in zip(arrays, swapped, strict=True):
        changed[source], changed[dest] = original[dest], original[source]
        require(
            np.array_equal(changed[dest], original[source])
            and np.array_equal(changed[source], original[dest]),
            "paired pixel/depth/mask translation failed",
        )
    source_hashes = {
        k: hashlib.sha256(a[source].tobytes()).hexdigest()
        for k, a in zip(("rgb", "optical_z_f32", "valid_u8"), arrays, strict=True)
    }
    center_depth = float(depth[(y + y1) // 2, (x + x1) // 2])
    proof = {
        "roi_xyxy_end_exclusive": [x, y, x1, y1],
        "movement_px": [dx, 0],
        "original_depth_at_center_m": center_depth,
        "expected_x_translation_m": dx * center_depth / frame.intrinsics[0],
        "unchanged_source_chip_sha256_at_destination": source_hashes,
        "method": (
            "exchange disjoint pixel-aligned rectangles in each of RGB, original float32 "
            "optical Z and validity mask"
        ),
    }
    blocks = dictionary_patterns()
    p7 = blocks[7]
    alternatives = [
        (np.count_nonzero(p7 != np.rot90(p, n)), i, n, np.rot90(p, n))
        for i, p in enumerate(blocks)
        for n in range(4)
        if i != 7
    ]
    _, alt, turns, option = min(alternatives, key=lambda v: v[:3])
    dark, white, unknown = 30, 230, 130
    board = np.where(p7, white, dark).astype("uint8")
    partial = board.copy()
    partial[1, 1] = unknown
    ambiguous = board.copy()
    ambiguous[p7 != option] = unknown
    mirror = {}
    for code in (7, 8):
        mirror[str(code)] = [
            {"id": i, "quarter_turns_ccw": n}
            for i, p in enumerate(blocks)
            for n in range(4)
            if np.array_equal(np.fliplr(blocks[code]), np.rot90(p, n))
        ]
    require(not mirror["7"] and mirror["8"], "dictionary mirror support changed")

    def stamp(base, cells, x0=230, y0=150):
        target = base.copy()
        print_image = np.repeat(np.repeat(cells, 3, axis=0), 3, axis=1)
        target[y0 - 3 : y0 + 21, x0 - 3 : x0 + 21] = white
        target[y0 : y0 + 18, x0 : x0 + 18] = print_image[:, :, None]
        return target

    zero = np.zeros_like(depth)
    uniform = np.full_like(rgb, white)
    flat = np.full_like(depth, frame.camera_to_world[11] - 0.070)
    foreign = np.where(blocks[17], white, dark).astype("uint8")
    x7, y7, x7b, y7b = boxes[7]
    src7, dst7 = np.s_[y7:y7b, x7:x7b], np.s_[y7:y7b, x7 + 50 : x7b + 50]
    duplicate = [a.copy() for a in arrays]
    for a, b in zip(arrays, duplicate, strict=True):
        b[dst7] = a[src7]
    damaged = depth.copy()
    damaged[source] = 0

    # 'identity' witnesses distinguish an observed threat from a print missed by every decoder.
    # The paired synthetic positive uses exactly the same camera, location, scale and photometry.
    cases = {
        "unaltered-dual": ("positive-dual", frame, {}),
        "unaltered-single": ("positive-single", single, {}),
        "paired-clean-grid": (
            "positive-grid",
            intervention(frame, 2, stamp(uniform, board), flat),
            {},
        ),
        "true-two-target-conflict": ("conflict", intervention(frame, 3, *swapped), proof),
        "full-occlusion": (
            "no-print",
            intervention(frame, 4, uniform),
            {"rgb": "all pixels uniform"},
        ),
        "foreign-only": (
            "foreign-only",
            intervention(frame, 5, stamp(uniform, foreign), flat),
            {"print_ids": [17]},
        ),
        "registered-plus-foreign": (
            "foreign-plus",
            intervention(frame, 6, stamp(rgb, foreign)),
            {"original_ids": [7, 8], "additional_id": 17},
        ),
        "two-physical-copies-id7": (
            "duplicate",
            intervention(frame, 7, *duplicate),
            {"source_roi": list(boxes[7]), "added_displacement_px": [50, 0]},
        ),
        "missing-data-cell": (
            "no-print",
            intervention(frame, 8, stamp(uniform, partial), flat),
            {"missing_rc": [1, 1], "level": unknown},
        ),
        "two-consistent-completions": (
            "no-print",
            intervention(frame, 9, stamp(uniform, ambiguous), flat),
            {
                "possible_ids": [7, alt],
                "second_code_quarter_turns_ccw": turns,
                "erased_rc": np.argwhere(p7 != option).tolist(),
                "erased_level": unknown,
            },
        ),
        "mirrored-id7": (
            "no-print",
            intervention(frame, 10, stamp(uniform, np.fliplr(board)), flat),
            {"exact_matches_across_dictionary_and_four_rotations": mirror["7"]},
        ),
        "insufficient-contrast": (
            "no-print",
            intervention(frame, 11, stamp(uniform, np.where(p7, 126, 110).astype("uint8")), flat),
            {"dark": 110, "bright": 126, "contrast": 16},
        ),
        "two-prints-no-depth": ("no-depth-dual", intervention(frame, 12, depth=zero), {}),
        "one-print-no-depth": ("no-depth-single", intervention(single, 13, depth=zero), {}),
        "one-valid-one-bad-depth": (
            "positive-fallback",
            intervention(frame, 14, depth=damaged),
            {"invalidated_roi": list(boxes[8]), "retained_valid_id": 7},
        ),
        "foreign-camera-source": (
            "wrong-camera",
            intervention(frame, 15, source="isaac_camera"),
            {"source": "isaac_camera"},
        ),
        "foreign-calibration": (
            "wrong-camera",
            intervention(frame, 16, calibration_version="foreign-fixture-calibration"),
            {},
        ),
        "foreign-episode": (
            "foreign-transport",
            intervention(frame, 17, episode_id="other-acquisition"),
            {},
        ),
        "frame-identity-replay": ("replay", frame, {}),
        "capture-clock-reversed": (
            "time",
            intervention(frame, 19, captured_at=frame.captured_at - timedelta(seconds=1)),
            {},
        ),
    }
    provenance = {
        "base_index_sha256": INDEX_SHA,
        "base_packets": {a: {"packet_set": t, **bins[t]["frames"][0]} for a, t in tokens.items()},
        "mirrored_dictionary_matches": mirror,
        "id8_mirror_limitation": (
            "A mirror matches a rotation of the legitimate ID8 bits. "
            "The image alone cannot distinguish these impressions."
        ),
    }
    return cases, bases, {a: bins[t]["geometry"] for a, t in tokens.items()}, provenance


def control_witness(kind, r):
    ids, valid = r["observed_ids"], r["usable_ids"]
    target = r["usable"] and r["selected_id"] is not None
    if kind == "conflict":
        return conflict_demonstrated(r)
    if kind == "positive-dual":
        return target and ids == valid == [7, 8] and r["target_disagreement_m"] <= LIMIT_M
    if kind in ("positive-grid", "positive-single"):
        return target and ids == valid == [7]
    if kind == "positive-fallback":
        return (
            target
            and ids == [7, 8]
            and valid == [7]
            and r["selected_id"] == 7
            and not r["by_id"]["8"]["usable"]
            and r["by_id"]["8"]["grasp_world_m"] is None
        )
    if target:
        return False
    if kind in ("no-depth-dual", "no-depth-single"):
        wanted = [7, 8] if kind == "no-depth-dual" else [7]
        return (
            ids == wanted
            and not valid
            and all("depth" in r["by_id"][str(i)]["reason"] for i in ids)
        )
    if kind == "no-print":
        return not valid
    if kind.startswith("foreign-") and kind != "foreign-transport":
        return r["reason"] == "foreign_marker_id" and ids == (
            [17] if kind == "foreign-only" else [7, 8, 17]
        )
    if kind == "duplicate":
        return r["reason"] == "duplicate_marker_id" and ids == [7, 7, 8]
    if kind == "wrong-camera":
        return r["reason"] == "registered_camera_mismatch"
    expected = {
        "time": "acquisition clock repeated or reversed",
        "replay": "duplicate acquisition identity",
        "foreign-transport": "foreign acquisition context",
    }
    return r["reason"] == expected[kind]


def controls(private, output):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    private.mkdir(parents=True, exist_ok=False)
    cases, reference, registrations, provenance = control_fixtures()
    stimuli = {}
    for key, (_, frame, _) in cases.items():
        path = private / (key + ".json")
        write(path, frame.model_dump(mode="json"))
        stimuli[key] = sha(path)
    write(private / "stimuli-manifest.json", {"source": provenance, "files_sha256": stimuli})
    rows = {}
    for key, (kind, _, method) in cases.items():
        arm = "original" if key in ("unaltered-single", "one-print-no-depth") else "dual"
        base = reference[arm]
        frame = RGBDObservation.model_validate(read(private / (key + ".json"), stimuli[key]))
        clock_case = kind in ("replay", "time", "foreign-transport")
        if clock_case:
            try:
                require(
                    frame.episode_id == base.episode_id and frame.scene_id == base.scene_id,
                    "foreign acquisition context",
                )
                check_acquisition(frame, {base.frame_id}, base)
            except ValueError as exc:
                observed = {
                    "observed_ids": [],
                    "usable_ids": [],
                    "selected_id": None,
                    "usable": False,
                    "reason": str(exc),
                    "top_m": None,
                    "tcp_m": None,
                    "per_id": {},
                }
            else:
                observed = measure(frame, registrations[arm])
        else:
            observed = measure(frame, registrations[arm])
        passed = control_witness(kind, observed)
        rows[key] = {
            "kind": kind,
            "positive": kind.startswith("positive-"),
            "qualification_witness": passed,
            "layer": "registered packet admission" if clock_case else "current RGB-D measurement",
            "packet_sha256": stimuli[key],
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "intervention": method,
            "result": observed,
        }
    discrepancy = rows["true-two-target-conflict"]
    if discrepancy["qualification_witness"] and rows["unaltered-dual"]["qualification_witness"]:
        actual = discrepancy["result"]["per_id"]
        original = rows["unaltered-dual"]["result"]["per_id"]
        measured_shift = np.subtract(actual["8"]["tcp_m"], original["8"]["tcp_m"])
        expected_shift = [discrepancy["intervention"]["expected_x_translation_m"], 0, 0]
        stable_error = math.dist(actual["7"]["tcp_m"], original["7"]["tcp_m"])
        rigid_error = math.dist(measured_shift, expected_shift)
        discrepancy["metric_crosscheck"] = {
            "per_id8_tcp_delta_m": measured_shift.tolist(),
            "expected_delta_m": expected_shift,
            "delta_difference_m": rigid_error,
            "untouched_id7_tcp_drift_m": stable_error,
        }
        discrepancy["qualification_witness"] = rigid_error <= 0.005 and stable_error <= 0.005
    negative = [r for r in rows.values() if not r["positive"]]
    positive = [r for r in rows.values() if r["positive"]]
    report = {
        "schema": "g1.visibility.end-to-end-controls.v1",
        "plan_sha256": PLAN_SHA,
        "provenance": provenance,
        "stimuli_manifest_sha256": sha(private / "stimuli-manifest.json"),
        "negative_controls": len(negative),
        "positive_controls": len(positive),
        "false_positive_controls": sum(r["result"]["usable"] for r in negative),
        "negative_witnesses_passed": sum(r["qualification_witness"] for r in negative),
        "positive_witnesses_passed": sum(r["qualification_witness"] for r in positive),
        "all_control_witnesses": all(r["qualification_witness"] for r in rows.values()),
        "cases": rows,
    }
    write(output / "replay-controls.public.json", report)
    return report


def legacy(private, output):
    """Reproduce the failed legacy expectation from the exact frozen production entry point."""
    private.mkdir(parents=True, exist_ok=False)
    plan = read(ROUND / "plan.json", PLAN_SHA)
    product = private / "legacy-native.json.gz"
    runtime = RAW / "runtime-source"
    script = ROOT / "scripts/graduation/g1_formal_failure_pixels.py"
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(script),
            "worker",
            str(PACKETS),
            str(runtime),
            INDEX_SHA,
            str(product),
        ],
        cwd=runtime,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        },
        check=True,
    )
    archive = DIAG / "pixels-frames.public.json.gz"
    require(
        sha(product) == sha(archive) == plan["inputs_sha256"][archive.relative_to(ROOT).as_posix()],
        "legacy reproduction differs from frozen diagnostic",
    )
    table = read(product)["frames"]
    tpath = DIAG / "episode-timelines.public.json"
    cases = read(tpath, plan["inputs_sha256"][tpath.relative_to(ROOT).as_posix()])["cases"]
    groups = {
        mode: {
            "frames": sum(f["mode"] == mode for f in table.values()),
            "usable": sum(f["mode"] == mode and f["usable"] for f in table.values()),
        }
        for mode in ("original", "dual")
    }
    anchors = {}
    for case in cases:
        item = {}
        for role in ("last_accepted", "first_refused"):
            row = table[case["anchors"][role]["frame_id"]]
            require(
                row["usable"] == (role == "last_accepted"), "legacy boundary failed to reproduce"
            )
            item[role] = {
                k: row[k]
                for k in (
                    "frame_id",
                    "physics_step",
                    "observed_ids",
                    "usable_ids",
                    "selected_id",
                    "usable",
                    "reason",
                    "target_disagreement_m",
                    "checksum_sha256",
                )
            }
        anchors[case["id"]] = item
    require(len(table) == 778 and len(anchors) == 8, "legacy evidence denominator changed")
    write(
        output / "replay-legacy-red.public.json",
        {
            "schema": "g1.visibility.legacy-red.v1",
            "plan_sha256": PLAN_SHA,
            "old_worker_sha256": sha(script),
            "pinned_input_index_sha256": INDEX_SHA,
            "fresh_worker_product_sha256": sha(product),
            "frozen_diagnostic_sha256": sha(archive),
            "identical_to_frozen_prior_two_worker_output": True,
            "historical_frames": len(table),
            "original_usable_by_arm": groups,
            "last_accepted_and_first_refused": anchors,
            "first_refusals_recovered": 0,
            "first_refusals_total": len(anchors),
            "acceptance_expected": 8,
            "gate": "EXPECTED_RED",
            "new_formal_trials": 0,
        },
    )


def qualify(attempt):
    seal, _ = sealed_products(attempt / "blind")
    require(
        all(sha(ROOT / name) == h for name, h in seal["detector_files_sha256"].items()),
        "candidate code changed between blind read and control qualification",
    )
    out = attempt / "report"
    out.mkdir()
    historical = join_historical(attempt / "blind", out)
    result = controls(attempt / "control-packets", out)
    sources = {k: sha(ROOT / k) for k in seal["detector_files_sha256"]}
    require(
        sources == seal["detector_files_sha256"],
        "candidate source changed during control qualification",
    )
    ok = historical["all_historical_gates"] and result["all_control_witnesses"]
    write(
        out / "qualification.json",
        {
            "eligible": ok,
            "historical_sha256": sha(out / "replay-historical.public.json"),
            "control_sha256": sha(out / "replay-controls.public.json"),
            "detector_files_sha256": sources,
        },
    )


def publish(attempt, destination):
    import shutil

    seal, _ = sealed_products(attempt / "blind")
    report = attempt / "report"
    q = read(report / "qualification.json")
    historical = read(report / "replay-historical.public.json", q["historical_sha256"])
    controls_report = read(report / "replay-controls.public.json", q["control_sha256"])
    require(
        q["detector_files_sha256"] == seal["detector_files_sha256"]
        and all(sha(ROOT / k) == v for k, v in q["detector_files_sha256"].items())
        and seal["reader_sha256"] == sha(SOURCE),
        "qualified source generation has changed",
    )
    require(
        historical["per_frame_sha256"] == sha(report / "replay-joined-frames.public.json.gz")
        and historical["prejoin_sha256"] == sha(attempt / "blind/seal.json")
        and historical["worker_sha256"] == seal["worker_sha256"]
        and controls_report["stimuli_manifest_sha256"]
        == sha(attempt / "control-packets/stimuli-manifest.json"),
        "qualification evidence dependencies changed",
    )
    stim = read(attempt / "control-packets/stimuli-manifest.json")
    require(
        all(
            sha(attempt / "control-packets" / (k + ".json")) == h
            for k, h in stim["files_sha256"].items()
        ),
        "control packet changed after qualification",
    )
    eligible = bool(
        q["eligible"]
        and historical["all_historical_gates"]
        and controls_report["all_control_witnesses"]
        and controls_report["false_positive_controls"] == 0
    )
    paths = {
        destination / name: report / name
        for name in (
            "replay-historical.public.json",
            "replay-joined-frames.public.json.gz",
            "replay-controls.public.json",
        )
    }
    paths.update(
        {
            destination / "replay-blind-frames.public.json.gz": attempt / "blind/one.json.gz",
            destination / "replay-blind-seal.public.json": attempt / "blind/seal.json",
            destination / "replay-input-lock.public.json": attempt / "blind/input-lock.json",
            destination / "replay-control-stimuli.public.json": attempt
            / "control-packets/stimuli-manifest.json",
        }
    )
    gate = destination / (
        "replay-release.public.json" if eligible else "replay-ineligible.public.json"
    )
    require(not any(path.exists() for path in [*paths, gate]), "publication already exists")
    old = read(destination / "replay-legacy-red.public.json")
    require(
        old["gate"] == "EXPECTED_RED"
        and old["plan_sha256"] == PLAN_SHA
        and old["historical_frames"] == 778,
        "missing original RED",
    )
    for path, source in paths.items():
        with source.open("rb") as src, path.open("xb") as out:
            shutil.copyfileobj(src, out)
    evidence = [*paths, destination / "replay-legacy-red.public.json", ROUND / "plan.json", SOURCE]
    write(
        gate,
        {
            "schema": "g1.visibility.offline-release.v1",
            "eligible": eligible,
            "plan_sha256": PLAN_SHA,
            "detector_files_sha256": q["detector_files_sha256"],
            "historical_frames": historical["historical_frames"],
            "first_refusals_recovered": historical["first_refusals_recovered"],
            "false_positive_controls": controls_report["false_positive_controls"],
            "negative_controls": controls_report["negative_controls"],
            "positive_controls": controls_report["positive_controls"],
            "historical_gates": historical["gates"],
            "control_witnesses": controls_report["all_control_witnesses"],
            "input_artifacts_sha256": {
                p.resolve().relative_to(ROOT).as_posix(): sha(p) for p in evidence
            },
            "claim_scope": "offline development software qualification",
            "new_formal_trials": 0,
            "real_hardware_trials": 0,
        },
    )
    print(f"{gate} {sha(gate)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="cmd", required=True)
    for name in ("blind", "worker"):
        cmd = modes.add_parser(name)
        cmd.add_argument("packets", type=Path)
        cmd.add_argument("index_sha")
        cmd.add_argument("output", type=Path)
        cmd.add_argument("--runtime", type=Path, default=ROOT)
    cmd = modes.add_parser("legacy")
    cmd.add_argument("private", type=Path)
    cmd.add_argument("output", type=Path)
    cmd = modes.add_parser("qualify")
    cmd.add_argument("attempt", type=Path)
    cmd = modes.add_parser("publish")
    cmd.add_argument("attempt", type=Path)
    cmd.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.cmd in ("blind", "worker"):
        {"blind": blind, "worker": worker}[args.cmd](
            args.packets, args.index_sha, args.output, args.runtime
        )
    elif args.cmd == "legacy":
        legacy(args.private, args.output)
    elif args.cmd == "qualify":
        qualify(args.attempt)
    else:
        publish(args.attempt, args.destination)


if __name__ == "__main__":
    main()
