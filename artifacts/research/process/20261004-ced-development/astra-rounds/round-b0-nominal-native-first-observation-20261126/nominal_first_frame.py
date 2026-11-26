"""Capture and read one local nominal B0 frame without a model or motion."""

import argparse
import fcntl
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from unittest.mock import patch

import mujoco
import numpy as np
from OpenGL import GL
from PIL import Image

from cloud_edge_robot_arm.research.freeze_evidence import _read_frame
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.planner import VisualDecision, _target_relief_above_local_support
from cloud_edge_robot_arm.vision.top_grasp import matches_calibrated_gripper, resolve_top_grasp
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
PLAN = json.loads((HERE / "plan.json").read_bytes())
OLD = ROOT / PLAN["old_root"] / PLAN["old_registered_slot"]
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def require(predicate, reason):
    if not predicate:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight():
    for name, expected in PLAN["sources_sha256"].items():
        require(sha(ROOT / name) == expected, f"changed source: {name}")
    manifest = ROOT / PLAN["manifest"]
    require(sha(manifest) == PLAN["manifest_sha256"], "old manifest changed")
    files = read(manifest)["files"]
    require(len(files) == 47, "incomplete nominal originals")
    for name, metadata in files.items():
        path = OLD.parent / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(OLD.parent)
            and sha(path) == metadata["sha256"],
            "old evidence drifted",
        )
    report = read(OLD / "attempt.json")
    require(
        report["request_sha256"] == sha(OLD / "request.raw")
        and report["response_sha256"] == sha(OLD / "response.raw"),
        "original wire bytes fail to join",
    )
    frame = _read_frame(OLD)
    wire = read(OLD / "response.raw")["choices"][0]["message"]["content"]
    decision = VisualDecision.model_validate_json(wire)
    fields = report["observation_evidence"]
    require(
        frame.observation.checksum_sha256 == fields["checksum_sha256"]
        and fields["scene_id"] == PLAN["scene"]
        and fields["grasp_profile"] == PLAN["profile"],
        "historical groundings have the wrong frame or profile",
    )
    return frame, decision, fields


