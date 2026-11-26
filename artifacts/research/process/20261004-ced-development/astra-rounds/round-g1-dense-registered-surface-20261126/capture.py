"""After sealed optical predictions, acquire ten true static RGB-D scene views."""

import fcntl
import importlib.util
import inspect
import os
import time
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from OpenGL import GL
from register import (
    ASSET,
    EGL_LOCK,
    HEIGHT,
    OPTICAL,
    OUT,
    PHYSICAL,
    PLAN,
    PLAN_PATH,
    ROOT,
    SCALE,
    WIDTH,
    pins,
    require,
)
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

RAW = OUT / "native"
PREDICTED = OUT / "prediction.json"


def restore_method():
    code = ROOT / PLAN["prior_geometry"]
    module = importlib.util.spec_from_file_location("frozen_same_view_rays", code)
    require(module is not None and module.loader is not None, "prior pose closure unavailable")
    old = importlib.util.module_from_spec(module)
    module.loader.exec_module(old)
    return old.restore


def raw_arrays(frame, path):
    require(frame.rgb is not None and frame.valid_mask is not None, "native RGB-D channels missing")
    rgb = np.frombuffer(frame.rgb, np.uint8).reshape((HEIGHT, WIDTH, 3))
    depth = np.asarray(frame.depth, dtype="<f4").reshape((HEIGHT, WIDTH))
    valid = np.frombuffer(frame.valid_mask, np.uint8).reshape((HEIGHT, WIDTH))
    require(
        np.isfinite(depth).all() and np.array_equal(depth > 0, valid.astype(bool)), "invalid depth"
    )
    with path.open("xb") as stream:
        np.savez_compressed(stream, rgb=rgb, depth_m=depth, valid=valid)


def forbidden(*_args, **_kwargs):
    raise RuntimeError("static replay does not integrate")


def snapshot(job, model, native, restore, camera, renderer):
    data, optical = restore(
        model,
        {
            "robot": {
                "camera_joint_positions_rad": job["joints_rad"],
                "camera_finger_positions_m": job["fingers_m"],
            },
            "physical": {
                "object_geom_position_m": job["world_object_center_m"],
                "object_geom_rotation_row_major": np.asarray(job["world_object_rotation"]).ravel(),
            },
            "time_s": job["time_s"],
        },
        camera,
    )
    state = MuJoCoRGBDCamera._physics_state_hash(data)
    started = time.perf_counter_ns()
    frame = native.capture(
        data,
        rng=np.random.default_rng(job["seed"]),
        noise_std_m=PLAN["noise_std_m"],
        scene_id=f"g1.development.dense-registered-surface/{job['archive']}",
        episode_id=job["key"],
    )
    elapsed = (time.perf_counter_ns() - started) / 1e6
    expected_intrinsics = (
        camera["intrinsics"][0] * SCALE,
        camera["intrinsics"][1] * SCALE,
        (WIDTH - 1) / 2,
        (HEIGHT - 1) / 2,
    )
    require(
        frame.sim_time_s == data.time == job["time_s"]
        and not frame.ground_truth_used_for_control
        and state == MuJoCoRGBDCamera._physics_state_hash(data)
        and frame.width == WIDTH
        and frame.height == HEIGHT
        and np.array_equal(frame.camera_to_world, optical.ravel())
        and np.allclose(frame.intrinsics, expected_intrinsics, rtol=0, atol=1e-12),
        "native camera calibration or static aperture pose changed",
    )
    path = RAW / (job["key"] + ".npz")
    raw_arrays(frame, path)
    return {
        "key": job["key"],
        "file": path.name,
        "file_sha256": sha(path),
        "dense_frame_id": frame.frame_id,
        "source_frame_id": job["frame_id"],
        "source_checksum_sha256": job["checksum_sha256"],
        "source_time_s": frame.sim_time_s,
        "width": WIDTH,
        "height": HEIGHT,
        "camera_to_world": frame.camera_to_world,
        "intrinsics": frame.intrinsics,
        "calibration_version": frame.calibration_version,
        "seed": job["seed"],
        "noise_std_m": PLAN["noise_std_m"],
        "renderer": renderer,
        "msaa": int(model.vis.quality.offsamples),
        "clip_near_far_m": [
            model.stat.extent * m for m in (model.vis.map.znear, model.vis.map.zfar)
        ],
        "state_sha256": state,
        "camera_call_wall_ms": elapsed,
    }


def capture():
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl", "EGL required"
    )
    pins()
    restore = restore_method()
    registered = read(PHYSICAL)
    prediction = read(PREDICTED)
    optical_hash = sha(OPTICAL)
    runtime_cam = ROOT / PLAN["runtime"] / "src/cloud_edge_robot_arm/simulation/mujoco/camera.py"
    require(
        Path(inspect.getfile(MuJoCoRGBDCamera)).resolve() == runtime_cam.resolve()
        and registered["plan_sha256"] == sha(PLAN_PATH)
        and registered["optical_input_sha256"] == prediction["optical_input_sha256"] == optical_hash
        and len(registered["jobs"]) == PLAN["max_new_captures"]
        and len(prediction["predictions"]) == PLAN["max_reference_projections"],
        "candidate reference must be complete before native capture",
    )
    captured = []
    with (
        EGL_LOCK.open("rb") as lease,
        patch.multiple(
            mujoco,
            mj_step=forbidden,
            mj_step1=forbidden,
            mj_step2=forbidden,
        ),
    ):
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        RAW.mkdir(exist_ok=False)
        try:
            model = mujoco.MjModel.from_xml_path(str(ASSET))
            native = MuJoCoRGBDCamera(mujoco, model, width=WIDTH, height=HEIGHT)
            try:
                renderer = GL.glGetString(GL.GL_RENDERER).decode()
                require(
                    renderer == prediction["renderer"] and int(model.vis.quality.offsamples) == 4,
                    "unregistered EGL renderer or MSAA",
                )
                for job in registered["jobs"]:
                    require(len(captured) < PLAN["max_new_captures"], "native budget exhausted")
                    captured.append(
                        snapshot(job, model, native, restore, registered["camera"], renderer)
                    )
            finally:
                native.close()
        finally:
            write(
                RAW / "index.json",
                {
                    "frames": captured,
                    "physics_steps": 0,
                    "source_sha256": sha(Path(__file__)),
                    "prediction_sha256": sha(PREDICTED),
                    "capture_input_sha256": sha(PHYSICAL),
                    "assembly_sha256": sha(ASSET),
                    "optical_input_sha256": optical_hash,
                },
            )
            write(
                RAW / "seal.json",
                {
                    "members": {p.name: sha(p) for p in sorted(RAW.iterdir()) if p.is_file()},
                },
            )


if __name__ == "__main__":
    capture()
