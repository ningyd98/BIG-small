"""Render known poses and compare current RGB-D estimates with independent geometry."""

from __future__ import annotations

import argparse
import fcntl
import gzip
import json
import os
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation import g1_dual_asset as asset
from scripts.graduation.g1_clearance_mount_physics import (
    CENTER,
    ROOT,
    digest,
    initialize,
    set_diagnostic_arm,
    write,
)
from scripts.graduation.g1_dual_observer import measure_frame

from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region


def set_known_cube(model, data, point, rot):
    adr = model.joint("object_free").qposadr[0]
    data.qpos[adr : adr + 3] = point
    mujoco.mju_mat2Quat(data.qpos[adr + 3 : adr + 7], np.array(rot).ravel())


def restore_observed_state(backend, row):
    model, data = backend._model, backend._data
    data.qpos[:7] = row["joints_rad"]
    for joint, q in zip(
        ("finger_left_joint", "finger_right_joint"), row["finger_joints_m"], strict=True
    ):
        data.qpos[model.joint(joint).qposadr[0]] = q
    set_known_cube(model, data, row["cube_xyz_m"], row["cube_rotation"])
    data.time = row["dt_s"]
    mujoco.mj_forward(model, data)


def optical_observation(backend, geometry, tracker, out, label):
    sensor, ids, names, states = backend.capture_sensor_frame_with_instances()
    frame = observation_from_sensor_frame(sensor, source="mujoco_camera", png_compress_level=1)
    write(out / (label + ".rgbd.json.gz"), frame.model_dump(mode="json"))
    # Raw RGB-D only for both existing marker and destination estimators.
    marks = measure_frame(frame, geometry)
    region_diagnostics = {}
    region, reason = (
        measure_servo_region(frame, tracker, diagnostics=region_diagnostics)
        if tracker
        else (None, "bootstrap_failed")
    )
    data = backend._data
    obj = data.geom("object_geom")
    R = obj.xmat.reshape(3, 3)
    top = obj.xpos + R @ [0, 0, 0.035]
    tcp = obj.xpos + R @ [0, 0, 0.010]
    instances = np.asarray(ids).reshape(frame.height, frame.width)
    np.savez_compressed(out / (label + ".instances.npz"), ids=instances.astype("int16"))
    # These instance IDs and true corners are used only for *post-measurement* optical audit.
    arm_names = {
        "base",
        "hand",
        "left_finger_geom",
        "right_finger_geom",
        *(f"link{i}" for i in range(1, 7)),
    }
    arm_ids = [i for i, name in names.items() if name in arm_names]
    extr = np.asarray(frame.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = frame.intrinsics
    unexplained = []
    if reason == "region_missing_color_not_explained_by_foreground":
        # Offline inspection of the existing reader's failing pixel predicate after its decision.
        def inspect_region(call, event, returned):
            if call.f_code is measure_servo_region.__code__ and event == "return":
                v = call.f_locals
                yy, xx = v["ys"], v["xs"]
                unconfirmed = ~v["high_foreground"][yy, xx] & ~v["sidewall"] & ~v["mixed_footprint"]
                for y, x in zip(yy[unconfirmed], xx[unconfirmed], strict=True):
                    unexplained.append(
                        {
                            "pixel_xy": [int(x), int(y)],
                            "rgb": list(
                                sensor.rgb[
                                    (y * frame.width + x) * 3 : (y * frame.width + x + 1) * 3
                                ]
                            ),
                            "depth_m": float(v["depth"][y, x]),
                            "source_geom_for_readback": names.get(
                                int(instances[y, x]), "background"
                            ),
                            "neighbor_geoms_for_readback": sorted(
                                {
                                    names.get(int(i), "background")
                                    for i in instances[
                                        max(0, y - 1) : y + 2, max(0, x - 1) : x + 2
                                    ].ravel()
                                }
                            ),
                        }
                    )

        previous = sys.getprofile()
        try:
            sys.setprofile(inspect_region)
            repeat = measure_servo_region(frame, tracker)
        finally:
            sys.setprofile(previous)
        if repeat != (None, reason):
            raise ValueError("original region read changed on cold pixel audit")
    by_id = {}
    for marker_id, pose in geometry["development_dual"]["markers"].items():
        code = int(marker_id)
        side = marks["by_id"][marker_id]
        T = np.array(pose["object_T_marker"]).reshape(4, 4)
        corners = np.asarray(pose["ordered_corners_marker_m"]) @ T[:3, :3].T + T[:3, 3]
        corners = corners @ R.T + obj.xpos
        opt = (corners - extr[:3, 3]) @ extr[:3, :3]
        uv = np.column_stack((fx * opt[:, 0] / opt[:, 2] + cx, fy * opt[:, 1] / opt[:, 2] + cy))
        mask = np.zeros(instances.shape, dtype="uint8")
        cv2.fillConvexPoly(mask, np.round(uv).astype("int32"), 1)
        inside = mask > 0
        by_id[marker_id] = {
            "observed": side["observed"],
            "usable": side["usable"],
            "reason": side["reason"],
            "observed_sides_px": side["side_lengths_px"],
            "projected_sides_px": np.linalg.norm(np.roll(uv, -1, axis=0) - uv, axis=1).tolist(),
            "projected_support_pixels": int(inside.sum()),
            "hand_arm_pixels_in_projected_support": int(
                np.sum(inside & np.isin(instances, arm_ids))
            ),
            "visible_print_pixels_in_support": int(
                np.sum(
                    inside
                    & np.isin(
                        instances,
                        [i for i, name in names.items() if name.startswith(f"g1_dual_id{code}_r")],
                    )
                )
            ),
            "top_error_mm": float(1000 * np.linalg.norm(top - side["object_top_world_m"]))
            if side["usable"]
            else None,
            "tcp_error_mm": float(1000 * np.linalg.norm(tcp - side["grasp_world_m"]))
            if side["usable"]
            else None,
        }
    return {
        "role": label,
        "camera": geometry["camera"],
        "frame_id": frame.frame_id,
        "raw_sha256": digest(out / (label + ".rgbd.json.gz")),
        "checksum_sha256": frame.checksum_sha256,
        "instance_sha256": digest(out / (label + ".instances.npz")),
        "same_state_all_render_passes": len(set(states)) == 1,
        "truth_cube_center_m": obj.xpos.tolist(),
        "truth_tcp_m": data.site("tcp").xpos.tolist(),
        "observed_ids": marks["observed_ids"],
        "usable_ids": marks["usable_ids"],
        "selected_id": marks["selected_id"],
        "usable": marks["usable"],
        "marker_reason": marks["reason"],
        "by_id": by_id,
        "dual_tcp_disagreement_m": marks["target_disagreement_m"],
        "destination_usable": region is not None,
        "destination_reason": reason,
        "destination_diagnostics": region_diagnostics,
        "unexplained_destination_pixels": unexplained,
        "detection_candidates": marks["candidates"],
        "destination_source": region.get("source") if region else None,
        "destination_observed_corners": region.get("observed_corner_anchors") if region else None,
        "destination_error_mm": float(
            1000 * np.linalg.norm(np.asarray(region["center"]) - geometry["region_world_m"])
        )
        if region
        else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--closed-control", type=Path, required=True)
    p.add_argument("--egl-lock", type=Path, required=True)
    a = p.parse_args()
    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("the original EGL capture is required")
    a.out.mkdir(parents=True, exist_ok=False)
    records = json.loads(gzip.decompress(a.closed_control.read_bytes()))
    geometry = asset.geometry_descriptor()
    asset.validate_geometry(geometry)
    audit = asset.audit_asset(ROOT)
    write(a.out / "compiled.json.gz", audit)
    rows = []
    close_index = next(i for i, row in enumerate(records) if row["phase"] == "GRASP")
    lift_index = next(i for i, row in enumerate(records) if row["phase"] == "LIFT")
    poses = {
        "reset": None,
        "open-near": records[close_index - 1],
        "bilateral-closed": records[lift_index - 1],
        "lift-with-hold": records[-1],
        "over-region-held": (0.2, 0.25, 0.15),
        "at-region-release-height": (0.2, 0.25, 0.035),
        "at-region-retracted": (0.2, 0.25, 0.035),
    }
    with a.egl_lock.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for label, pose in poses.items():
            backend = MuJoCoPhysicsBackend()
            try:
                robot = initialize(backend, CENTER, 0, 4361, True)
                base_frame = observation_from_sensor_frame(
                    backend.get_sensor_frame(), source="mujoco_camera"
                )
                write(a.out / (label + ".bootstrap.json.gz"), base_frame.model_dump(mode="json"))
                why = None
                try:
                    tracker, _ = bootstrap_collection_tracker(base_frame, geometry)
                except ValueError as exc:
                    tracker, why = None, str(exc)
                if isinstance(pose, dict):
                    restore_observed_state(backend, pose)
                elif isinstance(pose, tuple):
                    set_known_cube(backend._model, backend._data, pose, np.eye(3))
                    arm_z = 0.16 if label == "at-region-retracted" else pose[2] + 0.01
                    opening = (
                        (0.04, 0.04)
                        if label == "at-region-retracted"
                        else records[lift_index - 1]["finger_joints_m"]
                    )
                    set_diagnostic_arm(backend, robot, (pose[0], pose[1], arm_z), opening)
                row = optical_observation(backend, geometry, tracker, a.out, label)
                row["bootstrap_refusal"] = why
                row["pose_source"] = (
                    "new_static_reset"
                    if pose is None
                    else "independent_actual_grasp_trajectory"
                    if isinstance(pose, dict)
                    else "known_pose_fixture"
                )
                row["source_trajectory_step"] = pose["step"] if isinstance(pose, dict) else None
                rows.append(row)
                print(label, row["usable_ids"], row["destination_usable"], why or "", flush=True)
                device = {
                    k: GL.glGetString(v).decode()
                    for k, v in (
                        ("vendor", GL.GL_VENDOR),
                        ("renderer", GL.GL_RENDERER),
                        ("version", GL.GL_VERSION),
                    )
                }
            finally:
                backend.shutdown()
    write(
        a.out / "summary.json",
        dict(
            schema="g1.end-wings.optics.v1",
            asset_sha256=asset.ASSET_SHA,
            diagnostic_generation_sha256=digest(ROOT / "mount-diagnostic-generation.json"),
            physics_source_sha256=digest(a.closed_control),
            compiled_sha256=digest(a.out / "compiled.json.gz"),
            physics_steps=0,
            complete_skill_dispatches=0,
            rows=rows,
            egl=device,
            interpreter=sys.executable,
        ),
    )


if __name__ == "__main__":
    main()
