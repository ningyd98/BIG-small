"""Freeze and collect the 54-cell r593 development experiment, without a teacher."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import ROOT, check_sources, pinned, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    BackendOperationBoundary,
    MuJoCoPhysicsBackend,
)
from cloud_edge_robot_arm.vision.marker_families import SIDE_PREPARE_ONLY_FAMILY
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

STEPS = (0, 1, 2, 4, 8, 12)
VIEWS = {
    "axial": ((0.35, 0.0, 1.4), None),
    "left": ((0.30, -0.08, 1.35), (0.45, 0.0, 0.04)),
    "right": ((0.40, 0.08, 1.35), (0.45, 0.0, 0.04)),
}
POSES = (
    (-0.03, -0.025, -0.20),
    (0.0, 0.0, 0.0),
    (0.03, 0.025, 0.20),
    (-0.025, 0.025, 0.15),
    (0.025, -0.025, -0.15),
    (0.01, 0.015, 0.30),
)
SOURCE_PATHS = (
    "scripts/graduation/perception_capture.py",
    "scripts/graduation/perception_io.py",
    "scripts/graduation/perception_pixels.py",
    "scripts/graduation/perception_score.py",
    "tests/test_graduation_perception.py",
    "scripts/phase7/frozen_vision.py",
    "src/cloud_edge_robot_arm/simulation/config.py",
    "src/cloud_edge_robot_arm/simulation/models.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    "src/cloud_edge_robot_arm/research/native_collection_grounding.py",
    "src/cloud_edge_robot_arm/research/native_geometry_calibration.py",
    "src/cloud_edge_robot_arm/vision/marker_families.py",
    "src/cloud_edge_robot_arm/vision/native_calibration.py",
    "src/cloud_edge_robot_arm/vision/observations.py",
    "src/cloud_edge_robot_arm/vision/pose_markers.py",
)


def allocated_cells() -> list[dict]:
    cells = []
    for p, (dx, dy, yaw) in enumerate(POSES, start=1):
        group = f"graduation-dev-r593-p{p}"
        for h, offset in enumerate((0.0, 0.05, 0.085)):
            for view in VIEWS:
                cell = f"{group}-h{h}-{view}"
                cells.append(
                    {
                        "id": cell,
                        "group": group,
                        "split": "exploration" if p <= 3 else "holdout",
                        "scene_id": cell,
                        "seed": 23110001 + len(cells),
                        "center_xyz_m": [0.45 + dx, dy, 0.035 + offset],
                        "xy_offset_m": [dx, dy],
                        "yaw_rad": yaw,
                        "initial_height_offset_m": offset,
                        "view": view,
                        "steps": list(STEPS),
                    }
                )
    return cells


def optical_transform(position: tuple, aim: tuple | None) -> np.ndarray:
    result = np.eye(4)
    result[:3, 3] = position
    if aim is None:
        result[:3, :3] = np.diag([1.0, -1.0, -1.0])
    else:
        forward = np.subtract(aim, position)
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0.0, 1.0, 0.0])
        right /= np.linalg.norm(right)
        result[:3, :3] = np.column_stack((right, np.cross(forward, right), forward))
    return result


def allocate(destination: Path, plan: Path) -> None:
    import cv2
    import mujoco
    import PIL
    from OpenGL import GL

    if os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("run the development allocation and capture with MUJOCO_GL=egl")
    context = mujoco.GLContext(320, 240)
    try:
        context.make_current()
        gl = {
            k: GL.glGetString(v).decode()
            for k, v in {
                "vendor": GL.GL_VENDOR,
                "renderer": GL.GL_RENDERER,
                "version": GL.GL_VERSION,
            }.items()
        }
    finally:
        context.free()
    geometry = geometry_registration(marker_family_id=SIDE_PREPARE_ONLY_FAMILY)
    paths = (*SOURCE_PATHS, geometry["asset_path"])
    views = {
        name: {
            "position_m": position,
            "look_at_m": aim,
            "optical_to_world": optical_transform(position, aim).ravel().tolist(),
        }
        for name, (position, aim) in VIEWS.items()
    }
    write(
        destination,
        {
            "schema": "graduation.r593.allocation.v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "baseline_commit": "6416a6cc4b1b087c17cf1c738b202e8f28421e2a",
            "astra_plan_file_sha256": sha(plan),
            "cells": allocated_cells(),
            "geometry": geometry,
            "views": views,
            "dt_rational": [1, 240],
            "array_shape_hw": [240, 320],
            "sources_sha256": {p: sha(ROOT / p) for p in paths},
            "runtime": {
                "python": platform.python_version(),
                "mujoco": mujoco.__version__,
                "opencv": cv2.__version__,
                "numpy": np.__version__,
                "pillow": PIL.__version__,
                "gl": gl,
                "free_disk_bytes": shutil.disk_usage(destination.parent).free,
            },
            "analysis": {
                "primary": "SUBPIX",
                "paired_comparator": "NONE",
                "metrics": [
                    "object_top_center_3d_m",
                    "object_center_3d_m",
                    "marker_center_3d_m",
                    "marker_optical_depth_abs_m",
                    "orientation_angle_rad",
                    "full_rigid_max_m",
                ],
                "unit": "placement group",
                "group_counts": {"exploration": 3, "holdout": 3},
                "coverage_denominator": (
                    "all allocated frames, including capture and decoder failures"
                ),
                "quantile": "numpy linear sample quantile, observed samples only",
                "view_comparison": (
                    "same placement, initial height and step; compare coverage and "
                    "common-pair top-center errors to axial"
                ),
                "bias_source": "graduation-dev-r593-p2-h0-axial/step-0",
                "bias_mm": [-10, -5, 0, 5, 10, None],
                "truth_access": "only after pixel-decision seal",
                "online_facts": {"object_lifted": "UNKNOWN", "object_stable": "UNKNOWN"},
                "formal_claims": 0,
                "teacher_attempts": 0,
                "task_model_calls": 0,
                "hardware_actions": 0,
            },
        },
    )


def validate_camera(frame: RGBDObservation, cell: dict, allocation: dict) -> None:
    camera = allocation["geometry"]["camera"]
    actual = np.array(frame.camera_to_world).reshape(4, 4)
    expected = np.array(allocation["views"][cell["view"]]["optical_to_world"]).reshape(4, 4)
    intrinsics = np.array(frame.intrinsics)
    fingerprint = hashlib.sha256(np.r_[intrinsics, actual.ravel()].astype("<f8").tobytes())
    if not (
        frame.scene_id == cell["scene_id"]
        and frame.episode_id
        and frame.source == "mujoco_camera"
        and (frame.width, frame.height) == (camera["width"], camera["height"])
        and np.array_equal(intrinsics, camera["intrinsics"])
        and np.allclose(actual, expected, atol=1e-12, rtol=0)
        and frame.calibration_version == fingerprint.hexdigest()[:16]
        and (cell["view"] != "axial" or frame.calibration_version == camera["calibration_version"])
    ):
        raise ValueError("camera differs from allocated view or frame metadata")


def cell_observer(capture_count: Counter, source: dict):
    def observe(event: BackendOperationBoundary) -> None:
        if event.kind != "CAPTURE" or event.phase != "END":
            return
        capture_count["camera_acquisitions"] += 1
        if event.result is None or event.error_type:
            capture_count["capture_failures"] += 1
            return
        hashes = list(event.result["pass_state_hashes"])
        capture_count["render_passes"] += len(hashes)
        source.update(
            {
                "step": event.physics_step,
                "frame_id": event.result["sensor_frame"]["frame_id"],
                "pass_state_hashes": hashes,
                "operation_id": event.operation_id,
            }
        )

    return observe


def capture(allocation_path: Path, allocation_sha: str, output: Path) -> None:
    alloc = pinned(allocation_path, allocation_sha)
    check_sources(alloc)
    if alloc["cells"] != allocated_cells() or os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("unexpected allocation or GL backend")
    output.mkdir()
    pixels = output / "pixels"
    pixels.mkdir()
    truth_dir = output / "offline-truth"
    truth_dir.mkdir()
    rows, truths, outcomes = [], [], []
    for cell in alloc["cells"]:
        backend = MuJoCoPhysicsBackend()
        config = SimulatorConfig(
            model_path=str(ROOT / alloc["geometry"]["asset_path"]),
            seed=cell["seed"],
            physics_dt_s=1 / 240,
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
        )
        outcome = {"cell_id": cell["id"], "captured_steps": [], "capture_errors": []}
        capture_count = Counter()
        source = {}

        observe = cell_observer(capture_count, source)
        try:
            backend.initialize(config)
            with backend.observe_operation_boundaries(observe), backend.sensor_capture_on_demand():
                x, y, z = cell["center_xyz_m"]
                backend.reset(
                    PhysicalScenarioConfig(
                        scenario_id=cell["scene_id"],
                        seed=cell["seed"],
                        object_pose=Pose(x=x, y=y, z=z),
                        object_yaw_rad=cell["yaw_rad"],
                    )
                )
                if cell["view"] != "axial":
                    position, aim = VIEWS[cell["view"]]
                    backend.set_camera_position(position, look_at_m=aim)
                for step in cell["steps"]:
                    remaining = step - backend.total_physics_steps
                    if remaining:
                        backend.step(remaining)
                    sensor = backend.capture_sensor_frame()
                    frame = observation_from_sensor_frame(sensor, source="mujoco_camera")
                    validate_camera(frame, cell, alloc)
                    state = backend.current_physics_observation()
                    if not (
                        len(source["pass_state_hashes"]) == 2
                        and len(set(source["pass_state_hashes"])) == 1
                        and source["frame_id"] == frame.frame_id
                        and source["step"] == state.physics_step == step
                        and state.episode_id == frame.episode_id
                        and state.sim_time_s == frame.sim_time_s
                        and abs(frame.sim_time_s - step / 240) < 1e-12
                    ):
                        raise ValueError("RGB-D pass or physics acquisition mismatch")
                    key = {
                        "cell_id": cell["id"],
                        "step": step,
                        "frame_id": frame.frame_id,
                        "scene_id": frame.scene_id,
                        "episode_id": frame.episode_id,
                        "sim_time_s": frame.sim_time_s,
                        "checksum_sha256": frame.checksum_sha256,
                    }
                    name = f"{cell['id']}-s{step:02}.json"
                    with (pixels / name).open("x") as stream:
                        stream.write(frame.model_dump_json())
                    rows.append(
                        {
                            **key,
                            "file": name,
                            "sha256": sha(pixels / name),
                            "calibration_version": frame.calibration_version,
                            "rgbd_render_state_sha256": list(source["pass_state_hashes"]),
                            "capture_operation_id": source["operation_id"],
                        }
                    )
                    truths.append(
                        {
                            **key,
                            "object_center_world_m": state.object_geom_position_m,
                            "rotation_to_world": state.object_geom_rotation_row_major,
                            "half_extent_m": state.object_half_extent_m,
                        }
                    )
                    outcome["captured_steps"].append(step)
            if backend.operation_observer_failures:
                raise ValueError("development capture observer failed")
        except Exception as exc:
            outcome["capture_errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            outcome["physics_steps"] = backend.total_physics_steps
            outcome["commands"] = [r["type"] for r in backend.command_records]
            backend.shutdown()
        outcome["camera_counts"] = dict(capture_count)
        outcomes.append(outcome)
    write(
        pixels / "index.json",
        {
            "allocation_sha256": allocation_sha,
            "geometry": alloc["geometry"],
            "frames": rows,
            "cells": outcomes,
        },
    )
    write(truth_dir / "states.json", {"allocation_sha256": allocation_sha, "states": truths})
    write(
        output / "capture-seal.json",
        {
            "allocation_sha256": allocation_sha,
            "pixel_index_sha256": sha(pixels / "index.json"),
            "offline_states_sha256": sha(truth_dir / "states.json"),
            "allocated": 324,
            "captured": len(rows),
            "failed_or_missing": 324 - len(rows),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True, dest="command")
    a = sub.add_parser("allocate")
    a.add_argument("--plan", required=True, type=Path)
    a.add_argument("--output", required=True, type=Path)
    c = sub.add_parser("capture")
    c.add_argument("--allocation", required=True, type=Path)
    c.add_argument("--allocation-sha256", required=True)
    c.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "allocate":
        allocate(args.output, args.plan)
    else:
        capture(args.allocation, args.allocation_sha256, args.output)


if __name__ == "__main__":
    main()
