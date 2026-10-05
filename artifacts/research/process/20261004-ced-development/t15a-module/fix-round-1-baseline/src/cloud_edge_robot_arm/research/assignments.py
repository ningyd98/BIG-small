"""研究分配与记录契约：完整固定池、配对随机顺序和可核验轨迹引用。"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from pydantic import BaseModel

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json, content_digest
from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot
from cloud_edge_robot_arm.research.models import EvidenceKind, RunProvenance
from cloud_edge_robot_arm.research.network import NetworkSchedule
from cloud_edge_robot_arm.research.protocol import NETWORKS, STRATA, FrozenProtocol
from cloud_edge_robot_arm.research.provenance import audit_provenance
from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome


def _hash(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ArtifactReference:
    """引用实际产物字节及其格式版本，核验失败时拒绝作为来源。"""

    schema_version: str
    content_hash: str
    path: str

    def __post_init__(self) -> None:
        if not self.schema_version.strip() or not self.path.strip() or not _hash(self.content_hash):
            raise ValueError("artifact schema/path or SHA256 content hash missing")

    def verify(self, root: Path | None = None) -> Path:
        """读取文件并核对原始字节散列；不根据摘要假定产物存在。"""
        path = Path(self.path)
        if root is not None:
            path = path if path.is_absolute() else root / path
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("artifact reference escapes its evidence root")
        if not path.is_file():
            raise ValueError("artifact source is missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.content_hash:
            raise ValueError("artifact content hash mismatch")
        return path


def make_verification_record(
    record: Mapping[str, Any],
    source_refs: Sequence[ArtifactReference],
) -> dict[str, Any]:
    """封装原始在线判定与来源引用，不补写 PASS 或独立物理结论。"""
    if not source_refs:
        raise ValueError("verification source references required")
    payload = {
        "schema_version": "ced.verification-record.v1",
        "record": _json(record),
        "source_refs": [_json(ref) for ref in source_refs],
    }
    return {**payload, "content_hash": content_digest(payload)}


def _verification(value: Mapping[str, Any], *, attest_sources: bool) -> Mapping[str, Any]:
    if "schema_version" not in value:
        if attest_sources:
            raise ValueError("verification source attestation requires the versioned envelope")
        return cast(Mapping[str, Any], _freeze(value))  # Legacy diagnostic only; never accepted.
    if value.get("schema_version") != "ced.verification-record.v1" or set(value) != {
        "schema_version",
        "record",
        "source_refs",
        "content_hash",
    }:
        raise ValueError("verification envelope schema invalid")
    if not isinstance(value["record"], Mapping) or not isinstance(
        value["source_refs"], (list, tuple)
    ):
        raise ValueError("verification exact record/source references missing")
    if not value["source_refs"]:
        raise ValueError("verification source references missing")
    payload = {key: _json(item) for key, item in value.items() if key != "content_hash"}
    if content_digest(payload) != value["content_hash"]:
        raise ValueError("verification content hash mismatch")
    for raw in value["source_refs"]:
        if not isinstance(raw, Mapping):
            raise ValueError("verification source reference malformed")
        ref = ArtifactReference(**raw)
        if attest_sources:
            ref.verify()
    return cast(Mapping[str, Any], _freeze(value))


@dataclass(frozen=True)
class EpisodeAssignment:
    """将一次方法运行绑定到完整场景、物理种子与网络日程。"""

    assignment_id: str
    group_id: str
    stratum_id: str
    method_id: str
    physics_seed: int
    network_schedule_id: str
    order_index: int
    scene_payload_json: str = field(default="", kw_only=True)
    perturbation_json: str = field(default="", kw_only=True)
    network_schedule_json: str = field(default="", kw_only=True)
    pool_hash: str = field(default="", kw_only=True)
    protocol_hash: str = field(default="", kw_only=True)

    def __post_init__(self) -> None:
        if not all((self.assignment_id, self.group_id, self.method_id, self.network_schedule_id)):
            raise ValueError("assignment identity missing")
        if self.stratum_id not in STRATA:
            raise ValueError("assignment stratum outside fixed design")
        if any(
            type(value) is not int or value < 0 for value in (self.physics_seed, self.order_index)
        ):
            raise ValueError("assignment seed/order invalid")
        # Unbound seven-field legacy metadata is representable, never formally runnable.
        if any((self.scene_payload_json, self.network_schedule_json, self.perturbation_json)):
            if not all(
                (
                    self.scene_payload_json,
                    self.network_schedule_json,
                    self.perturbation_json,
                    _hash(self.pool_hash),
                    _hash(self.protocol_hash),
                )
            ):
                raise ValueError("assignment scene/source binding incomplete")
            scene = SceneSpec.model_validate_json(self.scene_payload_json)
            if scene.group_id != self.group_id or scene.seed != self.physics_seed:
                raise ValueError("assignment scene group or physics seed mismatch")
            schedule = NetworkSchedule.model_validate_json(self.network_schedule_json)
            if schedule.schedule_id != self.network_schedule_id:
                raise ValueError("assignment network schedule mismatch")
            schedule_payload = schedule.model_dump(mode="json", exclude={"schedule_id"})
            if content_digest(schedule_payload) != self.network_schedule_id:
                raise ValueError("assignment network schedule content hash mismatch")
            canonical_json(json.loads(self.perturbation_json))

    @property
    def content_hash(self) -> str:
        """绑定完整分配，供断点恢复和记录身份检查使用。"""
        return content_digest(_json(self))


@dataclass(frozen=True)
class EpisodeRecord:
    """保留每次分配及所有失败；原始来源未核验时不接受任务成功。"""

    assignment: EpisodeAssignment
    outcome: VisualEpisodeOutcome
    provenance: RunProvenance
    costs: CostSnapshot
    duration_penalized_s: float
    infrastructure_incident_id: str | None
    decision_trace_refs: Sequence[ArtifactReference]
    verification_records: Sequence[Mapping[str, Any]]
    recovery_trace_refs: Sequence[ArtifactReference]
    provider_versions: Mapping[str, str]
    run_status: str = field(default="COMPLETED", kw_only=True)
    source_verified: bool = field(default=False, kw_only=True)
    schema_version: str = field(default="ced.episode-record.v1", kw_only=True)

    def __post_init__(self) -> None:
        if self.run_status not in {"COMPLETED", "BLOCKED", "TIMEOUT", "STOP", "FALLBACK", "FAILED"}:
            raise ValueError("unsupported episode terminal status")
        if self.provenance.run_id != self.assignment.assignment_id or (
            self.provenance.scene_group_id != self.assignment.group_id
        ):
            raise ValueError("episode provenance does not match assignment")
        if self.provenance.cohort != "NEW_RESEARCH":
            raise ValueError("historical records cannot occupy a new research assignment")
        numbers = (
            self.duration_penalized_s,
            self.outcome.elapsed_s,
            self.outcome.measured_lift_m,
            self.outcome.hold_s,
            self.outcome.placed_stable_s,
        )
        if any(not math.isfinite(value) or value < 0 for value in numbers):
            raise ValueError("episode durations/measurements must be finite nonnegative")
        for name, value in self.costs.model_dump().items():
            if isinstance(value, (int, float)) and (not math.isfinite(value) or value < 0):
                raise ValueError(f"episode cost {name} must be finite nonnegative")
        for name in ("decision_trace_refs", "recovery_trace_refs"):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, ArtifactReference) for value in values):
                raise ValueError("trace references require schema and content hashes")
            object.__setattr__(self, name, values)
        object.__setattr__(
            self,
            "verification_records",
            tuple(
                _verification(value, attest_sources=self.source_verified)
                for value in self.verification_records
            ),
        )
        if any(not key or not value for key, value in self.provider_versions.items()):
            raise ValueError("provider versions cannot be blank")
        object.__setattr__(self, "provider_versions", _freeze(self.provider_versions))
        if self.source_verified:
            for ref in (*self.decision_trace_refs, *self.recovery_trace_refs):
                ref.verify()

    @property
    def accepted_task_success(self) -> bool:
        """真实来源重算尚未整合，声明式元数据不能验收物理成功。"""
        return False

    @property
    def structurally_complete_success(self) -> bool:
        """只表示记录结构齐全，独立物理重算之前不能用作接受成功。"""
        return bool(
            self.source_verified
            and self.run_status == "COMPLETED"
            and self.outcome.success
            and self.outcome.physical_success
            and self.outcome.online_reported_complete
            and self.decision_trace_refs
            and self.verification_records
            and self.provider_versions
            and self.provenance.evidence_kind == EvidenceKind.PHYSICS
            and audit_provenance([self.provenance]).physical_success_count == 1
        )

    @property
    def content_hash(self) -> str:
        """计算完整记录散列，保留原始失败及基础设施重跑关联。"""
        return content_digest(_json(self))

    def to_payload(self) -> dict[str, Any]:
        """输出可归档的 JSON 结构及完整记录散列。"""
        return {**_json(self), "content_hash": self.content_hash}


def validate_formal_protocol(protocol: FrozenProtocol) -> None:
    """检查 FINAL 元数据和不可变内容；此检查不替代真实来源验收。"""
    protocol.require_formal()
    payload = {"spec": protocol.spec.model_dump(mode="json"), "stage": protocol.stage}
    if content_digest(payload) != protocol.content_hash:
        raise ValueError("formal protocol content hash mismatch")
    hashes = (
        protocol.spec.initial_protocol_hash,
        protocol.spec.model_snapshot_hash,
        protocol.spec.opportunity_hash,
        protocol.spec.recovery_fault_manifest_hash,
    )
    if any(not isinstance(value, str) or not _hash(value) for value in hashes):
        raise ValueError("formal protocol lacks evidence source hashes")
    if protocol.spec.tcap_s is None or not protocol.spec.method_hashes:
        raise ValueError("formal protocol lacks frozen method or timeout")
    if any(not _hash(value) for value in protocol.spec.method_hashes.values()):
        raise ValueError("frozen method hash invalid")


def build_assignments(
    protocol: FrozenProtocol,
    methods: Sequence[str],
    *,
    scene_pool: Sequence[Mapping[str, Any]] | None = None,
) -> list[EpisodeAssignment]:
    """从完整散列绑定池按层取前 N，再随机固定每个场景的方法顺序。"""
    validate_formal_protocol(protocol)
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("methods missing or duplicate")
    if any(method not in protocol.spec.method_hashes for method in methods):
        raise ValueError("requested method is not frozen")
    if scene_pool is None:
        raise ValueError("hash-bound full formal scene pool is required")
    pool_hash = content_digest(list(scene_pool))
    if pool_hash != protocol.spec.pool_hashes.get("formal"):
        raise ValueError("formal pool content hash mismatch")
    if len(scene_pool) != 2400:
        raise ValueError("formal source pool must contain all 2400 candidates")
    seen_groups: set[str] = set()
    seen_ids: set[str] = set()
    seen_scenes: set[str] = set()
    layers: dict[str, list[tuple[Mapping[str, Any], SceneSpec]]] = {s: [] for s in STRATA}
    for row in scene_pool:
        scene = SceneSpec.model_validate(row["scene"])
        canonical_scene = SceneSpec.from_parameters(
            scene.scene_parameters, scene.asset_family_hash, scene.seed
        )
        if canonical_scene.group_id != scene.group_id or row.get("scene_hash") != scene.scene_hash:
            raise ValueError("formal scene identity/hash mismatch")
        row_id = str(row.get("assignment_id", ""))
        if (
            not row_id
            or scene.group_id in seen_groups
            or row_id in seen_ids
            or (scene.scene_hash in seen_scenes)
        ):
            raise ValueError("formal pool duplicate scene/group/assignment")
        seen_groups.add(scene.group_id)
        seen_ids.add(row_id)
        seen_scenes.add(scene.scene_hash)
        stratum = row.get("stratum_id")
        if stratum not in layers:
            raise ValueError("formal pool stratum outside fixed design")
        if not isinstance(row.get("perturbation"), dict):
            raise ValueError("formal scene perturbation binding missing")
        layers[stratum].append((row, scene))
    if any(len(rows) != 200 for rows in layers.values()):
        raise ValueError("formal source pool must balance 200 groups in each stratum")
    assert protocol.spec.selected_n is not None
    count = protocol.spec.selected_n // 12
    selected = {row["assignment_id"] for rows in layers.values() for row, _ in rows[:count]}
    result: list[EpisodeAssignment] = []
    for row in scene_pool:
        if row["assignment_id"] not in selected:
            continue
        scene = SceneSpec.model_validate(row["scene"])
        stratum = str(row["stratum_id"])
        network_index = int(stratum.split("_RTT")[1])
        rtt, loss = next((rtt, loss) for rtt, loss in NETWORKS if rtt == network_index)
        seed = int(
            content_digest(
                {"group": scene.group_id, "protocol": protocol.content_hash, "purpose": "network"}
            )[:16],
            16,
        )
        schedule_payload = {
            "rtt_ms": float(rtt),
            "jitter_fraction": 0.2,
            "loss_rate": loss,
            "bandwidth_mbit_s": 10.0,
            "outages": (),
            "seed": seed,
        }
        schedule_id = content_digest(schedule_payload)
        schedule = NetworkSchedule(schedule_id=schedule_id, rtt_ms=rtt, loss_rate=loss, seed=seed)
        order = sorted(methods)
        random.Random(f"{protocol.content_hash}:{scene.group_id}:method-order").shuffle(order)
        for method in order:
            result.append(
                EpisodeAssignment(
                    assignment_id=f"{row['assignment_id']}::{method}",
                    group_id=scene.group_id,
                    stratum_id=stratum,
                    method_id=method,
                    physics_seed=scene.seed,
                    network_schedule_id=schedule_id,
                    order_index=len(result),
                    scene_payload_json=canonical_json(scene.model_dump(mode="json")),
                    perturbation_json=canonical_json(row["perturbation"]),
                    network_schedule_json=canonical_json(schedule.model_dump(mode="json")),
                    pool_hash=pool_hash,
                    protocol_hash=protocol.content_hash,
                )
            )
    return result


def episode_record_from_payload(payload: Mapping[str, Any]) -> EpisodeRecord:
    """加载断点记录并重算完整散列，拒绝损坏或手改的失败惩罚。"""
    values = dict(payload)
    expected_hash = values.pop("content_hash", None)
    values["assignment"] = EpisodeAssignment(**values["assignment"])
    values["outcome"] = VisualEpisodeOutcome(**values["outcome"])
    values["provenance"] = RunProvenance.model_validate(values["provenance"])
    values["costs"] = CostSnapshot.model_validate(values["costs"])
    for name in ("decision_trace_refs", "recovery_trace_refs"):
        values[name] = tuple(ArtifactReference(**value) for value in values[name])
    record = EpisodeRecord(**values)
    if not isinstance(expected_hash, str) or record.content_hash != expected_hash:
        raise ValueError("episode record content hash mismatch")
    return record
