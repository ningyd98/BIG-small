"""Capture paired simulator images and retain auditable metric depth."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cloud_edge_robot_arm.simulation.backend import SimulatorBackend
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame


@dataclass(frozen=True)
class CapturedFrame:
    observation: RGBDObservation
    # Flattened row-major MuJoCo geom IDs; -1 is background. Names map IDs to MJCF geoms.
    instance_ids: tuple[int, ...]
    instance_labels: dict[int, str]
    physics_state_hash: str
    pass_state_hashes: tuple[str, ...]


class MuJoCoCaptureSession:
    """Reuse one renderer while explicitly capturing fresh frames from one episode."""

    def __init__(self, config: SimulatorConfig) -> None:
        self._config = config.model_copy(update={"render_rgb": True, "render_depth": True})
        self._backend = MuJoCoPhysicsBackend()
        self._open = False

    def __enter__(self) -> MuJoCoCaptureSession:
        try:
            self._backend.initialize(self._config)
            self._backend.reset(
                PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=self._config.seed)
            )
        except BaseException:
            self._backend.shutdown()
            raise
        self._open = True
        return self

    def __exit__(self, *_exc: object) -> None:
        self._open = False
        self._backend.shutdown()

    def capture(self) -> RGBDObservation:
        return self.capture_with_instances().observation

    def capture_with_instances(self) -> CapturedFrame:
        if not self._open:
            raise RuntimeError("MuJoCo capture session is closed")
        frame, ids, labels, pass_hashes = self._backend.capture_sensor_frame_with_instances()
        if len(set(pass_hashes)) != 1:
            raise RuntimeError("render passes observed different physics states")
        return CapturedFrame(
            observation=observation_from_sensor_frame(frame, source="mujoco_camera"),
            instance_ids=ids,
            instance_labels=labels,
            physics_state_hash=pass_hashes[0],
            pass_state_hashes=pass_hashes,
        )


def capture_simulated_observation(
    *,
    backend: Literal["MUJOCO", "ISAAC_SIM"] = "MUJOCO",
    scenario_id: str = "S01_NORMAL_STATIC",
    seed: int = 0,
) -> RGBDObservation:
    simulator: SimulatorBackend
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
    paths = {
        "rgb": directory / "rgb.png",
        "depth": directory / "depth.f32",
        "depth_visualization": directory / "depth.png",
        "observation": directory / "observation.json",
    }
    paths["rgb"].write_bytes(base64.b64decode(observation.rgb_png_base64))
    paths["depth"].write_bytes(base64.b64decode(observation.depth_float32_base64))
    paths["depth_visualization"].write_bytes(base64.b64decode(observation.depth_png_base64()))
    metadata = {
        **observation.evidence(),
        "model_image_count": 0,
        "files": {name: path.name for name, path in paths.items() if name != "observation"},
    }
    paths["observation"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def save_captured_frame(frame: CapturedFrame, directory: Path) -> dict[str, Path]:
    """Persist raw registered inputs and offline-only geom IDs for audit."""
    paths = save_observation(frame.observation, directory)
    paths["mask"] = directory / "valid_mask.u8"
    paths["instances"] = directory / "instance_geom_ids.i32"
    paths["mask"].write_bytes(frame.observation.valid_mask_bytes())
    paths["instances"].write_bytes(struct.pack(f"<{len(frame.instance_ids)}i", *frame.instance_ids))
    metadata = json.loads(paths["observation"].read_text(encoding="utf-8"))
    metadata.update(
        {
            "physics_state_hash": frame.physics_state_hash,
            "pass_state_hashes": list(frame.pass_state_hashes),
            "instance_id_convention": "MuJoCo geom ID, -1 background; row-major int32",
            "instance_labels": {str(key): value for key, value in frame.instance_labels.items()},
        }
    )
    metadata["files"].update(
        {
            "mask": paths["mask"].name,
            "instances": paths["instances"].name,
        }
    )
    paths["observation"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths
