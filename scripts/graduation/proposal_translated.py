"""Test one predeclared vertically translated camera against the unchanged r593 tracker."""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import proposal_camera as camera
from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

POSITION = {"nominal": (0.35, 0.0, 1.4), "translated": (0.40, 0.08, 1.35)}
STORED_POSES = (
    (0.431, 0.006, 0.035, 0.11),
    (0.469, -0.006, 0.035, -0.11),
    (0.447, -0.018, 0.035, 0.17),
    (0.453, 0.018, 0.035, -0.17),
)
ABSENT_STEPS = (120, 848)
SOURCE = "scripts/graduation/proposal_translated.py"


def slots():
    result = []
    for i, (x, y, z, yaw) in enumerate(STORED_POSES):
        views = ("nominal", "translated") if i % 2 == 0 else ("translated", "nominal")
        group = f"t{i + 1:02}"
        for v in views:
            result.append(
                {
                    "id": group + "-" + v,
                    "group": group,
                    "seed": 24112501 + i,
                    "view": v,
                    "reset_fixture_center_m": [x, y, z],
                    "yaw_rad": yaw,
                }
            )
    return result


def admissions(
    *, verified, nominal_positive, nominal_negative, translated_detected, probes, absent_rejected
):
    if set(verified) != set(camera.STEPS) or set(translated_detected) != set(camera.STEPS):
        raise ValueError("lost one or more registered evaluation states")
    if set(probes) != set(POSITION) or set(absent_rejected) != {
        f"{s}-{v}" for s, v in product(ABSENT_STEPS, POSITION)
    }:
        raise ValueError("missing a registered tracker or absent-marker control")
    facts = {
        "reconstruction": all(verified.values()),
        "nominal_original_positive_step840": nominal_positive,
        "nominal_original_negative_step848": nominal_negative,
        "translated_all_eight_steps": all(translated_detected.values()),
        "translated_endpoint_848": translated_detected[848],
        "zero_step_trackers": all(probes.values()),
        "absent_marker_rejected": all(absent_rejected.values()),
    }
    return [k for k, v in facts.items() if v is not True]


def check_view(view, meta, geometry):
    if view not in POSITION:
        raise ValueError("unregistered camera")
    org = geometry["camera"]
    if set(meta) != set(org) or any(
        meta[k] != org[k] for k in ("width", "height", "intrinsics", "source")
    ):
        raise ValueError("foreign source or intrinsic camera registration")
    transform = camera.optical_transform(POSITION[view], None)
    if not np.array_equal(transform, np.asarray(meta["camera_to_world"]).reshape(4, 4)):
        raise ValueError("view is not the predeclared vertical camera")
    import hashlib

    version = hashlib.sha256(
        np.r_[meta["intrinsics"], transform.ravel()].astype("<f8").tobytes()
    ).hexdigest()[:16]
    if version != meta["calibration_version"] or (view == "nominal") != (meta == org):
        raise ValueError("view fingerprint does not match exact calibration")
    measured = {**geometry, "camera": dict(meta)}
    NativeGeometryRegistration(measured).validate_asset(ROOT)
    return measured


def allocate(raw, plan, plan_hash, parent):
    p = pinned(plan, plan_hash)
    if sha(plan.with_suffix(".md")) != p["plan_md_sha256"]:
        raise ValueError("plan markdown differs")
    check_sources({"sources_sha256": p["input_sha256"]})
    prior = pinned(parent, p["input_sha256"][str(parent.resolve().relative_to(ROOT))])
    if os.environ.get("MUJOCO_GL") != "egl" or shutil.disk_usage(raw).free < 2**29:
        raise ValueError("EGL and local headroom required")
    write(
        raw / "qualification-allocation.json",
        {
            "schema": "proposal.translated.camera-allocation.v1",
            "issued": datetime.now(UTC).isoformat(),
            "baseline": p["baseline"],
            "plan_sha256": plan_hash,
            "plan_md_sha256": p["plan_md_sha256"],
            "parent_allocation_sha256": sha(parent),
            "positions": POSITION,
            "all_camera_quaternions_wxyz": [1, 0, 0, 0],
            "view_labels": list(POSITION),
            "steps": list(camera.STEPS),
            "absent_steps": list(ABSENT_STEPS),
            "neutral_reset_seed": 24112000,
            "depth_noise_std_m": 0.001,
            "noise_seed_offset": 241125000,
            "validation_upper_limits": camera.CHECK_LIMITS,
            "geometry": prior["geometry"],
            "asset_sha256": prior["asset_sha256"],
            "reference": prior["reference"],
            "reference_seal_sha256": prior["reference_seal_sha256"],
            "original_rows": prior["original_rows"],
            "original_episode": prior["original_episode"],
            "original_scene": prior["original_scene"],
            "slots": slots(),
            "sources_sha256": {**prior["sources_sha256"], SOURCE: sha(ROOT / SOURCE)},
            "formal_claims": 0,
            "model_calls": 0,
            "hardware_actions": 0,
        },
    )


