"""Bind the two original t01 exposures and test the near-return pixel on CPU."""

import argparse
import base64
import importlib.util
import io
import os
import sys
from collections import Counter
from itertools import combinations, product
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from PIL import Image
from scripts.graduation.dynamic_vision_score import frame_from_row
from scripts.graduation.g1_complete_cv_calibrate import BAND, axial
from scripts.graduation.g1_complete_cv_clearance import depth_changes
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import object_matrix
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
CALIBRATION = REPO / "experiments/results/g1-complete-cv-repair-20261125/calibration-gpu-01"
UV = tuple(PLAN["pixel_uv"])
STEPS = (1840, 1848)
TRIPLES = np.array(list(combinations(range(12), 3)))
SIGNS = np.array(list(product((-1, 1), repeat=3)))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prohibited(*args, **kwargs):
    raise AssertionError("optical readback cannot render or integrate")


def blind_audit(event, args):
    if event == "open" and isinstance(args[0], (bytes, str)):
        file = os.fsdecode(args[0])
        if any(
            s in file
            for s in (
                "offline-truth",
                "stop-readback-",
                "lift-qualification-trace",
                "dense-check",
                "cvfix-e0",
            )
        ):
            raise PermissionError("physical or held-out input is unavailable to the pixel reader")


def verify_inputs(physical):
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen import root")
    for name, expected in PLAN["sha256"].items():
        if not physical and any(
            s in name for s in ("offline-truth", "stop-readback-", "lift-qualification-trace")
        ):
            continue
        path = (REPO / name).resolve()
        require(path.is_relative_to(REPO) and sha(path) == expected, f"input changed: {name}")
    manifest = read(ROOT / "runtime-build.json")
    for name, expected in manifest["runtime_files_sha256"].items():
        require(sha(ROOT / name) == expected, f"locked import or asset changed: {name}")


def verify_exposure(observed, indexed, robot, step, role, camera):
    require(
        indexed["label"] == role["label"] == "LIFT/feedback"
        and observed.model_dump(include=set(camera), mode="json") == camera
        and robot["checksum_sha256"] == observed.checksum_sha256 == indexed["checksum_sha256"]
        and indexed["physics_step"] == role["physics_step"] == robot["physics_step"] == step
        and robot["camera_encoder_sim_time_s"] == observed.sim_time_s == robot["sim_time_s"],
        "wrong exposure/clock/encoder/calibration binding",
    )


def negative_bindings(observed, indexed, robot, step, role, camera, terminal):
    wrong_eye = camera["camera_to_world"].copy()
    wrong_eye[3] += 0.001
    alternatives = (
        (observed, terminal, robot),
        (observed.model_copy(update={"camera_to_world": tuple(wrong_eye)}), indexed, robot),
        (observed, indexed, dict(robot, camera_encoder_sim_time_s=observed.sim_time_s - 1 / 240)),
        (observed.model_copy(update={"calibration_version": "wrong"}), indexed, robot),
    )
    for frame, frame_index, encoder in alternatives:
        try:
            verify_exposure(frame, frame_index, encoder, step, role, camera)
        except ValueError:
            continue
        raise ValueError("wrong optical binding passed a negative control")


