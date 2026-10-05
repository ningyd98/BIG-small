"""Deterministic, per-parameter domain-randomization sampling.

The sampler is simulator-neutral.  A sample is created once and then mapped to
MuJoCo and Isaac Lab so paired runs consume exactly the same physical values.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from cloud_edge_robot_arm.simulation.config import RandomizationLevel


class RandomizationDistribution(StrEnum):
    UNIFORM = "UNIFORM"
    NORMAL = "NORMAL"
    FIXED = "FIXED"


class RandomizationRangeMode(StrEnum):
    """How a configured range interacts with the legacy global DR level."""

    LEVEL_SCALED = "LEVEL_SCALED"
    ABSOLUTE = "ABSOLUTE"


@dataclass(frozen=True)
class ParameterRandomizationSpec:
    name: str
    enabled: bool
    distribution: RandomizationDistribution
    nominal: float
    minimum: float
    maximum: float
    unit: str
    range_mode: RandomizationRangeMode = RandomizationRangeMode.LEVEL_SCALED
    mean: float | None = None
    std: float | None = None

    def validate(self) -> None:
        values = [self.nominal, self.minimum, self.maximum]
        if self.mean is not None:
            values.append(self.mean)
        if self.std is not None:
            values.append(self.std)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"randomization parameter {self.name} must be finite")
        if self.minimum > self.maximum:
            raise ValueError(f"randomization parameter {self.name} has min > max")
        if not self.minimum <= self.nominal <= self.maximum:
            raise ValueError(f"randomization parameter {self.name} nominal is outside its range")
        if self.distribution == RandomizationDistribution.NORMAL:
            if self.std is None or self.std <= 0:
                raise ValueError(f"randomization parameter {self.name} requires std > 0")
            mean = self.nominal if self.mean is None else self.mean
            if not self.minimum <= mean <= self.maximum:
                raise ValueError(f"randomization parameter {self.name} mean is outside its range")


@dataclass(frozen=True)
class RandomizedParameter:
    name: str
    value: float
    unit: str
    source: str
    distribution: RandomizationDistribution = RandomizationDistribution.UNIFORM
    requested_min: float = 0.0
    requested_max: float = 0.0
    nominal: float = 0.0
    parameter_seed: int = 0


@dataclass(frozen=True)
class RandomizationSample:
    version: str
    level: RandomizationLevel
    seed: int
    parameters: dict[str, RandomizedParameter]

    @property
    def values(self) -> dict[str, float]:
        return {name: parameter.value for name, parameter in self.parameters.items()}

    def to_jsonable(self) -> dict[str, object]:
        return {
            "version": self.version,
            "level": self.level.value,
            "seed": self.seed,
            "parameters": {
                name: {
                    "value": parameter.value,
                    "unit": parameter.unit,
                    "source": parameter.source,
                    "distribution": parameter.distribution.value,
                    "requested_min": parameter.requested_min,
                    "requested_max": parameter.requested_max,
                    "nominal": parameter.nominal,
                    "parameter_seed": parameter.parameter_seed,
                }
                for name, parameter in sorted(self.parameters.items())
            },
        }


class DomainRandomizationPolicy:
    def __init__(
        self,
        *,
        level: RandomizationLevel,
        config_path: Path,
        parameter_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._level = level
        self._config_path = config_path
        self._config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        self._parameter_overrides = dict(parameter_overrides or {})

    @classmethod
    def default(
        cls,
        level: RandomizationLevel,
        parameter_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> DomainRandomizationPolicy:
        return cls(
            level=level,
            config_path=Path("configs/phase9/domain_randomization.yaml"),
            parameter_overrides=parameter_overrides,
        )

    def specs(self) -> dict[str, ParameterRandomizationSpec]:
        configured = dict(self._config["parameters"])
        unknown = sorted(set(self._parameter_overrides).difference(configured))
        if unknown:
            raise ValueError(f"unsupported randomization parameter: {unknown[0]}")
        result: dict[str, ParameterRandomizationSpec] = {}
        for name, raw in configured.items():
            base = dict(raw)
            override = dict(self._parameter_overrides.get(str(name), {}))
            distribution = RandomizationDistribution(
                str(override.get("distribution", base.get("distribution", "UNIFORM"))).upper()
            )
            range_mode = RandomizationRangeMode(
                str(override.get("range_mode", "LEVEL_SCALED")).upper()
            )
            spec = ParameterRandomizationSpec(
                name=str(name),
                enabled=bool(override.get("enabled", True)),
                distribution=distribution,
                nominal=float(override.get("nominal", base["nominal"])),
                minimum=float(override.get("min", base["min"])),
                maximum=float(override.get("max", base["max"])),
                unit=str(base["unit"]),
                range_mode=range_mode,
                mean=_optional_float(override.get("mean")),
                std=_optional_float(override.get("std")),
            )
            spec.validate()
            result[spec.name] = spec
        return result

    def sample(self, *, seed: int) -> RandomizationSample:
        scale = float(self._config["levels"][self._level.value]["scale"])
        parameters: dict[str, RandomizedParameter] = {}
        for name, spec in sorted(self.specs().items()):
            parameter_seed = _parameter_seed(seed, name, str(self._config["version"]))
            rng = random.Random(parameter_seed)
            lower, upper = _effective_bounds(spec, scale)
            value = _sample_value(spec, lower=lower, upper=upper, rng=rng)
            parameters[name] = RandomizedParameter(
                name=name,
                value=round(value, 8),
                unit=spec.unit,
                source=str(self._config_path),
                distribution=spec.distribution,
                requested_min=round(lower, 8),
                requested_max=round(upper, 8),
                nominal=spec.nominal,
                parameter_seed=parameter_seed,
            )
        return RandomizationSample(
            version=str(self._config["version"]),
            level=self._level,
            seed=seed,
            parameters=parameters,
        )


def _effective_bounds(spec: ParameterRandomizationSpec, level_scale: float) -> tuple[float, float]:
    if not spec.enabled:
        return spec.nominal, spec.nominal
    if spec.range_mode == RandomizationRangeMode.ABSOLUTE:
        return spec.minimum, spec.maximum
    return (
        spec.nominal + (spec.minimum - spec.nominal) * level_scale,
        spec.nominal + (spec.maximum - spec.nominal) * level_scale,
    )


def _sample_value(
    spec: ParameterRandomizationSpec,
    *,
    lower: float,
    upper: float,
    rng: random.Random,
) -> float:
    if not spec.enabled or lower == upper or spec.distribution == RandomizationDistribution.FIXED:
        return spec.nominal
    if spec.distribution == RandomizationDistribution.UNIFORM:
        return rng.uniform(lower, upper)
    mean = spec.nominal if spec.mean is None else spec.mean
    assert spec.std is not None
    return min(upper, max(lower, rng.gauss(mean, spec.std)))


def _parameter_seed(seed: int, name: str, version: str) -> int:
    digest = hashlib.sha256(f"{version}:{seed}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"expected a numeric value, got {type(value).__name__}")
    return float(value)
