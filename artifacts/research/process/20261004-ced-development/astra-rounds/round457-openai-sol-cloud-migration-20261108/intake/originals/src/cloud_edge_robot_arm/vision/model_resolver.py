"""Immutable visual-model settings resolved once for each planning run."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from cloud_edge_robot_arm.model_control.endpoint_security import EndpointSecurityPolicy
from cloud_edge_robot_arm.model_control.models import PlannerProviderKind

if TYPE_CHECKING:
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter


@dataclass(frozen=True, slots=True)
class ModelConfigSnapshot:
    """A model identity and bounded request configuration, detached from live profiles."""

    provider: Literal["ollama", "openai_compatible"]
    model: str
    endpoint: str
    weight_digest: str | None
    quantization: str | None
    image_size: tuple[int, int]
    generation_parameters: Mapping[str, int | float | bool]
    timeout_s: float
    coordinate_system: Literal["pixel", "normalized_1000"] = "pixel"
    grasp_profile: Literal[
        "unconfigured", "mujoco_upright_box_v1", "mujoco_upright_box_v2"
    ] = "unconfigured"

    def __post_init__(self) -> None:
        if self.coordinate_system not in {"pixel", "normalized_1000"}:
            raise ValueError("invalid coordinate system")
        if not isinstance(self.grasp_profile, str) or self.grasp_profile not in {
            "unconfigured", "mujoco_upright_box_v1", "mujoco_upright_box_v2",
        }:
            raise ValueError("invalid grasp profile")
        kind = (
            PlannerProviderKind.OLLAMA
            if self.provider == "ollama"
            else PlannerProviderKind.OPENAI_COMPATIBLE
            if self.provider == "openai_compatible"
            else None
        )
        if kind is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}", self.model):
            raise ValueError("invalid visual model provider or name")
        canonical = EndpointSecurityPolicy().validate(kind, self.endpoint)
        object.__setattr__(self, "endpoint", canonical)
        if self.provider == "ollama" and (
            self.weight_digest is None or self.quantization is None
        ):
            raise ValueError("local snapshots require explicit weight identity fields")
        if self.weight_digest is not None and (
            not isinstance(self.weight_digest, str)
            or (self.weight_digest and not re.fullmatch(r"[0-9a-f]{64}", self.weight_digest))
        ):
            raise ValueError("weight_digest must be a full SHA-256 hex digest")
        if self.quantization is not None and (
            not isinstance(self.quantization, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", self.quantization)
        ):
            raise ValueError("invalid quantization")
        size = tuple(self.image_size)
        if (
            len(size) != 2
            or not all(type(value) is int for value in size)
            or not 1 <= size[0] <= 1280
            or not 1 <= size[1] <= 720
        ):
            raise ValueError("invalid model image size")
        object.__setattr__(self, "image_size", size)
        if not math.isfinite(self.timeout_s) or not 0 < self.timeout_s <= 600:
            raise ValueError("invalid model timeout")
        allowed = {"temperature", "num_ctx", "num_predict", "top_k", "top_p", "seed", "think"}
        params = dict(self.generation_parameters)
        if not params or set(params) - allowed:
            raise ValueError("invalid model generation parameters")
        for key, value in params.items():
            if key == "think":
                if type(value) is not bool:
                    raise ValueError("think must be boolean")
            elif type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError(f"invalid {key} value")
        object.__setattr__(self, "generation_parameters", MappingProxyType(params))

    def evidence(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint_hash": hashlib.sha256(self.endpoint.encode()).hexdigest(),
            "weight_digest": self.weight_digest,
            "quantization": self.quantization,
            "image_size": list(self.image_size),
            "generation_parameters": dict(self.generation_parameters),
            "timeout_s": self.timeout_s,
            "coordinate_system": self.coordinate_system,
            "grasp_profile": self.grasp_profile,
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.evidence(), sort_keys=True).encode()).hexdigest()


def resolve_visual_planner(
    snapshot: ModelConfigSnapshot,
    *,
    api_key: str = "",
    chat_path: str = "/v1/chat/completions",
    allow_paid: bool = False,
) -> RGBDPlannerAdapter:
    """Bind a profile snapshot to an adapter without rereading mutable configuration."""
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    return RGBDPlannerAdapter(
        base_url=snapshot.endpoint,
        model=snapshot.model,
        provider=snapshot.provider,
        api_key=api_key,
        timeout_s=snapshot.timeout_s,
        allow_paid=allow_paid,
        chat_path=chat_path,
        model_snapshot=snapshot,
    )
