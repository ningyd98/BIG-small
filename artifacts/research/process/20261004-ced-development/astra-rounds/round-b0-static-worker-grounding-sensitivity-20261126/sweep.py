"""Read frozen passive B0 images without opening instance or physics inputs."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.research.freeze_evidence import _registered_observation
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.online_intent import validate_grounded_colors
from cloud_edge_robot_arm.vision.planner import _GroundingError, ground_observation
from cloud_edge_robot_arm.vision.top_grasp import CURRENT_GRASP_PROFILE
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / "plan.json").read_bytes())
IMAGE_INPUTS = ("rgb.png", "depth.f32", "valid_mask.u8", "observation.json")
INSTRUCTION = "Move the red block to the green region."


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def seal(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def verify_sources():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["baseline"], "source commit differs")
    for names, directory in (
        (PLAN["public_inputs_sha256"], PLAN["public_input_directory"]),
        (PLAN["source_sha256"], PLAN["source_directory"]),
    ):
        for name, digest in names.items():
            require(sha(Path(directory) / name) == digest, f"source mismatch: {name}")


def validate_frame(row, frame, ref):
    require(
        frame.frame_id == row["frame_id"]
        and frame.checksum_sha256 == row["checksum_sha256"]
        and frame.sim_time_s == row["sim_time_s"],
        "frozen capture identity changed",
    )
    if ref is not None:
        require(
            (
                frame.episode_id,
                frame.scene_id,
                frame.source,
                frame.width,
                frame.height,
                frame.calibration_version,
                frame.intrinsics,
                frame.camera_to_world,
            )
            == (
                ref.episode_id,
                ref.scene_id,
                ref.source,
                ref.width,
                ref.height,
                ref.calibration_version,
                ref.intrinsics,
                ref.camera_to_world,
            ),
            "frozen camera binding changed",
        )


def frames(cap, receipt):
    loaded = []
    metadata = []
    previous_hashes = None
    for row in receipt["frames"]:
        folder = cap / row["folder"]
        hashes = {}
        for name in IMAGE_INPUTS:
            path = folder / name
            hashes[name] = sha(path)
            require(
                hashes[name] == receipt["files_sha256"][str(path.relative_to(cap))],
                "optical file SHA differs",
            )
        payload_hashes = {key: hashes[key] for key in IMAGE_INPUTS[:-1]}
        require(previous_hashes in (None, payload_hashes), "candidate reuse lacks byte equivalence")
        previous_hashes = payload_hashes
        frame = _registered_observation(folder)
        validate_frame(row, frame, loaded[0] if loaded else None)
        metadata.append(row | {"files_sha256": hashes})
        loaded.append(frame)
    require(
        len({f.frame_id for f in loaded}) == len(loaded) == PLAN["design"]["frames"],
        "missing or duplicate scheduled frame",
    )
    return loaded, metadata


def grounded_geometry(frame, request, target, destination):
    geometry = ground_observation(
        request,
        frame,
        target_pixel=target,
        destination_pixel=destination,
        target_label="red block",
        grasp_profile=CURRENT_GRASP_PROFILE,
        evidence={},
    ).evidence
    tracker = OpenCVTargetTracker._inspect_frozen_geometry(frame, geometry, {})
    validate_grounded_colors(
        INSTRUCTION, tracker.target_color.tolist(), tracker.destination_color.tolist()
    )
    region, reason = tracker._geometry(
        frame, tracker.destination_color, target=False, occlusion_geometry=tracker.initial
    )
    require(region is not None, reason)
    return geometry, tracker, region


def canonical_wire(x, y, frame):
    point = (
        (1000 * x + frame.width - 1) // frame.width,
        (1000 * y + frame.height - 1) // frame.height,
    )
    require(
        model_to_observation_pixel(point, frame, coordinate_system="normalized_1000") == (x, y),
        "pixel mapping does not round trip",
    )
    return point


def reject(label, call, expected):
    try:
        call()
    except ValueError as error:
        require(str(error) == expected, f"wrong negative-control failure for {label}: {error}")
        return label, str(error)
    raise ValueError(f"negative accepted: {label}")


def collect():
    root = Path(PLAN["private_input_directory"])
    optical_inputs = ["rgb-seeds.json", "capture/receipt.json"]
    for name in optical_inputs:
        require(
            sha(root / name) == PLAN["private_inputs_sha256"][name], f"source SHA differs: {name}"
        )
    seeds = read(root / "rgb-seeds.json")
    receipt = read(root / "capture/receipt.json")
    records, metadata = frames(root / "capture", receipt)
    ref = records[0]
    request = InitialPlanningRequest(
        request_id="offline-b0-sensitivity", user_instruction=INSTRUCTION, observation=ref
    )
    target = tuple(seeds["target"]["pixel"])
    destination = tuple(seeds["destination"]["pixel"])
    require(
        list(target) == PLAN["design"]["original_target_pixel"]
        and list(destination) == PLAN["design"]["fixed_destination_pixel"]
        and metadata[0]["step"] == PLAN["design"]["anchor_step"]
        and seeds["rgb_sha256"] == metadata[0]["files_sha256"]["rgb.png"],
        "frozen anchor or semantic seed differs",
    )
    destination_wire = canonical_wire(*destination, ref)
    _, anchor, _ = grounded_geometry(ref, request, target, destination)
    rows = []
    ys, xs = np.nonzero(anchor.initial["mask"])
    for u, v in zip(xs.tolist(), ys.tolist(), strict=True):
        wire = canonical_wire(u, v, ref)
        row = {"pixel": [u, v], "normalized_1000": list(wire)}
        try:
            original, tracker, region = grounded_geometry(ref, request, (u, v), destination)
        except (_GroundingError, ValueError) as error:
            rows.append(row | {"status": "REJECTED", "reason": str(error)})
            continue
        planner_center = original["estimated_object_center"]
        planner_tcp = original["resolved_top_grasp_tcp"]
        center = tracker.initial["center"]
        offset = planner_tcp["z"] - center[2]
        rows.append(
            row
            | {
                "status": "ACCEPTED",
                "planner_center_m": [planner_center[k] for k in "xyz"],
                "planner_tcp_m": [planner_tcp[k] for k in "xyz"],
                "tracker_top_m": center,
                "initial_tcp_z_offset_m": offset,
                "worker_grasp_input_m": [center[0], center[1], center[2] + offset],
                "worker_region_input_m": region["center"],
                "support_height_m": original["top_grasp_support_height_m"],
                "signed_depth_bound_m": tracker.depth_error_bound_m,
            }
        )
    require(
        any(row["pixel"] == list(target) and row["status"] == "ACCEPTED" for row in rows),
        "original positive rejected",
    )
    negatives = dict(
        (
            reject(
                "wrong_frame",
                lambda: validate_frame(metadata[0], records[1], ref),
                "frozen capture identity changed",
            ),
            reject(
                "wrong_calibration",
                lambda: validate_frame(
                    metadata[0], ref.model_copy(update={"calibration_version": "other"}), ref
                ),
                "frozen camera binding changed",
            ),
            reject(
                "swapped_colors",
                lambda: validate_grounded_colors(
                    INSTRUCTION, anchor.destination_color.tolist(), anchor.target_color.tolist()
                ),
                "observed pixels do not identify the requested target",
            ),
        )
    )
    return {
        "plan_sha256": sha(HERE / "plan.json"),
        "anchor_step": metadata[0]["step"],
        "frame_bindings": metadata,
        "reuse_rule": "RGB, depth and mask identical; camera and frame identities checked",
        "instruction": INSTRUCTION,
        "target_anchor": list(target),
        "destination": list(destination),
        "destination_normalized_1000": list(destination_wire),
        "candidates": rows,
        "negatives": negatives,
        "owner_record_used": False,
    }


def restrict_optical_input(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0])
        raw = Path(PLAN["private_input_directory"]).absolute()
        if path.absolute().is_relative_to(raw):
            require(
                path.name in {*IMAGE_INPUTS, "receipt.json", "rgb-seeds.json"},
                "optical producer requested truth or unregistered inputs",
            )
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise PermissionError("offline optical producer")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    sys.addaudithook(restrict_optical_input)
    verify_sources()
    seal(args.output, collect())


if __name__ == "__main__":
    main()
