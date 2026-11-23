"""Replay registered v10 RGB-D pixels and produce the public Phase 7 vision summary.

Run at the worktree root with PYTHONPATH=<frozen source root>/src:. and a fresh
private output directory. Supply --public for the complete three-stage audit.
The private pixel decisions are sealed before opening labels for attribution.
"""

from __future__ import annotations

import argparse
import base64
import inspect
import io
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image

from cloud_edge_robot_arm.research.native_calibration_collection import digest, load_json
from cloud_edge_robot_arm.research.native_collection_grounding import validate_camera
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    _camera_hash,
    _path,
    _restore_frame,
    _sha_file,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import (
    PoseMarkerRegistration,
    _decode_subpix_rejected_candidates,
    detect_pose_marker,
)
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

Mode = Literal["NONE", "SUBPIX"]
MODES: tuple[Mode, Mode] = ("NONE", "SUBPIX")
PER_STEP = "REGISTERED_PER_PHYSICS_STEP"
CACHE = "IMPLICIT_SENSOR_CACHE_UPDATE"
BOUNDARY = "REGISTERED_ACTION_BOUNDARY"
PIXEL_FIELDS = {
    "rgb_png_base64": "rgb.png",
    "depth_float32_base64": "depth.f32",
    "valid_mask_base64": "mask.u8",
}
REGISTERED_GENERATION = "186e76435e7dc470175190622e4f3658eaaad4298e6fab214e08110d0e9112b0"
Json = dict[str, Any]


