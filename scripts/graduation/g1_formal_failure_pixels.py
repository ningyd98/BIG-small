"""Seal two native RGB-D reads before joining archived G1 decisions and feedback labels."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import PIL
from PIL import Image

PLAN_SHA = "31d5db8c1fea5aa9bdccdef8a2ccceac66dabaa5382ad5488ca2d6bc2d5f4767"
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "experiments/results/g1-formal-paired-20261124"
PACKETS = RAW / "scoring-q6lm7_gt/packets"
FORMAL = "round-g1-formal-paired-20261124"
ROUND = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / ("round-g1-formal-failure-observation-20261124")
)
ROWS = "pixels-frames.public.json.gz"
SEAL = "pixels-seal.public.json"
SOURCE = Path(__file__).resolve()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pinned(path, digest):
    require(sha(path) == digest, f"input hash differs: {path}")
    return json.loads(path.read_bytes())


def write_new(path, value, *, compressed=False):
    raw = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=None if compressed else 2,
            separators=(",", ":") if compressed else None,
        ).encode()
        + b"\n"
    )
    with path.open("xb") as stream:
        if compressed:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as gz:
                gz.write(raw)
        else:
            stream.write(raw)


def projective_sample(gray, quad, dictionary, code):
    """Bin untouched integer pixel centers through the inverse detected-print homography."""
    print_cells = np.float32([[0, 0], [6, 0], [6, 6], [0, 6]])
    board_cells = np.float32([[-1, -1], [7, -1], [7, 7], [-1, 7]])
    corners = np.float32(quad).reshape(4, 2)
    forward = cv2.getPerspectiveTransform(print_cells, corners)
    backward = cv2.getPerspectiveTransform(corners, print_cells)
    board = cv2.perspectiveTransform(board_cells[None], forward)[0]
    height, width = gray.shape
    x0, y0 = np.maximum(np.floor(board.min(axis=0)).astype(int), [0, 0])
    x1, y1 = np.minimum(np.ceil(board.max(axis=0)).astype(int) + 1, [width, height])
    y, x = np.mgrid[y0:y1, x0:x1]
    xy = np.stack([x, y], axis=-1).astype(np.float32)
    uv = cv2.perspectiveTransform(xy, backward)
    u, v = uv[..., 0], uv[..., 1]
    pixels = gray[y0:y1, x0:x1]
    inner = (u >= 0) & (u < 6) & (v >= 0) & (v < 6)
    quiet = (u >= -1) & (u < 7) & (v >= -1) & (v < 7) & ~inner
    cell = cv2.aruco.generateImageMarker(dictionary, code, 6)
    expected = cell[np.clip(np.floor(v).astype(int), 0, 5), np.clip(np.floor(u).astype(int), 0, 5)]
    black_border = inner & ((u < 1) | (u >= 5) | (v < 1) | (v >= 5))

    def stats(mask):
        vals = pixels[mask]
        return {
            "n": int(vals.size),
            "median": float(np.median(vals)) if vals.size else None,
            "mean": float(vals.mean()) if vals.size else None,
            "min": int(vals.min()) if vals.size else None,
            "max": int(vals.max()) if vals.size else None,
        }

    def difference(a, b):
        return a["median"] - b["median"] if a["n"] and b["n"] else None

    black = stats(inner & (expected == 0))
    white = stats(inner & (expected == 255))
    border = stats(black_border)
    margin = stats(quiet)
    directions = (
        (v, (u >= 0) & (u < 6)),
        (6 - u, (v >= 0) & (v < 6)),
        (6 - v, (u >= 0) & (u < 6)),
        (u, (v >= 0) & (v < 6)),
    )
    edges = []
    for distance, along in directions:
        outside = stats(quiet & along & (distance <= 0) & (distance >= -1))
        inside = stats(inner & along & (distance >= 0) & (distance <= 1) & black_border)
        edges.append(
            {"quiet": outside, "black_border": inside, "delta": difference(outside, inside)}
        )
    return {
        "board_from_detected_print_homography_px": board.tolist(),
        "black_cells": black,
        "white_cells": white,
        "quiet": margin,
        "black_border": border,
        "white_minus_black_median": difference(white, black),
        "quiet_minus_border_median": difference(margin, border),
        "edges": edges,
    }


def quad_features(quad, width, height):
    points = np.asarray(quad, dtype=float).reshape(4, 2)
    edges = np.roll(points, -1, axis=0) - points
    return {
        "side_lengths_px": np.linalg.norm(edges, axis=1).tolist(),
        "edge_directions_deg": np.degrees(np.arctan2(edges[:, 1], edges[:, 0])).tolist(),
        "image_margins_px": {
            "left": float(points[:, 0].min()),
            "right": float(width - 1 - points[:, 0].max()),
            "top": float(points[:, 1].min()),
            "bottom": float(height - 1 - points[:, 1].max()),
        },
    }


def native_candidates(gray, mode, dictionary):
    from cloud_edge_robot_arm.vision.pose_markers import _decode_subpix_rejected_candidates

    params = cv2.aruco.DetectorParameters()
    params.errorCorrectionRate = 0.0
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    direct, ids, rejected = detector.detectMarkers(gray)
    direct_ids = ids.ravel().tolist() if ids is not None else []
    retried = bool(rejected) and (mode == "dual" or ids is None)
    recovered_ids, recovered, source_indices, ambiguous = [], [], [], []
    if retried:
        for i, quad in enumerate(rejected):
            try:
                found, codes = _decode_subpix_rejected_candidates(gray, [quad], dictionary)
            except ValueError as exc:
                if str(exc) != "ambiguous exact marker dictionary match":
                    raise
                ambiguous.append(i)
                continue
            if codes is not None:
                recovered.extend(found)
                recovered_ids.extend(codes.ravel().tolist())
                source_indices.extend([i] * len(found))

    def quads(items):
        return [np.asarray(item).reshape(4, 2).tolist() for item in items]

    return {
        "direct_ids": direct_ids,
        "direct_quads_px": quads(direct),
        "rejected_quads_px": quads(rejected),
        "exact_rejected_attempted": retried,
        "recovered_ids": recovered_ids,
        "recovered_quads_px": quads(recovered),
        "recovered_candidate_indices": source_indices,
        "ambiguous_candidate_indices": ambiguous,
        "rejected_quad_features": [
            quad_features(q, gray.shape[1], gray.shape[0]) for q in rejected
        ],
    }


def depth_features(depth, corners):
    samples, medians = [], []
    height, width = depth.shape
    pts = np.asarray(corners)
    for x, y in [*pts, pts.mean(axis=0)]:
        u, v = round(float(x)), round(float(y))
        patch = depth[max(0, v - 1) : min(height, v + 2), max(0, u - 1) : min(width, u + 2)]
        values = patch[np.isfinite(patch) & (patch > 0)]
        full = patch.size == values.size == 9
        median = float(np.median(values)) if full else None
        samples.append(
            {
                "sample_px": [float(x), float(y)],
                "rounded_px": [u, v],
                "n_pixels": int(patch.size),
                "n_positive": int(values.size),
                "optical_depth_values_m": patch.ravel().tolist(),
                "median_m": median,
                "positive_range_m": float(np.ptp(values)) if values.size else None,
            }
        )
        medians.append(median)
    spread = float(np.ptp(medians[:4])) if None not in medians[:4] else None
    return {"five_patches": samples, "four_corner_median_range_m": spread}


def original_side(frame, geometry, detection):
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
    from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp

    info = {}
    try:
        point, marker = measure_registered_marker_grasp(
            frame, geometry["marker_family"], diagnostics=info
        )
        reason = marker.reason
    except ValueError as exc:
        marker = detect_pose_marker(
            frame,
            PoseMarkerRegistration(**geometry["pose_marker"]),
            corner_refinement="SUBPIX",
            diagnostics=info,
        )
        point, reason = None, str(exc)
    observed = list(marker.observed_marker_ids)
    require(
        observed == (detection["direct_ids"] or detection["recovered_ids"]),
        "single decoder IDs differ",
    )
    used = point is not None
    corners = detection["direct_quads_px"] or detection["recovered_quads_px"]
    origins = ["direct" if detection["direct_ids"] else "exact_rejected"] if observed == [7] else []
    side = {
        "observed": 7 in observed,
        "usable": used,
        "reason": marker.reason,
        "ordered_corners_px": corners[0] if observed == [7] else None,
        "origins": origins,
        "plane": info.get("plane"),
        "measured_edge_lengths_m": marker.measured_edge_lengths_m,
        "marker_center_world_m": marker.marker_center_world_m,
        "rotation_marker_to_world": marker.rotation_marker_to_world,
        "object_center_world_m": None,
        "object_top_world_m": None,
        "grasp_world_m": point.tolist() if used else None,
    }
    if used:
        rotation = np.reshape(marker.rotation_marker_to_world, (3, 3))
        attachment = np.reshape(geometry["marker_to_object"], (4, 4))
        r_obj = rotation @ attachment[:3, :3].T
        center = np.asarray(marker.marker_center_world_m) - r_obj @ attachment[:3, 3]
        side["object_center_world_m"] = center.tolist()
        side["object_top_world_m"] = (
            center + r_obj[:, 2] * geometry["object_half_extent_m"][2]
        ).tolist()
    return {
        "observed_ids": observed,
        "usable_ids": [7] if used else [],
        "selected_id": 7 if used else None,
        "reason": reason,
        "usable": used,
        "target_disagreement_m": None,
        "by_id": {"7": side},
    }


def describe(frame, geometry, mode, dictionary):
    from scripts.graduation.g1_dual_observer import measure_frame

    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as image:
        gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
        gray.shape
    )
    require(gray.shape == (240, 320), "unexpected native resolution")
    detection = native_candidates(gray, mode, dictionary)
    if mode == "original":
        result = original_side(frame, geometry, detection)
    else:
        result = measure_frame(frame, geometry)
        require(
            result["rejected_candidate_count"] == len(detection["rejected_quads_px"]),
            "dual quad count differs",
        )
        for candidate in result["candidates"]:
            for origin in candidate["origins"]:
                prefix = {"direct": "direct", "exact_rejected": "recovered"}[origin]
                pairs = zip(
                    detection[prefix + "_ids"], detection[prefix + "_quads_px"], strict=True
                )
                require(
                    any(
                        c == candidate["id"]
                        and np.allclose(q, candidate["ordered_corners_px"], rtol=0, atol=1.0)
                        for c, q in pairs
                    ),
                    "dual decoded footprint differs",
                )
    by_id = {}
    for code, side in result["by_id"].items():
        metrics = (
            "observed",
            "usable",
            "reason",
            "plane",
            "measured_edge_lengths_m",
            "ordered_corners_px",
            "marker_center_world_m",
            "rotation_marker_to_world",
            "object_center_world_m",
            "object_top_world_m",
            "grasp_world_m",
        )
        row = {k: side[k] for k in metrics}
        row["origins"] = side.get("origins", [])
        quad = row["ordered_corners_px"]
        if quad is None:
            row.update(
                side_lengths_px=None,
                edge_directions_deg=None,
                image_margins_px=None,
                depth=None,
                contrast=None,
            )
        else:
            row.update(quad_features(quad, frame.width, frame.height))
            row["depth"] = depth_features(depth, quad)
            row["contrast"] = projective_sample(gray, quad, dictionary, int(code))
        by_id[code] = row
    return {
        **{
            k: result[k]
            for k in (
                "observed_ids",
                "usable_ids",
                "selected_id",
                "reason",
                "usable",
                "target_disagreement_m",
            )
        },
        "by_id": by_id,
        "detection": detection,
    }


def restrict_evidence_reads(packets, runtime, output):
    """Guard Python-level project file opens before importing any project code in the child."""
    workspace = ROOT
    writes = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def guard(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if args[2] & writes:
            if path != output:
                raise PermissionError(
                    "blind worker write outside exclusive packet result: " + str(path)
                )
        elif path.is_relative_to(workspace):
            if path == SOURCE or path.is_relative_to(runtime):
                return
            if path.is_relative_to(packets):
                rel = path.relative_to(packets).as_posix()
                if rel == "index.json" or re.fullmatch(r"[0-9a-f]{64}/[0-9]{4}\.json", rel):
                    return
            raise PermissionError(
                "project data outside anonymous packets and frozen runtime: " + str(path)
            )

    sys.addaudithook(guard)


def worker(packets, runtime, index_sha, output):
    restrict_evidence_reads(packets, runtime, output)
    sys.path[:0] = [str(runtime), str(runtime / "src")]
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.g1_formal_runtime import bind_scene

    cv2.setNumThreads(1)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    bins = pinned(packets / "index.json", index_sha)
    rows, episodes = {}, set()
    for token, register in bins.items():
        require(
            re.fullmatch(r"[0-9a-f]{64}", token)
            and set(register)
            == {"episode", "scene", "registered_scene", "geometry", "mode", "frames"},
            "foreign fields in anonymous packet set",
        )
        mode, episode, scene = (register[k] for k in ("mode", "episode", "registered_scene"))
        require(
            mode in {"original", "dual"} and scene == register["scene"] and episode not in episodes,
            "blind scene, mode or episode mismatch",
        )
        episodes.add(episode)
        with bind_scene(scene):
            for ordinal, row in enumerate(register["frames"]):
                require(
                    set(row)
                    == {"file", "file_sha256", "checksum_sha256", "physics_step", "frame_id"}
                    and row["file"] == f"{ordinal:04d}.json"
                    and row["frame_id"] not in rows,
                    "foreign fields, duplicate acquisition or reordered packet",
                )
                frame = frame_from_row(packets / token, row, episode, scene, register["geometry"])
                camera = register["geometry"]["camera"]
                require(
                    frame.model_dump(mode="json", include=set(camera)) == camera,
                    "frozen camera mismatch",
                )
                rows[frame.frame_id] = {
                    **{
                        k: row[k]
                        for k in ("frame_id", "file_sha256", "checksum_sha256", "physics_step")
                    },
                    "episode": episode,
                    "mode": mode,
                    "packet_set": token,
                    "packet_ordinal": ordinal,
                    "captured_at": frame.captured_at.isoformat(),
                    "sim_time_s": frame.sim_time_s,
                    **describe(frame, register["geometry"], mode, dictionary),
                }
    require(len(rows) == 778 and len(episodes) == 8, "incomplete blind packet population")
    sources = {
        Path(m.__file__).resolve()
        for name, m in sys.modules.items()
        if (name.startswith("cloud_edge_robot_arm") or name.startswith("scripts."))
        and getattr(m, "__file__", None)
    }
    require(
        all(p.is_relative_to(runtime) for p in sources), "import escaped frozen project source tree"
    )
    native = sorted(Path(cv2.__file__).parent.glob("*.so"))
    require(native, "OpenCV native module not located")
    write_new(
        output,
        {
            "schema": "g1.failure-observation.blind-native-pixels.v1",
            "reader_sha256": sha(SOURCE),
            "anonymous_index_sha256": index_sha,
            "native_size_width_height_px": [320, 240],
            "runtime": {
                "python": sys.version.split()[0],
                "numpy": np.__version__,
                "opencv": cv2.__version__,
                "pillow": PIL.__version__,
                "opencv_native_sha256": {p.name: sha(p) for p in native},
                "imported_project_sources_sha256": {
                    str(p.relative_to(runtime)): sha(p) for p in sorted(sources)
                },
            },
            "measurement": {
                "corner_order": (
                    "dictionary top-left, top-right, bottom-right, bottom-left. each edge "
                    "goes to the next corner"
                ),
                "direction": (
                    "atan2(dy,dx), degrees in native image coordinates, positive clockwise"
                ),
                "margins": "distance to outermost pixel centers x=0,319 and y=0,239",
                "depth": (
                    "four ordered corners then their 2D mean. native 3x3 patch. median "
                    "requires 9/9 positive finite optical z values"
                ),
                "contrast": (
                    "original integer gray pixels (OpenCV RGB2GRAY, 0..255). detector quad "
                    "maps a six-cell square onto the image. board extrapolation adds one cell "
                    "per side (100/75 mm). regional means and medians use original pixel "
                    "centers, no upsampling"
                ),
                "edges": (
                    "outside one-cell quiet strip minus inside black-border strip. adjacent "
                    "side-specific strips overlap at print corners. deltas are median gray "
                    "differences"
                ),
                "missing": (
                    "unobserved IDs have null corners, contrast and depth. a rejected quad "
                    "alone has no registered identity"
                ),
                "source": (
                    "detector-derived footprints only. independently projected registered "
                    "poses are in the separate geometry evidence"
                ),
            },
            "frames": rows,
        },
        compressed=True,
    )


def validate_inputs():
    plan = pinned(ROUND / "plan.json", PLAN_SHA)
    for rel, expected in plan["inputs_sha256"].items():
        require(sha(ROOT / rel) == expected, "Astra input changed: " + rel)
    originals = Path(plan["transitive_inputs"]["manifest"])
    manifest = pinned(ROOT / originals, plan["inputs_sha256"][str(originals)])
    total = 0
    for rel, source in manifest["files"].items():
        path = RAW / rel
        require(
            path.stat().st_size == source["bytes"] and sha(path) == source["sha256"],
            "changed original: " + rel,
        )
        total += source["bytes"]
    require(
        len(manifest["files"]) == 919 and total == plan["transitive_inputs"]["bytes"],
        "original population differs",
    )
    runtime = json.loads((RAW / "runtime-source/runtime-build.json").read_bytes())[
        "runtime_files_sha256"
    ]
    for rel, expected in runtime.items():
        require(
            sha(RAW / "runtime-source" / rel) == expected, "frozen runtime file changed: " + rel
        )
    external = pinned(
        RAW / "trials/external-dependencies.json",
        manifest["files"]["trials/external-dependencies.json"]["sha256"],
    )
    for path, expected in external.items():
        require(sha(Path(path)) == expected, "frozen dependency changed: " + path)
    return {
        "plan_inputs_verified": len(plan["inputs_sha256"]),
        "originals_verified": len(manifest["files"]),
        "original_bytes_verified": total,
        "runtime_files_verified": len(runtime),
        "external_files_verified": len(external),
    }


def seal(private):
    proof = validate_inputs()
    previous = formal_verification()
    index_hash = previous["blind_input_sha256"]
    require(sha(PACKETS / "index.json") == index_hash, "anonymous index changed")
    private.mkdir(parents=True, exist_ok=False)
    runtime = RAW / "runtime-source"
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    reads = []
    for name in ("one", "two"):
        product = private / (name + ".json.gz")
        cmd = [
            sys.executable,
            "-I",
            "-B",
            str(SOURCE),
            "worker",
            str(PACKETS),
            str(runtime),
            index_hash,
            str(product),
        ]
        proc = subprocess.Popen(
            cmd, cwd=runtime, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        reads.append((name, proc, product))
    receipts = []
    for name, proc, product in reads:
        stdout, stderr = proc.communicate()
        receipt = {
            "reader": name,
            "pid": proc.pid,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "product_sha256": sha(product) if proc.returncode == 0 else None,
        }
        write_new(private / (name + ".receipt.json"), receipt)
        receipts.append(receipt)
    require(
        all(r["exit_code"] == 0 for r in receipts),
        "worker failed; inspect the private process receipts",
    )
    require(
        len({r["pid"] for r in receipts}) == 2
        and len({r["product_sha256"] for r in receipts}) == 1,
        "independent worker signatures differ",
    )
    one, two = (r[2].read_bytes() for r in reads)
    require(one == two, "worker payloads differ")
    with (ROUND / ROWS).open("xb") as stream:
        stream.write(one)
    report = {
        "schema": "g1.failure-observation.pixels.pre-join-seal.v1",
        "plan_sha256": PLAN_SHA,
        "reader_sha256": sha(SOURCE),
        "anonymous_index_sha256": index_hash,
        "source_checks_before": proof,
        "input_scope": (
            "pinned anonymous index and 778 frame files. registered geometry and camera. "
            "byte-pinned frozen runtime and libraries"
        ),
        "worker_isolation": (
            "separate Python -I -B processes. independent full loops. worker Python file-open "
            "guard restricts research data to anonymous packets and frozen runtime. writes "
            "limited to one child-specific output"
        ),
        "pre_join_sequence": [
            "write two exclusive child products",
            "compare SHA256 and bytes",
            "publish data and seal",
            "join separately",
        ],
        "separate_pids": [r["pid"] for r in receipts],
        "exit_codes": [r["exit_code"] for r in receipts],
        "distinct_frames": 778,
        "distinct_episodes": 8,
        "identical_bytes": True,
        "worker_payload_sha256": [r["product_sha256"] for r in receipts],
        "sealed_table_file": ROWS,
        "sealed_table_sha256": sha(ROUND / ROWS),
        "deterministic_gzip_mtime": 0,
    }
    write_new(ROUND / SEAL, report)
    print(
        json.dumps(
            {"seal": sha(ROUND / SEAL), "data": report["sealed_table_sha256"], "workers": receipts}
        )
    )


def formal_verification():
    plan = pinned(ROUND / "plan.json", PLAN_SHA)
    path = ROUND.parent / FORMAL / "scoring-verification.public.json"
    return pinned(path, plan["inputs_sha256"][str(path.relative_to(ROOT))])


def join():
    seal_doc = json.loads((ROUND / SEAL).read_bytes())
    digest = sha(ROUND / ROWS)
    require(
        seal_doc["reader_sha256"] == sha(SOURCE)
        and seal_doc["worker_payload_sha256"] == [digest, digest]
        and seal_doc["sealed_table_sha256"] == digest
        and seal_doc["identical_bytes"],
        "missing matching pre-join seal",
    )
    frames = json.loads(gzip.decompress((ROUND / ROWS).read_bytes()))["frames"]
    formal = formal_verification()
    previous = [PACKETS.parent / name for name in ("blind-one", "blind-two")]
    old, other = (pinned(p / "seal.json", formal["blind_seal_sha256"]) for p in previous)
    require(
        old == other
        and old["index_sha256"] == seal_doc["anonymous_index_sha256"]
        and len(frames) == old["n_frames"],
        "previous output links differ",
    )
    seen, mismatches, changed_bytes = set(), [], []
    counts, max_axis = Counter(), Counter()

    def reported(frame_id, key, observed, expected):
        counts[key] += 1
        if observed != expected:
            mismatches.append(
                {"frame_id": frame_id, "field": key, "fresh": observed, "stored": expected}
            )

    for token, old_sha in old["packets"].items():
        a, b = (pinned(p / (token + ".json"), old_sha) for p in previous)
        require(a == b, "prior blind readbacks differ")
        for i, archived in enumerate(a):
            key = archived["frame_id"]
            row = frames[key]
            require(
                key not in seen and row["packet_set"] == token and row["packet_ordinal"] == i,
                "old frame misjoined",
            )
            seen.add(key)
            for field in (
                "file_sha256",
                "checksum_sha256",
                "physics_step",
                "captured_at",
                "observed_ids",
                "usable_ids",
                "usable",
                "reason",
                "selected_id",
            ):
                reported(key, field, row[field], archived[field])
            reported(key, "sim_time_s", row["sim_time_s"], archived["time"])
            reported(
                key, "per_id_keys", [str(i) for i in row["usable_ids"]], sorted(archived["per_id"])
            )
            for code, pose in archived["per_id"].items():
                fresh = row["by_id"][code]
                for new, previous_key in (
                    ("object_center_world_m", "center_m"),
                    ("object_top_world_m", "top_m"),
                    ("grasp_world_m", "tcp_m"),
                ):
                    counts[new] += 1
                    observed, expected = fresh[new], pose[previous_key]
                    delta = (
                        float(np.max(np.abs(np.subtract(observed, expected))))
                        if observed is not None
                        else None
                    )
                    if delta is None or delta > 1e-10:
                        mismatches.append(
                            {
                                "frame_id": key,
                                "field": new,
                                "marker_id": code,
                                "fresh": observed,
                                "stored": expected,
                            }
                        )
                    if delta is not None:
                        max_axis[new] = max(max_axis[new], delta)
                        if delta > 0:
                            changed_bytes.append((key, code, new, delta))
            for field, new in (("top_m", "object_top_world_m"), ("tcp_m", "grasp_world_m")):
                selected = row["selected_id"]
                value = row["by_id"][str(selected)][new] if selected is not None else None
                expected = archived[field]
                counts["selected_" + field] += 1
                if (
                    (value is None) != (expected is None)
                    or value is not None
                    and not np.allclose(value, expected, rtol=0, atol=1e-10)
                ):
                    mismatches.append(
                        {"frame_id": key, "field": field, "fresh": value, "stored": expected}
                    )
    require(seen == set(frames), "old archive population differs")
    feedback, per_slot, order = {}, {}, set()
    for index_path in sorted((RAW / "trials").glob("*/instance/pixel-index.json")):
        token = sha(index_path)
        require(token in old["packets"], "unsealed capture index at feedback join")
        index = pinned(index_path, token)
        slot = index_path.parents[1].name
        by_slot, counts_by_mode = [], Counter()
        for i, recorded in enumerate(index["frames"]):
            key = recorded["frame_id"]
            row = frames[key]
            require(
                key not in order
                and row["episode"] == index["episode"]
                and row["packet_set"] == token
                and row["packet_ordinal"] == i
                and all(
                    row[k] == recorded[k]
                    for k in ("checksum_sha256", "physics_step", "file_sha256")
                ),
                "ambiguous packet/capture join",
            )
            order.add(key)
            d = row["detection"]
            counts_by_mode.update(
                {
                    "frames": 1,
                    "usable": int(row["usable"]),
                    "with_direct": int(bool(d["direct_ids"])),
                    "with_recovery": int(bool(d["recovered_ids"])),
                    "with_rejected": int(bool(d["rejected_quads_px"])),
                    "raw_rejected_quads": len(d["rejected_quads_px"]),
                    "no_decoded_ids": int(not row["observed_ids"]),
                }
            )
            if recorded["label"].endswith("/feedback"):
                by_slot.append(
                    {
                        "frame_id": key,
                        "checksum_sha256": row["checksum_sha256"],
                        "physics_step": row["physics_step"],
                        "packet_ordinal": i,
                        "capture_label": recorded["label"],
                        "observed_ids": row["observed_ids"],
                        "usable_ids": row["usable_ids"],
                        "selected_id": row["selected_id"],
                        "usable": row["usable"],
                        "reason": row["reason"],
                        "target_disagreement_m": row["target_disagreement_m"],
                    }
                )
        feedback[slot] = by_slot
        per_slot[slot] = {**counts_by_mode, "feedback_rows": len(by_slot)}
    require(order == seen, "incomplete archive/capture join")
    feedpath = ROUND / "pixels-feedback.public.json.gz"
    write_new(
        feedpath,
        {
            "schema": "g1.failure-observation.pixels.feedback-lookup.v1",
            "full_table_sha256": digest,
            "population": (
                "capture-index rows labelled <skill>/feedback in acquisition order. frame_id "
                "looks up native features in sealed table. command/consumption fields belong "
                "to timeline"
            ),
            "slots": feedback,
        },
        compressed=True,
    )
    write_new(
        ROUND / "pixels-summary.public.json",
        {
            "schema": "g1.failure-observation.pixels.join.v1",
            "plan_sha256": PLAN_SHA,
            "pre_join_seal_sha256": sha(ROUND / SEAL),
            "full_table_sha256": digest,
            "feedback_table_sha256": sha(feedpath),
            "fresh_processes": 2,
            "prior_formal_blind_seals_sha256": [sha(p / "seal.json") for p in previous],
            "formal_rows": len(seen),
            "archived_quantities_compared": dict(counts),
            "maximum_absolute_axis_difference_m": dict(max_axis),
            "metric_comparison_tolerance_m": 1e-10,
            "nonidentical_numeric_fields_within_tolerance": [
                list(item) for item in changed_bytes if item[3] <= 1e-10
            ],
            "comparison_mismatches": mismatches,
            "pose_scope": (
                "both archived reads retain each usable marker's object center, top and TCP. "
                "Marker basis matrices and ordered corners are absent in the archived blind "
                "rows. the fresh native table retains both."
            ),
            "per_slot": per_slot,
            "verified_after_join": validate_inputs(),
        },
    )
    print(
        json.dumps(
            {
                "compared": len(seen),
                "mismatches": len(mismatches),
                "numeric_differences": len(changed_bytes),
                "max_axis": max_axis,
                "feedback": sum(map(len, feedback.values())),
                "per_slot": per_slot,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="mode", required=True)
    p = cmds.add_parser("worker")
    for key in ("packets", "runtime", "index_sha", "output"):
        p.add_argument(key, type=str if key == "index_sha" else Path)
    cmds.add_parser("seal").add_argument("private", type=Path)
    cmds.add_parser("join")
    args = parser.parse_args()
    if args.mode == "worker":
        worker(
            args.packets.resolve(), args.runtime.resolve(), args.index_sha, args.output.resolve()
        )
    elif args.mode == "seal":
        seal(args.private.resolve())
    else:
        join()


if __name__ == "__main__":
    main()
