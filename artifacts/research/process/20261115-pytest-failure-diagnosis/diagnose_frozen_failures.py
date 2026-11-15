"""只读复核原 V3 失败的像素与控制器记录；不渲染、不执行、不调用模型。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
    NetworkDenyGuard,
    load_observation,
    load_v3_manifest,
)
from cloud_edge_robot_arm.vision import tracking
from cloud_edge_robot_arm.vision.top_grasp import _MAX_TOP_PATCH_Z_SPAN_M
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker, _rgb

TRACKING_SHA = "e52c691f09589d4620fbaa9e4222862da6a4cb41940e54c9bb9e9b7998a68c69"


def diagnose(v3: Path, snapshot: Path) -> dict:
    """验证冻结输入后，用原函数独立复算九例几何拒绝原因。"""
    source_sha = hashlib.sha256(Path(tracking.__file__).read_bytes()).hexdigest()
    if source_sha != TRACKING_SHA:
        raise ValueError("TRACKING_SOURCE_NOT_FROZEN_V3")
    manifest = load_v3_manifest(v3, snapshot)
    rows = []
    for name, case in sorted(manifest.cases.items()):
        result = case.json("result.json")
        if result["component_success"]:
            continue
        row = {
            "case": name,
            "terminal_reason": result["terminal_reason"],
            "executed_actions": result["executed_actions"],
            "planning_outcome": result["planning_outcome"],
        }
        read_names = {"result.json"}
        if result["terminal_reason"] == "RGBDModelCallFailed":
            folder = "component/frames/post-cloud"
            stage_path = "planning/planning-stage-02.json"
            stage = case.json(stage_path)
            evidence = stage["attempts"][0]["draft"]["observation_evidence"]
            obs = load_observation(case, folder)
            for key in ("frame_id", "observation_id", "checksum_sha256"):
                if getattr(obs, key) != evidence[key]:
                    raise ValueError("PLANNING_FRAME_IDENTITY_MISMATCH")
            for key in ("rgb_sha256", "depth_sha256"):
                if obs.evidence()[key] != evidence[key]:
                    raise ValueError("PLANNING_FRAME_BYTES_MISMATCH")
            pixel = tuple(evidence["original_pixel_target"])
            tracker = OpenCVTargetTracker.__new__(OpenCVTargetTracker)
            tracker.depth_error_bound_m = evidence.get("depth_error_bound_m")
            tracker.support_z = evidence["top_grasp_support_height_m"]
            rgb = _rgb(obs)
            color = tracker._color(rgb, pixel)
            geometry, reason = tracker._geometry(obs, color, target=True)
            expected_reason = stage["reason"].split(": ", 1)[1]
            if geometry is not None or reason != expected_reason:
                raise ValueError("ORIGINAL_GEOMETRY_REJECTION_NOT_REPRODUCED:" + name)
            chroma = rgb.astype(float) / np.maximum(rgb.sum(axis=2, keepdims=True), 1.0)
            mask = (
                (np.linalg.norm(chroma - color, axis=2) < 0.14)
                & (np.ptp(rgb.astype(float), axis=2) > 30)
            ).astype(np.uint8)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 8]
            if len(candidates) != 1:
                raise ValueError("COMPONENT_NOT_UNIQUE")
            selected = labels == candidates[0]
            ys, xs = np.nonzero(selected)
            core_mask = cv2.erode(selected.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            core = core_mask[ys, xs]
            depth = np.asarray(obs.depth_values()).reshape(mask.shape)
            valid = np.frombuffer(obs.valid_mask_bytes(), dtype=np.uint8).reshape(mask.shape)
            invalid = selected & ~((depth > 0) & np.isfinite(depth) & (valid > 0))
            raw_ids = case.read(folder + "/instance_geom_ids.i32")
            ids = np.frombuffer(raw_ids, dtype="<i4").reshape(mask.shape)
            metadata = case.json(folder + "/observation.json")
            row.update(
                {
                    "frame_id": obs.frame_id,
                    "frame_checksum": obs.checksum_sha256,
                    "target_pixel": pixel,
                    "recomputed_reason": reason,
                    "original_reason_matches": True,
                    "selected_pixels": int(selected.sum()),
                    "core_pixels": int(core.sum()),
                    "invalid_selected_pixels": int(invalid.sum()),
                    "depth_error_bound_m": tracker.depth_error_bound_m,
                    "instance_ids_used_only_for_offline_diagnosis": True,
                }
            )
            diagnostic_z = None
            if reason == "target_depth_incomplete":
                py, px = np.nonzero(invalid)
            else:
                points = tracker._points(obs, xs, ys, depth[ys, xs])
                top, _, top_reason = tracker._top_support(points, selected, ys, xs)
                if top_reason != reason:
                    raise ValueError("TOP_REJECTION_NOT_REPRODUCED")
                heights = points[:, 2]
                front = ~top & (heights > heights[top].max())
                py, px = ys[front], xs[front]
                diagnostic_z = dict(
                    zip(zip(xs.tolist(), ys.tolist(), strict=True), heights.tolist(), strict=True)
                )
                row.update(
                    {
                        "top_pixels": int(top.sum()),
                        "top_span_limit_m": 2 * tracker.depth_error_bound_m
                        if tracker.depth_error_bound_m is not None
                        else _MAX_TOP_PATCH_Z_SPAN_M,
                        "core_world_z_range_m": [
                            float(heights[core].min()),
                            float(heights[core].max()),
                        ],
                        "top_world_z_range_m": [
                            float(heights[top].min()),
                            float(heights[top].max()),
                        ],
                        "front_pixels": int(front.sum()),
                        "front_pixels_in_core": int(core[front].sum()),
                        "front_excess_above_top_max_m": [
                            float((heights[front] - heights[top].max()).min()),
                            float((heights[front] - heights[top].max()).max()),
                        ],
                        "msaa_causality": "UNPROVEN_NO_CONTROLLED_RENDER_COMPARISON",
                    }
                )
            details = []
            for y, x in zip(py.tolist(), px.tolist(), strict=True):
                geom = int(ids[y, x])
                details.append(
                    {
                        "xy": [x, y],
                        "rgb": rgb[y, x].tolist(),
                        "depth_m": float(depth[y, x]),
                        "valid": int(valid[y, x]),
                        "in_3x3_eroded_core": bool(core_mask[y, x]),
                        "world_z_m": diagnostic_z[(x, y)] if diagnostic_z is not None else None,
                        "offline_instance_id": geom,
                        "offline_instance_label": metadata["instance_labels"].get(str(geom)),
                        "depth_3x3_m": depth[y - 1 : y + 2, x - 1 : x + 2].tolist(),
                    }
                )
            row["diagnostic_pixels"] = details
            row["diagnostic_pixel_instance_counts"] = dict(
                Counter(p["offline_instance_label"] for p in details)
            )
            read_names |= {stage_path} | {
                folder + "/" + f
                for f in [
                    "observation.json",
                    "rgb.png",
                    "depth.f32",
                    "valid_mask.u8",
                    "instance_geom_ids.i32",
                ]
            }
        else:
            episode = case.json("component/episode.json")
            row.update(
                {
                    "recorded_action_ranges": [
                        {
                            k: action[k]
                            for k in ("step_id", "skill", "start_step", "end_step")
                            if k in action
                        }
                        for action in episode["actions"]
                    ],
                    "last_safety_phase": episode["safety_checks"][-1]["phase"],
                    "last_safety_step": episode["safety_checks"][-1]["step_id"],
                    "last_safety_allowed": episode["safety_checks"][-1]["verdict"]["allowed"],
                }
            )
            controller = episode["actions"][-1].get("controller_result")
            if controller is not None:
                row["controller_error"] = controller["error"]
            if result["terminal_reason"] == "HARD_FINGER_LIMIT":
                row["quantitative_finger_root_cause"] = (
                    "NOT_PROVEN_BY_THIS_RECEIPT: no per-step finger qpos/control values here; "
                    "terminal reason alone cannot distinguish overshoot, contact, "
                    "or command trajectory"
                )
            read_names.add("component/episode.json")
        row["bound_inputs"] = {
            path: {k: case.files[path][k] for k in ("sha256", "bytes")}
            for path in sorted(read_names)
        }
        rows.append(row)
    if len(rows) != 13:
        raise ValueError("ORIGINAL_FAILURE_DENOMINATOR_MISMATCH")
    return {
        "scope": "READ_ONLY_FROZEN_V3_FAILURE_DIAGNOSIS_NOT_NEW_EXPERIMENT",
        "tracking_source_sha256": source_sha,
        "manifest_verified_files": manifest.verified_files,
        "cases": rows,
        "summary": dict(
            Counter(row.get("recomputed_reason", row["terminal_reason"]) for row in rows)
        ),
        "new_model_requests": 0,
        "new_renders": 0,
        "new_controller_or_physics_steps": 0,
        "formal_research_acceptance": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v3", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with NetworkDenyGuard() as network:
        data = diagnose(args.v3, args.snapshot)
    data["network_attempts"] = network.attempts
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps({"summary": data["summary"], "verified_files": data["manifest_verified_files"]})
    )
