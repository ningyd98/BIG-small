"""Re-render preregistered phase poses with the nominal camera and read pixels independently."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import proposal_camera as camera
from scripts.graduation.g1_mount_phase_reference import reference_records, usable_reconstruction
from scripts.graduation.g1_mount_phase_sources import (
    SKILLS,
    check_teacher_grid,
    fresh_sources,
    phase_steps,
    requires_teacher,
)
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.perception_pixels import measure
from scripts.graduation.proposal_translated import config

from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.marked_asset import validate_development_marker_asset
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp

__all__ = ["SKILLS", "check_teacher_grid", "phase_steps", "requires_teacher"]
PLAN = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"
POINTS = ("start", "middle", "end")


def token(episode, step, mount=""):
    return hashlib.sha256(f"{PLAN}/{episode}/{step}/{mount}".encode()).hexdigest()[:24]


def pin_geometry(mount, calibration):
    geometry = geometry_registration(marker_family_id=mount["family"])
    if (
        geometry["asset_path"] != mount["asset_path"]
        or geometry["pose_marker"]["marked_asset_sha256"] != mount["asset_sha256"]
        or geometry["camera"]["calibration_version"] != calibration
        or np.asarray(geometry["marker_to_object"]).reshape(4, 4)[:3, 3].tolist()
        != mount["object_T_marker_translation_m"]
    ):
        raise ValueError("wrong marker attachment, camera or asset")
    return geometry


def render_mount(destination, mount, geometry, records, noise):
    model_path = ROOT / geometry["asset_path"]
    equivalence = validate_development_marker_asset(
        model_path, "mujoco_upright_box_v2", mount["family"]
    )
    backend = MuJoCoPhysicsBackend()
    frames, truth = {}, {}
    renderer = None
    try:
        backend.initialize(config({"geometry": geometry}, 24112900))
        model, data = backend._model, backend._data
        renderer = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        for record in records:
            if mount["id"] not in record["mounts"]:
                continue
            for step, state in record["states"].items():
                name = token(record["episode"], step, mount["id"])
                if name in frames or state["episode_id"] != record["episode"]:
                    raise ValueError("reused phase frame key or foreign source episode")
                residual = camera.restore(model, data, state)
                geometry_matches = (
                    np.allclose(
                        model.geom("object_geom").size,
                        state["object_half_extent_m"],
                        rtol=0,
                        atol=1e-12,
                    )
                    and np.allclose(
                        data.geom("target_region_geom").xpos,
                        state["region_center_m"],
                        rtol=0,
                        atol=1e-9,
                    )
                    and np.allclose(
                        model.geom("target_region_geom").size,
                        state["region_half_extent_m"],
                        rtol=0,
                        atol=1e-12,
                    )
                    and math.isclose(
                        data.geom("table").xpos[2] + model.geom("table").size[2],
                        state["table_top_m"],
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                )
                verified = usable_reconstruction(geometry_matches, residual)
                scene_id = "nominal-mount-phase-diagnostic"
                frame = observation_from_sensor_frame(
                    renderer.capture(
                        data,
                        rng=np.random.default_rng(int(token(record["episode"], step)[:16], 16)),
                        noise_std_m=noise,
                        scene_id=scene_id,
                        episode_id="phase-" + name,
                    ),
                    source="mujoco_camera",
                )
                if camera.camera_meta(frame) != geometry["camera"] or not math.isclose(
                    frame.sim_time_s, state["sim_time_s"], rel_tol=0, abs_tol=1e-10
                ):
                    raise ValueError("pose render is not the registered step and camera")
                path = destination / (name + ".json")
                write(path, frame.model_dump(mode="json"))
                frames[name] = {
                    "file": path.name,
                    "sha256": sha(path),
                    "mount": mount["id"],
                    "frame_id": frame.frame_id,
                    "checksum": frame.checksum_sha256,
                }
                rot = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
                center = np.asarray(state["object_geom_position_m"])
                truth[name] = {
                    "source_episode": record["episode"],
                    "step": step,
                    "source_time_s": state["sim_time_s"],
                    "capture_utc": frame.captured_at.isoformat(),
                    "geometry_matches": bool(geometry_matches),
                    "verified": bool(verified),
                    "residuals": residual,
                    "actual_top_m": (
                        center + rot[:, 2] * state["object_half_extent_m"][2]
                    ).tolist(),
                    "actual_grasp_target_m": (center + rot[:, 2] * 0.01).tolist(),
                }
        if backend.total_physics_steps:
            raise ValueError("phase reconstruction advanced dynamics")
    finally:
        if renderer is not None:
            renderer.close()
        backend.shutdown()
    return frames, truth, equivalence


def capture(private, public, dest, reference_plan):
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("phase images require EGL")
    plan = pinned(public / "plan.json", PLAN)
    if sha(public / "plan.md") != plan["plan_md_sha256"]:
        raise ValueError("phase plan text differs")
    check_sources({"sources_sha256": plan["input_sha256"]})
    batch = read(public / "trial-allocation.public.json")
    selection = pinned(public / "selection.public.json", batch["selection_sha256"])
    records = fresh_sources(plan, batch, selection, private / "trials")
    reference_status = {}
    if any(r["requires_separate_reference"] for r in records):
        extra, reference_status = reference_records(
            plan, reference_plan, selection["selected_mount"]
        )
        records.extend(extra)
    dest.mkdir()
    pixels_dir = dest / "pixels"
    pixels_dir.mkdir()
    geometry, frames, truth, invariants = {}, {}, {}, {}
    for mount in plan["mounts"]:
        if not any(mount["id"] in r["mounts"] for r in records):
            continue
        descriptor = pin_geometry(mount, plan["camera_calibration_version"])
        fs, ts, inv = render_mount(
            pixels_dir, mount, descriptor, records, plan["paired_noise_std_m"]
        )
        geometry[mount["id"]] = descriptor
        frames.update(fs)
        truth.update(ts)
        invariants[mount["id"]] = inv
    roles = []
    for record in records:
        for mount_name in record["mounts"]:
            for skill, ticks in record["ticks"].items():
                for point, step in zip(POINTS, ticks, strict=bool(ticks)):
                    name = token(record["episode"], step, mount_name)
                    if name not in frames:
                        raise ValueError("role has no sealed phase frame")
                    roles.append(
                        {
                            "scope": record["scope"],
                            "case": record["case"],
                            "mount": mount_name,
                            "skill": skill,
                            "point": point,
                            "frame_key": name,
                        }
                    )
    write(pixels_dir / "index.json", {"geometry": geometry, "frames": frames})
    write(
        dest / "joins.json",
        {
            "roles": roles,
            "truth": truth,
            "reference_status": reference_status,
            "source_records": [{k: v for k, v in r.items() if k != "states"} for r in records],
            "model_equivalence": invariants,
        },
    )
    write(
        dest / "capture-seal.json",
        {
            "plan_sha256": PLAN,
            "batch_sha256": sha(public / "trial-allocation.public.json"),
            "selection_sha256": batch["selection_sha256"],
            "index_sha256": sha(pixels_dir / "index.json"),
            "joins_sha256": sha(dest / "joins.json"),
            "physics_steps_advanced": 0,
            "reference_plan_sha256": sha(reference_plan) if reference_status else None,
        },
    )


def load_pixel(directory, spec):
    frame = RGBDObservation.model_validate(pinned(directory / spec["file"], spec["sha256"]))
    if frame.checksum_sha256 != spec["checksum"] or frame.frame_id != spec["frame_id"]:
        raise ValueError("phase RGB-D frame changed")
    return frame


def pixels(directory, index_hash, output):
    idx = pinned(directory / "index.json", index_hash)
    rows = {}
    for key, source in idx["frames"].items():
        frame = load_pixel(directory, source)
        geometry = idx["geometry"][source["mount"]]
        modes = {mode: measure(frame, geometry, mode) for mode in ("NONE", "SUBPIX")}
        try:
            point, observation = measure_registered_marker_grasp(frame, geometry["marker_family"])
            reason = observation.reason
        except ValueError as exc:
            point, reason = None, str(exc)
        rows[key] = {
            "modes": modes,
            "grasp_m": None if point is None else point.tolist(),
            "grasp_reason": reason,
            "checksum": frame.checksum_sha256,
            "file_sha256": source["sha256"],
        }
    write(output, {"index_sha256": index_hash, "rows": rows})


def score(dest, decision_sha, out):
    cap = read(dest / "capture-seal.json")
    data = pinned(dest / "joins.json", cap["joins_sha256"])
    idx = pinned(dest / "pixels/index.json", cap["index_sha256"])
    decisions = pinned(dest / "decisions.json", decision_sha)
    rows = decisions["rows"]
    if (
        decisions["index_sha256"] != cap["index_sha256"]
        or set(rows) != set(idx["frames"])
        or set(rows) != set(data["truth"])
    ):
        raise ValueError("phase observations do not match sealed roles")
    unique, counts, result = {}, {}, []
    for role in data["roles"]:
        k = role["frame_key"]
        rec, state, src = rows[k], data["truth"][k], idx["frames"][k]
        if rec["checksum"] != src["checksum"] or rec["file_sha256"] != src["sha256"]:
            raise ValueError("phase observation does not match frame bytes")
        if k not in unique:
            frame = load_pixel(dest / "pixels", src)
            if frame.episode_id != "phase-" + k:
                raise ValueError("wrong phase observation identity")
            verified = usable_reconstruction(state["geometry_matches"], state["residuals"])
            if verified != state["verified"]:
                raise ValueError("stored pose verdict differs from the three FK residuals")
            estimate = rec["modes"]["SUBPIX"]
            depth = estimate["marker_center_optical_depth_m"]
            located = camera.valid(estimate) and depth is not None and 0 < depth < math.inf
            unique[k] = {
                "verified": verified,
                "pose_status": (
                    "VERIFIED"
                    if verified
                    else ("SCENE_MISMATCH" if not state["geometry_matches"] else "FK_OUT_OF_BOUNDS")
                ),
                "scene_matches": state["geometry_matches"],
                "source_time_s": state["source_time_s"],
                "capture_utc": state["capture_utc"],
                "source_episode": state["source_episode"],
                "physics_step": state["step"],
                "frame_id": src["frame_id"],
                "rgbd_sha256": src["sha256"],
                "source_pose_residuals": state["residuals"],
                "id7_and_depth": located,
                "marker_ids": estimate["ids"],
                "marker_status": {m: v["status"] for m, v in rec["modes"].items()},
                "grasp_usable": located and rec["grasp_m"] is not None,
                "reason": rec["grasp_reason"],
                "top_error_mm": None
                if estimate["object_top_center_world_m"] is None
                else float(
                    1000
                    * np.linalg.norm(
                        np.subtract(estimate["object_top_center_world_m"], state["actual_top_m"])
                    )
                ),
                "grasp_target_error_mm": None
                if rec["grasp_m"] is None
                else float(
                    1000
                    * np.linalg.norm(np.subtract(rec["grasp_m"], state["actual_grasp_target_m"]))
                ),
            }
        metrics = unique[k]
        result.append({**role, **metrics})
        group = counts.setdefault((role["scope"], role["mount"], role["skill"]), {})
        group[k] = metrics
    if set(unique) != set(rows):
        raise ValueError("unassigned diagnostic frame")
    aggregates = []
    for (scope, mount, skill), values in sorted(counts.items()):
        counts_by_status = Counter(
            "unverified_pose"
            if not r["verified"]
            else ("usable" if r["grasp_usable"] else "unusable")
            for r in values.values()
        )
        aggregates.append(
            {
                "scope": scope,
                "mount": mount,
                "skill": skill,
                "unique_poses": len(values),
                **{key: counts_by_status[key] for key in ("usable", "unusable", "unverified_pose")},
            }
        )
    write(
        out,
        {
            "schema": "graduation.g1.marker-mount.phase-pose-readback.v1",
            "scope": "Normal RGB-D rendered from logged poses. Separate from observed live frames.",
            "input_seal_sha256": sha(dest / "capture-seal.json"),
            "decisions_sha256": decision_sha,
            "source_provenance": data["source_records"],
            "reference_status": data["reference_status"],
            "model_equivalence": data["model_equivalence"],
            "camera": "nominal",
            "unique_rgbd_frames": len(unique),
            "role_rows": len(result),
            "counts": aggregates,
            "roles": result,
            "physics_steps_advanced": 0,
            "new_formal_claims": 0,
        },
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="cmd", required=True)
    cap = subs.add_parser("capture")
    for arg in ("private", "public", "destination", "reference_plan"):
        cap.add_argument(arg, type=Path)
    px = subs.add_parser("pixels")
    px.add_argument("directory", type=Path)
    px.add_argument("index_sha256")
    px.add_argument("output", type=Path)
    sc = subs.add_parser("score")
    sc.add_argument("destination", type=Path)
    sc.add_argument("decisions_sha256")
    sc.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.cmd == "capture":
        capture(args.private, args.public, args.destination, args.reference_plan)
    elif args.cmd == "pixels":
        pixels(args.directory, args.index_sha256, args.output)
    else:
        score(args.destination, args.decisions_sha256, args.output)


if __name__ == "__main__":
    main()
