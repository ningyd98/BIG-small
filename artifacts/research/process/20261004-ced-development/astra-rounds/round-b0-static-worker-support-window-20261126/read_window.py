"""Select RGB-only seeds, then independently read vision and passive physics."""

import argparse
from functools import partial
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from support_window import PLAN, read, require, sha, write

from cloud_edge_robot_arm.research.freeze_evidence import _read_frame, _registered_observation
from cloud_edge_robot_arm.vision.planner import _target_relief_above_local_support
from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


def color_seed(path, color):
    limits = PLAN["rgb_only_seed_selection"]
    with Image.open(path) as image:
        red, green, blue = np.array(image.convert("RGB"), dtype=np.int16).transpose(2, 0, 1)
    e = limits["channel_dominance_min"]
    rules = {
        "red": red - np.maximum(green, blue) >= e,
        "green": green - np.maximum(red, blue) >= e,
        "blue": blue - np.maximum(red, green) >= e,
        "yellow": (np.minimum(red, green) - blue >= e) & (abs(red - green) <= 65),
    }
    valid = rules[color] & (np.maximum.reduce((red, green, blue)) >= limits["brightness_min"])
    _, labels, stats, centers = cv2.connectedComponentsWithStats(
        valid.astype(np.uint8), connectivity=8
    )
    candidates = np.flatnonzero(
        (stats[:, cv2.CC_STAT_AREA] >= limits["component_area_min_px"])
        & (stats[:, cv2.CC_STAT_AREA] <= limits["component_area_max_px"])
        & (np.arange(len(stats)) > 0)
    )
    if len(candidates) != 1:
        return {
            "status": "REJECTED",
            "reason": "RGB support is not unique",
            "regions": len(candidates),
        }
    index = candidates[0]
    kernel = np.ones((limits["interior_erosion_kernel"],) * 2, np.uint8)
    y, x = cv2.erode((labels == index).astype(np.uint8), kernel).nonzero()
    if len(x) == 0:
        return {"status": "REJECTED", "reason": "RGB support has no observed interior"}
    nearest = int(np.argmin((x - centers[index, 0]) ** 2 + (y - centers[index, 1]) ** 2))
    return {"status": "ACCEPTED", "pixel": [int(x[nearest]), int(y[nearest])], "regions": 1}


def seed_rgb(path, color):
    return {
        "rgb_sha256": sha(path),
        "declared_target_color": color,
        "target": color_seed(path, color),
        "destination": color_seed(path, "green"),
    }


def joined_receipt(root):
    cap = root / "capture"
    receipt = read(cap / "receipt.json")
    require(
        receipt["status"] == "COMPLETE"
        and receipt["registration_sha256"] == sha(root / "registration.json")
        and [x["step"] for x in receipt["frames"]] == PLAN["registered_window_exposure_steps"],
        "missing frozen exposure coverage",
    )
    return cap, receipt


def observations(root):
    cap, receipt = joined_receipt(root)
    obs = []
    previous_time = None
    for row in receipt["frames"]:
        directory = cap / row["folder"]
        for name in ("observation.json", "rgb.png", "depth.f32", "valid_mask.u8"):
            path = directory / name
            require(
                sha(path) == receipt["files_sha256"][path.relative_to(cap).as_posix()],
                "image drift",
            )
        value = _registered_observation(directory)
        require(
            value.frame_id == row["frame_id"]
            and value.checksum_sha256 == row["checksum_sha256"]
            and value.sim_time_s == row["sim_time_s"]
            and (previous_time is None or value.sim_time_s > previous_time),
            "missing, repeated or shifted observation",
        )
        previous_time = value.sim_time_s
        obs.append(value)
    return receipt["frames"], obs


def vision(root, seeds_path):
    seeds = read(seeds_path)
    require(
        seeds["rgb_sha256"] == sha(root / "capture/step-0120/rgb.png")
        and seeds["declared_target_color"] == read(root / "registration.json")["target_color"],
        "optical seed does not identify this scene/frame",
    )
    index, frames = observations(root)
    result = []
    if any(seeds[name]["status"] != "ACCEPTED" for name in ("target", "destination")):
        result = [
            row | {"status": "REJECTED", "reason": "first RGB seed unavailable"} for row in index
        ]
    else:
        target = tuple(seeds["target"]["pixel"])
        destination = tuple(seeds["destination"]["pixel"])
        _, support = _target_relief_above_local_support(frames[0], target)
        ground = {
            "original_pixel_target": target,
            "original_pixel_destination": destination,
            "top_grasp_support_height_m": support,
        }
        try:
            tracker = OpenCVTargetTracker._inspect_frozen_geometry(frames[0], ground, {})
            first_reason = None
        except ValueError as exc:
            first_reason = str(exc)
        for row, frame in zip(index, frames, strict=True):
            if first_reason is not None:
                result.append(row | {"status": "REJECTED", "reason": first_reason})
                continue
            reason = tracker._binding_reason_at(frame, frame.captured_at)
            target_geo, target_error = tracker._geometry(frame, tracker.target_color, target=True)
            dest_geo, dest_error = tracker._geometry(frame, tracker.destination_color, target=False)
            reason = reason or target_error or dest_error
            if reason is None and (
                not target_geo["mask"][target[1], target[0]]
                or not dest_geo["mask"][destination[1], destination[0]]
            ):
                reason = "original_colour_seed_no_longer_in_support"
            if reason is not None:
                result.append(row | {"status": "REJECTED", "reason": reason})
                continue
            try:
                _, local_support = _target_relief_above_local_support(frame, target)
                grasp = resolve_top_grasp(frame, target, local_support)
            except ValueError as exc:
                result.append(row | {"status": "REJECTED", "reason": str(exc)})
            else:
                result.append(
                    row
                    | {
                        "status": "ACCEPTED",
                        "visible_top_estimate": target_geo["center"],
                        "top_samples": target_geo["top_pixels"],
                        "extent_complete": target_geo["extent_complete"],
                        "measured_center": grasp["estimated_object_center"],
                        "estimated_grasp_tcp": grasp["resolved_top_grasp_tcp"],
                        "support_height_m": local_support,
                        "depth_error_bound_m": tracker.depth_error_bound_m,
                    }
                )
    return {"seeds_sha256": sha(seeds_path), "rows": result, "ground_truth_opened": False}