def config(a, seed):
    return runtime.SimulatorConfig(
        model_path=str(ROOT / a["geometry"]["asset_path"]),
        seed=seed,
        physics_dt_s=1 / 240,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
    )


def observe(raw, a, h):
    root = raw / "capture"
    root.mkdir()
    pixels = root / "pixels"
    pixels.mkdir()
    reference = ROOT / a["reference"]
    seal = pinned(reference / "acquisition-seal.json", a["reference_seal_sha256"])
    truth = pinned(reference / "offline-truth.json", seal["truth_sha256"])
    states = checked_steps(
        truth["samples"], a["original_episode"], a["asset_sha256"], truth["asset_sha256"]
    )
    backend = MuJoCoPhysicsBackend()
    backend.initialize(config(a, 241125))
    model, data = backend._model, backend._data
    cam = MuJoCoRGBDCamera(
        mujoco,
        model,
        width=a["geometry"]["camera"]["width"],
        height=a["geometry"]["camera"]["height"],
    )
    marker_ids = [
        i for i in range(model.ngeom) if model.geom(i).name.startswith("pose_marker_outboard_v3_")
    ]
    if len(marker_ids) != 37:
        raise ValueError("r593 marker and border geometry changed")
    alpha = model.geom_rgba[marker_ids, 3].copy()
    frames, residuals = {}, {}

    def save(key, f):
        file = pixels / (key + ".json")
        write(file, f.model_dump(mode="json"))
        frames[key] = {"file": file.name, "sha256": sha(file)}

    try:
        for i, (view, pos) in enumerate(POSITION.items()):
            backend.set_camera_position(pos)
            if not np.array_equal(model.cam_quat[model.camera("rgbd").id], [1, 0, 0, 0]):
                raise ValueError("physical camera quaternion changed")
            for step in camera.STEPS:
                err = camera.restore(model, data, states[step])
                if step in residuals and residuals[step] != err:
                    raise ValueError("viewpoint changed kinematics")
                residuals[step] = err
                for condition in ("visible", "absent") if step in ABSENT_STEPS else ("visible",):
                    model.geom_rgba[marker_ids, 3] = alpha if condition == "visible" else 0
                    f = observation_from_sensor_frame(
                        cam.capture(
                            data,
                            rng=np.random.default_rng(a["noise_seed_offset"] + 2 * step + i),
                            noise_std_m=a["depth_noise_std_m"],
                            scene_id="translated-offline-observe",
                            episode_id="translated-" + h[:16],
                        ),
                        source="mujoco_camera",
                    )
                    check_view(view, camera.camera_meta(f), a["geometry"])
                    save(f"{step}-{view}-{condition}", f)
                    model.geom_rgba[marker_ids, 3] = alpha
    finally:
        model.geom_rgba[marker_ids, 3] = alpha
        cam.close()
        backend.shutdown()
    for r in a["original_rows"]:
        if r["label"] == "MOVE_ABOVE/feedback":
            orig = frame_from_row(
                reference, r, a["original_episode"], a["original_scene"], a["geometry"]
            )
            save(f"{r['physics_step']}-original", orig)
    write(
        pixels / "index.json",
        {
            "frames": frames,
            "allocation_sha256": h,
            "marker_geometry": {
                k: a["geometry"][k]
                for k in ("marker_to_object", "pose_marker", "object_half_extent_m")
            },
        },
    )
    write(root / "kinematic-check.json", {"residuals": residuals, "allocation_sha256": h})
    write(
        raw / "capture-seal.json",
        {
            "allocation_sha256": h,
            "pixels_sha256": sha(pixels / "index.json"),
            "kinematic_sha256": sha(root / "kinematic-check.json"),
        },
    )


