"""Acquire the bounded four-way same-optical-center comparison, without integrating."""

import fcntl
import inspect
import os
import time
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from OpenGL import GL
from rays import (
    OUT,
    PLAN,
    PLAN_PATH,
    ROOT,
    models,
    original_inputs,
    prohibited,
    read_cpu,
    require,
    restore,
)
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

RAW = OUT / "capture-01"
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def raw_frame(frame, folder, record, shape):
    height, width = shape
    require(
        (frame.height, frame.width) == shape
        and frame.rgb is not None
        and frame.valid_mask is not None
        and not frame.ground_truth_used_for_control,
        "raw native sensor packet dimensions or source differ",
    )
    color = np.frombuffer(frame.rgb, np.uint8).reshape(height, width, 3)
    depth = np.asarray(frame.depth, dtype="<f4").reshape(shape)
    valid = np.frombuffer(frame.valid_mask, np.uint8).reshape(shape)
    require(
        np.isfinite(depth).all()
        and (depth >= 0).all()
        and np.array_equal(valid, (depth > 0).astype(np.uint8)),
        "native axis depth and mask differ",
    )
    path = folder / record["file"]
    with path.open("xb") as stream:
        np.savez_compressed(stream, rgb=color, depth_m=depth, valid=valid)
    return depth, valid, sha(path)


def start():
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "native EGL required before imports",
    )
    camera, source, old = original_inputs()
    runtime = ROOT / PLAN["runtime"]
    camera_source = Path(inspect.getfile(MuJoCoRGBDCamera)).resolve()
    require(
        camera_source == runtime / "src/cloud_edge_robot_arm/simulation/mujoco/camera.py"
        and sha(camera_source) == old["verified_native_source_sha256"]
        and mujoco.__version__ == "3.3.7"
        and read(OUT / "rays.json") == read_cpu(),
        "camera implementation or CPU prerequisite differs",
    )
    return camera, source, old


def capture():
    camera, source, archive = start()
    records = []
    with (
        LOCK.open("rb") as lease,
        patch.multiple(
            mujoco,
            mj_step=prohibited,
            mj_step1=prohibited,
            mj_step2=prohibited,
        ),
    ):
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        RAW.mkdir(exist_ok=False)
        registration = RAW / "registration.json"
        write(
            registration,
            {
                "driver_sha256": sha(Path(__file__)),
                "plan_sha256": sha(PLAN_PATH),
                "cpu_sha256": sha(OUT / "rays.json"),
                "original_optics": camera,
                "width_height_scales": PLAN["grids"],
            },
        )
        try:
            # The entire original 320 control is closed before the diagnostic 4x grid.
            for scale in PLAN["grids"]:
                width, height = (dimension * scale for dimension in PLAN["original_dimensions"])
                pair = models()
                for step, original in source.items():
                    frames = {}
                    for key, model in pair.items():
                        require(len(records) < PLAN["gpu_capture_limit"], "frame budget exhausted")
                        data, optic = restore(model, original, camera)
                        identity = MuJoCoRGBDCamera._physics_state_hash(data)
                        native = MuJoCoRGBDCamera(mujoco, model, width=width, height=height)
                        try:
                            renderer = GL.glGetString(GL.GL_RENDERER).decode()
                            require(
                                renderer == archive["gpu"]
                                and int(model.vis.quality.offsamples) == 4,
                                "original renderer or MSAA differs",
                            )
                            began = time.perf_counter_ns()
                            frame = native.capture(
                                data,
                                rng=np.random.default_rng(PLAN["noise_seed_offset"] + step),
                                noise_std_m=PLAN["noise_std_m"],
                                scene_id=f"g1.development.same-view.t02/{key}",
                                episode_id=f"static-{step}-{scale}x",
                            )
                            ended = time.perf_counter_ns()
                            require(
                                identity == MuJoCoRGBDCamera._physics_state_hash(data)
                                and frame.sim_time_s == data.time == original["time_s"]
                                and np.array_equal(frame.camera_to_world, optic.ravel())
                                and np.allclose(
                                    frame.intrinsics,
                                    (
                                        camera["intrinsics"][0] * scale,
                                        camera["intrinsics"][1] * scale,
                                        (width - 1) / 2,
                                        (height - 1) / 2,
                                    ),
                                    atol=1e-12,
                                    rtol=0,
                                )
                                and (
                                    scale != 1
                                    or frame.calibration_version == camera["calibration_version"]
                                ),
                                "physics, original optical center or diagnostic projection changed",
                            )
                            record = {
                                "step": step,
                                "scale": scale,
                                "model": key,
                                "file": f"step-{step}-{scale}x-{key}.npz",
                                "frame_id": frame.frame_id,
                                "original_frame_id": original["original_frame_id"],
                                "original_checksum_sha256": original["original_checksum_sha256"],
                                "state_sha256": identity,
                                "source_time_s": frame.sim_time_s,
                                "width": width,
                                "height": height,
                                "calibration_version": frame.calibration_version,
                                "intrinsics": frame.intrinsics,
                                "camera_to_world": frame.camera_to_world,
                                "renderer": renderer,
                                "msaa": int(model.vis.quality.offsamples),
                                "seed": PLAN["noise_seed_offset"] + step,
                                "noise_std_m": PLAN["noise_std_m"],
                                "capture_ns": ended - began,
                            }
                            depth, valid, record["file_sha256"] = raw_frame(
                                frame,
                                RAW,
                                record,
                                (height, width),
                            )
                            records.append(record)
                            frames[key] = depth, valid
                        finally:
                            native.close()
                    bare, pin = frames["bare"], frames["pin"]
                    require(np.array_equal(bare[1], pin[1]), "paired noise masks differ")
                    if scale == 1:
                        diff = abs(bare[0] - pin[0])
                        past = original["old_match"]
                        require(
                            int(np.count_nonzero(diff)) == past["different_depth_pixels"]
                            and abs(float(diff.max()) - past["peak_depth_delta_m"]) < 1e-6,
                            "320 native control does not reproduce the original depth comparison",
                        )
                    print(step, scale, float(abs(bare[0] - pin[0]).max()), flush=True)
        finally:
            write(RAW / "index.json", {"frames": records, "new_physics_steps": 0})
            write(
                RAW / "seal.json",
                {
                    "members": {p.name: sha(p) for p in sorted(RAW.iterdir()) if p.is_file()},
                },
            )


if __name__ == "__main__":
    capture()
