from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RandomizationLevel(StrEnum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class SimulatorConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    backend: str = "mujoco"
    headless: bool = True
    robot_profile: str = "franka_panda"
    scene_profile: str = "desktop_pick_place"
    seed: int = 0
    physics_dt_s: float = Field(default=0.0041666667, gt=0)
    control_dt_s: float = Field(default=0.02, gt=0)
    sensor_dt_s: float = Field(default=0.0333333333, gt=0)
    realtime_factor: float = Field(default=0.0, ge=0)
    max_episode_s: float = Field(default=60.0, gt=0)
    domain_randomization: bool = True
    randomization_level: RandomizationLevel = RandomizationLevel.NONE
    render_rgb: bool = False
    render_depth: bool = False
    record_video: bool = False
    artifact_dir: Path = Path("experiments/results/phase9")
    model_path: str = "assets/robots/franka_panda/scene.xml"

    @model_validator(mode="after")
    def validate_time_grid(self) -> SimulatorConfig:
        if self.control_dt_s < self.physics_dt_s:
            raise ValueError("control_dt_s must be greater than or equal to physics_dt_s")
        if self.sensor_dt_s < self.physics_dt_s:
            raise ValueError("sensor_dt_s must be greater than or equal to physics_dt_s")
        return self


def load_simulator_config(path: Path) -> SimulatorConfig:
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SimulatorConfig.model_validate(payload)