def register(raw, a, h):
    decision_seal = read(raw / "decision-seal.json")
    cap = pinned(raw / "capture-seal.json", decision_seal["capture_sha256"])
    index = pinned(raw / "capture/pixels/index.json", cap["pixels_sha256"])
    if index["allocation_sha256"] != h:
        raise ValueError("foreign pixel allocation")
    dest = raw / "zero-step-tracker"
    dest.mkdir()
    results = {}
    inventory = runtime.inventory()
    for view, pos in POSITION.items():
        backend = MuJoCoPhysicsBackend()
        try:
            backend.initialize(config(a, a["neutral_reset_seed"]))
            backend.reset(
                runtime.PhysicalScenarioConfig(
                    scenario_id="TRANSLATED_ZERO_STEP",
                    seed=a["neutral_reset_seed"],
                    object_pose=runtime.Pose(x=0.45, y=0, z=0.035),
                    object_yaw_rad=0.0,
                )
            )
            if view != "nominal":
                backend.set_camera_position(pos)
            f = observation_from_sensor_frame(
                backend.capture_sensor_frame(), source="mujoco_camera"
            )
            geometry = check_view(view, camera.camera_meta(f), a["geometry"])
            expected = camera.load_frame(
                raw / "capture/pixels", index["frames"][f"120-{view}-visible"]
            )
            if camera.camera_meta(f) != camera.camera_meta(expected):
                raise ValueError("reset camera does not reproduce actual offline registration")
            runtime.validate_camera(f, geometry)
            try:
                runtime.bootstrap_registered_collection_tracker_v2(
                    f,
                    NativeGeometryRegistration(geometry),
                    source_root=ROOT,
                    source_hashes=inventory,
                    nominal_policy=runtime.registered_nominal_region_policy_v1(inventory),
                )
                supported, reason = True, None
            except ValueError as exc:
                supported, reason = False, str(exc)
            if backend.total_physics_steps != 0:
                raise ValueError("registration advanced physics")
            path = dest / (view + "-frame.json")
            write(path, f.model_dump(mode="json"))
            results[view] = {
                "geometry": geometry,
                "supported": supported,
                "reason": reason,
                "frame_sha256": sha(path),
                "frame_id": f.frame_id,
                "episode": f.episode_id,
                "observation_sha256": f.checksum_sha256,
                "physics_steps": 0,
                "commands": backend.command_records,
            }
        finally:
            backend.shutdown()
    write(
        dest / "probes.json",
        {
            "results": results,
            "allocation_sha256": h,
            "product_catalog_sha256": runtime.digest(inventory),
            "pixel_decision_seal_sha256": sha(raw / "decision-seal.json"),
        },
    )


