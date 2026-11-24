"""Read anonymous raw RGB-D packets and their rigid marker registration without trial results."""

from __future__ import annotations

import argparse
import math
from contextlib import nullcontext
from pathlib import Path

import numpy as np
from scripts.graduation.dynamic_vision_score import frame_from_row
from scripts.graduation.g1_mount_score_blind import measure_packet
from scripts.graduation.perception_io import pinned, sha, write


def rigid_points(marker_center, rotation, marker_id):
    offsets = {7: (0, 0.100, 0.03505), 8: (0.100, 0, 0.03505)}
    if marker_id not in offsets:
        raise ValueError("marker is outside the frozen two-attachment register")
    rot = np.reshape(rotation, (3, 3))
    obj = np.asarray(marker_center) - rot @ offsets[marker_id]
    return obj, obj + 0.035 * rot[:, 2], obj + 0.010 * rot[:, 2]


def dual_read(frame, geometry):
    from scripts.graduation.g1_dual_observer import measure_frame

    result = measure_frame(frame, geometry)
    if result["frame_id"] != frame.frame_id or not set(result["usable_ids"]) <= {7, 8}:
        raise ValueError("dual readback differs from original packet or registered identity")
    per_id = {}
    for marker in result["usable_ids"]:
        measure = result["by_id"][str(marker)]
        obj, top, tcp = rigid_points(
            measure["marker_center_world_m"], measure["rotation_marker_to_world"], marker
        )
        per_id[str(marker)] = {
            "center_m": obj.tolist(),
            "top_m": top.tolist(),
            "tcp_m": tcp.tolist(),
        }
    selected = result["selected_id"]
    if result["usable"]:
        if selected not in result["usable_ids"] or len(result["observed_ids"]) != len(
            set(result["observed_ids"])
        ):
            raise ValueError("selected marker is not uniquely identified on this frame")
        if len(per_id) == 2:
            separation = np.linalg.norm(np.subtract(per_id["7"]["tcp_m"], per_id["8"]["tcp_m"]))
            if separation > 0.01 or selected != 7:
                raise ValueError("dual arbitration differs from registered agreement and priority")
        for key, field in (
            ("object_center_world_m", "center_m"),
            ("object_top_world_m", "top_m"),
            ("grasp_world_m", "tcp_m"),
        ):
            if not np.allclose(result[key], per_id[str(selected)][field], rtol=0, atol=1e-10):
                raise ValueError(
                    "command geometry differs from independent marker to object transform"
                )
    elif selected is not None:
        raise ValueError("rejected frame supplied a target")
    return {
        "usable": result["usable"],
        "reason": result["reason"],
        "observed_ids": result["observed_ids"],
        "usable_ids": result["usable_ids"],
        "selected_id": selected,
        "per_id": per_id,
        "top_m": result["object_top_world_m"] if result["usable"] else None,
        "tcp_m": result["grasp_world_m"] if result["usable"] else None,
    }


def single_read(frame, geometry):
    packet = measure_packet(frame, geometry)
    est = packet["estimate"]
    valid = packet["servo_grasp_world_m"] is not None
    per_id = {}
    if valid:
        if (
            est["ids"] != [7]
            or packet["subpix_depth_patches"] != 5
            or not 0 < est["marker_center_optical_depth_m"] < math.inf
        ):
            raise ValueError(
                "single-marker accepted packet lacks identity or original metric depth"
            )
        obj, top, tcp = rigid_points(est["marker_center_world_m"], est["rotation_to_world"], 7)
        if not np.allclose(tcp, packet["servo_grasp_world_m"], rtol=0, atol=1e-10):
            raise ValueError("single-marker original TCP differs from independent reconstruction")
        per_id["7"] = {"center_m": obj.tolist(), "top_m": top.tolist(), "tcp_m": tcp.tolist()}
    return {
        "usable": valid,
        "reason": packet["servo_reason"],
        "observed_ids": est["ids"],
        "usable_ids": [7] if valid else [],
        "selected_id": 7 if valid else None,
        "per_id": per_id,
        "top_m": per_id["7"]["top_m"] if valid else None,
        "tcp_m": packet["servo_grasp_world_m"],
    }


def read_images(index, digest, output):
    packets = pinned(index, digest)
    output.mkdir()
    seals, frame_ids = {}, set()
    for token, bundle in packets.items():
        fields = {"episode", "scene", "mode", "geometry", "frames"}
        if len(token) != 64 or set(bundle) not in (fields, fields | {"registered_scene"}):
            raise ValueError("unexpected input in blind package")
        expected = bundle.get("registered_scene", "S01_NORMAL_STATIC")
        if not isinstance(expected, str) or not expected or bundle["scene"] != expected:
            raise ValueError("blind input lacks the registered scene or names a different scene")
        if bundle["mode"] not in ("dual", "original"):
            raise ValueError("unknown capture installation")
        context = nullcontext()
        if "registered_scene" in bundle:
            from scripts.graduation.g1_formal_runtime import bind_scene

            context = bind_scene(expected)
        with context:
            rows = []
            for i, source in enumerate(bundle["frames"]):
                if source["file"] != f"{i:04d}.json" or source["frame_id"] in frame_ids:
                    raise ValueError("reordered or duplicated anonymous frame")
                f = frame_from_row(
                    index.parent / token, source, bundle["episode"], expected, bundle["geometry"]
                )
                observed = (dual_read if bundle["mode"] == "dual" else single_read)(
                    f, bundle["geometry"]
                )
                rows.append(
                    {
                        **observed,
                        "frame_id": f.frame_id,
                        "checksum_sha256": f.checksum_sha256,
                        "time": f.sim_time_s,
                        "captured_at": f.captured_at.isoformat(),
                        "physics_step": source["physics_step"],
                        "file_sha256": source["file_sha256"],
                    }
                )
                frame_ids.add(f.frame_id)
        path = output / (token + ".json")
        write(path, rows)
        seals[token] = sha(path)
    write(
        output / "seal.json", {"index_sha256": digest, "packets": seals, "n_frames": len(frame_ids)}
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("digest")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    read_images(args.index, args.digest, args.output)
