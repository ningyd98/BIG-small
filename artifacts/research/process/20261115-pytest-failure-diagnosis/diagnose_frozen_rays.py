"""重建冻结初始状态，仅离线比较边缘像素射线与原深度，不更改渲染设置。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import cv2
import mujoco
import numpy as np
from replay_controller_prefix import inventory

from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
    NetworkDenyGuard,
    load_observation,
    load_v3_manifest,
)
from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot


class _NoCaptureDiagnosticBackend(MuJoCoPhysicsBackend):
    """仅本诊断跳过采集；保留原 reset 的姿态分支及物理路径，必须匹配冻结状态。"""

    def __init__(self):
        super().__init__()
        self.suppressed_sensor_updates = 0

    def _update_sensor_frame(self):
        self.suppressed_sensor_updates += 1


def diagnose(case, row: dict, root: Path) -> dict:
    """匹配原帧状态和标定后只查射线，实例几何仅用于事后诊断。"""
    assignment = case.json("scene-assignment.json")
    observation = load_observation(case, "component/frames/post-cloud")
    metadata = case.json("component/frames/post-cloud/observation.json")
    assert observation.frame_id == row["frame_id"]
    assert observation.checksum_sha256 == row["frame_checksum"]
    assert assignment["settle_steps"] == 120
    assert assignment["physics_dt_rational"] == [1, 240]
    asset = root / assignment["model_path"]
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == assignment["asset_sha256"]
    backend = _NoCaptureDiagnosticBackend()
    try:
        backend.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=assignment["seed"],
                domain_randomization=False,
                render_rgb=True,
                render_depth=True,
                camera_width=320,
                camera_height=240,
                physics_dt_s=1 / 240,
            )
        )
        backend.reset(
            physical_component_scenario(assignment["seed"], assignment["component_scene"])
        )
        MuJoCoSkillRobot(backend)
        backend.step(120)
        model, data = backend._model, backend._data
        initial = MuJoCoRGBDCamera._physics_state_hash(data)
        assert initial == metadata["physics_state_hash"]
        assert all(value == initial for value in metadata["pass_state_hashes"])
        transform = np.asarray(observation.camera_to_world).reshape(4, 4)
        camera = model.camera("rgbd").id
        assert np.array_equal(transform[:3, 3], data.cam_xpos[camera])
        rotation = data.cam_xmat[camera].reshape(3, 3) @ np.diag([1, -1, -1])
        assert np.array_equal(transform[:3, :3], rotation)
        fx, fy, cx, cy = observation.intrinsics
        focal = observation.height / 2 / math.tan(math.radians(float(model.cam_fovy[camera])) / 2)
        assert np.array_equal([fx, fy, cx, cy], [focal, focal, 159.5, 119.5])
        groups = mujoco.MjvOption().geomgroup.copy()

        def ray(x, y, dx=0.0, dy=0.0):
            optical = np.array([(x + dx - cx) / fx, (y + dy - cy) / fy, 1.0])
            direction = rotation @ optical
            scale = float(np.linalg.norm(direction))
            direction /= scale
            geom = np.array([-1], dtype=np.int32)
            distance = mujoco.mj_ray(model, data, transform[:3, 3], direction, groups, 1, -1, geom)
            name = model.geom(int(geom[0])).name if geom[0] >= 0 else None
            return {
                "offset_xy": [dx, dy],
                "geom_id": int(geom[0]),
                "geom_name": name,
                "distance_m": float(distance),
                "optical_z_m": float(distance / scale) if distance >= 0 else None,
            }

        shape = (observation.height, observation.width)
        ids = np.frombuffer(
            case.read("component/frames/post-cloud/instance_geom_ids.i32"), dtype="<i4"
        ).reshape(shape)
        depths = np.asarray(observation.depth_values()).reshape(shape)
        controls = []
        for name in ("object_geom", "table", "link4"):
            mask = ((ids == model.geom(name).id) & (depths > 0)).astype(np.uint8)
            interior = cv2.distanceTransform(mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            y, x = np.unravel_index(np.argmax(interior), shape)
            assert interior[y, x] > 0
            hit = ray(int(x), int(y))
            controls.append(
                {
                    "selection": "DEEPEST_VALID_INSTANCE_INTERIOR_OFFLINE_ONLY",
                    "stored_instance_label": name,
                    "xy": [int(x), int(y)],
                    "interior_distance_pixels": float(interior[y, x]),
                    "stored_depth_m": float(depths[y, x]),
                    "center_ray": hit,
                    "same_nearest_geom": hit["geom_name"] == name,
                    "ray_minus_stored_depth_m": hit["optical_z_m"] - depths[y, x]
                    if hit["optical_z_m"] is not None
                    else None,
                }
            )
        pixels = []
        for old in row["diagnostic_pixels"]:
            x, y = old["xy"]
            rays = []
            for dy in (-0.4, 0.0, 0.4):
                for dx in (-0.4, 0.0, 0.4):
                    rays.append(ray(x, y, dx, dy))
            pixels.append(
                {
                    "xy": old["xy"],
                    "stored_depth_m": old["depth_m"],
                    "stored_valid": old["valid"],
                    "stored_instance_label": old["offline_instance_label"],
                    "center_ray": rays[4],
                    "grid_hit_counts": dict(Counter(ray["geom_name"] for ray in rays)),
                    "grid_rays": rays,
                }
            )
        assert backend.total_physics_steps == 120
        assert MuJoCoRGBDCamera._physics_state_hash(data) == initial
        assert backend._camera is None  # 本次没有创建渲染器或执行捕获。
        return {
            "case": case.root.name,
            "frozen_frame_id": observation.frame_id,
            "frozen_physics_state_hash": initial,
            "initial_state_matches": True,
            "camera_calibration_matches": True,
            "query_state_unchanged": True,
            "initial_settle_steps": 120,
            "query_physics_steps": 0,
            "new_renders": 0,
            "sensor_updates_suppressed_for_offline_query": backend.suppressed_sensor_updates,
            "sensor_rng_not_replayed": True,
            "default_mjv_geomgroup": groups.tolist(),
            "interior_controls": controls,
            "interior_control_labels_all_match": all(c["same_nearest_geom"] for c in controls),
            "pixels": pixels,
            "bound_inputs": {
                name: {key: case.files[name][key] for key in ("sha256", "bytes")}
                for name in (
                    "scene-assignment.json",
                    "component/frames/post-cloud/observation.json",
                    "component/frames/post-cloud/rgb.png",
                    "component/frames/post-cloud/depth.f32",
                    "component/frames/post-cloud/valid_mask.u8",
                    "component/frames/post-cloud/instance_geom_ids.i32",
                )
            },
        }
    finally:
        backend.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v3", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("source_spec", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("pixel_diagnosis", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sources = inventory(args.root, args.source_spec)
    entry = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    helper = hashlib.sha256(Path(inventory.__code__.co_filename).read_bytes()).hexdigest()
    pixel_sha = hashlib.sha256(args.pixel_diagnosis.read_bytes()).hexdigest()
    selected = [
        row
        for row in json.loads(args.pixel_diagnosis.read_text())["cases"]
        if "diagnostic_pixels" in row
    ]
    assert len(selected) == 9
    with NetworkDenyGuard() as guard:
        manifest = load_v3_manifest(args.v3, args.snapshot)
        cases = [diagnose(manifest.cases[row["case"]], row, args.root) for row in selected]
    assert inventory(args.root, args.source_spec) == sources
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == entry
    assert hashlib.sha256(Path(inventory.__code__.co_filename).read_bytes()).hexdigest() == helper
    assert hashlib.sha256(args.pixel_diagnosis.read_bytes()).hexdigest() == pixel_sha
    output = {
        "scope": "OFFLINE_FROZEN_STATE_RAY_DIAGNOSIS_NOT_RENDER_CAUSALITY_OR_ADMISSION",
        "sources": sources,
        "entry_sha256": entry,
        "inventory_helper_sha256": helper,
        "pixel_diagnosis_sha256": pixel_sha,
        "new_models": 0,
        "network_attempts": guard.attempts,
        "new_renders": 0,
        "controller_skills_executed": 0,
        "total_initial_settle_steps": 9 * 120,
        "msaa_modified": False,
        "grid_is_actual_msaa_samples": False,
        "sensor_capture_suppressed_for_diagnostic": True,
        "analytic_ray_is_not_equivalent_to_rasterized_depth": True,
        "formal_research_acceptance": False,
        "cases": cases,
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"cases": len(cases), "pixels": sum(len(c["pixels"]) for c in cases)}))