def freeze(raw, a, h, out):
    dest = raw / "capture"
    probes = read(raw / "zero-step-tracker/probes.json")
    cap = pinned(raw / "capture-seal.json", read(raw / "decision-seal.json")["capture_sha256"])
    kin = pinned(dest / "kinematic-check.json", cap["kinematic_sha256"])
    index = pinned(dest / "pixels/index.json", cap["pixels_sha256"])
    decisions = pinned(raw / "decisions.json", read(raw / "decision-seal.json")["sha256"])
    if any(item["allocation_sha256"] != h for item in (probes, cap, kin, index, decisions)):
        raise ValueError("mismatched phase-1 inputs")
    if probes["pixel_decision_seal_sha256"] != sha(raw / "decision-seal.json"):
        raise ValueError("tracker and blind pixel seals differ")
    verified, converted, checks, negatives = {}, {}, {}, {}
    detected = {}
    for step in camera.STEPS:
        old = f"{step}-original"
        k = f"{step}-nominal-visible"
        orig = camera.load_frame(dest / "pixels", index["frames"][old])
        f = camera.load_frame(dest / "pixels", index["frames"][k])

        def estimate(key):
            row = decisions["estimates"][key]
            if row["source_sha256"] != index["frames"][key]["sha256"]:
                raise ValueError("estimate made on foreign frame")
            return row["estimate"]

        old_est, nom_est = estimate(old), estimate(k)
        errs = {**kin["residuals"][str(step)], **camera.compare(orig, f)}
        verified[step] = all(errs[n] <= v for n, v in camera.CHECK_LIMITS.items()) and (
            nom_est["status"],
            nom_est["ids"],
        ) == (old_est["status"], old_est["ids"])
        this_step = {}
        for v in POSITION:
            e = estimate(f"{step}-{v}-visible")
            as_used = camera.camera_meta(
                camera.load_frame(dest / "pixels", index["frames"][f"{step}-{v}-visible"])
            )
            if as_used != probes["results"][v]["geometry"]["camera"]:
                raise ValueError("state camera and original tracker camera differ")
            this_step[v] = {
                "status": e["status"],
                "ids": e["ids"],
                "reason": e["reason"],
                "valid_metric_pose": bool(
                    camera.valid(e) and e["marker_center_optical_depth_m"] > 0
                ),
                "min_side_px": e["min_side_px"],
                "object_top_center_world_m": e["object_top_center_world_m"],
            }
            if step in ABSENT_STEPS:
                absent = estimate(f"{step}-{v}-absent")
                negatives[f"{step}-{v}"] = (
                    absent["status"] == "UNKNOWN"
                    and absent["ids"] == []
                    and absent["object_top_center_world_m"] is None
                )
        converted[step] = this_step["translated"]["valid_metric_pose"]
        detected[step] = this_step
        checks[step] = {
            **errs,
            "verified": verified[step],
            "original_status": old_est["status"],
            "original_ids": old_est["ids"],
        }
    for v, probe in probes["results"].items():
        if sha(raw / "zero-step-tracker" / (v + "-frame.json")) != probe["frame_sha256"]:
            raise ValueError("changed zero-step frame")
    causes = admissions(
        verified=verified,
        nominal_positive=detected[840]["nominal"]["valid_metric_pose"],
        nominal_negative=(
            detected[848]["nominal"]["status"] == "UNKNOWN"
            and checks[848]["original_status"] == "UNKNOWN"
        ),
        translated_detected=converted,
        probes={v: p["supported"] for v, p in probes["results"].items()},
        absent_rejected=negatives,
    )
    write(
        out,
        {
            "schema": "proposal.translated.qualification.v1",
            "allocation_sha256": h,
            "plan_sha256": a["plan_sha256"],
            "eligible": not causes,
            "failure_reasons": causes,
            "selected_view": "translated" if not causes else None,
            "views": {
                v: {
                    "camera": r["geometry"]["camera"],
                    "real_zero_step_tracker": r["supported"],
                    "tracker_reason": r["reason"],
                    "probe_frame_sha256": r["frame_sha256"],
                    "valid_steps": sum(x[v]["valid_metric_pose"] for x in detected.values()),
                    "allocated_steps": 8,
                }
                for v, r in probes["results"].items()
            },
            "state_reconstruction": checks,
            "observations": detected,
            "absent_render_rejected": negatives,
            "decision_seal_sha256": sha(raw / "decision-seal.json"),
            "probe_sha256": sha(raw / "zero-step-tracker/probes.json"),
            "capture_sha256": sha(raw / "capture-seal.json"),
            "source_sha256": a["sources_sha256"],
            "development_slots": [
                {
                    **c,
                    "status": "ELIGIBLE_PENDING_ISSUE"
                    if not causes
                    else "NOT_RUN_QUALIFICATION_FAILED",
                }
                for c in slots()
            ],
            "formal_claims": 0,
            "dispatched_at_preflight": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("allocate")
    p.add_argument("raw", type=Path)
    p.add_argument("plan", type=Path)
    p.add_argument("plan_sha256")
    p.add_argument("parent", type=Path)
    for name in ("observe", "pixels", "register", "freeze"):
        p = sub.add_parser(name)
        p.add_argument("raw", type=Path)
        p.add_argument("allocation_sha256")
        if name == "freeze":
            p.add_argument("output", type=Path)
    a = parser.parse_args()
    if a.command == "allocate":
        allocate(a.raw, a.plan, a.plan_sha256, a.parent)
        return
    alloc = pinned(a.raw / "qualification-allocation.json", a.allocation_sha256)
    check_sources(alloc)
    if alloc["slots"] != slots() or alloc["steps"] != list(camera.STEPS):
        raise ValueError("wrong poses or missing slots")
    if a.command == "observe":
        observe(a.raw, alloc, a.allocation_sha256)
    elif a.command == "pixels":
        camera.pixels(a.raw, a.allocation_sha256)
    elif a.command == "register":
        register(a.raw, alloc, a.allocation_sha256)
    else:
        freeze(a.raw, alloc, a.allocation_sha256, a.output)


if __name__ == "__main__":
    main()