def bound_sources():
    receipt = read(RAW / "receipt.json")
    seal = pinned(RAW / "acquisition-seal.json", receipt["capture_sha256"])
    allocation = pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"])
    index = pinned(RAW / "pixel-index.json", seal["index_sha256"])
    run = pinned(RAW / "run.json", seal["run_sha256"])
    local_seal = read(RAW / "local-clearance-seal.json")
    local = pinned(RAW / "local-clearance.json", local_seal["local_clearance_sha256"])
    scene, episode = native_reset_ids(
        pinned(RAW / "reset-observed.json", receipt["reset_sha256"]),
        allocation["case"]["scene_id"],
        receipt["physical_reset"]["episode_id"],
    )
    require(
        scene == index["scene"]
        and episode == index["episode"]
        and index["allocation_sha256"] == receipt["allocation_sha256"]
        and local_seal["acquisition_seal_sha256"] == receipt["capture_sha256"],
        "foreign optical allocation or reset",
    )
    geometry = allocation["geometry"]
    camera = geometry["camera"]
    calibration = pinned(CALIBRATION / "manifest.json", allocation["calibration_sha256"])
    require(calibration["primary_camera"] == camera, "frozen calibration disagrees")
    table = calibration["maps"]["table"]
    table_path = CALIBRATION / table["depth_file"]
    require(sha(table_path) == table["depth_sha256"], "original table map differs")
    reference = np.load(table_path, allow_pickle=False)
    require(reference.shape == (camera["height"], camera["width"]), "table map size")
    sources = {}
    for step in STEPS:
        (indexed,) = [
            r for r in index["frames"] if r["file"] == PLAN["historical_slots"][str(step)]
        ]
        (terminal,) = [
            r for r in index["frames"] if r["file"] == PLAN["historical_slots"]["wrong_role_1848"]
        ]
        require(
            terminal["label"] == "terminal"
            and terminal["frame_id"] != indexed["frame_id"]
            and terminal["physics_step"] == 1848
            and indexed["label"] == "LIFT/feedback",
            "terminal must not substitute for a LIFT exposure",
        )
        (row,) = [
            r
            for r in local["rows"]
            if r["frame_id"] == indexed["frame_id"] and r["phase"] == "FEEDBACK"
        ]
        (role,) = [
            r
            for r in run["frame_roles"]
            if r["frame_id"] == indexed["frame_id"] and r["label"] == "LIFT/feedback"
        ]
        observed = frame_from_row(RAW, indexed, episode, scene, geometry)
        robot = row["robot"]
        verify_exposure(observed, indexed, robot, step, role, camera)
        require(
            row["checksum_sha256"] == indexed["checksum_sha256"] and row["physics_step"] == step,
            "gate evidence and original exposure differ",
        )
        if step == 1848:
            negative_bindings(observed, indexed, robot, step, role, camera, terminal)
        sources[step] = (row, observed, indexed)
    return allocation, seal, reference, sources


def pixel_point(camera, uv, depth):
    fx, fy, cx, cy = camera["intrinsics"]
    u, v = uv
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    return tf[:3, 3] + tf[:3, :3] @ [depth * (u - cx) / fx, depth * (v - cy) / fy, depth]


def pixel_readback(camera, reference, sources):
    output = {}
    u, v = UV
    for step, (row, frame, indexed) in sources.items():
        depth = axial(frame)
        mask = np.frombuffer(frame.valid_mask_bytes(), np.uint8).reshape(depth.shape) > 0
        rgb = np.asarray(
            Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))).convert("RGB")
        )
        near, lost = depth_changes(depth, reference, BAND)
        evidence = row["evidence"]["depth"]
        value = float(depth[v, u])
        point = pixel_point(camera, UV, value)
        claimed = UV in {tuple(uv) for uv in evidence["unmatched_pixels_uv"]}
        require(
            near.sum() == evidence["nearer_returns"]
            and lost.sum() == evidence["lost_or_farther_static"],
            "CPU near/far counts disagree with the frozen gate",
        )
        if step == 1848:
            expected = evidence["unmatched_world_m"][0]
            require(
                row["status"] == "BLOCKED"
                and row["reason"] == "unregistered_near_surface"
                and evidence["unknown_pixels"] == 1
                and claimed
                and near[v, u]
                and np.array_equal(point.round(5), expected)
                and not np.array_equal(pixel_point(camera, (v, u), value).round(5), expected),
                "first refusal or original pixel-axis control differs",
            )
        output[str(step)] = {
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "file_sha256": indexed["file_sha256"],
            "gate_status": row["status"],
            "gate_reason": row["reason"],
            "depth_m": value,
            "empty_table_depth_m": float(reference[v, u]),
            "world_point_m": point.tolist(),
            "RGB": rgb[v, u].tolist(),
            "valid": bool(mask[v, u]),
            "near_count": int(near.sum()),
            "unmatched_count": evidence["unknown_pixels"],
            "unmatched_here": claimed,
            "adjacent_depth_and_valid": [
                [x, y, float(depth[y, x]), bool(mask[y, x])]
                for x, y in ((u - 1, v), (u + 1, v), (u, v - 1), (u, v + 1))
            ],
        }
    return output


