"""Portable configuration for the first development scenario."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CONFIG_RESOURCE = "s01-component.json"


def strict_json(raw: bytes) -> object:
    """Read UTF-8 JSON with unique keys and without nonfinite literals."""
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject(_: str) -> None:
        raise ValueError("nonfinite JSON literal")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject)


class HarnessConfig(BaseModel):
    """Inputs supported by the single S01 development application."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["bigsmall.harness.config.v1"]
    scenario_id: Literal["S01_NORMAL_STATIC"]
    seed: Annotated[int, Field(ge=0, lt=2**31)]
    scene_split: Literal["development"] | None
    cloud_model: Literal["gpt-6.1-sol"]
    perception_model: Literal["allenai/Molmo2-ER"]
    edge_provider: Literal["deterministic_rules_cost_v1"]
    marker_family: Literal["side_y_plus_id7_75mm_component_v1"]
    visual_servo: Literal[True]
    # The original executor verifies these workspace bounds again against its role policy.
    camera_position_m: tuple[
        Annotated[float, Field(ge=-0.1, le=0.8, allow_inf_nan=False)],
        Annotated[float, Field(ge=-0.5, le=0.5, allow_inf_nan=False)],
        Annotated[float, Field(ge=0.6, le=2.0, allow_inf_nan=False)],
    ] | None

    @field_validator("visual_servo", mode="before")
    @classmethod
    def _exact_visual_servo(cls, value: object) -> object:
        if value is not True:
            raise ValueError("visual_servo must be JSON true")
        return value

    def fingerprint(self) -> str:
        """Hash the normalized configuration separately from native runtime identity."""
        raw = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_config(path: Path | None = None) -> HarnessConfig:
    """Load an explicit config or the wheel's example without reading runtime state."""
    if path is None:
        raw = files("cloud_edge_robot_arm.harness").joinpath(CONFIG_RESOURCE).read_bytes()
    else:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Harness configuration exceeds 64 KiB")
    try:
        strict_json(raw)
        return HarnessConfig.model_validate_json(raw)
    except ValidationError:
        # Invalid configuration can include user-entered secrets. Report field issues only.
        raise ValueError("invalid Harness configuration fields or values") from None
    except ValueError:
        raise ValueError("invalid Harness JSON configuration") from None
