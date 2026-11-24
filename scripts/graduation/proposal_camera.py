"""Paired camera observations on eight sealed r593 development states, without dispatch.

Run the four subcommands in order. Only the offline renderer reads the old trajectory;
the detector consumes RGB-D frames and marker registration only. Score joins the seals.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import shutil
from collections import Counter
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import cv2
import mujoco
import numpy as np
from PIL import Image
from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.perception_capture import VIEWS as REGISTERED_VIEWS
from scripts.graduation.perception_capture import optical_transform, validate_camera
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.perception_pixels import measure

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

STEPS = (120, 720, 792, 816, 824, 832, 840, 848)
VIEWS = {"nominal": "axial", "left": "left", "right": "right"}
ARMS = ("visible", "hidden")
OLD_ROUND = "round-graduation-guarded-clock-20261123"
CHECK_LIMITS = {
    "tcp_residual_m": 0.00001,
    "object_center_residual_m": 1e-8,
    "object_rotation_max_abs": 1e-8,
    "rgb_changed_pixel_fraction": 0.0025,
    "valid_mask_disagreement_fraction": 0.005,
    "common_valid_depth_abs_p99_m": 0.006,
}
SOURCE_PATHS = (
    "scripts/graduation/proposal_camera.py",
    "scripts/graduation/perception_capture.py",
    "scripts/graduation/perception_io.py",
    "scripts/graduation/perception_pixels.py",
    "scripts/graduation/dynamic_vision_score.py",
    "scripts/phase7/frozen_vision.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
    "src/cloud_edge_robot_arm/vision/observations.py",
    "src/cloud_edge_robot_arm/vision/pose_markers.py",
)


def valid(e):
    return (
        e["status"] == "OBSERVED"
        and e["ids"] == [7]
        and e["object_top_center_world_m"] is not None
        and e["min_side_px"] is not None
    )


def select_view(normal, verified):
    if set(normal) != set(product(STEPS, VIEWS)) or set(verified) != set(STEPS):
        raise ValueError("camera selection requires every allocated normal frame and state")
    scores = {}
    for v in VIEWS:
        good = [verified[s] and valid(normal[s, v]) for s in STEPS]
        streak = 0
        for ok in reversed(good):
            if not ok:
                break
            streak += 1
        scores[v] = {
            "allocated_steps": len(STEPS),
            "valid_steps": sum(good),
            "terminal_streak": streak,
            "min_valid_side_px": min(
                (normal[s, v]["min_side_px"] for s, ok in zip(STEPS, good, strict=True) if ok),
                default=None,
            ),
        }

    def rank(v):
        m = scores[v]
        return (m["valid_steps"], m["terminal_streak"], m["min_valid_side_px"] or 0.0)

    return max(("nominal", "right", "left"), key=rank), scores


def allocate(raw, plan_path, reference):
    plan = read(plan_path)
    if sha(plan_path.with_suffix(".md")) != plan["plan_md_sha256"]:
        raise ValueError("plan differs from its markdown")
    for name, digest in plan["input_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"changed plan input: {name}")
    old_path = plan_path.parent.parent / OLD_ROUND / "allocation.public.json"
    old = pinned(old_path, plan["input_sha256"][str(old_path.resolve().relative_to(ROOT))])
    seal_path = str(Path(os.path.relpath(reference, ROOT)) / "acquisition-seal.json")
    evidence = pinned(reference / "acquisition-seal.json", plan["input_sha256"][seal_path])
    original = pinned(reference / "pixel-index.json", evidence["index_sha256"])
    if original["allocation_sha256"] != sha(old_path):
        raise ValueError("r2 input index and allocation mismatch")
    original_rows = [
        r
        for r in original["frames"]
        if r["physics_step"] in STEPS
        and (
            r["label"] == "MOVE_ABOVE/feedback"
            or (r["physics_step"], r["label"]) == (848, "terminal")
        )
    ]
    if [r["physics_step"] for r in original_rows if r["label"].endswith("/feedback")] != list(
        STEPS
    ):
        raise ValueError("unavailable original feedback anchor")
    for row in original_rows:
        frame_from_row(reference, row, original["episode"], original["scene"], old["geometry"])
    if os.environ.get("MUJOCO_GL") != "egl" or shutil.disk_usage(raw).free < 2**29:
        raise ValueError("EGL and 512 MiB are required for the paired offline captures")
    geometry = old["geometry"]
    if sha(ROOT / geometry["asset_path"]) != old["asset_sha256"]:
        raise ValueError("r593 marked source changed")
    views = {}
    for name, source in VIEWS.items():
        position, aim = REGISTERED_VIEWS[source]
        views[name] = {
            "position": position,
            "aim": aim,
            "optical_to_world": optical_transform(position, aim).ravel().tolist(),
        }
    write(
        raw / "allocation.json",
        {
            "schema": "proposal.r593.camera-allocation.v1",
            "issued_utc": datetime.now(UTC).isoformat(),
            "plan_sha256": sha(plan_path),
            "baseline": plan["baseline"],
            "reference": seal_path.rsplit("/", 1)[0],
            "reference_seal_sha256": sha(reference / "acquisition-seal.json"),
            "reference_decisions_sha256": plan["input_sha256"][
                str(Path(seal_path).with_name("decisions.json"))
            ],
            "original_rows": original_rows,
            "original_episode": original["episode"],
            "original_scene": original["scene"],
            "r2_allocation_sha256": sha(old_path),
            "steps": list(STEPS),
            "views": views,
            "arm_visibility": ARMS,
            "tie_order": ["nominal", "right", "left"],
            "validation_upper_limits": CHECK_LIMITS,
            "rank": ["valid steps", "terminal streak", "minimum observed side px"],
            "paired_noise": "same per-view/step seed, Gaussian 0.001 m on valid depth",
            "noise_seed_offset": 241124000,
            "old_sensor_noise_m": 0.001,
            "checker": "SUBPIX",
            "pose_source": "named qpos and object geom pose, rendered after mj_forward",
            "geometry": geometry,
            "asset_sha256": old["asset_sha256"],
            "sources_sha256": {
                name: sha(ROOT / name) for name in (*SOURCE_PATHS, geometry["asset_path"])
            },
            "mujoco": mujoco.__version__,
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "no_dynamics_steps": True,
            "formal_claims": 0,
            "model_calls": 0,
        },
    )


def restore(model, data, row):
    """Use the archived generalized positions; FK residuals test geometric reconstruction."""
    mujoco.mj_resetData(model, data)
    joints = [f"joint{i}" for i in range(1, 8)] + ["finger_left_joint", "finger_right_joint"]
    qs = row["joint_positions_rad"] + row["finger_positions_m"]
    vs = row["joint_velocities_rad_s"] + row["finger_velocities_m_s"]
    for j, q, v in zip(joints, qs, vs, strict=True):
        data.qpos[model.joint(j).qposadr[0]] = q
        data.qvel[model.joint(j).dofadr[0]] = v
    obj = model.geom("object_geom")
    if not np.array_equal(obj.pos, [0, 0, 0]) or not np.array_equal(obj.quat, [1, 0, 0, 0]):
        raise ValueError("object geometry is no longer aligned with free body")
    free = model.joint("object_free").qposadr[0]
    data.qpos[free : free + 3] = row["object_position_m"]
    mujoco.mju_mat2Quat(
        data.qpos[free + 3 : free + 7], np.array(row["object_geom_rotation_row_major"])
    )
    data.time = row["sim_time_s"]
    mujoco.mj_forward(model, data)
    return {
        "tcp_residual_m": float(np.linalg.norm(data.site("tcp").xpos - row["tcp_position_m"])),
        "object_center_residual_m": float(
            np.linalg.norm(data.geom("object_geom").xpos - row["object_geom_position_m"])
        ),
        "object_rotation_max_abs": float(
            np.max(np.abs(data.geom("object_geom").xmat - row["object_geom_rotation_row_major"]))
        ),
    }


def arm_geometries(model):
    root = model.body("panda_link0").id
    result = {}
    for i in range(model.ngeom):
        body = int(model.geom_bodyid[i])
        while body and body != root:
            body = int(model.body_parentid[body])
        if body == root:
            result[i] = model.geom(i).name
    if not {"hand", "right_finger_geom", "left_finger_geom"}.issubset(result.values()):
        raise ValueError("r593 robot body geometry incomplete")
    return result


def frame_name(step, view, arm):
    return f"{step}-{view}-{arm}"


def render(raw, a, digest):
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("EGL required")
    ref = ROOT / a["reference"]
    seal = pinned(ref / "acquisition-seal.json", a["reference_seal_sha256"])
    truth = pinned(ref / "offline-truth.json", seal["truth_sha256"])
    states = checked_steps(
        truth["samples"], a["original_episode"], a["asset_sha256"], truth["asset_sha256"]
    )
    dest = raw / "capture"
    dest.mkdir()
    (dest / "pixels").mkdir()
    (dest / "geometry").mkdir()
    index, labels, residuals = {}, {}, {}
    reg = a["geometry"]
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(
            model_path=str(ROOT / reg["asset_path"]),
            seed=241124,
            physics_dt_s=1 / 240,
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
        )
    )
    # Private simulator state is confined to this offline reconstruction.
    model, data = backend._model, backend._data
    camera = MuJoCoRGBDCamera(
        mujoco, model, width=reg["camera"]["width"], height=reg["camera"]["height"]
    )
    arm_dict = arm_geometries(model)
    geom_ids = sorted(arm_dict)
    alphas = model.geom_rgba[geom_ids, 3].copy()
    try:
        for v_i, (v, registered) in enumerate(VIEWS.items()):
            position, aim = REGISTERED_VIEWS[registered]
            backend.set_camera_position(position, look_at_m=aim)
            for s in STEPS:
                resid = restore(model, data, states[s])
                if s in residuals and resid != residuals[s]:
                    raise ValueError("changing camera altered restored kinematics")
                residuals[s] = resid
                for visibility in ARMS:
                    model.geom_rgba[geom_ids, 3] = alphas if visibility == "visible" else 0
                    sensor, ids, names, state_hashes = camera.capture_with_instances(
                        data,
                        rng=np.random.default_rng(a["noise_seed_offset"] + s * 3 + v_i),
                        noise_std_m=a["old_sensor_noise_m"],
                        scene_id="r593-camera-diagnosis",
                        episode_id=f"reconstruction-{digest[:16]}",
                    )
                    if len(state_hashes) != 3 or len(set(state_hashes)) != 1:
                        raise ValueError("render passes changed the reconstructed state")
                    key = frame_name(s, v, visibility)
                    frame = observation_from_sensor_frame(sensor, source="mujoco_camera")
                    validate_camera(
                        frame,
                        {"scene_id": "r593-camera-diagnosis", "view": registered},
                        {
                            "geometry": reg,
                            "views": {registered: a["views"][v]},
                        },
                    )
                    if (
                        v == "nominal"
                        and frame.calibration_version != reg["camera"]["calibration_version"]
                    ):
                        raise ValueError("nominal camera registration changed")
                    frame_file = dest / "pixels" / f"{key}.json"
                    write(frame_file, frame.model_dump(mode="json"))
                    index[key] = {"file": frame_file.name, "sha256": sha(frame_file)}
                    seg_file = dest / "geometry" / f"{key}.npy"
                    with seg_file.open("xb") as out:
                        np.save(
                            out, np.asarray(ids, dtype="<i2").reshape(frame.height, frame.width)
                        )
                    if visibility == "hidden" and set(names).intersection(geom_ids):
                        raise ValueError(
                            "robot geometry still present after renderer-only intervention"
                        )
                    labels[key] = {
                        "file": seg_file.name,
                        "sha256": sha(seg_file),
                        "names": names,
                        "state_sha256": state_hashes[0],
                    }
                model.geom_rgba[geom_ids, 3] = alphas
                if (
                    labels[frame_name(s, v, "visible")]["state_sha256"]
                    != labels[frame_name(s, v, "hidden")]["state_sha256"]
                ):
                    raise ValueError("paired visibility intervention changed physics")
    finally:
        model.geom_rgba[geom_ids, 3] = alphas
        camera.close()
        backend.shutdown()
    for row in a["original_rows"]:
        frame = frame_from_row(ref, row, a["original_episode"], a["original_scene"], reg)
        key = frame_name(row["physics_step"], "original", row["label"].split("/")[-1])
        name = dest / "pixels" / f"{key}.json"
        write(name, frame.model_dump(mode="json"))
        index[key] = {"file": name.name, "sha256": sha(name)}
    write(
        dest / "pixels/index.json",
        {
            "frames": index,
            "marker_geometry": {
                k: reg[k] for k in ("marker_to_object", "pose_marker", "object_half_extent_m")
            },
            "allocation_sha256": digest,
        },
    )
    write(
        dest / "geometry/index.json",
        {
            "segmentation": labels,
            "arm_geoms": arm_dict,
            "residuals": residuals,
            "allocation_sha256": digest,
        },
    )
    write(
        raw / "capture-seal.json",
        {
            "allocation_sha256": digest,
            "pixels_sha256": sha(dest / "pixels/index.json"),
            "geometry_sha256": sha(dest / "geometry/index.json"),
        },
    )


def load_frame(dir_, row):
    return RGBDObservation.model_validate(pinned(dir_ / row["file"], row["sha256"]))


def pixels(raw, digest):
    # This stage deliberately receives neither offline states nor segmentation paths as input.
    capture = read(raw / "capture-seal.json")
    dir_ = raw / "capture/pixels"
    idx = pinned(dir_ / "index.json", capture["pixels_sha256"])
    if idx["allocation_sha256"] != digest or capture["allocation_sha256"] != digest:
        raise ValueError("wrong pixel allocation")
    estimates = {}
    for key, row in idx["frames"].items():
        frame = load_frame(dir_, row)
        estimates[key] = {
            "source_sha256": row["sha256"],
            "observed_checksum": frame.checksum_sha256,
            "estimate": measure(frame, idx["marker_geometry"], "SUBPIX"),
        }
    write(
        raw / "decisions.json",
        {
            "allocation_sha256": digest,
            "pixels_sha256": capture["pixels_sha256"],
            "estimates": estimates,
        },
    )
    write(
        raw / "decision-seal.json",
        {"sha256": sha(raw / "decisions.json"), "capture_sha256": sha(raw / "capture-seal.json")},
    )


def depth(frame):
    return np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
        frame.height, frame.width
    )


def rgb(frame):
    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as image:
        return np.array(image)


def compare(original, reconstructed):
    x, y = depth(original), depth(reconstructed)
    common = (x > 0) & (y > 0)
    if not np.any(common):
        raise ValueError("no common positive depth")
    return {
        "rgb_changed_pixel_fraction": float(
            np.any(rgb(original) != rgb(reconstructed), axis=-1).mean()
        ),
        "valid_mask_disagreement_fraction": float(((x > 0) != (y > 0)).mean()),
        "common_valid_depth_abs_p99_m": float(np.quantile(np.abs(x[common] - y[common]), 0.99)),
    }


def regions(frame, model_geometry, row, ids, names, arms):
    # Integer pixel centres follow RGBDObservation.world_point coordinates.
    H = np.array(frame.camera_to_world).reshape(4, 4)
    y, x = np.indices((frame.height, frame.width))
    fx, fy, cx, cy = frame.intrinsics
    rays = np.stack(((x - cx) / fx, (y - cy) / fy, np.ones_like(x)), axis=-1) @ H[:3, :3].T
    R = np.array(row["object_geom_rotation_row_major"]).reshape(3, 3)
    marker = np.asarray(model_geometry["marker_to_object"]).reshape(4, 4)
    center = np.asarray(row["object_geom_position_m"]) + R @ marker[:3, 3]
    axis = R @ marker[:3, :3]
    normal = axis[:, 2]
    z_plane = ((center - H[:3, 3]) @ normal) / (rays @ normal)
    xy = (H[:3, 3] - center + z_plane[:, :, None] * rays) @ axis[:, :2]
    extent = np.max(np.abs(xy), axis=2)
    masked_depth = depth(frame)
    diff = z_plane - masked_depth
    half = model_geometry["pose_marker"]["marker_size_m"] / 2
    out = {}
    for label, mask in (("printed", extent <= half), ("quiet", (extent > half) & (extent <= 0.05))):
        mask &= z_plane > 0
        vals, n = np.unique(ids[mask], return_counts=True)
        counts = {
            names.get(str(i), "other_rendered_element"): int(k)
            for i, k in zip(vals, n, strict=True)
        }
        arm_counts = {n: c for n, c in counts.items() if n in arms}
        roles = Counter()
        for name, count in counts.items():
            role = (
                "robot" if name in arms else ("marker" if name.startswith("pose_marker_") else name)
            )
            roles[role] += count
        out[label] = {
            "pixels": int(mask.sum()),
            "role_pixels": dict(roles),
            "robot_by_geom": arm_counts,
            "valid": int((mask & (masked_depth > 0)).sum()),
            "nearer_5mm": int((mask & (masked_depth > 0) & (diff > 0.005)).sum()),
            "nearer_20mm": int((mask & (masked_depth > 0) & (diff > 0.020)).sum()),
        }
    return out


def camera_meta(f):
    return {
        "width": f.width,
        "height": f.height,
        "camera_to_world": list(f.camera_to_world),
        "intrinsics": list(f.intrinsics),
        "calibration_version": f.calibration_version,
        "source": f.source,
    }


def score(raw, a, digest, out):
    dec_seal = read(raw / "decision-seal.json")
    cap = pinned(raw / "capture-seal.json", dec_seal["capture_sha256"])
    decisions = pinned(raw / "decisions.json", dec_seal["sha256"])
    pix = raw / "capture/pixels"
    g = raw / "capture/geometry"
    idx = pinned(pix / "index.json", cap["pixels_sha256"])
    seg = pinned(g / "index.json", cap["geometry_sha256"])
    if (
        any(v["allocation_sha256"] != digest for v in (cap, decisions, idx, seg))
        or decisions["pixels_sha256"] != cap["pixels_sha256"]
    ):
        raise ValueError("crossed evidence seals")
    estimates = decisions["estimates"]
    if set(estimates) != set(idx["frames"]) or any(
        val["source_sha256"] != idx["frames"][k]["sha256"] for k, val in estimates.items()
    ):
        raise ValueError("pixel decisions missing or foreign")
    ref = ROOT / a["reference"]
    original_seal = pinned(ref / "acquisition-seal.json", a["reference_seal_sha256"])
    truth = pinned(ref / "offline-truth.json", original_seal["truth_sha256"])
    original = pinned(ref / "decisions.json", a["reference_decisions_sha256"])
    old_by_id = {r["frame_id"]: r["estimate"] for r in original["decisions"]}
    rows = checked_steps(
        truth["samples"], a["original_episode"], a["asset_sha256"], truth["asset_sha256"]
    )
    checks, verified, normal, cameras, pairs = {}, {}, {}, {}, []
    for s in STEPS:
        old_key = frame_name(s, "original", "feedback")
        nom_key = frame_name(s, "nominal", "visible")
        obs = load_frame(pix, idx["frames"][old_key])
        e_old, e_nom = estimates[old_key]["estimate"], estimates[nom_key]["estimate"]
        if old_by_id[obs.frame_id] != e_old:
            raise ValueError("original feedback no longer reproduces the frozen pixel estimate")
        diag = {**seg["residuals"][str(s)], **compare(obs, load_frame(pix, idx["frames"][nom_key]))}
        diag["decision_matches"] = [e_old["status"], e_old["ids"]] == [
            e_nom["status"],
            e_nom["ids"],
        ]
        verified[s] = diag["decision_matches"] and all(
            diag[k] <= limit for k, limit in CHECK_LIMITS.items()
        )
        checks[s] = {
            **diag,
            "verified": verified[s],
            "original_status": e_old["status"],
            "original_ids": e_old["ids"],
        }
        for v in VIEWS:
            pair = {"step": s, "view": v, "verified": verified[s]}
            for arm in ARMS:
                key = frame_name(s, v, arm)
                dr = seg["segmentation"][key]
                path = g / dr["file"]
                if sha(path) != dr["sha256"]:
                    raise ValueError("segmentation SHA mismatch")
                f = load_frame(pix, idx["frames"][key])
                cam = camera_meta(f)
                if v in cameras and cameras[v] != cam:
                    raise ValueError("changed camera registration across paired frames")
                cameras[v] = cam
                e = estimates[key]["estimate"]
                pair[arm] = {
                    "status": e["status"],
                    "ids": e["ids"],
                    "reason": e["reason"],
                    "top_center_world_m": e["object_top_center_world_m"],
                    "min_side_px": e["min_side_px"],
                    "regions": regions(
                        f,
                        a["geometry"],
                        rows[s],
                        np.load(path, allow_pickle=False),
                        dr["names"],
                        set(seg["arm_geoms"].values()),
                    ),
                }
                if arm == "visible":
                    normal[s, v] = e
            pairs.append(pair)
    terminal = load_frame(pix, idx["frames"][frame_name(848, "original", "terminal")])
    term_est = estimates[frame_name(848, "original", "terminal")]["estimate"]
    if term_est != old_by_id[terminal.frame_id]:
        raise ValueError("original terminal evidence changed")
    selected, scores = select_view(normal, verified)
    write(
        out,
        {
            "schema": "proposal.r593.camera-diagnosis.v1",
            "allocation_sha256": digest,
            "source_reference_seal": a["reference_seal_sha256"],
            "original_episode": a["original_episode"],
            "asset_sha256": a["asset_sha256"],
            "plan_sha256": a["plan_sha256"],
            "sources_sha256": a["sources_sha256"],
            "decision_seal": dec_seal,
            "capture_seal": cap,
            "selected_view": selected,
            "views": {v: {"camera": cameras[v], **scores[v]} for v in VIEWS},
            "reconstruction": checks,
            "terminal_original": {
                "step": 848,
                "status": term_est["status"],
                "ids": term_est["ids"],
            },
            "counts": {
                "states": len(STEPS),
                "normal": len(normal),
                "paired_hidden": len(pairs),
                "archived_frames": len(a["original_rows"]),
                "verified_states": sum(verified.values()),
            },
            "pairs": pairs,
            "visibility_control": "Hide panda_link0 subtree geoms only in the renderer. "
            "Selection uses normal images from verified reconstructions.",
            "arm_geometry_names": sorted(seg["arm_geoms"].values()),
            "limitations": "Eight correlated states of one development motion. "
            "Hidden-arm images assess the rendering intervention. Independent placement success "
            "and calibrated error bounds require additional experiments.",
            "new_physics_steps": 0,
            "new_formal_claims": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("allocate")
    ap.add_argument("raw", type=Path)
    ap.add_argument("plan", type=Path)
    ap.add_argument("reference", type=Path)
    for cmd in ("render", "pixels", "score"):
        p = sub.add_parser(cmd)
        p.add_argument("raw", type=Path)
        p.add_argument("allocation_sha256")
        if cmd == "score":
            p.add_argument("output", type=Path)
    arg = parser.parse_args()
    if arg.cmd == "allocate":
        allocate(arg.raw, arg.plan, arg.reference)
        return
    allocation = pinned(arg.raw / "allocation.json", arg.allocation_sha256)
    check_sources(allocation)
    if allocation["steps"] != list(STEPS) or allocation["validation_upper_limits"] != CHECK_LIMITS:
        raise ValueError("camera observation protocol mismatch")
    if arg.cmd == "render":
        render(arg.raw, allocation, arg.allocation_sha256)
    elif arg.cmd == "pixels":
        pixels(arg.raw, arg.allocation_sha256)
    else:
        score(arg.raw, allocation, arg.allocation_sha256, arg.output)


if __name__ == "__main__":
    main()