def require(value: object, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def encoded(row: object) -> str:
    return json.dumps(
        row, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def capture_step(prev_step: int, step: int, prev_utc: datetime, utc: datetime) -> str:
    if utc <= prev_utc:
        return "OUT_OF_ORDER_CAPTURE"
    if step < prev_step:
        return "OUT_OF_ORDER_PHYSICS"
    if step == prev_step:
        return "SAME_STEP_REACQUISITION"
    return "ADVANCED"


def rgb(observation: RGBDObservation) -> np.ndarray:
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        return np.asarray(image.convert("RGB"))


def row_runs(xs: np.ndarray, ys: np.ndarray) -> list[list[int]]:
    starts = np.flatnonzero(np.r_[True, (np.diff(xs) != 1) | (np.diff(ys) != 0)])
    ends = np.r_[starts[1:] - 1, len(xs) - 1]
    return [[int(ys[i]), int(xs[i]), int(xs[j])] for i, j in zip(starts, ends, strict=True)]


def color_measurement(observation: RGBDObservation, tracker: OpenCVTargetTracker) -> Json:
    """Preserve every registered color support and evaluate the frozen extent predicates."""
    values = rgb(observation).astype(float)
    chroma = values / np.maximum(values.sum(axis=2, keepdims=True), 1.0)
    mask = (np.linalg.norm(chroma - tracker.target_color, axis=2) < 0.14) & (
        np.ptp(values, axis=2) > 30
    )
    count, labels, stats, centers = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    z = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").reshape(
        mask.shape
    )
    valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(mask.shape)
    parts = []
    for index in range(1, count):
        left, top, width, height, area = (int(v) for v in stats[index])
        if area < 8:
            continue
        ys, xs = np.nonzero(labels[top : top + height, left : left + width] == index)
        ys, xs = ys + top, xs + left
        ok = (valid[ys, xs] > 0) & np.isfinite(z[ys, xs]) & (z[ys, xs] > 0.0)
        zs = z[ys[ok], xs[ok]]
        points = tracker._points(observation, xs[ok], ys[ok], zs)
        parts.append(
            {
                "bbox_xywh": [left, top, width, height],
                "area_px": area,
                "centroid_px": centers[index].tolist(),
                "row_runs_px": row_runs(xs, ys),
                "valid_depth_pixels": int(ok.sum()),
                "median_optical_z_m": float(np.median(zs)) if zs.size else None,
                "range_optical_z_m": [float(zs.min()), float(zs.max())] if zs.size else None,
                "mean_visible_world_xyz_m": points.mean(axis=0).tolist() if zs.size else None,
                "visible_world_aabb_m": (
                    [points.min(axis=0).tolist(), points.max(axis=0).tolist()] if zs.size else None
                ),
            }
        )
    target, reason = tracker._geometry(observation, tracker.target_color, target=True)
    if target is not None:
        initial = tracker.initial
        assert initial is not None
        widths = np.subtract(target["max"][:2], target["min"][:2])
        initial_widths = np.subtract(initial["max"][:2], initial["min"][:2])
        if np.any(np.abs(widths / initial_widths - 1.0) > 0.15):
            reason = "target_extent_changed_or_partially_occluded"
    return {
        "components": parts,
        "tracker_geometry_reason": reason,
        "same_target_identity": (
            "SINGLE_COLOR_SUPPORT_MATCH_AT_SAMPLE"
            if target is not None and not reason
            else "UNKNOWN"
        ),
        "full_extent": bool(target is not None and not reason and target["extent_complete"]),
        "sample_geometry": None if target is None else tracker._public(target),
    }


def marker_measurement(
    observation: RGBDObservation,
    registration: PoseMarkerRegistration,
    mode: Mode,
) -> Json:
    diagnostics: Json = {}
    estimate = detect_pose_marker(
        observation, registration, corner_refinement=mode, diagnostics=diagnostics
    )
    result = asdict(estimate)
    for key in (
        "observation_id",
        "observation_checksum_sha256",
        "captured_at",
        "registration_hash",
    ):
        del result[key]  # envelope is stored once on the shared acquisition row
    result["diagnostics"] = diagnostics
    return result


def decoder_trace(gray: np.ndarray, mode: Mode) -> Json:
    """Inspect detector stage and rejected quadrilaterals without changing its verdict."""
    params = cv2.aruco.DetectorParameters()
    params.errorCorrectionRate = 0.0
    if mode == "SUBPIX":
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    corners, ids, rejected = detector.detectMarkers(gray)
    native_ids = [] if ids is None else ids.ravel().tolist()
    fallback = ids is None and mode == "SUBPIX" and len(rejected) > 0
    if fallback:
        corners, ids = _decode_subpix_rejected_candidates(gray, rejected, dictionary)
    return {
        "native_ids": native_ids,
        "zero_bit_fallback_examined": fallback,
        "decoded_ids": [] if ids is None else ids.ravel().tolist(),
        "decoded_corners_px": [pts.reshape(4, 2).tolist() for pts in corners],
        "rejected_quads_px": [p.reshape(4, 2).tolist() for p in rejected],
    }


def object_pose(marker: Json, geometry: Json) -> Json | None:
    if marker["status"] != "OBSERVED":
        return None
    transform = np.asarray(geometry["marker_to_object"]).reshape(4, 4)
    rotation = np.asarray(marker["rotation_marker_to_world"]).reshape(3, 3) @ transform[:3, :3].T
    center = np.asarray(marker["marker_center_world_m"]) - rotation @ transform[:3, 3]
    return {"center_world_m": center.tolist(), "rotation_to_world": rotation.ravel().tolist()}


def read_inventory(root: Path, plan: Json) -> tuple[Json, set[str]]:
    manifest_path = _path(root, "inventory.json")
    require(
        _sha_file(manifest_path) == plan["inputs_sha256"][plan["immutable_raw_manifest"]],
        "frozen inventory SHA256 differs",
    )
    manifest = load_json(manifest_path)
    files = manifest["files"]
    require(
        len(files) == manifest["file_count"] == plan["raw_manifest_file_count"]
        and digest(files) == manifest["inventory_sha256"],
        "frozen inventory count/digest differs",
    )
    names = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    require(names == set(files) | {"inventory.json"}, "unlisted/missing originals")
    require(sum(r["bytes"] for r in files.values()) == manifest["original_bytes"], "raw bytes")
    return manifest, set()


def checked_file(root: Path, files: Json, checked: set[str], name: str) -> Path:
    path = _path(root, name)
    entry = files[name]
    require(
        path.stat().st_size == entry["bytes"] and _sha_file(path) == entry["sha256"],
        "changed inventory file: " + name,
    )
    checked.add(name)
    return path


def pins(source_root: Path, protocol: Json, raw: Json, binding: Json) -> Json:
    require(
        raw["source_hashes"] == protocol["source_hashes"]
        and binding["source_generation"] == protocol["source_generation"] == REGISTERED_GENERATION
        and binding["protocol_sha256"] == digest(protocol)
        and binding["geometry"] == protocol["geometry"]
        and binding["truth"] == "OFFLINE_LABELS_ONLY",
        "different registered generation or geometry",
    )
    paths = {
        Path(inspect.getfile(obj)).resolve()
        for obj in (
            RGBDObservation,
            OpenCVTargetTracker,
            detect_pose_marker,
            _restore_frame,
            validate_camera,
            digest,
            _camera_hash,
        )
    }
    paths.add(source_root / protocol["geometry"]["asset_path"])
    actual = {str(p.relative_to(source_root)): _sha_file(p) for p in paths}
    require(all(raw["source_hashes"][p] == h for p, h in actual.items()), "algorithm SHA256")
    return actual


def indexed(values: list[Json], key: str) -> Json:
    result = {item[key]: item for item in values}
    require(len(result) == len(values), "duplicate key " + key)
    return result


def grounding_clock(record: Json, index: int, step_id: str) -> Json:
    clock: Json = record["tracker_clock"]
    fields = (
        "index",
        "step_id",
        "observation_id",
        "checksum_sha256",
        "source_generation",
        "acquisition",
    )
    require(
        record["index"] == index
        and record["step_id"] == step_id
        and clock["purpose"] == "GROUNDING"
        and all(clock[k] == record[k] for k in fields)
        and record["tracker_evaluated_at"] == clock["evaluated_at"],
        "grounding clock identity/reference mismatch",
    )
    return clock


def load_index(
    root: Path, protocol: Json, source_root: Path, files: Json, checked: set[str]
) -> Json:
    raw: Json = load_json(checked_file(root, files, checked, "partial-originals.json"))
    binding = load_json(checked_file(root, files, checked, "source-binding.json"))
    running_sources = pins(source_root, protocol, raw, binding)
    allocated = raw["allocated_frames"]
    ids = set(allocated)
    require(
        len(ids) == len(allocated) == 11109
        and ids == set(raw["frame_sources"])
        and len(ids) == len(raw["capture_source_roles"]),
        "allocated denominator",
    )
    ops = [o for o in raw["operational_events"] if o["kind"] == "CAPTURE"]
    require({o["acquisition_id"] for o in ops} == ids, "capture operations")
    state_rows = [raw["reset"]["physics_state"]] + [s["post_state_payload"] for s in raw["physics"]]
    identity = raw["identity"]
    require(all(s["episode_id"] == identity["episode_id"] for s in state_rows), "state episodes")
    step_hashes = {s["physics_step"]: digest(s) for s in state_rows}
    intervals = {s["interval_id"]: s for s in raw["intervals"] if s["kind"] == "ACQUISITION"}
    require(len(step_hashes) == raw["total_physics_steps"] + 1, "physics range")
    require(len(intervals) == len(ops) == len(ids), "acquisition operation denominator")
    clocks: dict[str, list[Json]] = defaultdict(list)
    timeline = load_json(checked_file(root, files, checked, "registration-timeline.json"))
    active = load_json(checked_file(root, files, checked, "registered-tracker-bootstrap.json"))
    require(
        timeline["active_tracker_reference_acquisition_id"]
        == active["acquisition"]["acquisition_id"]
        and timeline["dispatch"]["acquisition"] == active["acquisition"]
        and timeline["bootstrap"]["acquisition"] == active["compiler_reference_acquisition"],
        "bootstrap cross-binding",
    )
    joins = {(j["span_id"], j["relation"]): j for j in raw["joins"]}
    original_clocks = [
        load_json(checked_file(root, files, checked, "tracker-clock/" + p + ".json"))
        for p in ("bootstrap", "dispatch")
    ]
    for position, action in enumerate(raw["actions"]):
        path = f"grounding/{action['step_id']}.json"
        record = load_json(checked_file(root, files, checked, path))
        original_clocks.append(grounding_clock(record, position, action["step_id"]))
    for row in raw["decisions"]:
        item = row["inputs"]
        require(digest(item) == row["decision"]["original_inputs_sha256"], "decision inputs")
        j = joins[
            (
                raw["actions"][item["tracker_clock"]["index"]]["span_id"],
                "BEFORE_SUBMIT" if item["phase"] == "PRE" else "AFTER_RETURN",
            )
        ]
        require(
            j["acquisition_id"]
            == item["capture"]["acquisition_id"]
            == item["tracker_clock"]["acquisition"]["acquisition_id"]
            and j["observation_id"] == item["tracker_clock"]["observation_id"]
            and j["checksum_sha256"] == item["tracker_clock"]["checksum_sha256"],
            "decision joins",
        )
        original_clocks.append(item["tracker_clock"])
    consumptions = {
        digest(v)
        for v in load_json(checked_file(root, files, checked, "capture-consumptions.json"))
    }
    clock_keys = {(c["purpose"], c["index"], c["step_id"]) for c in original_clocks}
    require(len(clock_keys) == len(original_clocks) == 14, "original tracker clock denominator")
    original_clocks.sort(key=lambda c: datetime.fromisoformat(c["started_at"]))
    for previous, current in zip(original_clocks, original_clocks[1:], strict=False):
        require(
            datetime.fromisoformat(previous["finished_at"])
            <= datetime.fromisoformat(current["started_at"]),
            "overlapping recorded tracker evaluations",
        )
    for clock in original_clocks:
        reference = clock["acquisition"]
        aid = reference["acquisition_id"]
        path = raw["frame_sources"][aid]
        require(
            reference["path"] == path and reference["sha256"] == files[path]["sha256"],
            "clock references different source",
        )
        require(clock["source_generation"] == REGISTERED_GENERATION, "clock generation")
        require(
            all(
                clock[k]["acquisition_id"] == aid and digest(clock[k]) in consumptions
                for k in ("consumption_before", "consumption_after")
            ),
            "clock lacks original matching consumption",
        )
        clocks[aid].append(
            {
                k: clock[k]
                for k in (
                    "purpose",
                    "step_id",
                    "index",
                    "started_at",
                    "evaluated_at",
                    "finished_at",
                    "observation_id",
                    "checksum_sha256",
                )
            }
        )
    lift = raw["horizons"][-1]
    require(
        (lift["dispatch_step"], lift["controller_return_step"], lift["terminal_step"])
        == (4200, 5155, 6240),
        "unexpected action boundaries",
    )
    pre, post = [row["inputs"] for row in raw["decisions"] if row["inputs"]["skill"] == "LIFT"]
    return {
        "allocated": allocated,
        "sources": raw["frame_sources"],
        "roles": raw["capture_source_roles"],
        "operations": indexed(ops, "acquisition_id"),
        "intervals": intervals,
        "state_hashes": step_hashes,
        "episode": identity["episode_id"],
        "clocks": clocks,
        "bootstrap": [timeline["bootstrap"]["acquisition"], timeline["dispatch"]["acquisition"]],
        "horizons": [
            {
                k: h[k]
                for k in (
                    "skill",
                    "dispatch_step",
                    "controller_return_step",
                    "terminal_step",
                    "terminal_acquisition_id",
                )
            }
            for h in raw["horizons"]
        ],
        "lift_dispatch_id": pre["capture"]["acquisition_id"],
        "terminal_id": post["capture"]["acquisition_id"],
        "lift_online": {
            "shield_allowed": post["shield"]["allowed"],
            "decision_reasons": raw["decisions"][-1]["decision"]["reasons"],
            "facts": {
                k: {
                    v: post["facts"][k][v]
                    for v in ("reasons", "value", "identity_confirmed", "extent_complete")
                }
                for k in ("object_lifted", "object_stable")
            },
        },
        "runtime_pins": running_sources,
    }


def source_frame(
    root: Path,
    files: Json,
    checked: set[str],
    aid: str,
    index: Json,
    geometry: Json,
) -> tuple[RGBDObservation, Json]:
    path = index["sources"][aid]
    require(path == f"frames/{aid}/source-frame.json", "foreign acquisition metadata")
    metadata = load_json(checked_file(root, files, checked, path))
    ref = metadata["frame"]
    role = metadata["capture_source"]
    op = index["operations"][aid]
    n = role["physics_step"]
    interval = index["intervals"][ref["interval_id"]]
    require(
        ref["acquisition_id"] == aid
        and ref["source_acquisition_id"] is None
        and ref["interval_id"] == f"operation-{op['operation_id']}"
        and role == index["roles"][str(op["operation_id"])]
        and op["episode_id"] == index["episode"]
        and op["error_type"] is None
        and n
        == op["begin_step"]
        == op["end_step"]
        == interval["start_step"]
        == interval["end_step"]
        and ref["joined_physics_observation_hash"] == index["state_hashes"][n]
        and interval["disposition"] == "COMPLETE"
        and role["role"] in (CACHE, PER_STEP, BOUNDARY)
        and role["instances_requested"] is (role["role"] != CACHE)
        and role["sample_slot"] == n
        and metadata["pass_count"]
        == len(ref["pass_state_hashes"])
        == (2 if role["role"] == CACHE else 3)
        and set(ref["pass_state_hashes"]) == {_camera_hash(ref["camera_state_payload"])},
        "invalid source/role/operation/physics join for " + aid,
    )
    require(
        metadata["encoded_fields"] == {k: f"frames/{aid}/{v}" for k, v in PIXEL_FIELDS.items()}
        and set(ref["file_hashes"])
        == set(metadata["encoded_fields"].values()) | {f"frames/{aid}/instances.i32"},
        "foreign frame blobs",
    )
    frame = _restore_frame(root, metadata)
    obs = RGBDObservation.model_validate(frame["observation_payload"])
    validate_camera(obs, geometry)
    require(
        obs.depth_convention == "optical_z_m"
        and obs.episode_id == index["episode"]
        and math.isclose(obs.sim_time_s, n / 240, abs_tol=1e-9, rel_tol=0)
        and interval["start_sim_time_s"] == obs.sim_time_s == interval["end_sim_time_s"],
        "different episode/camera/time " + aid,
    )
    for name, sha in ref["file_hashes"].items():
        require(
            files[name]["sha256"] == sha and (root / name).stat().st_size == files[name]["bytes"],
            "blob missing from pinned inventory",
        )
        checked.add(name)  # _restore_frame also hashes every listed blob's original bytes.
    clocks = []
    for clock in index["clocks"].get(aid, []):
        times = [
            datetime.fromisoformat(clock[k]) for k in ("started_at", "evaluated_at", "finished_at")
        ]
        age = (times[1] - obs.captured_at).total_seconds()
        require(
            clock["observation_id"] == obs.observation_id
            and clock["checksum_sha256"] == obs.checksum_sha256
            and times[0] <= times[1] <= times[2]
            and -0.05 <= age <= 5.0,
            "original tracker identity, time or freshness differs",
        )
        clocks.append(
            {k: clock[k] for k in ("purpose", "step_id", "index", "evaluated_at")}
            | {"age_at_evaluation_s": age}
        )
    return obs, {
        "acquisition": int(aid.removeprefix("acquisition-")),
        "role": role["role"],
        "step": n,
        "record_seq": ref["record_seq"],
        "operation_id": op["operation_id"],
        "episode": obs.episode_id,
        "observation_id": obs.observation_id,
        "observation_checksum_sha256": obs.checksum_sha256,
        "captured_at": obs.captured_at.isoformat(),
        "sim_time_s": obs.sim_time_s,
        "calibration_version": obs.calibration_version,
        "utc_capture_interval": [interval["start"][2], interval["end"][2]],
        "operation_ns": [op["bracket"]["lower_ns"], op["bracket"]["upper_ns"]],
        "metadata_sha256": files[path]["sha256"],
        "pixel_and_instance_blob_sha256": ref["file_hashes"],
        "mask_valid_px": sum(obs.valid_mask_bytes()),
        "tracker_evaluations": clocks,
    }


def references(
    root: Path,
    files: Json,
    checked: set[str],
    index: Json,
    geometry: Json,
) -> tuple[OpenCVTargetTracker, list[Json]]:
    rows = []
    for ref, evidence_name in zip(
        index["bootstrap"],
        ("bootstrap.json", "dispatch-bootstrap.json"),
        strict=True,
    ):
        obs, _ = source_frame(root, files, checked, ref["acquisition_id"], index, geometry)
        require(files[ref["path"]]["sha256"] == ref["sha256"], "bootstrap SHA")
        evidence = load_json(checked_file(root, files, checked, evidence_name))
        support = {
            k: evidence[k]
            for k in (
                "original_pixel_target",
                "original_pixel_destination",
                "depth_error_bound_m",
                "top_grasp_support_height_m",
            )
        }
        tracker = OpenCVTargetTracker._inspect_frozen_geometry(obs, support, {})
        u, v = support["original_pixel_target"]
        rows.append(
            {
                "acquisition": ref["acquisition_id"],
                "target_pixel": [u, v],
                "raw_rgb": rgb(obs)[v, u].tolist(),
                "chroma": tracker.target_color.tolist(),
                "depth_error_bound_m": tracker.depth_error_bound_m,
                "source_sha256": ref["sha256"],
            }
        )
    require(rows[0]["chroma"] == rows[1]["chroma"], "different compiler/active target chroma")
    return tracker, rows  # last initialization is active E


def scan(root: Path, protocol_path: Path, source_root: Path, plan_path: Path, out: Path) -> None:
    root, source_root = root.resolve(strict=True), source_root.resolve(strict=True)
    require(not out.resolve().is_relative_to(root), "output overlaps immutable originals")
    plan = load_json(plan_path)
    protocol = load_json(protocol_path)
    require(protocol["source_generation"] == plan["source_generation"], "protocol generation")
    out.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    manifest, checked = read_inventory(root, plan)
    files = manifest["files"]
    index = load_index(root, protocol, source_root, files, checked)
    geometry = protocol["geometry"]
    marker = PoseMarkerRegistration(**geometry["pose_marker"])
    tracker, bootstrap = references(root, files, checked, index, geometry)
    observation_ids: set[str] = set()
    seqs: set[int] = set()
    roles: Counter[str] = Counter()
    previous: Json | None = None
    with (out / "frames.private.jsonl").open("x") as details:
        for number, aid in enumerate(index["allocated"], 1):
            obs, row = source_frame(root, files, checked, aid, index, geometry)
            require(
                row["acquisition"] == number
                and row["record_seq"] not in seqs
                and obs.observation_id not in observation_ids,
                "reused acquisition/record",
            )
            observation_ids.add(obs.observation_id)
            seqs.add(row["record_seq"])
            roles[row["role"]] += 1
            row["time_progress"] = (
                "INITIAL"
                if previous is None
                else capture_step(
                    previous["step"],
                    row["step"],
                    datetime.fromisoformat(previous["captured_at"]),
                    obs.captured_at,
                )
            )
            if previous is not None:
                require(row["record_seq"] > previous["record_seq"], "record order")
            previous = row
            gray = cv2.cvtColor(rgb(obs), cv2.COLOR_RGB2GRAY)
            row["markers"] = {}
            for mode in MODES:
                measured = marker_measurement(obs, marker, mode)
                trace = decoder_trace(gray, mode)
                require(
                    list(measured["observed_marker_ids"]) == trace["decoded_ids"],
                    "independent decoder trace differs",
                )
                if measured["status"] == "OBSERVED":
                    require(
                        measured["observed_marker_ids"] == (marker.marker_id,),
                        "observed nonunique or incorrect ID",
                    )
                measured["trace"] = trace
                measured["registered_sample_object_pose"] = object_pose(measured, geometry)
                row["markers"][mode] = measured
            if 4200 <= row["step"] <= 6240:
                row["color"] = color_measurement(obs, tracker)
            details.write(encoded(row) + "\n")
            if number % 500 == 0 or number == len(index["allocated"]):
                details.flush()
                print(datetime.now(UTC).isoformat(), "acquisitions", number, flush=True)
    for name in sorted(set(files) - checked):
        checked_file(root, files, checked, name)
    summary = {
        "inventory_file_sha256": _sha_file(root / "inventory.json"),
        "inventory_entry_digest": manifest["inventory_sha256"],
        "verified_files": len(checked),
        "inventory_bytes": manifest["original_bytes"],
        "allocated": len(index["allocated"]),
        "roles": dict(roles),
        "references": bootstrap,
        "camera": geometry["camera"],
        "marker_family": geometry["marker_family"],
        "registration": asdict(marker),
        "marker_to_object": geometry["marker_to_object"],
        "source_generation": REGISTERED_GENERATION,
        "algorithm_and_asset_sha256": index["runtime_pins"],
        "protocol_sha256": _sha_file(protocol_path),
        "calibration_error_bound_m": tracker.depth_error_bound_m,
        "horizons": index["horizons"],
        "lift_dispatch_id": index["lift_dispatch_id"],
        "terminal_id": index["terminal_id"],
        "lift_online": index["lift_online"],
        "details_sha256": _sha_file(out / "frames.private.jsonl"),
        "cv2": cv2.__version__,
        "numpy": np.__version__,
        "cached_detector_results": 0,
    }
    (out / "source.private.json").write_text(encoded(summary) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("originals", "protocol", "frozen-source", "plan", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--public", type=Path, help="write the full summary after attribution")
    args = parser.parse_args()
    if args.public:
        require(
            not args.public.resolve().is_relative_to(args.originals.resolve())
            and not args.public.exists(),
            "public destination overlaps or already exists",
        )
    scan(args.originals, args.protocol, args.frozen_source, args.plan, args.output)
    if args.public:
        from scripts.phase7.offline_vision_attribution import attribute, failure_regions
        from scripts.phase7.summarize_vision import summarize

        attribute(args.originals, args.output)
        failure_regions(args.originals, args.output)
        summarize(args.output, args.public)
