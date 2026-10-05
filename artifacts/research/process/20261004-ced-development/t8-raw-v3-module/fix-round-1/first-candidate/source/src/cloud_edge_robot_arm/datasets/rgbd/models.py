"""Shared, payload-free contracts for offline RGB-D evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def content_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def safe_component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value):
        raise ValueError("ID must be a safe opaque path component")
    return value


def safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or ":" in value
    ):
        raise ValueError("payload path must be normalized and relative to the dataset root")
    return value


SafeID = Annotated[str, AfterValidator(safe_component)]


class DurableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    schema_version: Literal["rgbd.dataset.v1"] = "rgbd.dataset.v1"


class DatasetConfig(DurableModel):
    dataset_id: SafeID
    groups: int = Field(default=100, ge=1, le=10000)
    seed: int = Field(default=0, ge=0)
    width: int = Field(default=320, ge=1, le=1280)
    height: int = Field(default=240, ge=1, le=720)
    model_path: str = "assets/robots/franka_panda/scene.xml"
    max_attempt_multiplier: int = Field(default=5, ge=1, le=5)
    min_free_bytes: int = Field(default=268435456, ge=0)
    max_bytes: int = Field(default=8589934592, gt=0)
    target_x: tuple[float, float] = (0.18, 0.55)
    target_y: tuple[float, float] = (-0.20, 0.28)
    half_size: tuple[float, float] = (0.025, 0.045)
    camera_height: tuple[float, float] = (1.2, 1.6)
    camera_x: tuple[float, float] = (0.30, 0.40)
    camera_y: tuple[float, float] = (-0.04, 0.04)
    camera_fovy: tuple[float, float] = (45, 55)
    light_intensity: tuple[float, float] = (0.65, 1.0)
    distractor_count: tuple[int, int] = (0, 3)
    depth_noise_m: tuple[float, ...] = (0.0, 0.002, 0.005)
    invalid_depth_fractions: tuple[float, ...] = (0.0, 0.1, 0.3)
    settle_steps: int = Field(default=120, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_ranges(self) -> DatasetConfig:
        for name in (
            "target_x",
            "target_y",
            "half_size",
            "camera_height",
            "camera_x",
            "camera_y",
            "camera_fovy",
            "light_intensity",
            "distractor_count",
        ):
            lo, hi = getattr(self, name)
            if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
                raise ValueError(f"{name} must be a finite ordered range")
        if self.half_size[0] <= 0 or self.camera_height[0] <= 0:
            raise ValueError("object size and camera height must be positive")
        if not 0 < self.camera_fovy[0] <= self.camera_fovy[1] < 180:
            raise ValueError("camera_fovy must lie inside (0, 180)")
        if not 0 <= self.light_intensity[0] <= self.light_intensity[1] <= 1:
            raise ValueError("light intensity must lie in [0, 1]")
        if not 0 <= self.distractor_count[0] <= self.distractor_count[1] <= 3:
            raise ValueError("distractor_count must lie in [0, 3]")
        if not self.depth_noise_m or any(not math.isfinite(v) or v < 0 for v in self.depth_noise_m):
            raise ValueError("depth noise choices must be finite and nonnegative")
        if not self.invalid_depth_fractions or any(
            not math.isfinite(v) or not 0 <= v <= 1 for v in self.invalid_depth_fractions
        ):
            raise ValueError("invalid depth fractions must lie in [0, 1]")
        return self

    @property
    def config_hash(self) -> str:
        return content_digest(self.model_dump(mode="json"))


class SceneSpec(DurableModel):
    group_id: SafeID
    scene_parameters: dict[str, Any]
    asset_family_hash: str = Field(min_length=1)
    seed: int = Field(ge=0)

    @field_validator("scene_parameters")
    @classmethod
    def json_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        canonical_json(value)
        return value

    @property
    def scene_hash(self) -> str:
        return content_digest(
            {"parameters": self.scene_parameters, "asset_family_hash": self.asset_family_hash}
        )

    @classmethod
    def from_parameters(
        cls, parameters: dict[str, Any], asset_family_hash: str, seed: int
    ) -> SceneSpec:
        physical = {
            k: v
            for k, v in parameters.items()
            if k not in {"camera", "light_intensity", "depth_noise_m", "invalid_depth_fraction"}
        }
        group = content_digest({"parameters": physical, "asset_family_hash": asset_family_hash})
        return cls(
            group_id=f"g-{group[:32]}",
            scene_parameters=parameters,
            asset_family_hash=asset_family_hash,
            seed=seed,
        )


class TrajectoryFrame(DurableModel):
    """One executed action bounded by two observations from the same episode."""

    observation: RGBDObservation
    action: ActionResult
    next_observation: RGBDObservation
    sim_time_s: float = Field(ge=0, allow_inf_nan=False)
    skill_boundary: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_episode_order(self) -> TrajectoryFrame:
        before, after = self.observation, self.next_observation
        if not before.episode_id or before.episode_id != after.episode_id:
            raise ValueError("trajectory observations must belong to the same episode")
        if after.frame_id == before.frame_id or after.sim_time_s <= before.sim_time_s:
            raise ValueError("next observation must be later and freshly captured")
        if abs(self.sim_time_s - after.sim_time_s) > 1e-9:
            raise ValueError("trajectory sim_time_s must match next observation")
        return self


class SampleRecord(DurableModel):
    sample_id: SafeID
    group_id: SafeID
    episode_id: SafeID
    frame_id: SafeID
    scene: SceneSpec
    observation_metadata: dict[str, Any]
    labels: dict[str, Any]
    physics_state_hash: str
    paths: dict[str, str] = Field(default_factory=dict)
    file_hashes: dict[str, str] = Field(default_factory=dict)
    content_hash: str = ""
    perceptual_hash: str = ""
    status: Literal["POSITIVE", "NEGATIVE"]
    source: str = "mujoco_camera"
    label_source: Literal["SIMULATOR_GROUND_TRUTH"] = "SIMULATOR_GROUND_TRUTH"
    execution_verified: Literal[False] = False
    captured_frame: CapturedFrame | None = Field(default=None, exclude=True, repr=False)
    raw_captured_frame: CapturedFrame | None = Field(default=None, exclude=True, repr=False)
    root: Path | None = Field(default=None, exclude=True, repr=False)

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for path in value.values():
            safe_relative_path(path)
        return value

    @model_validator(mode="after")
    def validate_metadata(self) -> SampleRecord:
        if self.group_id != self.scene.group_id:
            raise ValueError("sample and scene group IDs disagree")
        if any(
            key in self.observation_metadata
            for key in {"rgb_png_base64", "depth_float32_base64", "valid_mask_base64"}
        ):
            raise ValueError("observation metadata must not contain image payloads")
        canonical_json(self.observation_metadata)
        canonical_json(self.labels)
        return self

    @classmethod
    def from_capture(
        cls,
        scene: SceneSpec,
        frame: CapturedFrame,
        labels: dict[str, Any],
        *,
        raw_captured_frame: CapturedFrame | None = None,
    ) -> SampleRecord:
        observation = frame.observation
        metadata = observation.model_dump(
            mode="json", exclude={"rgb_png_base64", "depth_float32_base64", "valid_mask_base64"}
        )
        identity = content_digest(
            {"scene": scene.scene_hash, "observation": observation.checksum_sha256}
        )
        return cls(
            sample_id=f"s-{identity[:32]}",
            group_id=scene.group_id,
            episode_id=f"e-{scene.group_id}",
            frame_id=observation.frame_id,
            scene=scene,
            observation_metadata=metadata,
            labels=labels,
            physics_state_hash=frame.physics_state_hash,
            status="POSITIVE" if labels.get("positive") is True else "NEGATIVE",
            source=observation.source,
            captured_frame=frame,
            raw_captured_frame=raw_captured_frame,
        )


class DatasetManifest(DurableModel):
    dataset_id: SafeID
    config: DatasetConfig
    config_hash: str
    status: Literal["RUNNING", "COMPLETE", "INCOMPLETE", "CANCELLED", "BLOCKED", "FAILED"]
    requested_groups: int = Field(ge=1, le=10000)
    completed_groups: int = Field(default=0, ge=0)
    sample_count: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def validate_config(self) -> DatasetManifest:
        if self.dataset_id != self.config.dataset_id or self.config_hash != self.config.config_hash:
            raise ValueError("manifest/config mismatch")
        if self.requested_groups != self.config.groups:
            raise ValueError("manifest requested groups disagree with configuration")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("manifest timestamps must include timezone")
        return self


class QualityReport(DurableModel):
    valid: bool
    sample_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    positive_count: int = 0
    negative_count: int = 0
    split_counts: dict[str, int] = Field(default_factory=dict)
    duplicate_count: int = 0


class SplitManifest(DurableModel):
    seed: int = Field(ge=0)
    group_assignments: dict[str, Literal["train", "calibration", "selection", "test"]]
    sample_assignments: dict[str, Literal["train", "calibration", "selection", "test"]]
    counts: dict[str, int]
    duplicates: list[dict[str, Any]] = Field(default_factory=list)
    algorithm_version: str = "group-content-v1"
