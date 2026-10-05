"""Independently reconstruct registered INITIAL sources; never admit a method.

Source integrity is one prerequisite. This module has no callback/receipt bypass,
cache, policy enablement, current execution registration or physical submission.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.freeze_evidence import initial_spec_from_evidence
from cloud_edge_robot_arm.research.protocol import FrozenProtocol, ProtocolSpec, load_protocol
from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

AdmissionScope = Literal["INITIAL_SOURCE", "METHOD"]
AdmissionStatus = Literal["VALID", "INVALID", "UNKNOWN"]


class _AuditFailure(Exception):
    def __init__(
        self,
        status: AdmissionStatus,
        reason: str,
        observed_sources: Mapping[str, str] | None = None,
    ) -> None:
        self.status, self.reason = status, reason
        self.observed_sources = dict(observed_sources) if observed_sources is not None else None
        super().__init__(reason)


def _snapshot(snapshot: RoleProviderSnapshot) -> RoleProviderSnapshot:
    return RoleProviderSnapshot(
        snapshot.role,
        snapshot.provider_id,
        snapshot.provider_location,
        snapshot.model_id,
        snapshot.revision,
        snapshot.weight_digest,
        snapshot.quantization,
        snapshot.request_config_hash,
        dict(snapshot.source_hashes),
    )


def _binding(binding: RoleRuntimeBinding) -> RoleRuntimeBinding:
    cloud, edge = _snapshot(binding.bundle.cloud_snapshot), _snapshot(binding.edge_snapshot)
    return RoleRuntimeBinding(
        RoleModelBundle(
            cloud,
            binding.bundle.edge_provider_id,
            binding.bundle.edge_provider_hash,
            binding.bundle.device_pipeline_hash,
        ),
        edge,
        dict(binding.device_source_hashes),
        cast(Mapping[str, object], binding.evidence()["edge_policy"]),
        root=Path(binding.root),
    )


@dataclass(frozen=True)
class InitialSourceRegistration:
    evidence_root: Path
    protocol_path: Path
    current_role_binding: RoleRuntimeBinding
    current_source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.current_role_binding, RoleRuntimeBinding):
            raise TypeError("current_role_binding must identify the actual registered roles")
        sources = dict(self.current_source_hashes)
        if not sources or any(
            not isinstance(name, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for name, digest in sources.items()
        ):
            raise ValueError("current source inventory requires named full SHA256 bindings")
        object.__setattr__(self, "evidence_root", Path(self.evidence_root).absolute())
        object.__setattr__(self, "protocol_path", Path(self.protocol_path).absolute())
        object.__setattr__(self, "current_role_binding", _binding(self.current_role_binding))
        object.__setattr__(self, "current_source_hashes", MappingProxyType(sources))


@dataclass(frozen=True)
class ResearchAdmissionResult:
    requested_scope: AdmissionScope
    verified_scope: Literal["INITIAL_SOURCE"] | None
    status: AdmissionStatus
    initial_source_status: AdmissionStatus
    reasons: tuple[str, ...]
    protocol_hash: str | None
    role_bundle_hash: str | None
    raw_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    inventory_hash: str | None
    method_admitted: Literal[False] = False
    execution_admitted: Literal[False] = False

    def __post_init__(self) -> None:
        if self.method_admitted is not False or self.execution_admitted is not False:
            raise ValueError("INITIAL source audit never admits a method or execution")
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "raw_file_hashes", MappingProxyType(dict(self.raw_file_hashes)))
        object.__setattr__(
            self, "current_source_hashes", MappingProxyType(dict(self.current_source_hashes))
        )


def _checked(path: Path, *, root: Path | None = None) -> Path:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise _AuditFailure("INVALID", "registered_path_symlink")
    if root is not None and not path.resolve().is_relative_to(root.resolve()):
        raise _AuditFailure("INVALID", "registered_path_escape")
    return path


def _file_hash(path: Path, *, root: Path | None = None) -> str:
    _checked(path, root=root)
    if not stat.S_ISREG(path.stat().st_mode):
        raise _AuditFailure("INVALID", "registered_path_not_regular")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(registration: InitialSourceRegistration) -> dict[str, str]:
    root = _checked(registration.evidence_root)
    if not root.is_dir():
        raise _AuditFailure("UNKNOWN", "registered_evidence_missing")
    protocol = _checked(registration.protocol_path)
    if not protocol.is_file():
        raise _AuditFailure("UNKNOWN", "registered_protocol_missing")
    if protocol.name != "protocol.json":
        raise _AuditFailure("INVALID", "registered_protocol_path_not_exact")
    files = {}
    for path in sorted(root.rglob("*")):
        _checked(path, root=root)
        if path.is_dir():
            continue
        files["evidence:" + path.relative_to(root).as_posix()] = _file_hash(path, root=root)
    files["protocol:protocol.json"] = _file_hash(protocol)
    return files


def _sources(registration: InitialSourceRegistration) -> dict[str, str]:
    binding = registration.current_role_binding
    source_root = _checked(binding.root)
    expected = dict(registration.current_source_hashes)
    for sources in (
        binding.bundle.cloud_snapshot.source_hashes,
        binding.edge_snapshot.source_hashes,
        binding.device_source_hashes,
    ):
        for name, digest in sources.items():
            if name in expected and expected[name] != digest:
                raise _AuditFailure("INVALID", "current_role_source_binding_mismatch")
            expected[name] = digest
    actual = {}
    drifted = False
    for name, digest in expected.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise _AuditFailure("INVALID", "current_source_path_escape")
        try:
            observed = _file_hash(source_root / relative, root=source_root)
        except FileNotFoundError as exc:
            raise _AuditFailure("UNKNOWN", "current_source_missing") from exc
        actual[name] = observed
        if observed != digest:
            drifted = True
    if drifted:
        raise _AuditFailure("INVALID", "current_source_drift", actual)
    return actual


def _assert_initial(
    frozen: FrozenProtocol,
    derived: ProtocolSpec,
    current_role_bundle_hash: str,
) -> None:
    """Pure comparison is not source acceptance; the auditor must reconstruct first."""
    if (
        frozen.stage != "INITIAL"
        or frozen.spec.schema_version != "ced.research.v2"
        or frozen.spec.selected_n is not None
    ):
        raise _AuditFailure("INVALID", "requires_v2_initial_protocol")
    if frozen.spec.model_dump(mode="json") != derived.model_dump(mode="json"):
        raise _AuditFailure("INVALID", "initial_derived_spec_mismatch")
    if (
        derived.role_bundle_hash != current_role_bundle_hash
        or derived.model_snapshot_hash != current_role_bundle_hash
    ):
        raise _AuditFailure("INVALID", "current_role_bundle_mismatch")


class InitialSourceAdmissionAuditor:
    """Owner allowlist plus independent original reconstruction, with no cache."""

    def __init__(self, registrations: Mapping[str, InitialSourceRegistration]) -> None:
        copied = {}
        for name, registration in registrations.items():
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name) is None
            ):
                raise ValueError("registration IDs must be opaque names, not paths")
            if not isinstance(registration, InitialSourceRegistration):
                raise TypeError("registration must be InitialSourceRegistration")
            copied[name] = InitialSourceRegistration(
                registration.evidence_root,
                registration.protocol_path,
                registration.current_role_binding,
                registration.current_source_hashes,
            )
        self._registrations = MappingProxyType(copied)

    def audit(
        self,
        evidence_id: str,
        *,
        scope: AdmissionScope = "INITIAL_SOURCE",
    ) -> ResearchAdmissionResult:
        if scope not in {"INITIAL_SOURCE", "METHOD"}:
            raise ValueError("unsupported admission scope")
        registration = self._registrations.get(evidence_id)
        files: dict[str, str] = {}
        sources: dict[str, str] = {}
        protocol_hash = role_hash = None
        status: AdmissionStatus = "UNKNOWN"
        reasons: list[str] = []
        if registration is None:
            reasons.append("evidence_id_not_registered")
        else:
            role_hash = registration.current_role_binding.bundle.digest()
            try:
                files = _inventory(registration)
                sources = _sources(registration)
                try:
                    frozen = load_protocol(registration.protocol_path.parent)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    raise _AuditFailure("INVALID", "initial_protocol_invalid") from exc
                protocol_hash = frozen.content_hash
                if (
                    frozen.stage != "INITIAL"
                    or frozen.spec.schema_version != "ced.research.v2"
                    or frozen.spec.selected_n is not None
                ):
                    raise _AuditFailure("INVALID", "requires_v2_initial_protocol")
                manifest_path = registration.evidence_root / "source-hashes.json"
                try:
                    archived_sources = json.loads(manifest_path.read_bytes())
                except ValueError as exc:
                    raise _AuditFailure("INVALID", "initial_source_inventory_invalid") from exc
                if archived_sources != dict(registration.current_source_hashes):
                    raise _AuditFailure("INVALID", "initial_source_inventory_mismatch")
                for required in ("summary.json", "resource-plan.json"):
                    if not (registration.evidence_root / required).is_file():
                        raise _AuditFailure("UNKNOWN", "initial_source_missing")
                try:
                    derived = initial_spec_from_evidence(registration.evidence_root)
                except FileNotFoundError as exc:
                    raise _AuditFailure("UNKNOWN", "initial_source_missing") from exc
                except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                    raise _AuditFailure("INVALID", "initial_source_invalid") from exc
                _assert_initial(frozen, derived, role_hash)
                status = "VALID"
                reasons.append("initial_source_reconstructed")
            except _AuditFailure as exc:
                status, reasons = exc.status, [exc.reason]
                if exc.observed_sources is not None:
                    sources = exc.observed_sources
            except FileNotFoundError:
                status, reasons = "UNKNOWN", ["initial_source_missing"]
            except OSError:
                status, reasons = "UNKNOWN", ["initial_source_unreadable"]
            if files:
                try:
                    if _inventory(registration) != files or _sources(registration) != sources:
                        status, reasons = "INVALID", ["evidence_changed_during_audit"]
                except _AuditFailure as exc:
                    status, reasons = exc.status, [exc.reason]
                    if exc.observed_sources is not None:
                        sources = exc.observed_sources
                except OSError:
                    status, reasons = "INVALID", ["evidence_changed_during_audit"]
        initial_status = status
        if scope == "METHOD":
            status = "UNKNOWN"
            reasons.extend(
                (
                    "method_risk_source_verifier_unavailable",
                    "method_weight_selection_verifier_unavailable",
                    "execution_owner_registration_unavailable",
                )
            )
        return ResearchAdmissionResult(
            scope,
            "INITIAL_SOURCE" if initial_status == "VALID" else None,
            status,
            initial_status,
            tuple(reasons),
            protocol_hash,
            role_hash,
            files,
            sources,
            content_digest(files) if files else None,
        )
