"""Estimate r593 poses from a sealed RGB-D directory without simulator state access."""

from __future__ import annotations

import argparse
import base64
import hashlib
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import numpy as np
from scripts.graduation.perception_io import MODES, pinned, sha, write
from scripts.phase7.frozen_vision import object_pose

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker


def measure(frame: RGBDObservation, geometry: dict, mode: Literal["NONE", "SUBPIX"]) -> dict:
    if type(frame) is not RGBDObservation:
        raise TypeError("exact RGB-D observation required")
    reg = PoseMarkerRegistration(**geometry["pose_marker"])
    marker = detect_pose_marker(frame, reg, corner_refinement=mode)
    if (
        marker.observation_checksum_sha256 != frame.checksum_sha256
        or marker.observation_id != frame.frame_id
        or marker.registration_hash != reg.digest()
    ):
        raise ValueError("marker result differs from source observation or geometry")
    pose = object_pose(asdict(marker), geometry)
    top, optical_depth = None, None
    if pose is not None:
        center = np.array(pose["center_world_m"])
        rotation = np.array(pose["rotation_to_world"]).reshape(3, 3)
        top = (center + rotation[:, 2] * geometry["object_half_extent_m"][2]).tolist()
        camera = np.array(frame.camera_to_world).reshape(4, 4)
        optical_depth = float(camera[:3, 2] @ (marker.marker_center_world_m - camera[:3, 3]))
    return {
        "status": marker.status,
        "reason": marker.reason,
        "ids": list(marker.observed_marker_ids),
        "marker_center_world_m": marker.marker_center_world_m,
        "marker_center_optical_depth_m": optical_depth,
        "sampled_marker_center_px": (
            None
            if marker.ordered_corners_px is None
            else np.array(marker.ordered_corners_px).mean(axis=0).tolist()
        ),
        "object_center_world_m": None if pose is None else pose["center_world_m"],
        "rotation_to_world": None if pose is None else pose["rotation_to_world"],
        "object_top_center_world_m": top,
        "min_side_px": marker.measured_min_side_px,
        "effective_depth_bound_m": marker.geometric_error_bound_m,
        "interval_motion_bound_m_s": None,
        "object_stable": marker.stability_status,
    }


def biased_observation(base: RGBDObservation, bias_mm: int | None) -> RGBDObservation:
    if bias_mm is not None and (type(bias_mm) is not int or bias_mm not in {-10, -5, 0, 5, 10}):
        raise ValueError("unallocated optical depth bias")
    depth = np.frombuffer(base64.b64decode(base.depth_float32_base64), dtype="<f4").copy()
    keep = np.frombuffer(base.valid_mask_bytes(), dtype=np.uint8).astype(bool)
    if bias_mm is None:
        depth.fill(0.0)
    else:
        depth[keep] += bias_mm / 1000
        if (depth[keep] <= 0).any():
            raise ValueError("bias would change the original valid mask")
    return RGBDObservation.model_validate(
        {
            **base.model_dump(),
            "frame_id": f"dev-bias-{bias_mm}-{base.checksum_sha256[:32]}",
            "observation_id": "",
            "checksum_sha256": "",
            "valid_mask_base64": None,
            "depth_float32_base64": base64.b64encode(depth.tobytes()).decode("ascii"),
        }
    )


def frame_rows(pixels: Path, index: dict) -> Iterator[tuple[dict, RGBDObservation]]:
    for row in index["frames"]:
        frame = RGBDObservation.model_validate(pinned(pixels / row["file"], row["sha256"]))
        if any(
            getattr(frame, name) != row[name]
            for name in (
                "scene_id",
                "episode_id",
                "frame_id",
                "sim_time_s",
                "checksum_sha256",
                "calibration_version",
            )
        ):
            raise ValueError("frame source metadata differs from its pixel index")
        yield row, frame


def estimate(pixels: Path, index_sha: str, output: Path) -> None:
    index = pinned(pixels / "index.json", index_sha)
    output.mkdir()
    decisions = []
    for row, frame in frame_rows(pixels, index):
        intrinsic = list(frame.intrinsics)
        extrinsic = list(frame.camera_to_world)
        decisions.append(
            {
                **{k: v for k, v in row.items() if k not in {"file", "sha256"}},
                "intrinsics": intrinsic,
                "camera_to_world": extrinsic,
                "modes": {mode: measure(frame, index["geometry"], mode) for mode in MODES},
            }
        )
    write(
        output / "decisions.json",
        {
            "allocation_sha256": index["allocation_sha256"],
            "pixel_index_sha256": index_sha,
            "frames": decisions,
        },
    )
    write(
        output / "estimate-seal.json",
        {
            "pixel_index_sha256": index_sha,
            "allocation_sha256": index["allocation_sha256"],
            "decision_file_sha256": sha(output / "decisions.json"),
            "acquisitions": len(decisions),
            "detector_calls": len(decisions) * len(MODES),
        },
    )


