from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from cloud_edge_robot_arm.simulation.config import RandomizationLevel


@dataclass(frozen=True)
class RandomizedParameter:
    name: str
    value: float
    unit: str
    source: str


@dataclass(frozen=True)
class RandomizationSample:
    version: str
    level: RandomizationLevel
    seed: int
    parameters: dict[str, RandomizedParameter]

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
                }
                for name, parameter in sorted(self.parameters.items())
            },
        }


class DomainRandomizationPolicy:
    def __init__(self, *, level: RandomizationLevel, config_path: Path) -> None:
        self._level = level
        self._config_path = config_path
        self._config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    @classmethod
    def default(cls, level: RandomizationLevel) -> DomainRandomizationPolicy:
        return cls(level=level, config_path=Path("configs/phase9/domain_randomization.yaml"))

    def sample(self, *, seed: int) -> RandomizationSample:
        rng = random.Random(seed)
        scale = float(self._config["levels"][self._level.value]["scale"])
        parameters: dict[str, RandomizedParameter] = {}
        for name, spec in dict(self._config["parameters"]).items():
            nominal = float(spec["nominal"])
            lower = nominal + (float(spec["min"]) - nominal) * scale
            upper = nominal + (float(spec["max"]) - nominal) * scale
            value = nominal if scale == 0 else rng.uniform(lower, upper)
            parameters[name] = RandomizedParameter(
                name=str(name),
                value=round(value, 8),
                unit=str(spec["unit"]),
                source=str(self._config_path),
            )
        return RandomizationSample(
            version=str(self._config["version"]),
            level=self._level,
            seed=seed,
            parameters=parameters,
        )
