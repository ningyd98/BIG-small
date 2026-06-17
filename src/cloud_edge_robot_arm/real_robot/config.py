from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExecutionMode(StrEnum):
    SIMULATION = "SIMULATION"
    DRY_RUN = "DRY_RUN"
    HARDWARE_READ_ONLY = "HARDWARE_READ_ONLY"
    HARDWARE_LOW_SPEED = "HARDWARE_LOW_SPEED"
    HARDWARE_OPERATIONAL = "HARDWARE_OPERATIONAL"


class WorkspaceLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    @model_validator(mode="after")
    def validate_bounds(self) -> WorkspaceLimits:
        if self.x_min >= self.x_max or self.y_min >= self.y_max or self.z_min >= self.z_max:
            raise ValueError("workspace min bounds must be lower than max bounds")
        return self


class RealRobotConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    robot_vendor: str = Field(min_length=1)
    robot_model: str = Field(min_length=1)
    robot_serial: str = Field(min_length=1)
    controller_address: str = Field(min_length=1)
    ros_namespace: str = Field(min_length=1)
    planning_group: str = Field(min_length=1)
    end_effector_link: str = Field(min_length=1)
    base_link: str = Field(min_length=1)
    joint_names: list[str] = Field(min_length=1)
    velocity_scale: float = Field(gt=0, le=0.1)
    acceleration_scale: float = Field(gt=0, le=0.1)
    workspace_limits: WorkspaceLimits
    payload_limit_kg: float = Field(gt=0)
    emergency_stop_topic: str = Field(min_length=1)
    hardware_status_topic: str = Field(min_length=1)
    config_source: str = ""
    config_hash: str = ""

    @field_validator(
        "robot_vendor",
        "robot_model",
        "robot_serial",
        "controller_address",
        "ros_namespace",
        "planning_group",
        "end_effector_link",
        "base_link",
        "emergency_stop_topic",
        "hardware_status_topic",
        "config_source",
    )
    @classmethod
    def reject_placeholders(cls, value: str) -> str:
        if value and _contains_placeholder(value):
            raise ValueError("real robot configuration contains placeholder values")
        return value

    @field_validator("joint_names")
    @classmethod
    def joint_names_must_be_unique_and_not_placeholders(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("joint_names must be unique")
        if any(_contains_placeholder(item) for item in value):
            raise ValueError("joint_names contain placeholder values")
        return value

    @model_validator(mode="after")
    def reject_simulation_sources(self) -> RealRobotConfig:
        lower = self.config_source.lower()
        if "configs/phase9" in lower or "simulation" in lower or "simulator" in lower:
            raise ValueError("real robot configuration cannot use simulation config sources")
        return self

    def with_source(self, source: str, *, raw_payload: dict[str, object]) -> RealRobotConfig:
        if _contains_placeholder(source):
            raise ValueError("real robot configuration source contains placeholder values")
        payload = dict(raw_payload)
        payload.pop("config_hash", None)
        digest = stable_config_hash(payload)
        return self.model_copy(update={"config_source": source, "config_hash": digest})


class RealRobotRuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    runtime_profile: str = "test"
    execution_mode: ExecutionMode = ExecutionMode.DRY_RUN
    enable_real_robot: bool = False
    config: RealRobotConfig | None = None
    operator_confirmation_token: str | None = None
    local_start_parameter: str | None = None

    @model_validator(mode="after")
    def validate_real_hardware_settings(self) -> RealRobotRuntimeSettings:
        profile = self.runtime_profile.strip().lower()
        if self.execution_mode == ExecutionMode.SIMULATION:
            raise ValueError("simulation execution mode cannot instantiate real robot runtime")
        if self.execution_mode in {
            ExecutionMode.HARDWARE_READ_ONLY,
            ExecutionMode.HARDWARE_LOW_SPEED,
            ExecutionMode.HARDWARE_OPERATIONAL,
        }:
            if profile == "simulation":
                raise ValueError("simulation runtime_profile cannot access real robot hardware")
            if self.config is None:
                raise ValueError("hardware execution modes require real robot configuration")
        return self


def load_real_robot_config(path: Path) -> RealRobotConfig:
    raw_text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text)
    if not isinstance(loaded, dict):
        raise ValueError("real robot configuration must be a mapping")
    raw_payload = dict(loaded)
    config = RealRobotConfig.model_validate(raw_payload)
    return config.with_source(str(path), raw_payload=raw_payload)


def stable_config_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def redacted_config_payload(config: RealRobotConfig) -> dict[str, Any]:
    payload = config.model_dump(mode="json")
    for key in ("robot_serial", "controller_address"):
        payload[key] = "<redacted>"
    return payload


def _contains_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    placeholder_tokens = (
        "replace",
        "placeholder",
        "example_",
        "todo",
        "tbd",
        "changeme",
        "your_",
    )
    return any(token in lowered for token in placeholder_tokens)
