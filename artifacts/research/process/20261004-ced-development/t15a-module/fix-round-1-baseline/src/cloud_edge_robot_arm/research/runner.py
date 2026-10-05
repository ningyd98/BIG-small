"""研究运行与回放边界；当前未集成真实方法时明确保留 BLOCKED 记录。"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol, cast

from cloud_edge_robot_arm.edge.evidence.opportunities import (
    GateReplayRecord,
    Opportunity,
    replay_opportunities,
)
from cloud_edge_robot_arm.research.assignments import (
    ArtifactReference,
    EpisodeAssignment,
    EpisodeRecord,
    validate_formal_protocol,
)
from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot
from cloud_edge_robot_arm.research.models import (
    EvidenceKind,
    RunProvenance,
    StageEvidence,
    StageStatus,
)
from cloud_edge_robot_arm.research.protocol import FrozenProtocol
from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome


class SoftwareEpisodeAdapter(Protocol):
    """仅用于显式 MOCK 软件夹具，不能作为正式方法适配器。"""

    evidence_kind: EvidenceKind

    def run(self, assignment: EpisodeAssignment, protocol: FrozenProtocol) -> EpisodeRecord:
        """返回软件运行记录，不得伪装真实物理来源。"""
        ...


def _blocked(assignment: EpisodeAssignment, protocol: FrozenProtocol, reason: str) -> EpisodeRecord:
    provenance = RunProvenance(
        run_id=assignment.assignment_id,
        source_tree_hash="",
        scene_group_id=assignment.group_id,
        split_role="formal",
        physics_steps=0,
        evidence_kind=EvidenceKind.SOFTWARE,
        blocked_reason=reason,
        stages=[
            StageEvidence(stage=name, status=StageStatus.NOT_EXECUTED, reason=reason)
            for name in ("PERCEPTION", "INFERENCE", "ACTION")
        ],
    )
    return EpisodeRecord(
        assignment,
        VisualEpisodeOutcome(
            False, "INCOMPLETE", False, reason, 0.0, 0.0, 0.0, 0.0, terminal_reason=reason
        ),
        provenance,
        CostSnapshot(),
        float(protocol.spec.tcap_s or 600),
        None,
        (),
        (),
        (),
        {},
        run_status="BLOCKED",
    )


def run_assignment(
    assignment: EpisodeAssignment,
    protocol: FrozenProtocol,
    *,
    software_adapter: SoftwareEpisodeAdapter | None = None,
) -> EpisodeRecord:
    """记录一次分配；拒绝旧协议/未冻结方法，未接真实运行器时不执行。"""
    try:
        validate_formal_protocol(protocol)
        if assignment.method_id not in protocol.spec.method_hashes:
            raise ValueError("assignment method is not frozen")
        if (
            assignment.protocol_hash != protocol.content_hash
            or (assignment.pool_hash != protocol.spec.pool_hashes.get("formal"))
            or not assignment.scene_payload_json
        ):
            raise ValueError("assignment protocol/pool/scene source hash mismatch")
    except ValueError as error:
        return _blocked(assignment, protocol, str(error))
    if software_adapter is None:
        return _blocked(assignment, protocol, "actual research runtime adapter is not integrated")
    if software_adapter.evidence_kind != EvidenceKind.MOCK:
        raise ValueError("injected software adapter must be explicitly MOCK")
    result = software_adapter.run(assignment, protocol)
    if result.assignment != assignment or result.provenance.evidence_kind != EvidenceKind.MOCK:
        raise ValueError("software adapter returned wrong assignment or non-MOCK evidence")
    # A software fixture may simulate a completion branch but cannot contribute
    # a physical success or a shorter formal failure penalty.
    provenance = result.provenance.model_copy(update={"task_success": False})
    result = replace(
        result,
        outcome=replace(result.outcome, success=False, physical_success=False),
        provenance=provenance,
        source_verified=False,
        duration_penalized_s=float(protocol.spec.tcap_s or 600),
    )
    return result


def penalized_recovery_duration(record: EpisodeRecord, *, elapsed_s: float) -> float:
    """失败、未完成和未验收恢复统一使用预注册 60 秒惩罚。"""
    if not math.isfinite(elapsed_s) or elapsed_s < 0:
        raise ValueError("recovery duration must be finite nonnegative")
    return min(elapsed_s, 60.0) if record.accepted_task_success else 60.0


@dataclass(frozen=True)
class RerunAuthorization:
    """保留所有原记录散列，仅授权受同一基础设施损坏影响的完整配对。"""

    infrastructure_incident_id: str
    group_id: str
    method_ids: tuple[str, ...]
    original_record_hashes: tuple[str, ...]
    incident_ref: ArtifactReference


def authorize_paired_rerun(
    originals: Sequence[EpisodeRecord],
    incident: ArtifactReference | None,
    *,
    expected_method_ids: Sequence[str] | None = None,
) -> RerunAuthorization:
    """核对可读取的事故资料和全部原记录，任务失败不是重跑理由。"""
    if incident is None:
        raise ValueError("documented infrastructure incident is required")
    if not originals:
        raise ValueError("incident must retain original paired records")
    document = json.loads(incident.verify().read_text())
    if incident.schema_version != "incident.v1" or document.get("category") not in {
        "RENDERER_CRASH",
        "BACKEND_PROCESS_CRASH",
        "CORRUPTED_CAPTURE_STORAGE",
    }:
        raise ValueError("only documented infrastructure damage permits paired rerun")
    groups = {row.assignment.group_id for row in originals}
    methods = {row.assignment.method_id for row in originals}
    hashes = {row.content_hash for row in originals}
    if len(groups) != 1 or len(methods) != len(originals) or len(methods) < 2:
        raise ValueError("incident originals must be one complete unique method pair")
    if (
        expected_method_ids is None
        or methods != set(expected_method_ids)
        or (len(set(expected_method_ids)) != len(expected_method_ids))
    ):
        raise ValueError("incident must retain the complete frozen assignment method set")
    contexts = {
        (
            row.assignment.physics_seed,
            row.assignment.network_schedule_json,
            row.assignment.scene_payload_json,
            row.assignment.perturbation_json,
            row.assignment.pool_hash,
            row.assignment.protocol_hash,
        )
        for row in originals
    }
    if len(contexts) != 1:
        raise ValueError("incident originals must have identical paired scene/seed/network")
    if (
        set(document.get("affected_methods", ())) != methods
        or (set(document.get("original_record_hashes", ())) != hashes)
        or document.get("group_id") not in groups
    ):
        raise ValueError("incident does not bind all original paired records")
    if (
        not document.get("incident_id")
        or not document.get("diagnostic")
        or (not document.get("source_hashes"))
    ):
        raise ValueError("incident identity/diagnostic/source evidence missing")
    return RerunAuthorization(
        document["incident_id"],
        next(iter(groups)),
        tuple(sorted(methods)),
        tuple(sorted(hashes)),
        incident,
    )


def run_gate_replay(opportunities: Sequence[Opportunity], method_id: str) -> list[GateReplayRecord]:
    """保持全机会顺序，按各自冻结时刻回放；独立标签不输入门控。"""
    if method_id not in {"JOINT", "B3"}:
        raise ValueError("unsupported fixed gate replay method")
    if not opportunities or (
        len({value.opportunity_id for value in opportunities}) != len(opportunities)
    ):
        raise ValueError("fixed opportunities missing or duplicate")
    records = []
    for opportunity in opportunities:
        records.extend(
            replay_opportunities(
                [opportunity],
                cast(Literal["JOINT", "B3"], method_id),
                opportunity.replay_at,
                opportunity.replay_calibration_version,
            )
        )
    return records