def sensitivity(
    pixels: Path,
    index_sha: str,
    output: Path,
    fallback: Path | None = None,
    fallback_sha: str | None = None,
) -> None:
    index = pinned(pixels / "index.json", index_sha)
    geometry = index["geometry"]
    designated = [
        r
        for r in index["frames"]
        if r["cell_id"] == "graduation-dev-r593-p2-h0-axial" and r["step"] == 0
    ]
    original = None
    if len(designated) == 1:
        (row,) = designated
        original = RGBDObservation.model_validate(pinned(pixels / row["file"], row["sha256"]))
    selection = {
        "allocated_input": "graduation-dev-r593-p2-h0-axial/step-0",
        "allocated_source_file_sha256": designated[0]["sha256"] if designated else None,
        "allocated_subpix_status": None
        if original is None
        else measure(original, geometry, "SUBPIX")["status"],
        "source": "development_grid",
    }
    if original is None or selection["allocated_subpix_status"] != "OBSERVED":
        if fallback is None or fallback_sha is None:
            raise ValueError(
                "allocated base unavailable: sealed Phase 7 development fallback required"
            )
        original = RGBDObservation.model_validate(pinned(fallback, fallback_sha))
        selection.update(source="phase7_development_single_frame", fallback_sha256=fallback_sha)
    reference = {mode: measure(original, geometry, mode) for mode in MODES}
    cases = []
    output.mkdir()
    for change in (-10, -5, 0, 5, 10, None):
        derived = biased_observation(original, change)
        if (
            derived.rgb_png_base64 != original.rgb_png_base64
            or derived.calibration_version != original.calibration_version
            or (change is not None and derived.valid_mask_bytes() != original.valid_mask_bytes())
        ):
            raise ValueError("bias changed the image, calibration or valid support")
        name = f"derived-{change}.json"
        with (output / name).open("x") as stream:
            stream.write(derived.model_dump_json())
        for mode in MODES:
            item = measure(derived, geometry, mode)
            if (change == 0 and item != reference[mode]) or (
                change is None and item["status"] != "UNKNOWN"
            ):
                raise ValueError("depth-bias control failed")
            delta = None
            if item["status"] == reference[mode]["status"] == "OBSERVED":
                delta = np.subtract(
                    item["object_top_center_world_m"], reference[mode]["object_top_center_world_m"]
                )
            cases.append(
                {
                    "bias_mm": change,
                    "all_depth_invalid": change is None,
                    "mode": mode,
                    "status": item["status"],
                    "reason": item["reason"],
                    "frame_id": derived.frame_id,
                    "frame_checksum_sha256": derived.checksum_sha256,
                    "file_sha256": sha(output / name),
                    "valid_pixels": derived.valid_mask_bytes().count(1),
                    "top_center_delta_world_xyz_m": None if delta is None else delta.tolist(),
                    "top_center_delta_3d_m": None
                    if delta is None
                    else float(np.linalg.norm(delta)),
                }
            )
    write(
        output / "summary.json",
        {
            "source_binding": {
                **selection,
                "frame_id": original.frame_id,
                "source_checksum_sha256": original.checksum_sha256,
                "rgb_png_sha256": hashlib.sha256(
                    base64.b64decode(original.rgb_png_base64)
                ).hexdigest(),
                "calibration_version": original.calibration_version,
            },
            "scope": "DERIVED_OPTICAL_DEPTH_PERTURBATION",
            "cases": cases,
            "allocated": 12,
            "observed": sum(r["status"] == "OBSERVED" for r in cases),
            "unavailable": sum(r["status"] == "UNKNOWN" for r in cases),
            "base_detector_results": reference,
            "certified_sensor_error_bound_m": None,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("estimate", "sensitivity"))
    parser.add_argument("--pixels", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fallback", type=Path)
    parser.add_argument("--fallback-sha256")
    args = parser.parse_args()
    if args.command == "estimate":
        estimate(args.pixels, args.index_sha256, args.output)
    else:
        sensitivity(
            args.pixels, args.index_sha256, args.output, args.fallback, args.fallback_sha256
        )


if __name__ == "__main__":
    main()
