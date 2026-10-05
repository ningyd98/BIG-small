"""Aggregate a research run ledger without promoting legacy or mock evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, Field

from cloud_edge_robot_arm.research.models import EvidenceKind, RunProvenance, StageStatus

CORE_STAGES = ("PERCEPTION", "INFERENCE", "ACTION")


def _has_hashes(values: Sequence[str]) -> bool:
    return bool(values) and all(value.strip() for value in values)


class ProvenanceAudit(BaseModel):
    historical_count: int = 0
    success_denominator: int = 0
    physical_success_count: int = 0
    occurred_stage_count: int = 0
    real_stage_count: int = 0
    expected_stage_count: int = 0
    stage_coverage: float = 0.0
    stage_authenticity: float = 0.0
    stage_authenticity_by_name: dict[str, dict[str, int]] = Field(default_factory=dict)
    leakage_count: int = 0
    cross_split_scene_groups: dict[str, list[str]] = Field(default_factory=dict)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)
    duplicate_run_ids: list[str] = Field(default_factory=list)
    audit_issues: dict[str, list[str]] = Field(default_factory=dict)


def audit_provenance(records: Sequence[RunProvenance]) -> ProvenanceAudit:
    """Audit only new research trials; retain pre-action blocks in the rate base."""
    result = ProvenanceAudit()
    splits_by_group: dict[str, set[str]] = defaultdict(set)
    first_by_id: dict[str, RunProvenance] = {}
    conflicting_ids: set[str] = set()
    online_truth_ids: set[str] = set()
    for record in records:
        if record.cohort == "HISTORICAL":
            result.historical_count += 1
            continue
        splits_by_group[record.scene_group_id].add(record.split_role)
        if record.ground_truth_exposed_online:
            online_truth_ids.add(record.run_id)
        first = first_by_id.get(record.run_id)
        if first is not None:
            if record.run_id not in result.duplicate_run_ids:
                result.duplicate_run_ids.append(record.run_id)
            if record != first:
                conflicting_ids.add(record.run_id)
            continue
        first_by_id[record.run_id] = record

    for record in first_by_id.values():
        result.success_denominator += 1
        result.expected_stage_count += max(len(record.stages), len(CORE_STAGES))
        occurred = [stage for stage in record.stages if stage.status != StageStatus.NOT_EXECUTED]
        result.occurred_stage_count += len(occurred)
        result.real_stage_count += sum(
            stage.status == StageStatus.REAL and _has_hashes(stage.source_hashes)
            for stage in occurred
        )
        for stage in occurred:
            counts = result.stage_authenticity_by_name.setdefault(
                stage.stage, {"real": 0, "occurred": 0}
            )
            counts["occurred"] += 1
            counts["real"] += int(
                stage.status == StageStatus.REAL and _has_hashes(stage.source_hashes)
            )

        issues: list[str] = []
        if record.run_id in conflicting_ids:
            issues.append("conflicting duplicate run ID")
        for name in CORE_STAGES:
            count = sum(stage.stage == name for stage in record.stages)
            if count == 0:
                issues.append(f"missing {name} stage")
            elif count > 1:
                issues.append(f"duplicate {name} stage")
        for stage in record.stages:
            if stage.status == StageStatus.REAL and not _has_hashes(stage.source_hashes):
                issues.append(f"{stage.stage} REAL stage has no source hashes")
        if issues:
            result.audit_issues[record.run_id] = issues

        reason = record.blocked_reason
        if not reason and not (record.model_snapshot_hash or "").strip():
            reason = "missing model snapshot"
        if not reason and not _has_hashes(record.observation_hashes):
            reason = "missing RGB-D observation hashes"
        if not reason:
            blocked_stage = next(
                (stage for stage in record.stages if stage.status == StageStatus.BLOCKED), None
            )
            if blocked_stage is not None:
                reason = blocked_stage.reason or f"{blocked_stage.stage} blocked"
        if reason:
            result.blocked_reasons[record.run_id] = reason

        authentic = (
            record.evidence_kind == EvidenceKind.PHYSICS
            and record.physics_steps > 0
            and bool(record.source_tree_hash.strip())
            and bool((record.model_snapshot_hash or "").strip())
            and _has_hashes(record.observation_hashes)
            and bool(record.stages)
            and not issues
            and all(
                stage.status == StageStatus.REAL and _has_hashes(stage.source_hashes)
                for stage in record.stages
            )
            and not reason
            and record.run_id not in online_truth_ids
        )
        if record.task_success and authentic:
            result.physical_success_count += 1

    result.cross_split_scene_groups = {
        group: sorted(splits)
        for group, splits in splits_by_group.items()
        if len(splits) > 1
    }
    result.leakage_count = len(online_truth_ids) + len(result.cross_split_scene_groups)
    if result.expected_stage_count:
        result.stage_coverage = result.occurred_stage_count / result.expected_stage_count
    if result.occurred_stage_count:
        result.stage_authenticity = result.real_stage_count / result.occurred_stage_count
    return result
