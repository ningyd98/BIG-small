"""Read only anonymous RGB-D packets and the installation's registered camera/geometry."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scripts.graduation.dynamic_vision_score import frame_from_row
from scripts.graduation.perception_io import pinned, sha, write
from scripts.graduation.perception_pixels import measure

from cloud_edge_robot_arm.research.native_collection_grounding import (
    geometry_registration,
    validate_camera,
)
from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp


def checked_geometry(geometry):
    original = geometry_registration(marker_family_id=geometry["marker_family"])
    if geometry != original or geometry["camera"]["calibration_version"] != "f33940579c533afe":
        raise ValueError("geometry differs from the native fixed-camera asset registration")
    return geometry


def measure_packet(frame, geometry):
    validate_camera(frame, geometry)
    estimate = measure(frame, geometry, "SUBPIX")
    default = measure(frame, geometry, "NONE")
    diagnostics = {}
    try:
        point, marker = measure_registered_marker_grasp(
            frame, geometry["marker_family"], diagnostics=diagnostics
        )
        reason = marker.reason
        grasp = point.tolist() if point is not None else None
    except ValueError as exc:
        reason, grasp = str(exc), None
    patches = [d["median_optical_depth_m"] for d in diagnostics.get("depth_samples", [])]
    if any(not np.isfinite(d) or d <= 0 for d in patches):
        raise ValueError("nonpositive measured optical depth")
    return {
        "estimate": estimate,
        "default": default,
        "servo_grasp_world_m": grasp,
        "servo_reason": reason,
        "subpix_depth_patches": len(patches),
        "subpix_optical_depths_m": patches,
        "captured_at": frame.captured_at.isoformat(),
        "sim_time_s": frame.sim_time_s,
    }


def read_set(directory, bundle):
    if set(bundle) != {"episode", "scene", "geometry", "frames"}:
        raise ValueError("unregistered fields in pixel-only set")
    geometry = checked_geometry(bundle["geometry"])
    decisions = []
    seen = set()
    for i, source in enumerate(bundle["frames"]):
        if set(source) != {"file", "file_sha256", "checksum_sha256", "physics_step", "frame_id"}:
            raise ValueError("unregistered fields in pixel-only packet")
        if source["frame_id"] in seen:
            raise ValueError("duplicate RGB-D acquisition")
        if source["file"] != f"{i:04d}.json":
            raise ValueError("pixel packet does not occupy its anonymous ordinal")
        frame = frame_from_row(directory, source, bundle["episode"], bundle["scene"], geometry)
        decisions.append(
            {
                **{
                    k: source[k]
                    for k in ("frame_id", "checksum_sha256", "physics_step", "file_sha256")
                },
                **measure_packet(frame, geometry),
            }
        )
        seen.add(frame.frame_id)
    return decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("digest")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    datasets = pinned(args.index, args.digest)
    seen_ids, episodes, seals = set(), set(), {}
    args.out.mkdir()
    for token, bundle in datasets.items():
        if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise ValueError("invalid anonymous set identity")
        if bundle["episode"] in episodes:
            raise ValueError("duplicate episode across RGB-D sets")
        rows = read_set(args.index.parent / token, bundle)
        ids = {r["frame_id"] for r in rows}
        if seen_ids & ids:
            raise ValueError("duplicate packet across RGB-D sets")
        seen_ids.update(ids)
        episodes.add(bundle["episode"])
        path = args.out / (token + ".json")
        write(path, {"token": token, "packets": rows})
        seals[token] = sha(path)
    write(
        args.out / "seal.json",
        {
            "inputs_sha256": args.digest,
            "decisions_sha256": seals,
            "packet_count": len(seen_ids),
            "reader_sha256": sha(Path(__file__)),
        },
    )


if __name__ == "__main__":
    main()
