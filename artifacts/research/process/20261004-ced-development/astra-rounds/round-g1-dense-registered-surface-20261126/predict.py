"""Render dense optical references without access to raw measurements or physical labels."""

import fcntl
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
from OpenGL import GL
from register import (
    ASSET,
    EGL_LOCK,
    HEIGHT,
    NEEDLE_ARCHIVE,
    OPTICAL,
    OUT,
    PHYSICAL,
    PLAN,
    PLAN_PATH,
    REFERENCE_XML,
    ROOT,
    SCALE,
    WIDTH,
    buffered_xml,
    require,
)
from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
from scripts.graduation.perception_io import read, sha, write

PREDICTED = OUT / "prediction.json"
DATA_ROOT = ROOT / "experiments/results"


def blind_inputs_only():
    allowed = {OPTICAL, REFERENCE_XML, ASSET, EGL_LOCK, PREDICTED}

    def deny_raw(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(DATA_ROOT) and path not in allowed:
                raise PermissionError(f"unregistered input {path.name}")

    sys.addaudithook(deny_raw)
    denied = 0
    for path in (PHYSICAL, NEEDLE_ARCHIVE / "step-2112-4x-pin.npz"):
        try:
            path.read_bytes()
        except PermissionError:
            denied += 1
        else:
            raise ValueError("prediction opened a protected input")
    return denied


def forbid_integration(*_args, **_kwargs):
    raise RuntimeError("static comparison does not integrate")


def camera_for_projection(camera):
    fx, fy, _, _ = camera["intrinsics"]
    return SimpleNamespace(
        intrinsics=(fx * SCALE, fy * SCALE, (WIDTH - 1) / 2, (HEIGHT - 1) / 2),
        camera_to_world=camera["camera_to_world"],
        width=WIDTH,
        height=HEIGHT,
    )


def center_face(boxes, optics, pose, u, v):
    transform = np.asarray(optics.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = optics.intrinsics
    rotation = np.asarray(pose["rotation"])
    ray = transform[:3, :3] @ [(u - cx) / fx, (v - cy) / fy, 1.0]
    ray = ray @ rotation
    eye = (transform[:3, 3] - pose["center_m"]) @ rotation
    first = float("inf")
    identity = None
    for box in boxes:
        with np.errstate(divide="ignore", invalid="ignore"):
            left = (box.c - box.h - eye) / ray
            right = (box.c + box.h - eye) / ray
        entry, exit = np.minimum(left, right), np.maximum(left, right)
        axis = int(entry.argmax())
        z = float(entry[axis])
        if 0 < z < first and exit.min() >= z:
            first = z
            identity = [box.name, axis, -1 if ray[axis] > 0 else 1]
    return identity


def predict_job(reference, optics, job):
    pose = job["optical"]
    require(
        pose["frame_id"] == job["frame_id"] and pose["checksum_sha256"] == job["checksum_sha256"],
        "optical pose detached from its source",
    )
    reference.data.time = job["time_s"]
    begun = time.perf_counter_ns()
    rgb, z = reference.project(
        pose["center_m"],
        pose["rotation"],
        job["joints_rad"],
        job["fingers_m"],
    )
    elapsed = (time.perf_counter_ns() - begun) / 1e6
    native = reference.data.camera("rgbd")
    expect = np.asarray(optics.camera_to_world).reshape(4, 4)
    require(
        np.array_equal(native.xpos, expect[:3, 3])
        and np.array_equal(native.xmat.reshape(3, 3) * [1, -1, -1], expect[:3, :3])
        and int(reference.model.vis.quality.offsamples) == 4
        and reference.data.time == job["time_s"],
        "reference world optics or time differs",
    )
    result = []
    for original_u, original_v in job["pixels_original_uv"]:
        subpixels = []
        for j in range(SCALE):
            for i in range(SCALE):
                u, v = original_u * SCALE + i, original_v * SCALE + j
                require(0 < u < WIDTH - 1 and 0 < v < HEIGHT - 1, "dense patch outside image")
                roi = np.s_[v - 1 : v + 2, u - 1 : u + 2]
                subpixels.append(
                    {
                        "uv": [u, v],
                        "depth_m": z[roi].tolist(),
                        "rgb": rgb[roi].tolist(),
                        "interior": reference._first_interior_face(
                            (u, v), optics, pose, z[roi]
                        ).tolist(),
                        "center_face": center_face(reference.boxes, optics, pose, u, v),
                    }
                )
        result.append({"original_uv": [original_u, original_v], "subpixels": subpixels})
    return {
        "key": job["key"],
        "shutter_checksum_sha256": job["checksum_sha256"],
        "reference_rgb_depth_wall_ms": elapsed,
        "pixels": result,
    }


def run():
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl", "EGL required"
    )
    negatives = blind_inputs_only()
    optical = read(OPTICAL)
    require(
        optical["plan_sha256"] == sha(PLAN_PATH)
        and optical["reference_xml_sha256"] == sha(REFERENCE_XML)
        and optical["assembly_sha256"] == sha(ASSET) == PLAN["sha256"][PLAN["asset"]]
        and REFERENCE_XML.read_bytes() == buffered_xml()
        and len(optical["jobs"]) == PLAN["max_reference_projections"],
        "prediction registration or buffered reference XML differs",
    )
    source = "scripts/graduation/g1_complete_cv_carried_surface.py"
    require(sha(ROOT / source) == PLAN["sha256"][source], "production reference differs")
    optics = camera_for_projection(optical["camera"])
    with (
        EGL_LOCK.open("rb") as lease,
        patch.multiple(
            mujoco,
            mj_step=forbid_integration,
            mj_step1=forbid_integration,
            mj_step2=forbid_integration,
        ),
    ):
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reference = CarriedSurface(REFERENCE_XML, width=WIDTH, height=HEIGHT)
        try:
            predictions = [predict_job(reference, optics, job) for job in optical["jobs"]]
            renderer = GL.glGetString(GL.GL_RENDERER).decode()
        finally:
            reference.close()
    write(
        PREDICTED,
        {
            "source_sha256": sha(Path(__file__)),
            "optical_input_sha256": sha(OPTICAL),
            "renderer": renderer,
            "predictions": predictions,
            "blocked_file_controls": negatives,
            "rgb_passes": len(predictions),
            "depth_passes": len(predictions),
            "physics_steps": 0,
        },
    )


if __name__ == "__main__":
    run()