def original_rays():
    path = HERE.parent / "round-g1-same-view-needle-sampling-20261126/rays.py"
    spec = importlib.util.spec_from_file_location("registered_camera_rays", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cast_pixel(helper, model, data, optical, camera):
    eye = optical[:3, 3].copy()
    groups = mujoco.MjvOption().geomgroup.copy()
    offsets = [
        (0, 0),
        *product((-0.5, 0.5), repeat=2),
        *product((-0.375, -0.125, 0.125, 0.375), repeat=2),
    ]
    samples = []
    for du, dv in offsets:
        xy = (UV[0] + du, UV[1] + dv)
        ray = helper.original_ray(xy, optical, camera)
        hit = helper.first_return(model, data, eye, ray, groups)
        ray_length = np.linalg.norm(ray)
        surfaces = {}
        for name in ("right_finger_geom", "table"):
            g, pose = model.geom(name), data.geom(name)
            distance = mujoco.mju_rayGeom(
                pose.xpos, pose.xmat, g.size, eye, ray / ray_length, g.type[0]
            )
            if distance >= 0:
                surfaces[name] = float(distance / ray_length)
        hit["finger_and_table_axial_m"] = sorted(surfaces.items(), key=lambda item: item[1])
        if hit["geom"]:
            g, pose = model.geom(hit["geom"]), data.geom(hit["geom"])
            if g.type[0] == mujoco.mjtGeom.mjGEOM_BOX:
                rotation = pose.xmat.reshape(3, 3)
                local = (eye + hit["axial_m"] * ray - pose.xpos) @ rotation
                faces = np.flatnonzero(abs(abs(local) - g.size) < 1e-9)
                if len(faces) == 1:
                    axis = faces[0]
                    hit["world_normal"] = (np.sign(local[axis]) * rotation[:, axis]).tolist()
        samples.append(dict(hit, uv=list(xy)))
    return samples


def cone_planes(camera, depth_low, depth_high):
    fx, fy, cx, cy = camera["intrinsics"]
    left, right = (np.asarray([UV[0] - 0.5, UV[0] + 0.5]) - cx) / fx
    upper, lower = (np.asarray([UV[1] - 0.5, UV[1] + 0.5]) - cy) / fy
    return (
        np.array(
            [[1, 0, -right], [-1, 0, left], [0, 1, -lower], [0, -1, upper], [0, 0, 1], [0, 0, -1]]
        ),
        np.array([0, 0, 0, 0, depth_high, -depth_low]),
    )


def box_cone_overlap(center, rotation, half, optical, planes):
    a, b = planes
    eye, camera_axes = optical[:3, 3], optical[:3, :3]
    local_center = (center - eye) @ camera_axes
    axes = camera_axes.T @ rotation
    corners = local_center + (SIGNS * half) @ axes.T
    if ((corners @ a.T).min(axis=0) > b + 1e-10).any():
        return False
    a = np.vstack((a, axes.T, -axes.T))
    b = np.r_[b, half + axes.T @ local_center, half - axes.T @ local_center]
    tests = a[TRIPLES]
    nonsingular = abs(np.linalg.det(tests)) > 1e-11
    vertices = np.linalg.solve(tests[nonsingular], b[TRIPLES[nonsingular], None])[..., 0]
    return bool((vertices @ a.T <= b + 1e-10).all(axis=1).any())


def stop_overlap(asset, optical, camera, pixel):
    stopped = REPO / PLAN["stop_archive"]
    stop_summary = read(stopped.parent / "result.json")
    require(
        stop_summary["branches"][stopped.name] == sha(stopped)
        and stop_summary["first_uncovered"]["tick"] == 1840
        and stop_summary["trace_sha256"] == sha(RAW.parent / "lift-qualification-trace.json"),
        "foreign stop archive",
    )
    motion = MotionGeometry(Model(asset))
    with np.load(stopped, allow_pickle=False) as z:
        q = z["q"]
    require(q.shape == (241, 16), "incomplete 1840 hold/stop geometry")
    centers, rotations, _, _ = motion.solids(q[:, :7], q[:, 7:9], q[:, 9:12], object_matrix(q))
    z = pixel["depth_m"]
    depth_ranges = {
        "measured_axis_depth_band": [z - BAND, z + BAND],
        "in_front_of_measured_band": [0.01, z - BAND],
        "behind_measured_band_to_table": [z + BAND, pixel["empty_table_depth_m"] + BAND],
    }
    hits = {}
    for region, interval in depth_ranges.items():
        planes = cone_planes(camera, *interval)
        hits[region] = {}
        for j, name in enumerate(motion.names):
            supported = [
                i
                for i in range(len(q))
                if box_cone_overlap(
                    centers[i, j], rotations[i, j], motion.sizes[j], optical, planes
                )
            ]
            if supported:
                hits[region][name] = supported
    return {
        "stop_source_step": 1840,
        "delay": 0,
        "optical_exposure_step": 1848,
        "discrete_intersections": hits,
        "depth_bands_m": depth_ranges,
        "continuous_sweep_coverage": False,
        "is_actual_1848_stop": False,
    }


def geometry_readback(allocation, seal, sources, pixels):
    truth = pinned(RAW / "offline-truth.json", seal["truth_sha256"])["samples"]
    asset = ROOT / allocation["case"]["asset_path"]
    require(sha(asset) == allocation["asset_sha256"], "candidate asset differs")
    model = mujoco.MjModel.from_xml_path(str(asset))
    helper = original_rays()
    camera = allocation["geometry"]["camera"]
    readbacks = {}
    for step, (row, frame, _) in sources.items():
        label = truth[step]
        require(
            frame.sim_time_s == label["sim_time_s"] and frame.episode_id == label["episode_id"],
            "physical label lacks the original clock",
        )
        data, optical = helper.restore(
            model, dict(robot=row["robot"], physical=label, time_s=frame.sim_time_s), camera
        )
        tcp = data.site("tcp")
        pos_error = np.linalg.norm(tcp.xpos - row["robot"]["tcp_position_m"])
        archived_rotation = np.empty(9)
        mujoco.mju_quat2Mat(archived_rotation, np.asarray(row["robot"]["tcp_quaternion_wxyz"]))
        rotation_error = np.linalg.norm(tcp.xmat - archived_rotation)
        require(pos_error <= 1e-9 and rotation_error <= 1e-9, "exposure TCP failed restoration")
        rays = cast_pixel(helper, model, data, optical, camera)
        readbacks[str(step)] = {
            "tcp_position_error_m": float(pos_error),
            "tcp_rotation_error_frobenius": float(rotation_error),
            "center": rays[0],
            "first_surfaces_4x4": dict(Counter(r["geom"] for r in rays[5:])),
            "rays": rays,
        }
    return {
        "frames": readbacks,
        "stop_pixel_cone": stop_overlap(asset, optical, camera, pixels["1848"]),
        "static_capture_admitted": False,
        "reason": (
            "Original per-geometry exposure poses and a fixed physical positive/challenge pair "
            "are not registered. Continuous empty-space coverage is unverified."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("pixels", "geometry"))
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    physical = args.step == "geometry"
    if not physical:
        sys.addaudithook(blind_audit)
    verify_inputs(physical)
    allocation, seal, reference, sources = bound_sources()
    path = OUT / args.reader / f"{args.step}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with patch.multiple(
        mujoco,
        Renderer=prohibited,
        mjr_render=prohibited,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
    ):
        pixels = pixel_readback(allocation["geometry"]["camera"], reference, sources)
        if physical:
            require(pixels == read(path.with_name("pixels.json"))["result"], "pixel seal differs")
            result = geometry_readback(allocation, seal, sources, pixels)
        else:
            result = pixels
    write(
        path,
        dict(result=result, plan_sha256=sha(HERE / "plan.json"), source_sha256=sha(Path(__file__))),
    )


if __name__ == "__main__":
    main()
