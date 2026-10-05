"""Task 9 contracts with a closed, provenance-bearing online feature schema."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction

FeatureSource = Literal["IMAGE", "DEPTH", "CALIBRATION", "PROPRIOCEPTION", "ESTIMATOR"]
FEATURE_SOURCES: Mapping[str, FeatureSource] = MappingProxyType(
    {
        "invalid_depth_fraction": "DEPTH",
        "depth_median_m": "DEPTH",
        "depth_dispersion_m": "DEPTH",
        "pixel_consistency": "IMAGE",
        "calibration_residual_m": "CALIBRATION",
        "calibration_valid": "CALIBRATION",
        "calibration_fingerprint": "CALIBRATION",
        "motion_pair_valid": "ESTIMATOR",
        "observed_motion_m_s": "ESTIMATOR",
        "frame_interval_s": "ESTIMATOR",
    }
)
ACTIONS = tuple(action.value for action in DecisionAction)


@dataclass(frozen=True)
class FeatureValue:
    value: float
    source: FeatureSource

    def __post_init__(self) -> None:
        if self.source not in {"IMAGE", "DEPTH", "CALIBRATION", "PROPRIOCEPTION", "ESTIMATOR"}:
            raise ValueError("online feature source must be observable")
        if not math.isfinite(self.value):
            raise ValueError("online features must be finite")


@dataclass(frozen=True)
class RiskFeatures:
    values: Mapping[str, FeatureValue]
    observation_id: str

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ValueError("observation identity is required")
        for key, value in self.values.items():
            if key not in FEATURE_SOURCES or value.source != FEATURE_SOURCES[key]:
                raise ValueError(f"unapproved online feature or source: {key}")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True)
class RiskEstimate:
    failure_probability: float | None
    failure_probability_by_action: Mapping[str, float | None]
    geometric_error_bound_m: float | None
    motion_bound_m_s: float | None
    status: Literal["VALID", "UNKNOWN"]


@dataclass(frozen=True)
class RiskModelArtifact:
    model_hash: str
    model_path: str
    calibration_path: str
    fit_group_ids: tuple[str, ...]
    calibration_group_ids: tuple[str, ...]
    feature_schema: Mapping[str, FeatureSource]
