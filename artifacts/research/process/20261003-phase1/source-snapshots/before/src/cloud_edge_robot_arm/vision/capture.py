"""Capture paired simulator images and retain auditable metric depth."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Literal

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame


def capture_simulated_observation(*, backend: Literal["MUJOCO", "ISAAC_SIM"] = "MUJOCO",
                                  scenario_id: str = "S01_NORMAL_STATIC", seed: int = 0) -> RGBDObservation:
    if backend == "MUJOCO":
        from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
        simulator = MuJoCoPhysicsBackend()
        source = "mujoco_camera"
    elif backend == "ISAAC_SIM":
        from cloud_edge_robot_arm.simulation.isaac.backend import IsaacSimBackend
        simulator = IsaacSimBackend()
        source = "isaac_camera"
    else:
        raise ValueError("RGBD_CAMERA_REQUIRED: Mock cannot provide real RGB-D observations")
    try:
        simulator.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        simulator.reset(PhysicalScenarioConfig.scenario(scenario_id, seed=seed))
        return observation_from_sensor_frame(simulator.get_sensor_frame(), source=source)
    finally:
        simulator.shutdown()


def save_observation(observation: RGBDObservation, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {"rgb": directory / "rgb.png", "depth": directory / "depth.f32",
             "depth_visualization": directory / "depth.png", "observation": directory / "observation.json"}
    paths["rgb"].write_bytes(base64.b64decode(observation.rgb_png_base64))
    paths["depth"].write_bytes(base64.b64decode(observation.depth_float32_base64))
    paths["depth_visualization"].write_bytes(base64.b64decode(observation.depth_png_base64()))
    metadata = {**observation.evidence(), "model_image_count": 0,
                "files": {name: path.name for name, path in paths.items() if name != "observation"}}
    paths["observation"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths
