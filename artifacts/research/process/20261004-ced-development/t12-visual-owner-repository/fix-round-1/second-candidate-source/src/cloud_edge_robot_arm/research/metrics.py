"""研究全分母诊断；正式物理来源重算未整合时不接受元数据成功。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

import numpy as np

from cloud_edge_robot_arm.edge.evidence.opportunities import (
    GateReplayRecord,
    Opportunity,
    summarize_gate_replay,
)
from cloud_edge_robot_arm.research.assignments import EpisodeRecord
from cloud_edge_robot_arm.research.provenance import audit_provenance
from cloud_edge_robot_arm.research.statistics import (
    clustered_rate_reduction,
    holm_adjust,
    paired_binary_effect,
    stratified_paired_bootstrap,
    zero_event_upper_bound,
)

PRIMARY_FAMILY = ("G2_REQUESTS", "G2_SUCCESS", "G2_SAFETY", "G3_FALSE_ACCEPT", "G4_DURATION")


def _rate(count: int, n: int) -> float | None:
    return count / n if n else None


def _verification_statuses(record: EpisodeRecord) -> list[str]:
    statuses = []
    for value in record.verification_records:
        raw = value.get("record", value)
        if isinstance(raw, Mapping):
            statuses.append(str(raw.get("status", "UNKNOWN")))
    return statuses


def _method_metrics(rows: Sequence[EpisodeRecord], *, software_only: bool) -> dict[str, Any]:
    n = len(rows)
    online = sum(row.outcome.online_reported_complete is True for row in rows)
    false_completion = sum(
        row.outcome.online_reported_complete is True and not row.outcome.physical_success
        for row in rows
    )
    declared_success = sum(
        bool(
            row.outcome.success
            and row.outcome.physical_success
            and row.outcome.online_reported_complete
        )
        for row in rows
    )
    safety = sum(row.outcome.safety_violation for row in rows)
    group_n = len({row.assignment.group_id for row in rows})
    progress = sum(
        any(
            marker in (row.outcome.terminal_reason or row.outcome.failure_reason or "").upper()
            for marker in ("NO_PROGRESS", "STALL")
        )
        for row in rows
    )
    fallback = sum(row.run_status == "FALLBACK" for row in rows)
    unknown = sum("UNKNOWN" in _verification_statuses(row) for row in rows)
    roles: Counter[str] = Counter()
    for row in rows:
        roles.update(row.costs.requests_by_role)
    durations = [row.duration_penalized_s for row in rows]
    latency = [row.costs.decision_latency_s for row in rows]
    return {
        "assigned_denominator": n,
        "diagnostic_only": True,
        "task_success_count": declared_success if software_only else 0,
        "task_success_rate": _rate(declared_success, n) if software_only else None,
        "declared_task_success_count": declared_success,
        "declared_safety_violation_count": safety,
        "safety_violation_rate": _rate(safety, n) if software_only else None,
        "safety_zero_event_upper95": zero_event_upper_bound(group_n)
        if group_n and safety == 0
        else None,
        "safety_zero_event_bound_basis": "INDEPENDENT_BASE_GROUP_ANY_VIOLATION",
        "provider_refusal_rate": None,
        "provider_refusal_status": "NOT_RECORDED",
        "fault_response_p90_s": None,
        "fault_response_status": "RAW_FAULT_TIMELINE_NOT_VERIFIED",
        "online_done_denominator": online,
        "false_completion_count": false_completion,
        "false_completion_rate": _rate(false_completion, online),
        "false_completion_basis": "DECLARED_UNVERIFIED_PHYSICAL_OUTCOME",
        "fallback_episode_count": fallback,
        "fallback_episode_rate": _rate(fallback, n),
        "fallback_decision_count": None,
        "decision_round_denominator": None,
        "fallback_rate": None,
        "fallback_decision_rate": None,
        "fallback_decision_status": "NOT_RECORDED",
        "fallback_basis": "SOURCE_QUALIFIED_DECISION_ROUNDS_REQUIRED",
        "no_progress_count": progress,
        "no_progress_rate": _rate(progress, n),
        "unknown_episode_count": unknown,
        "unknown_episode_rate": _rate(unknown, n),
        "unknown_condition_count": None,
        "condition_evaluation_denominator": None,
        "unknown_condition_rate": None,
        "unknown_condition_status": "NOT_RECORDED",
        "unknown_condition_basis": "SOURCE_QUALIFIED_CONDITION_EVALUATIONS_REQUIRED",
        "terminal_status_counts": dict(Counter(row.run_status for row in rows)),
        "cloud_requests_total": sum(row.costs.cloud_model_requests for row in rows),
        "cloud_requests_mean": float(np.mean([row.costs.cloud_model_requests for row in rows]))
        if n
        else None,
        "model_requests_total": sum(row.costs.model_requests for row in rows),
        "model_requests_by_role": dict(roles),
        "telemetry_messages_total": sum(row.costs.telemetry_messages for row in rows),
        "application_bytes_total": sum(row.costs.application_bytes for row in rows),
        "penalized_duration_p95_s": float(np.quantile(durations, 0.95)) if n else None,
        "penalized_duration_mean_s": float(np.mean(durations)) if n else None,
        "recovery_failed_penalty_s": 60.0,
        "decision_latency_mean_s": float(np.mean(latency)) if n else None,
        "latency_scope": "DECLARED_MEASURED_COMPONENT_SUM",
        "inference_unknown_count": sum(row.costs.inference_s is None for row in rows),
        "provider_versions": [dict(row.provider_versions) for row in rows],
    }


def compute_research_metrics(
    records: Sequence[EpisodeRecord],
    opportunities: Sequence[Opportunity],
    gate_records: Sequence[GateReplayRecord],
    *,
    software_only: bool = False,
) -> Mapping[str, object]:
    """保留全部分配及回放分母；显式软件结果只供数学实现校验。"""
    ids = [record.assignment.assignment_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate run assignment cannot inflate research denominator")
    method_ids = sorted({record.assignment.method_id for record in records})
    methods = {
        method: _method_metrics(
            [row for row in records if row.assignment.method_id == method],
            software_only=software_only,
        )
        for method in method_ids
    }
    audit = audit_provenance([record.provenance for record in records])
    metrics: dict[str, Any] = {
        "schema_version": "ced.research-metrics.v1",
        "scope": "SOFTWARE_ONLY" if software_only else "UNVERIFIED",
        "formal_accepted": False,
        "source_validation_status": "NOT_CONFIGURED",
        "source_validation_reason": (
            "independent raw physics/capture/model/decision source verifier is not integrated"
        ),
        "assignment_denominator": len(records),
        "independent_group_denominator": len({row.assignment.group_id for row in records}),
        "accepted_physical_success": 0,
        "methods": methods,
        "gate": {},
        "effects": {},
        "declared_stage_audit": audit.model_dump(),
        "physical_source_validation": {"accepted": 0, "missing": len(records)},
        "goal_source_status": {
            key: "NOT_RUN" for key in ("G0", "G1", "G2", "G2a", "G3", "G4", "G5")
        },
        "recovery": {
            "assigned_groups": len(
                {
                    row.assignment.group_id
                    for row in records
                    if row.provenance.split_role == "recovery"
                }
            ),
            "accepted_recovery_success": 0,
            "failure_penalty_s": 60.0,
        },
    }
    if {"B0", "JOINT"}.issubset(methods):
        pairs: dict[str, dict[str, EpisodeRecord]] = {}
        for row in records:
            if (
                row.assignment.method_id in {"B0", "JOINT"}
                and row.provenance.split_role == "formal"
            ):
                pair = pairs.setdefault(row.assignment.group_id, {})
                if row.assignment.method_id in pair:
                    raise ValueError(
                        "repeated base group needs hierarchical explicit seed analysis"
                    )
                pair[row.assignment.method_id] = row
        if any(set(pair) != {"B0", "JOINT"} for pair in pairs.values()):
            raise ValueError("main analysis must retain all paired assigned groups")
        if pairs:
            success = [
                (
                    bool(
                        pair["JOINT"].outcome.success
                        and pair["JOINT"].outcome.physical_success
                        and pair["JOINT"].outcome.online_reported_complete
                    ),
                    bool(
                        pair["B0"].outcome.success
                        and pair["B0"].outcome.physical_success
                        and pair["B0"].outcome.online_reported_complete
                    ),
                )
                for pair in pairs.values()
            ]
            safety = [
                (pair["JOINT"].outcome.safety_violation, pair["B0"].outcome.safety_violation)
                for pair in pairs.values()
            ]
            effects = metrics["effects"]
            effects["G2_SUCCESS"] = asdict(
                paired_binary_effect(success, null_difference=-0.03, alternative="greater")
            )
            effects["G2_SAFETY"] = asdict(
                paired_binary_effect(safety, null_difference=0.01, alternative="less")
            )
            formal_rows = [row for row in records if row.provenance.split_role == "formal"]
            for goal, metric in (
                ("G2_REQUESTS", "cloud_requests_relative_reduction"),
                ("G2A_BYTES", "application_bytes_relative_reduction"),
                ("G2A_DURATION", "duration_penalized_s_p95_relative_reduction"),
            ):
                effects[goal] = asdict(stratified_paired_bootstrap(formal_rows, metric))
            metrics["main_paired_group_denominator"] = len(pairs)
    if gate_records:
        if not opportunities:
            raise ValueError("gate records require their identical fixed source opportunities")
        for method in sorted({row.method_id for row in gate_records}):
            metrics["gate"][method] = summarize_gate_replay(
                opportunities, [row for row in gate_records if row.method_id == method]
            )
        if {"B3", "JOINT"}.issubset(metrics["gate"]):
            base = metrics["gate"]["B3"]["false_acceptance_rate"]
            joint = metrics["gate"]["JOINT"]["false_acceptance_rate"]
            metrics["gate"]["relative_false_acceptance_reduction"] = (
                (base - joint) / base if base else None
            )
            # All opportunities remain in the descriptive table. Only independently
            # INVALID opportunities enter FA counts; multiple frames/actions from one
            # base scene remain a single resampling unit, including zero-count groups.
            groups = sorted({value.group_id for value in opportunities})
            by_method = {
                method: {row.opportunity_id: row for row in gate_records if row.method_id == method}
                for method in ("B3", "JOINT")
            }
            counts = []
            for group in groups:
                invalid = [
                    value
                    for value in opportunities
                    if value.group_id == group and value.oracle_label == "INVALID"
                ]
                method_counts = [
                    sum(
                        by_method[method][value.opportunity_id].verdict.status == "VALID"
                        for value in invalid
                    )
                    for method in ("B3", "JOINT")
                ]
                counts.append((method_counts[0], method_counts[1]))
            strata_by_group = {
                row.assignment.group_id: row.assignment.stratum_id for row in records
            }
            if any(group not in strata_by_group for group in groups) and not software_only:
                metrics["gate"]["cluster_analysis_status"] = "NOT_RUN_NO_SOURCE_STRATA"
            else:
                # Explicit SOFTWARE_ONLY fixtures may omit a formal scene assignment;
                # they use one declared diagnostic stratum, never a formal stratum claim.
                strata = [strata_by_group.get(group, "SOFTWARE_UNBOUND") for group in groups]
                metrics["effects"]["G3_FALSE_ACCEPT"] = asdict(
                    clustered_rate_reduction(counts, strata)
                )
            metrics["fixed_opportunity_group_denominator"] = len(groups)
            invalid_groups = len(
                {value.group_id for value in opportunities if value.oracle_label == "INVALID"}
            )
            for method in ("B3", "JOINT"):
                summary = metrics["gate"][method]
                summary["false_acceptance_zero_event_group_upper95"] = (
                    zero_event_upper_bound(invalid_groups)
                    if invalid_groups and summary["false_acceptance"] == 0
                    else None
                )
                summary["zero_event_bound_basis"] = "INDEPENDENT_BASE_GROUP_ANY_FALSE_ACCEPT"
    elif opportunities:
        metrics["gate"]["status"] = "NOT_RUN"
        metrics["gate"]["fixed_opportunity_denominator"] = len(opportunities)
    raw_p = {key: metrics["effects"].get(key, {}).get("p_value") for key in PRIMARY_FAMILY}
    adjusted = holm_adjust(
        {key: value if value is not None else 1.0 for key, value in raw_p.items()}
    )
    for key in PRIMARY_FAMILY:
        if key in metrics["effects"]:
            metrics["effects"][key]["adjusted_p_value"] = adjusted[key]
    metrics["primary_family"] = {
        "hypotheses": list(PRIMARY_FAMILY),
        "raw_p": raw_p,
        "holm_adjusted_p": adjusted,
        "missing_p_for_correction": 1.0,
        "interval_scope": "RAW_UNADJUSTED_95_PERCENT",
        "family_alpha": 0.05,
    }
    return metrics