def physical(root, sealed_vision):
    cap, receipt = joined_receipt(root)
    optical = read(sealed_vision)
    file = cap / "physical.jsonl"
    require(sha(file) == receipt["files_sha256"][file.name], "physical originals changed")
    import json

    states = [json.loads(line) for line in file.read_bytes().splitlines()]
    lo, hi = (
        PLAN["registered_window_exposure_steps"][0],
        PLAN["registered_window_exposure_steps"][-1],
    )
    require(
        [r["step"] for r in states] == list(range(lo, hi + 1)), "physical window missing a tick"
    )
    sim = np.array([row["sim_time_s"] for row in states])
    require(
        np.allclose(np.diff(sim), PLAN["native_step_dt_s"], atol=1e-12, rtol=0)
        and abs(sim[-1] - sim[0] - PLAN["passive_window_sim_s"]) < 1e-9
        and np.all(np.diff([row["monotonic_ns"] for row in states]) > 0),
        "wrong physical clock",
    )
    reg = read(root / "registration.json")
    h = np.asarray(reg["scene"]["scene_parameters"]["target"]["half_size"])
    centers = np.array([row["object_center_m"] for row in states])
    rotations = np.array([row["object_rotation_row_major"] for row in states]).reshape(-1, 3, 3)
    offsets = np.array([[x * h[0], y * h[1], h[2]] for x in (-1, 1) for y in (-1, 1)])
    top_vertices = np.einsum("nij,kj->nki", rotations, offsets) + centers[:, None, :]
    top = centers + rotations[:, :, 2] * h[2]
    support = [
        any(set(pair) == {"object_geom", "table"} for pair in row["contacts"]) for row in states
    ]
    vertex_speed = np.linalg.norm(np.diff(top_vertices, axis=0), axis=2) / np.diff(sim)[:, None]
    j, corner = np.unravel_index(vertex_speed.argmax(), vertex_speed.shape)
    rows = []
    seeds_path = root / "rgb-seeds.json"
    require(sha(seeds_path) == optical["seeds_sha256"], "incorrect independent seed seal")
    seeds = read(seeds_path)
    for opt, frame_index in zip(optical["rows"], receipt["frames"], strict=True):
        require(
            all(opt[k] == frame_index[k] for k in ("step", "frame_id", "checksum_sha256")),
            "wrong optical exposure",
        )
        at = opt["step"] - lo
        require(opt["sim_time_s"] == states[at]["sim_time_s"], "image/physical time mismatch")
        record = {"step": opt["step"], "frame_id": opt["frame_id"], "status": opt["status"]}
        if opt["status"] == "ACCEPTED":
            directory = cap / frame_index["folder"]
            raw_ids = directory / "instance_geom_ids.i32"
            require(
                sha(raw_ids) == receipt["files_sha256"][raw_ids.relative_to(cap).as_posix()],
                "unregistered native labels",
            )
            instance = _read_frame(directory)
            assigned = []
            for role in ("target", "destination"):
                x, y = seeds[role]["pixel"]
                assigned.append(instance.instance_labels[instance.instance_ids[y * 320 + x]])
            require(assigned == ["object_geom", "target_region_geom"], "seed labels swapped")
            estimate = np.array([opt["measured_center"][a] for a in "xyz"])
            record.update(
                offline_seed_roles=assigned,
                center_error_m=float(np.linalg.norm(estimate - centers[at])),
                visible_top_error_m=float(
                    np.linalg.norm(np.array(opt["visible_top_estimate"]) - top[at])
                ),
            )
        else:
            record["reason"] = opt["reason"]
        rows.append(record)
    return {
        "vision_sha256": sha(sealed_vision),
        "states": len(states),
        "simulated_window_s": float(sim[-1] - sim[0]),
        "physical_table_support_states": sum(support),
        "max_center_displacement_from_start_m": float(
            np.linalg.norm(centers - centers[0], axis=1).max()
        ),
        "max_top_displacement_from_start_m": float(np.linalg.norm(top - top[0], axis=1).max()),
        "max_vertex_displacement_from_start_m": float(
            np.linalg.norm(top_vertices - top_vertices[0], axis=2).max()
        ),
        "max_discrete_vertex_speed_m_s": float(vertex_speed[j, corner]),
        "max_vertex_speed_end_tick": lo + int(j) + 1,
        "matched_optical_count": sum(x["status"] == "ACCEPTED" for x in rows),
        "rows": rows,
        "sole_scope": "PASSIVE_DEVELOPMENT_SAMPLE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "vision", "physical"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-color", choices=("red", "blue", "yellow"))
    parser.add_argument("--sealed", type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    result = {
        "seed": partial(seed_rgb, args.input, args.target_color),
        "vision": partial(vision, args.input, args.sealed),
        "physical": partial(physical, args.input, args.sealed),
    }[args.mode]()
    write(args.output, result)


if __name__ == "__main__":
    main()
