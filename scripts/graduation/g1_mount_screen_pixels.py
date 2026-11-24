"""Decide anonymous sealed RGB-D frames under each attachment, with no role or simulator input."""

from __future__ import annotations

import numpy as np
from scripts.graduation import proposal_camera as cam
from scripts.graduation.g1_mount_geometry import require, verify_target
from scripts.graduation.perception_io import pinned, read, sha, write
from scripts.graduation.perception_pixels import measure

from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp


def estimate(f, g):
    results = {mode: measure(f, g, mode) for mode in ("NONE", "SUBPIX")}
    diagnostics = {}
    full = detect_pose_marker(
        f,
        PoseMarkerRegistration(**g["pose_marker"]),
        corner_refinement="SUBPIX",
        diagnostics=diagnostics,
    )
    try:
        grasp, marker = measure_registered_marker_grasp(f, g["marker_family"])
        reason = marker.reason
    except ValueError as exc:
        grasp, reason = None, str(exc)
    target = None
    if grasp is not None:
        target = verify_target(g, full.marker_center_world_m, full.rotation_marker_to_world, grasp)
        require(target["upright_zz"] >= 0.98, "upright gate mismatch")
    e = results["SUBPIX"]
    wrong_id = detect_pose_marker(
        f,
        PoseMarkerRegistration(**{**g["pose_marker"], "marker_id": 8}),
        corner_refinement="SUBPIX",
    )
    return {
        "estimates": results,
        "ordered_subpix_corners_px": full.ordered_corners_px,
        "marker_rotation_row_major": full.rotation_marker_to_world,
        "upright_zz": None
        if full.rotation_marker_to_world is None
        else float(np.asarray(full.rotation_marker_to_world).reshape(3, 3)[2, 2]),
        "subpix_depth_samples": diagnostics.get("depth_samples", []),
        "wrong_id8": {
            "status": wrong_id.status,
            "reason": wrong_id.reason,
            "observed_ids": list(wrong_id.observed_marker_ids),
        },
        "grasp_world_m": None if grasp is None else grasp.tolist(),
        "grasp_reason": reason,
        "independent_target": target,
        "usable": bool(
            cam.valid(e) and e["marker_center_optical_depth_m"] > 0 and target is not None
        ),
    }


def decide(raw, allocation_sha):
    seal = read(raw / "capture-seal.json")
    pixels = raw / "pixels"
    index = pinned(pixels / "index.json", seal["index_sha256"])
    require(
        index["allocation_sha256"] == seal["allocation_sha256"] == allocation_sha,
        "crossed blind frame index",
    )
    results = {}
    for key, row in sorted(index["frames"].items()):
        f = cam.load_frame(pixels, row)
        results[key] = {
            "frame_sha256": row["sha256"],
            "checksum": f.checksum_sha256,
            "frame_id": f.frame_id,
            "by_mount": {name: estimate(f, g) for name, g in index["hypotheses"].items()},
        }
    write(
        raw / "blind-decisions.json",
        {
            "allocation_sha256": allocation_sha,
            "index_sha256": seal["index_sha256"],
            "results": results,
        },
    )
    write(
        raw / "decision-seal.json",
        {
            "capture_sha256": sha(raw / "capture-seal.json"),
            "decisions_sha256": sha(raw / "blind-decisions.json"),
        },
    )
