"""Separate immutable cloud, edge and device identities for research runs.

A digest binds configuration and source evidence. It is not evidence that a
remote service exposed immutable weights or that a provider passed acceptance.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter


def configuration_hash(value: Mapping[str, object]) -> str:
    """Hash JSON configuration with stable ordering and no nonfinite values."""
    encoded = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} requires a full SHA-256 digest")


def _require_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"invalid {name}")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True, slots=True)
class RoleProviderSnapshot:
    role: Literal["CLOUD", "EDGE", "DEVICE"]
    provider_id: str
    provider_location: Literal["LOCAL_HOST", "REMOTE_SERVICE"]
    model_id: str | None
    revision: str | None
    weight_digest: str | None
    quantization: str | None
    request_config_hash: str
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.role not in {"CLOUD", "EDGE", "DEVICE"}:
            raise ValueError("invalid role")
        if self.provider_location not in {"LOCAL_HOST", "REMOTE_SERVICE"}:
            raise ValueError("invalid provider_location")
        _require_id(self.provider_id, "provider_id")
        if self.role == "CLOUD" and self.model_id is None:
            raise ValueError("CLOUD requires a model_id")
        for name in ("model_id", "revision", "quantization"):
            value = getattr(self, name)
            if value is not None:
                _require_id(value, name)
        if self.weight_digest is not None:
            _require_digest(self.weight_digest, "weight_digest")
        _require_digest(self.request_config_hash, "request_config_hash")
        sources = dict(self.source_hashes)
        if not sources:
            raise ValueError("source_hashes cannot be empty")
        for name, digest in sources.items():
            _require_id(name, "source path")
            _require_digest(digest, "source hash")
        object.__setattr__(self, "source_hashes", MappingProxyType(sources))

    def evidence(self) -> dict[str, object]:
        return {
            "role": self.role,
            "provider_id": self.provider_id,
            "provider_location": self.provider_location,
            "model_id": self.model_id,
            "revision": self.revision,
            "weight_digest": self.weight_digest,
            "quantization": self.quantization,
            "request_config_hash": self.request_config_hash,
            "source_hashes": dict(self.source_hashes),
        }

    def digest(self) -> str:
        return configuration_hash(self.evidence())


@dataclass(frozen=True, slots=True)
class RoleModelBundle:
    cloud_snapshot: RoleProviderSnapshot
    edge_provider_id: str
    edge_provider_hash: str
    device_pipeline_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.cloud_snapshot, RoleProviderSnapshot)
            or self.cloud_snapshot.role != "CLOUD"
        ):
            raise ValueError("cloud_snapshot must bind the CLOUD role")
        _require_id(self.edge_provider_id, "edge_provider_id")
        _require_digest(self.edge_provider_hash, "edge_provider_hash")
        _require_digest(self.device_pipeline_hash, "device_pipeline_hash")

    def evidence(self) -> dict[str, object]:
        return {
            "cloud_snapshot": self.cloud_snapshot.evidence(),
            "edge_provider_id": self.edge_provider_id,
            "edge_provider_hash": self.edge_provider_hash,
            "device_pipeline_hash": self.device_pipeline_hash,
        }

    def digest(self) -> str:
        return configuration_hash(self.evidence())

    def validate_bindings(
        self, *, cloud_snapshot_hash: str, edge_provider_hash: str, device_pipeline_hash: str
    ) -> None:
        if (cloud_snapshot_hash, edge_provider_hash, device_pipeline_hash) != (
            self.cloud_snapshot.digest(),
            self.edge_provider_hash,
            self.device_pipeline_hash,
        ):
            raise ValueError("role binding mismatch")


def select_cloud_model_id(model_id: str, available_model_ids: Iterable[str] = ()) -> str:
    """Prefer an advertised dated Max snapshot, never guess a service revision.

    An explicitly dated profile remains pinned. Registry availability must come
    from the caller's provider evidence; an alias stays an alias when unknown.
    """
    if not re.fullmatch(r"qwen3\.8-max(?:-\d{4}-\d{2}-\d{2})?", model_id):
        raise ValueError("cloud profile must select the qwen3.8-max family")
    if model_id != "qwen3.8-max":
        date.fromisoformat(model_id[-10:])
        return model_id
    candidates = []
    for candidate in available_model_ids:
        if not isinstance(candidate, str) or not re.fullmatch(
            r"qwen3\.8-max-\d{4}-\d{2}-\d{2}", candidate
        ):
            continue
        try:
            date.fromisoformat(candidate[-10:])
        except ValueError:
            continue
        candidates.append(candidate)
    return max(candidates, default=model_id)


def resolve_cloud_role(
    service: ModelControlService,
    profile_id: str,
    *,
    source_hashes: Mapping[str, str],
    allow_paid: bool = False,
    image_size: tuple[int, int] = (320, 240),
    coordinate_system: Literal["pixel", "normalized_1000"] = "pixel",
    grasp_profile: Literal[
        "unconfigured", "mujoco_upright_box_v1", "mujoco_upright_box_v2"
    ] = "unconfigured",
    available_model_ids: Iterable[str] = (),
) -> tuple[RGBDPlannerAdapter, RoleProviderSnapshot]:
    """Read a chosen profile and its existing secret store without activating it."""
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable

    profile = service.get_profile(profile_id)
    if not profile.enabled or profile.provider_kind != PlannerProviderKind.OPENAI_COMPATIBLE:
        raise RGBDModelUnavailable("cloud role requires an enabled compatible API profile")
    model_id = select_cloud_model_id(profile.model_name, available_model_ids)
    model_snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model=model_id,
        endpoint=profile.base_url,
        weight_digest=None,
        quantization=None,
        image_size=image_size,
        generation_parameters={
            "temperature": profile.temperature,
            "num_predict": profile.max_tokens,
        },
        timeout_s=profile.timeout_seconds,
        coordinate_system=coordinate_system,
        grasp_profile=grasp_profile,
    )
    request_settings = model_snapshot.evidence() | {
        "chat_path": profile.chat_completions_path,
        "config_version": profile.config_version,
        "response_format": {"type": "json_object"},
        "allow_paid": allow_paid,
    }
    location: Literal["LOCAL_HOST", "REMOTE_SERVICE"] = (
        "LOCAL_HOST"
        if urlparse(model_snapshot.endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
        else "REMOTE_SERVICE"
    )
    snapshot = RoleProviderSnapshot(
        role="CLOUD",
        provider_id=profile.profile_id,
        provider_location=location,
        model_id=model_id,
        revision=None,
        weight_digest=None,
        quantization=None,
        request_config_hash=configuration_hash(request_settings),
        source_hashes=source_hashes,
    )
    planner = resolve_visual_planner(
        model_snapshot,
        api_key=service.secret_store.get_secret(profile.profile_id) or "",
        chat_path=profile.chat_completions_path,
        allow_paid=allow_paid,
    )
    planner.role_snapshot = snapshot  # type: ignore[attr-defined]
    return planner, snapshot
