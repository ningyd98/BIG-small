"""Read original provider-reported tokens; never certify currency or admission."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from cloud_edge_robot_arm.research.cost_ledger import RequestCost
from cloud_edge_robot_arm.research.resource_plan import _read_request_costs
from cloud_edge_robot_arm.vision.role_models import RoleProviderSnapshot

REQUIRED_SOURCES = frozenset(
    f"src/cloud_edge_robot_arm/research/{name}.py"
    for name in ("provider_usage", "cost_ledger", "resource_plan")
)


def _hashes(values: Mapping[str, str]) -> Mapping[str, str]:
    copied = dict(values)
    if not copied or any(
        not isinstance(name, str)
        or not name
        or Path(name).is_absolute()
        or ".." in Path(name).parts
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for name, digest in copied.items()
    ):
        raise ValueError("named relative original SHA256 sources are required")
    return MappingProxyType(copied)


@dataclass(frozen=True)
class ProviderUsageRegistration:
    evidence_root: Path
    ledger_path: str
    wire_path: str
    cloud_role: RoleProviderSnapshot
    original_hashes: Mapping[str, str]
    source_root: Path
    current_source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        originals = _hashes(self.original_hashes)
        sources = _hashes(self.current_source_hashes)
        role = self.cloud_role
        if not isinstance(role, RoleProviderSnapshot) or (
            role.role != "CLOUD" or role.provider_location != "REMOTE_SERVICE" or not role.model_id
        ):
            raise ValueError("registered remote cloud model identity is required")
        role = RoleProviderSnapshot(
            role.role,
            role.provider_id,
            role.provider_location,
            role.model_id,
            role.revision,
            role.weight_digest,
            role.quantization,
            role.request_config_hash,
            dict(role.source_hashes),
        )
        if not REQUIRED_SOURCES <= sources.keys() or any(
            sources.get(name) != digest for name, digest in role.source_hashes.items()
        ):
            raise ValueError("complete reader and cloud source bindings are required")
        if self.ledger_path not in originals or self.wire_path not in originals:
            raise ValueError("ledger and wire must belong to the original inventory")
        object.__setattr__(self, "evidence_root", Path(self.evidence_root).absolute())
        object.__setattr__(self, "source_root", Path(self.source_root).absolute())
        object.__setattr__(self, "original_hashes", originals)
        object.__setattr__(self, "current_source_hashes", sources)
        object.__setattr__(self, "cloud_role", role)


@dataclass(frozen=True)
class ProviderAttemptUsage:
    local_attempt_id: str
    model_role: str
    status: str
    sent: bool
    provider_response_id: str | None = None
    requested_model: str | None = None
    returned_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    reason: str = "provider_usage_unknown"
    provider_request_id: None = field(default=None, init=False)


@dataclass(frozen=True)
class ProviderUsageAudit:
    status: Literal["OBSERVED", "UNKNOWN", "INVALID"]
    reasons: tuple[str, ...]
    attempts: tuple[ProviderAttemptUsage, ...]
    original_attempts: int | None
    sent_attempts: int | None
    raw_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    monetary_cost: None = field(default=None, init=False)
    billing_status: Literal["UNAVAILABLE"] = field(default="UNAVAILABLE", init=False)
    scope: Literal["ORIGINAL_PROVIDER_USAGE_METADATA"] = field(
        default="ORIGINAL_PROVIDER_USAGE_METADATA",
        init=False,
    )

    def __post_init__(self) -> None:
        if self.status not in {"OBSERVED", "UNKNOWN", "INVALID"}:
            raise ValueError("unsupported metadata status")
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        for name in ("raw_file_hashes", "current_source_hashes"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


def _safe(path: Path, root: Path) -> Path:
    if any(p.is_symlink() for p in (path, *path.parents)) or (
        not path.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError("source_path_invalid")
    return path


def _digest(path: Path, root: Path) -> str:
    _safe(path, root)
    if not path.is_file():
        raise ValueError("source_not_regular_file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(registration: ProviderUsageRegistration) -> tuple[dict[str, str], dict[str, str]]:
    root = registration.evidence_root
    _safe(root, root)
    if not root.is_dir():
        raise FileNotFoundError("registered_evidence_missing")
    raw = {}
    for path in sorted(root.rglob("*")):
        _safe(path, root)
        if not path.is_dir():
            raw[path.relative_to(root).as_posix()] = _digest(path, root)
    if raw != dict(registration.original_hashes):
        raise ValueError("original_inventory_drift")
    sources = {
        name: _digest(registration.source_root / name, registration.source_root)
        for name in registration.current_source_hashes
    }
    if sources != dict(registration.current_source_hashes):
        raise ValueError("current_source_drift")
    return raw, sources


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _json(path: Path) -> Any:
    return json.loads(path.read_bytes(), object_pairs_hook=_unique_object)


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid_provider_token_count")
    return value


def _usage(payload: Any) -> tuple[int, int, int, int | None, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("provider_usage_missing")
    inputs, outputs, total = (
        _integer(payload.get(name))
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    if total != inputs + outputs:
        raise ValueError("provider_token_total_inconsistent")
    subsets = []
    for name, subset, ceiling in (
        ("prompt_tokens_details", "cached_tokens", inputs),
        ("completion_tokens_details", "reasoning_tokens", outputs),
    ):
        details = payload.get(name)
        value = None
        if details is not None:
            if not isinstance(details, dict):
                raise ValueError("provider_token_details_invalid")
            for key in ("text_tokens", "image_tokens", "video_tokens", "audio_tokens", subset):
                if details.get(key) is not None and _integer(details[key]) > ceiling:
                    raise ValueError("provider_token_subset_inconsistent")
            if details.get(subset) is not None:
                value = _integer(details[subset])
            if (
                name == "completion_tokens_details"
                and value is not None
                and (
                    details.get("text_tokens") is not None
                    and value > _integer(details["text_tokens"])
                )
            ):
                raise ValueError("reasoning_exceeds_text_subset")
        subsets.append(value)
    return inputs, outputs, total, subsets[0], subsets[1]


class ProviderUsageAuditor:
    """Owner allowlist; no network, stored-receipt acceptance or billing policy."""

    def __init__(self, registrations: Mapping[str, ProviderUsageRegistration]) -> None:
        copied = {}
        for name, registration in registrations.items():
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name) is None
            ):
                raise ValueError("opaque registration ID required")
            if not isinstance(registration, ProviderUsageRegistration):
                raise TypeError("typed usage registration required")
            copied[name] = ProviderUsageRegistration(
                registration.evidence_root,
                registration.ledger_path,
                registration.wire_path,
                registration.cloud_role,
                registration.original_hashes,
                registration.source_root,
                registration.current_source_hashes,
            )
        self._registrations = MappingProxyType(copied)

    def audit(self, evidence_id: str) -> ProviderUsageAudit:
        registration = self._registrations.get(evidence_id)
        raw: dict[str, str] = {}
        sources: dict[str, str] = {}
        attempts: list[ProviderAttemptUsage] = []
        original_count = sent_count = None
        status: Literal["OBSERVED", "UNKNOWN", "INVALID"] = "UNKNOWN"
        reasons = ("evidence_id_not_registered",)
        if registration is not None:
            root, role = registration.evidence_root, registration.cloud_role
            try:
                raw, sources = _inventory(registration)
                ledger = _json(root / registration.ledger_path)
                if isinstance(ledger, dict):
                    ledger = ledger["requests"]
                if not isinstance(ledger, list):
                    raise ValueError("original_ledger_invalid")
                costs = [RequestCost.model_validate(value) for value in ledger]
                original_count = len(costs)
                sent_count = sum(cost.sent_at is not None for cost in costs)
                _read_request_costs(
                    root,
                    registration.ledger_path,
                    registration.wire_path,
                    expected_provider_version=role.digest(),
                )
                wire = _json(root / registration.wire_path)
                entries = {row["request_id"]: row for row in wire}
                seen_ids = set()
                for cost in costs:
                    if cost.provider_location != "REMOTE_SERVICE" or cost.model_role == "JUDGE":
                        raise ValueError("unsupported_request_role_or_location")
                    if cost.sent_at is None:
                        attempts.append(
                            ProviderAttemptUsage(
                                cost.request_id,
                                cost.model_role,
                                cost.status,
                                False,
                                reason="original_unsent_attempt",
                            )
                        )
                        continue
                    entry = entries[cost.request_id]
                    request = _json(root / entry["request_path"])
                    if not isinstance(request, dict) or request.get("model") != role.model_id:
                        raise ValueError("request_model_binding_mismatch")
                    response_path = entry.get("response_path")
                    response = None
                    if response_path:
                        try:
                            response = _json(root / response_path)
                        except ValueError:
                            pass  # Original empty/partial/error payload remains in denominator.
                    identity = model = None
                    if isinstance(response, dict):
                        identity, model = response.get("id"), response.get("model")
                        if model is not None and model != role.model_id:
                            raise ValueError("returned_model_binding_mismatch")
                        if identity is not None:
                            if (
                                not isinstance(identity, str)
                                or not identity
                                or identity in seen_ids
                            ):
                                raise ValueError("provider_response_identity_invalid")
                            seen_ids.add(identity)
                    counts: tuple[int | None, ...] = (None,) * 5
                    reason = "provider_usage_missing_or_unsupported"
                    if (
                        isinstance(response, dict)
                        and identity
                        and model == role.model_id
                        and (
                            request.get("stream", False) is False
                            and response.get("object") != "chat.completion.chunk"
                        )
                    ):
                        try:
                            counts = _usage(response.get("usage"))
                            reason = "original_provider_reported_tokens"
                        except ValueError:
                            pass
                    attempts.append(
                        ProviderAttemptUsage(
                            cost.request_id,
                            cost.model_role,
                            cost.status,
                            True,
                            provider_response_id=identity,
                            requested_model=role.model_id,
                            returned_model=model,
                            input_tokens=counts[0],
                            output_tokens=counts[1],
                            total_tokens=counts[2],
                            cached_input_tokens=counts[3],
                            reasoning_output_tokens=counts[4],
                            reason=reason,
                        )
                    )
                status = (
                    "UNKNOWN"
                    if any(row.sent and row.input_tokens is None for row in attempts)
                    else "OBSERVED"
                )
                reasons = (
                    ("provider_usage_incomplete",)
                    if status == "UNKNOWN"
                    else ("original_usage_metadata_observed_billing_unavailable",)
                )
                if _inventory(registration) != (raw, sources):
                    raise ValueError("evidence_changed_during_read")
            except FileNotFoundError:
                status, reasons = "UNKNOWN", ("original_or_current_source_missing",)
            except (ValueError, TypeError, KeyError, AttributeError, OSError):
                status, reasons = "INVALID", ("original_usage_source_invalid",)
        return ProviderUsageAudit(
            status,
            reasons,
            tuple(attempts),
            original_count,
            sent_count,
            raw,
            sources,
        )
