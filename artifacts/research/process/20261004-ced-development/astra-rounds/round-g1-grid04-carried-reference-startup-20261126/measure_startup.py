"""Measure the first archived-frame carried-surface reference, without live capture."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation import g1_complete_cv_carried_surface as carried_module
from scripts.graduation import g1_complete_cv_clearance as clearance_module

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
PLAN = json.loads((HERE / "plan.json").read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deny(*args, **kwargs):
    raise RuntimeError("reference-only experiment attempted a native exposure or integration")


def inputs():
    for key, expected in PLAN["inputs"].items():
        require(sha(ROOT / key) == expected, f"frozen reference source changed: {key}")
    for module in (carried_module, clearance_module):
        source = Path(module.__file__).resolve()
        require(sha(source) == PLAN["inputs"][source.relative_to(ROOT).as_posix()], "wrong import")
    parent = HERE.parent / "round-g1-grid04-2384-surface-attribution-20261126/attribute_surface.py"
    spec = importlib.util.spec_from_file_location("sealed_surface_reader", parent)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    return prior


def measure(prior, condition):
    import mujoco.renderer as renderer_module

    require(
        mujoco.__version__ == "3.3.7"
        and os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "original MuJoCo EGL required",
    )
    model, asset, rows = prior.load()
    row = rows[PLAN["source_tick"]]
    expected = row.recorded["current"]["depth"]
    reference_dir = prior.OUT / "reference-projections"
    seal = prior.read(reference_dir / "seal.json")
    with np.load(reference_dir / "2384.npz", allow_pickle=False) as data:
        robot = prior.RasterBuffer(data["robot"])
        archived_rgb, archived_depth = data["carried_rgb"], data["carried_depth"]
    carried, arrays = [], []
    times = defaultdict(list)
    original_class = carried_module.CarriedSurface
    renderer = mujoco.Renderer
    render, read_pixels = renderer_module._render.mjr_render, renderer_module._render.mjr_readPixels

    def clock(name, method, limit=None):
        def timed(*args, **kwargs):
            if limit is not None:
                require(len(times[name]) < limit, f"registered {name} call count exceeded")
            start = perf_counter_ns()
            result = method(*args, **kwargs)
            times[name].append((perf_counter_ns() - start) / 1e6)
            return result

        return timed

    def create_renderer(*args, **kwargs):
        ref = clock("renderer_constructor", renderer, limit=1)(*args, **kwargs)
        ref.update_scene = clock("scene_update", ref.update_scene, limit=1)
        ref.render = clock("completed_render_with_readback", ref.render, limit=2)
        return ref

    def create_reference(*args, **kwargs):
        ref = clock("carried_constructor", original_class, limit=1)(*args, **kwargs)
        carried.append(ref)
        gl = {
            key: GL.glGetString(value).decode()
            for key, value in (
                ("version", GL.GL_VERSION),
                ("renderer", GL.GL_RENDERER),
                ("vendor", GL.GL_VENDOR),
            )
        }
        require(gl == seal["graphics"], "frozen EGL renderer differs")
        original = ref.project

        def project(*values):
            rgb, depth = clock("projection", original, limit=1)(*values)
            arrays.append((rgb, depth))
            return rgb, depth

        ref.project = project
        ref.explain = clock("carried_explain", ref.explain, limit=1)
        return ref

    def call():
        precreated = create_reference(asset) if condition == "precreated" else None
        start = perf_counter_ns()
        result = prior.changed(model, row, robot, precreated)
        times["changed_surfaces"].append((perf_counter_ns() - start) / 1e6)
        return result

    with (
        patch.object(carried_module, "CarriedSurface", create_reference),
        patch.object(mujoco, "Renderer", create_renderer),
        patch.object(
            renderer_module._render, "mjr_render", clock("render_submit", render, limit=2)
        ),
        patch.object(
            renderer_module._render,
            "mjr_readPixels",
            clock("synchronous_pixel_read", read_pixels, limit=2),
        ),
    ):
        try:
            result = call()
        finally:
            for ref in carried:
                ref.close()
    require(
        len(arrays) == 1 and len(times["completed_render_with_readback"]) == 2, "projection count"
    )
    rgb, depth = arrays[0]
    require(
        np.array_equal(rgb, archived_rgb) and np.array_equal(depth, archived_depth),
        "reference framebuffer differs from sealed original",
    )
    require(
        result == expected
        and result["carried_surface_evidence"]["checked"] == PLAN["expected_checked"]
        and result["carried_surface_evidence"]["explained"] == PLAN["expected_explained"],
        "original near-surface rejection changed",
    )
    return {
        "condition": condition,
        "tick": PLAN["source_tick"],
        "frame_id": row.frame.frame_id,
        "renderer": seal["graphics"],
        "times_ms": dict(times),
        "rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
        "depth_sha256": hashlib.sha256(depth.tobytes()).hexdigest(),
        "depth_decision": result,
        "integrations": 0,
        "native_captures": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("condition", choices=("preflight", "cold", "precreated"))
    args = parser.parse_args()
    prior = inputs()
    cv2.setNumThreads(1)
    with (
        patch.multiple(mujoco, mj_step=deny, mj_step1=deny, mj_step2=deny),
        patch.multiple(MuJoCoRGBDCamera, capture=deny, _capture=deny),
        patch.object(MuJoCoPhysicsBackend, "capture_sensor_frame", deny),
    ):
        if args.condition == "preflight":
            with patch.multiple(mujoco, Renderer=deny, mjr_render=deny):
                _, _, rows = prior.load()
                require(PLAN["source_tick"] in rows, "registered frame missing")
            print(json.dumps({"preflight_passed": True, "new_captures": 0, "renders": 0}))
            return
        with prior.LOCK.open("rb") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            answer = measure(prior, args.condition)
    print(json.dumps(answer, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
