"""Recheck frozen cloud, edge and device software at actual runtime boundaries.

These bindings identify implementations; they do not certify remote weights,
calibration, method admission or physical task success.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    cloud_request_settings,
    configuration_hash,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class RoleRuntimeBinding:
    bundle: RoleModelBundle
    edge_snapshot: RoleProviderSnapshot
    device_source_hashes: Mapping[str, str]
    edge_policy: Mapping[str, object]
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3],
                       kw_only=True, repr=False)

    def __post_init__(self) -> None:
        if self.edge_snapshot.role != "EDGE" or (
            self.edge_snapshot.provider_id != self.bundle.edge_provider_id
            or self.edge_snapshot.digest() != self.bundle.edge_provider_hash
        ):
            raise ValueError("edge role binding differs from its bundle")
        if "src/cloud_edge_robot_arm/edge/recovery/verification_router.py" not in (
            self.edge_snapshot.source_hashes
        ):
            raise ValueError("edge binding requires the actual verification router source")
        sources = dict(self.device_source_hashes)
        if not sources or configuration_hash(sources) != self.bundle.device_pipeline_hash:
            raise ValueError("device source binding differs from its bundle")
        # Policies are JSON data: copy through serialization to break nested aliases.
        policy = json.loads(json.dumps(dict(self.edge_policy), allow_nan=False))
        if configuration_hash(policy) != self.edge_snapshot.request_config_hash:
            raise ValueError("edge policy binding differs from its snapshot")
        object.__setattr__(self, "device_source_hashes", MappingProxyType(sources))
        object.__setattr__(self, "edge_policy", _freeze(policy))
        object.__setattr__(self, "root", Path(self.root))

    def validate_execution_policy(self, policy: ExecutionPolicy) -> None:
        expected = _plain(self.edge_policy.get("verification_budget"))
        if expected != asdict(policy.verification_budget):
            raise ValueError("actual verification budget differs from frozen edge policy")
        capabilities = self.edge_policy.get("capabilities")
        if self.edge_policy.get("runtime_router") != "verification_router.v1" or (
            not isinstance(capabilities, tuple)
            or len(capabilities) != 3
            or set(capabilities) != {"CONTINUE", "REOBSERVE", "STOP"}
        ):
            raise ValueError("actual verification router/capabilities differ from edge policy")

    def _validate_sources(self, sources: Mapping[str, str]) -> None:
        root = self.root.resolve()
        for name, expected in sources.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("role source path escapes its repository")
            path = root / relative
            if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)
                                        if part.is_relative_to(root)):
                raise ValueError("role source unavailable or symlinked")
            if not path.resolve().is_relative_to(root) or (
                hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("role source hash changed")

    def validate(self, planner: RGBDPlannerAdapter) -> None:
        snapshot = getattr(planner, "role_snapshot", None)
        if not isinstance(snapshot, RoleProviderSnapshot) or (
            snapshot.digest() != self.bundle.cloud_snapshot.digest()
        ):
            raise ValueError("cloud role binding changed")
        if configuration_hash(cloud_request_settings(planner)) != snapshot.request_config_hash:
            raise ValueError("cloud request settings changed")
        if configuration_hash(cast(Mapping[str, object], _plain(self.edge_policy))) != (
            self.edge_snapshot.request_config_hash
        ):
            raise ValueError("edge policy changed")
        for sources in (snapshot.source_hashes, self.edge_snapshot.source_hashes,
                        self.device_source_hashes):
            self._validate_sources(sources)

    def evidence(self) -> dict[str, object]:
        return {"bundle_hash": self.bundle.digest(), "bundle": self.bundle.evidence(),
                "edge_snapshot": self.edge_snapshot.evidence(),
                "device_source_hashes": dict(self.device_source_hashes),
                "edge_policy": _plain(self.edge_policy)}