def capture(output):
    captures = Counter()
    sensor_capture = MuJoCoRGBDCamera._capture

    def observed(camera, data, **settings):
        role = (
            "explicit_rgb_depth_instances"
            if settings["include_instances"]
            else "implicit_rgb_depth"
        )
        require(captures[role] == 0, f"additional acquisition: {role}")
        captures[role] += 1
        return sensor_capture(camera, data, **settings)

    def deny(*args, **kwargs):
        raise RuntimeError("nominal static capture attempted an integration")

    config = SimulatorConfig(
        camera_width=320,
        camera_height=240,
        render_rgb=True,
        render_depth=True,
        domain_randomization=False,
        seed=PLAN["seed"],
    )
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(parents=True, exist_ok=False)
        with (
            patch.object(MuJoCoRGBDCamera, "_capture", observed),
            patch.multiple(mujoco, mj_step=deny, mj_step1=deny, mj_step2=deny),
            MuJoCoCaptureSession(config) as session,
        ):
            backend = session._backend
            require(
                backend.total_physics_steps == 0
                and backend.get_sim_time() == 0.0
                and matches_calibrated_gripper(backend._model, PLAN["profile"]),
                "reset does not resolve the registered gripper and clock",
            )
            renderer = GL.glGetString(GL.GL_RENDERER).decode()
            require("NVIDIA GeForce RTX 4070 Ti SUPER" in renderer, "unregistered renderer")
            before = MuJoCoRGBDCamera._physics_state_hash(backend._data)
            frame = session.capture_with_instances()
            require(
                before
                == frame.physics_state_hash
                == MuJoCoRGBDCamera._physics_state_hash(backend._data)
                and set(frame.pass_state_hashes) == {before}
                and frame.observation.sim_time_s == 0.0
                and len(frame.pass_state_hashes) == 3
                and frame.observation.scene_id == PLAN["scene"]
                and captures == {"implicit_rgb_depth": 1, "explicit_rgb_depth_instances": 1},
                "unexpected reset or explicit exposure lineage",
            )
            save_captured_frame(frame, output)
        (output / "capture.json").write_text(
            json.dumps(
                {
                    "counts": dict(captures),
                    "sim_time_s": 0.0,
                    "integrations": 0,
                    "mujoco_version": mujoco.__version__,
                    "renderer": renderer,
                    "reset": 1,
                    "gripper_geometry_matched": True,
                    "source_files": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )


def image(directory):
    return np.asarray(Image.open(io.BytesIO((directory / "rgb.png").read_bytes())))


def paired(new, old):
    candidate = _read_frame(new)
    receipt = read(new / "capture.json")
    require(receipt["gripper_geometry_matched"] and receipt["integrations"] == 0, "bad capture")
    for name, digest in receipt["source_files"].items():
        require(sha(new / name) == digest, "new original drifted")
    baseline = old.observation
    current = candidate.observation
    comparisons = {
        "rgb_decoded_exact": np.array_equal(image(OLD), image(new)),
        "depth_exact": (OLD / "depth.f32").read_bytes() == (new / "depth.f32").read_bytes(),
        "mask_exact": current.valid_mask_bytes() == baseline.valid_mask_bytes(),
        "instance_labels_and_pixels_exact": (
            candidate.instance_labels == old.instance_labels
            and candidate.instance_ids == old.instance_ids
        ),
        "camera_and_sim_time_exact": all(
            getattr(current, key) == getattr(baseline, key)
            for key in (
                "intrinsics",
                "camera_to_world",
                "calibration_version",
                "sim_time_s",
                "scene_id",
            )
        ),
        "physics_and_pass_hashes_exact": (
            candidate.physics_state_hash == old.physics_state_hash
            and candidate.pass_state_hashes == old.pass_state_hashes
        ),
    }
    require(
        current.frame_id != baseline.frame_id and current.episode_id != baseline.episode_id,
        "stale frame",
    )
    return current, comparisons


def optics(observation, wire, historic):
    pixels = [
        model_to_observation_pixel(
            p, observation, image_size=(320, 240), coordinate_system=historic["coordinate_system"]
        )
        for p in (wire.target_pixel, wire.destination_pixel)
    ]
    require(
        [list(p) for p in pixels]
        == [historic["original_pixel_target"], historic["original_pixel_destination"]],
        "historic mapping differs",
    )
    relief, support = _target_relief_above_local_support(observation, pixels[0])
    grasp = resolve_top_grasp(observation, pixels[0], support)
    geometry = {}
    tracker = OpenCVTargetTracker._inspect_frozen_geometry(
        observation,
        dict(
            original_pixel_target=pixels[0],
            original_pixel_destination=pixels[1],
            top_grasp_support_height_m=support,
        ),
        geometry,
    )
    return {
        "pixels": pixels,
        "support_m": support,
        "relief_m": relief,
        "center_m": grasp["estimated_object_center"],
        "grasp_tcp_m": grasp["resolved_top_grasp_tcp"],
        "top_patch_span_m": grasp["top_patch_world_z_span_m"],
        "tracker_center_m": tracker.initial["center"],
        "target_status": geometry["target"]["status"],
        "destination_status": geometry["destination"]["status"],
    }


def algebra(directory, wire):
    meta = read(directory / "observation.json")
    rgb = image(directory)
    w, h = meta["width"], meta["height"]
    ids = np.fromfile(directory / "instance_geom_ids.i32", dtype="<i4").reshape(h, w)
    depth = np.fromfile(directory / "depth.f32", dtype="<f4").reshape(h, w)
    mask = np.fromfile(directory / "valid_mask.u8", dtype="u1").reshape(h, w)
    require(np.array_equal(mask, depth > 0), "raw depth and validity disagree")
    fx, fy, cx, cy = meta["intrinsics"]
    tf = np.asarray(meta["camera_to_world"]).reshape(4, 4)

    def world(x, y):
        z = float(depth[y, x])
        require(z > 0, "invalid raw depth")
        ray = np.array([(x - cx) / fx, (y - cy) / fy, 1.0])
        return tf[:3, :3] @ (ray * z) + tf[:3, 3]

    points = [
        (min(w - 1, u * w // 1000), min(h - 1, v * h // 1000))
        for u, v in (wire.target_pixel, wire.destination_pixel)
    ]
    u, v = points[0]
    base = max(8, round(min(w, h) * 0.05))
    ring = {
        (
            round(u + radius * math.cos(2 * math.pi * k / 24)),
            round(v + radius * math.sin(2 * math.pi * k / 24)),
        )
        for radius in (base, round(1.5 * base), 2 * base)
        for k in range(24)
    }
    floor = [float(world(x, y)[2]) for x, y in ring if 0 <= x < w and 0 <= y < h and mask[y, x]]
    require(len(floor) >= 12, "insufficient raw support samples")
    support = median(floor)
    patch_z = [float(world(x, y)[2]) for x in range(u - 1, u + 2) for y in range(v - 1, v + 2)]
    top = world(u, v)
    centre = [float(top[0]), float(top[1]), (float(top[2]) + support) / 2]
    grasp = [*centre[:2], centre[2] + 0.010]
    labels = [meta["instance_labels"][str(ids[y, x])] for x, y in points]
    require(labels == ["object_geom", "target_region_geom"], "original pixel roles were exchanged")
    return {
        "support_m": support,
        "target_center_m": centre,
        "grasp_tcp_m": grasp,
        "top_patch_span_m": max(patch_z) - min(patch_z),
        "pixel_roles": labels,
        "seed_RGB": [rgb[y, x].tolist() for x, y in points],
        "pixel_coordinates": points,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture", "optics", "algebra"))
    parser.add_argument("new", type=Path)
    args = parser.parse_args()
    old, wire, historic = preflight()
    if args.mode == "capture":
        capture(args.new)
        return
    if args.mode == "preflight":
        output = optics(old.observation, wire, historic)
    else:
        fresh, comparisons = paired(args.new, old)
        transferable = all(comparisons.values())
        output = {
            "identity_comparison": comparisons,
            "historical_pixels_transferable": transferable,
        }
        if args.mode == "optics":
            output.update(
                historical=optics(old.observation, wire, historic),
                recaptured=optics(fresh, wire, historic) if transferable else None,
            )
        else:
            output.update(
                historical=algebra(OLD, wire),
                recaptured=algebra(args.new, wire) if transferable else None,
            )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
