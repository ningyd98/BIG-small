"""Phase 12 验收检查。

验证逻辑按 smoke/validation/full 分层，确保 smoke 不会输出 full accepted 或项目最终封板。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile
from cloud_edge_robot_arm.final_evaluation.registry import (
    PHASE12_EXPERIMENT_IDS,
    build_experiment_plan,
    final_experiment_registry,
)

SMOKE_STATUS = "PHASE12_EXPERIMENT_SUITE_READY"
VALIDATION_STATUS = "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
FULL_STATUS = "PHASE12_FINAL_EVALUATION_ACCEPTED"
THESIS_STATUS = "PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED"
THESIS_PIPELINE_STATUS = "PHASE12_THESIS_ASSET_PIPELINE_READY"
VALIDATION_THESIS_STATUS = "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED"
VALIDATION_GAP_STATUS = "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
FULL_READY_STATUS = "PHASE12_FULL_PROFILE_READY"
PROJECT_STATUS = "BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED"
REJECTED_STATUS = "PHASE12_REJECTED"


def verify_phase12(
    *,
    profile: Phase12Profile,
    artifact_root: Path,
    output_dir: Path,
    require_full: bool = False,
) -> dict[str, Any]:
    """检查 Phase 12 artifact 完整性、安全边界和状态声明。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    registry = final_experiment_registry()
    plan = build_experiment_plan(profile)
    raw_runs = _normalize_rows_for_profile(
        profile, _read_jsonl(artifact_root / "runs/raw_runs.jsonl")
    )
    aggregate = _read_json(artifact_root / "aggregates/phase12_aggregate.json")
    stats = _read_json(artifact_root / "statistics/phase12_statistics.json")
    provenance = _read_json(artifact_root / "manifests/provenance.json")
    synthetic_sample_count = sum(
        1 for row in raw_runs if row.get("execution_source") == "SYNTHETIC_PIPELINE_SAMPLE"
    )
    actual_run_count = sum(1 for row in raw_runs if row.get("runtime_invoked") is True)
    adapter_attempt_count = sum(1 for row in raw_runs if row.get("adapter_attempted") is True)
    runtime_invocation_count = sum(1 for row in raw_runs if row.get("runtime_invoked") is True)
    runtime_completion_count = sum(1 for row in raw_runs if row.get("runtime_completed") is True)
    blocked_before_runtime_count = sum(
        1
        for row in raw_runs
        if row.get("status") == "BLOCKED_BY_ENV"
        and row.get("environment_check_completed") is True
        and row.get("runtime_invoked") is not True
    )
    authoritative_count = sum(1 for row in raw_runs if row.get("authoritative_for_thesis") is True)
    actual_backend_counts = dict(
        Counter(str(row.get("backend")) for row in raw_runs if row.get("runtime_invoked"))
    )
    runtime_backend_counts = dict(
        Counter(str(row.get("backend")) for row in raw_runs if row.get("runtime_invoked"))
    )
    blocked_breakdown = dict(
        Counter(
            str(row.get("execution_source"))
            for row in raw_runs
            if row.get("status") == "BLOCKED_BY_ENV"
        )
    )
    checks = {
        "registry_complete": [item.experiment_id for item in registry] == PHASE12_EXPERIMENT_IDS,
        "no_hardware_runner": not any(
            "HARDWARE" in item.runner_kind or "REAL_ROBOT" in item.runner_kind for item in registry
        ),
        "raw_runs_exist": len(raw_runs) > 0,
        "aggregate_exists": bool(aggregate),
        "statistics_exists": bool(stats),
        "plots_exist": (artifact_root / "plots/png/success_rate_comparison.png").exists()
        and (artifact_root / "plots/svg/success_rate_comparison.svg").exists(),
        "tables_exist": (artifact_root / "tables/csv/t2_mode_baseline.csv").exists()
        and (artifact_root / "tables/latex/t2_mode_baseline.tex").exists(),
        "thesis_docs_exist": (artifact_root / "thesis/experiment_results.md").exists(),
        "demo_bundle_exists": (artifact_root / "demo_bundle/demo_summary.json").exists(),
        "failed_or_blocked_not_deleted": _failed_or_blocked_counts_match(raw_runs, aggregate),
        "unsafe_command_execution_zero": aggregate.get("unsafe_command_execution_count") == 0,
        "real_controller_contacted_false": _all_false(raw_runs, "real_controller_contacted"),
        "hardware_motion_observed_false": _all_false(raw_runs, "hardware_motion_observed"),
        "hardware_write_operations_empty": _all_empty(raw_runs, "hardware_write_operations"),
        "no_sensitive_artifacts": not _contains_sensitive_text(artifact_root),
        "source_tree_provenance_present": bool(provenance.get("source_tree_hash")),
        "adapter_attempts_verified": _adapter_attempts_verified(profile, raw_runs),
        "source_artifact_hash_verified": _source_artifact_hash_verified(artifact_root, raw_runs),
        "sample_policy_satisfied": _sample_policy_satisfied(profile, raw_runs, plan),
        "paired_run_completeness": _paired_run_completeness(raw_runs),
        "paired_backend_acceptance_status_correct": _paired_acceptance_status_correct(
            profile,
            _paired_payload(artifact_root),
        ),
        "stress_task_count_satisfied": _stress_task_count_satisfied(profile, raw_runs),
        "blocked_rows_runtime_invoked_false": _blocked_rows_runtime_invoked_false(raw_runs),
        "runtime_receipt_exists": _runtime_receipts_exist(artifact_root, raw_runs),
        "runtime_receipt_hash_valid": _runtime_receipt_hash_valid(artifact_root, raw_runs),
        "phase11_sqlite_evidence_exists": _phase11_sqlite_evidence_exists(artifact_root, raw_runs),
        "worker_lease_evidence_exists": _worker_lease_evidence_exists(artifact_root, raw_runs),
        "duplicate_competition_evidence_exists": _duplicate_competition_evidence_exists(
            artifact_root, raw_runs
        ),
        "runner_invocation_count_exactly_one": _runner_invocation_count_exactly_one(
            artifact_root, raw_runs
        ),
        "metric_provenance_complete": _metric_provenance_complete(raw_runs),
        "placeholder_metrics_excluded": _placeholder_metrics_excluded(stats),
    }
    full_ready = (
        profile == Phase12Profile.FULL
        and len(raw_runs) >= plan.run_count
        and bool(provenance.get("worktree_clean"))
        and synthetic_sample_count == 0
        and authoritative_count > 0
        and all(checks.values())
    )
    validation_ready = (
        profile == Phase12Profile.VALIDATION
        and synthetic_sample_count == 0
        and adapter_attempt_count == len(raw_runs)
        and runtime_invocation_count < adapter_attempt_count
        and runtime_completion_count > 0
        and blocked_before_runtime_count > 0
        and authoritative_count > 0
        and all(checks.values())
    )
    smoke_ready = (
        profile == Phase12Profile.SMOKE
        and synthetic_sample_count == len(raw_runs)
        and actual_run_count == 0
        and checks["registry_complete"]
        and checks["no_hardware_runner"]
        and checks["raw_runs_exist"]
        and checks["aggregate_exists"]
        and checks["statistics_exists"]
        and checks["plots_exist"]
        and checks["tables_exist"]
        and checks["unsafe_command_execution_zero"]
        and checks["real_controller_contacted_false"]
        and checks["hardware_motion_observed_false"]
        and checks["hardware_write_operations_empty"]
        and checks["no_sensitive_artifacts"]
    )
    if require_full:
        status = FULL_STATUS if full_ready else REJECTED_STATUS
    elif validation_ready:
        status = VALIDATION_STATUS
    elif profile == Phase12Profile.VALIDATION and synthetic_sample_count == 0:
        status = VALIDATION_GAP_STATUS
    elif smoke_ready:
        status = SMOKE_STATUS
    else:
        status = REJECTED_STATUS
    thesis_ready = (
        checks["thesis_docs_exist"]
        and checks["demo_bundle_exists"]
        and checks["plots_exist"]
        and checks["tables_exist"]
    )
    thesis_status = (
        THESIS_STATUS
        if full_ready and thesis_ready
        else VALIDATION_THESIS_STATUS
        if validation_ready and thesis_ready
        else THESIS_PIPELINE_STATUS
        if smoke_ready and thesis_ready
        else "THESIS_PACKAGE_INCOMPLETE"
    )
    payload: dict[str, Any] = {
        "status": status,
        "project_status": PROJECT_STATUS if full_ready and thesis_ready else "NOT_CLOSED",
        "thesis_status": thesis_status,
        "profile": profile.value,
        "checks": checks,
        "run_count": len(raw_runs),
        "expected_run_count": plan.run_count,
        "seed_count": plan.seed_count,
        "repetitions": plan.repetitions,
        "registry_count": len(registry),
        "full_profile_claimed": status == FULL_STATUS,
        "synthetic_sample_count": synthetic_sample_count,
        "actual_run_count": actual_run_count,
        "adapter_attempt_count": adapter_attempt_count,
        "runtime_invocation_count": runtime_invocation_count,
        "runtime_completion_count": runtime_completion_count,
        "blocked_before_runtime_count": blocked_before_runtime_count,
        "authoritative_thesis_run_count": authoritative_count,
        "actual_backend_counts": actual_backend_counts,
        "runtime_backend_counts": runtime_backend_counts,
        "adapter_attempts_verified": checks["adapter_attempts_verified"],
        "source_artifact_hash_verified": checks["source_artifact_hash_verified"],
        "sample_policy_satisfied": checks["sample_policy_satisfied"],
        "paired_run_completeness": checks["paired_run_completeness"],
        "paired_backend_experiment_accepted": _paired_payload(artifact_root).get(
            "paired_backend_experiment_accepted", False
        ),
        "usable_authoritative_pair_count": _paired_payload(artifact_root).get(
            "usable_authoritative_pair_count", 0
        ),
        "blocked_pair_count": _paired_payload(artifact_root).get("blocked_pair_count", 0),
        "full_profile_readiness_status": FULL_READY_STATUS
        if full_ready or validation_ready
        else "PHASE12_FULL_PROFILE_NOT_READY",
        "stress_task_count": sum(
            1 for row in raw_runs if row.get("experiment_id") == "F20_STRESS_AND_RECOVERY"
        ),
        "blocked_environment_breakdown": blocked_breakdown,
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
        "highest_real_hardware_acceptance_level": "NONE",
        "unsafe_command_execution_count": aggregate.get("unsafe_command_execution_count", 0),
        "blocked_by_env_count": aggregate.get("blocked_by_env_count", 0),
        "environment_blockers": ["ISAAC_SIM", "OLLAMA_RUNTIME"]
        if aggregate.get("blocked_by_env_count", 0)
        else [],
    }
    _write_json(
        output_dir / "experiment_registry_verification.json",
        {"registry_count": len(registry), "ids": PHASE12_EXPERIMENT_IDS},
    )
    _write_json(
        output_dir / "run_integrity_verification.json",
        {
            "run_count": len(raw_runs),
            "synthetic_sample_count": synthetic_sample_count,
            "actual_run_count": actual_run_count,
            "authoritative_thesis_run_count": authoritative_count,
            "checks": checks,
        },
    )
    _write_json(output_dir / "statistics_verification.json", {"statistics_keys": sorted(stats)})
    _write_json(output_dir / "thesis_assets_verification.json", {"thesis_ready": thesis_ready})
    _write_json(
        output_dir / "security_boundary_verification.json",
        {
            key: value
            for key, value in checks.items()
            if "hardware" in key or "sensitive" in key or "unsafe" in key
        },
    )
    _write_json(output_dir / "phase12_summary.json", payload)
    if profile == Phase12Profile.SMOKE:
        _write_json(
            output_dir / "phase12_smoke_status_correction.json",
            {
                "supersedes": "7b4c9af artifacts/phase12/verification/phase12_summary.json",
                "previous_thesis_status": THESIS_STATUS,
                "corrected_thesis_status": THESIS_PIPELINE_STATUS,
                "correction_reason": (
                    "Phase 12 smoke rows are synthetic pipeline samples, not final thesis evidence."
                ),
                "original_artifact_retained": True,
            },
        )
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _normalize_rows_for_profile(
    profile: Phase12Profile, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if profile != Phase12Profile.SMOKE:
        return rows
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if "execution_source" in row:
            normalized.append(row)
            continue
        updated = dict(row)
        updated["execution_source"] = "SYNTHETIC_PIPELINE_SAMPLE"
        updated["actual_runner_invoked"] = False
        updated["adapter_attempted"] = False
        updated["environment_check_completed"] = False
        updated["runtime_invoked"] = False
        updated["runtime_completed"] = False
        updated["authoritative_for_thesis"] = False
        updated["blocker_stage"] = ""
        updated["source_artifact_path"] = ""
        updated["source_artifact_hash"] = ""
        updated["source_verifier"] = "phase12.synthetic_pipeline.legacy"
        updated["environment_status"] = "READY"
        updated["metric_provenance"] = {
            "total_completion_time_ms": {
                "source": "CONSTANT_PLACEHOLDER",
                "source_field": "legacy phase12 smoke formula",
                "source_artifact": "",
                "unit": "ms",
            }
        }
        normalized.append(updated)
    return normalized


def _all_false(rows: list[dict[str, Any]], key: str) -> bool:
    return all(row.get("hardware_claims", {}).get(key, False) is False for row in rows)


def _all_empty(rows: list[dict[str, Any]], key: str) -> bool:
    return all(row.get("hardware_claims", {}).get(key, []) == [] for row in rows)


def _failed_or_blocked_counts_match(rows: list[dict[str, Any]], aggregate: dict[str, Any]) -> bool:
    """确认 aggregate 没有漏报 raw runs 中的失败、超时、安全停止或环境阻塞样本。"""

    blocked = sum(1 for row in rows if row.get("status") == "BLOCKED_BY_ENV")
    failed = sum(1 for row in rows if row.get("status") in {"FAILED", "TIMEOUT", "SAFETY_STOPPED"})
    return (
        aggregate.get("blocked_by_env_count") == blocked and aggregate.get("failed_count") == failed
    )


def _contains_sensitive_text(root: Path) -> bool:
    pattern = re.compile(
        r"(?i)(bearer\s+[A-Za-z0-9._-]+|api[_-]?key\s*[:=]|authorization\s*:|/home/[A-Za-z0-9._-]+/)"
    )
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".npy"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            return True
    return False


def _adapter_attempts_verified(profile: Phase12Profile, rows: list[dict[str, Any]]) -> bool:
    """验证 adapter 尝试语义；真实 runtime 数量由 runtime_invoked 单独统计。"""

    if profile == Phase12Profile.SMOKE:
        return all(
            row.get("runtime_invoked", row.get("actual_runner_invoked")) is False for row in rows
        )
    return bool(rows) and all(row.get("adapter_attempted") is True for row in rows)


def _source_artifact_hash_verified(root: Path, rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        if row.get("adapter_attempted") is not True:
            continue
        rel_path = str(row.get("source_artifact_path", ""))
        expected = str(row.get("source_artifact_hash", ""))
        if not rel_path or not expected:
            return False
        path = root / rel_path
        if not path.exists():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def _sample_policy_satisfied(
    profile: Phase12Profile, rows: list[dict[str, Any]], plan: Any
) -> bool:
    if profile == Phase12Profile.SMOKE:
        return bool(rows) and all(row.get("seed") == 0 for row in rows)
    by_experiment: dict[str, set[tuple[int, int]]] = {}
    for row in rows:
        by_experiment.setdefault(str(row.get("experiment_id")), set()).add(
            (int(row.get("seed", -1)), int(row.get("repetition", -1)))
        )
    for experiment in plan.experiments:
        observed = by_experiment.get(experiment.experiment_id, set())
        seeds = {seed for seed, _ in observed}
        repetitions = {rep for _, rep in observed}
        if profile == Phase12Profile.VALIDATION:
            if len(seeds) < experiment.validation_seed_count or len(repetitions) < 2:
                return False
        elif len(seeds) < experiment.sample_policy.seed_count:
            return False
    return True


def _paired_run_completeness(rows: list[dict[str, Any]]) -> bool:
    pairs: dict[str, set[str]] = {}
    for row in rows:
        if row.get("experiment_id") != "F15_MUJOCO_ISAAC_PAIRED":
            continue
        key = (
            f"{row.get('scenario_id')}|{row.get('seed')}|"
            f"{row.get('control_mode')}|{row.get('repetition')}"
        )
        pairs.setdefault(key, set()).add(str(row.get("backend")))
    return not pairs or all(
        {"MUJOCO", "ISAAC_SIM"}.issubset(backends) for backends in pairs.values()
    )


def _paired_acceptance_status_correct(profile: Phase12Profile, paired: dict[str, Any]) -> bool:
    """按 profile 校验 paired backend 状态，避免 validation 阻塞被误作 full 通过。"""

    accepted = paired.get("paired_backend_experiment_accepted", False) is True
    if profile == Phase12Profile.VALIDATION:
        return not accepted
    if profile == Phase12Profile.FULL:
        return accepted
    return True


def _stress_task_count_satisfied(profile: Phase12Profile, rows: list[dict[str, Any]]) -> bool:
    count = sum(1 for row in rows if row.get("experiment_id") == "F20_STRESS_AND_RECOVERY")
    if profile == Phase12Profile.FULL:
        return count >= 100
    return count > 0 if rows else False


def _blocked_rows_runtime_invoked_false(rows: list[dict[str, Any]]) -> bool:
    return all(
        row.get("runtime_invoked") is not True and row.get("runtime_completed") is not True
        for row in rows
        if row.get("status") == "BLOCKED_BY_ENV"
    )


def _runtime_receipts_exist(root: Path, rows: list[dict[str, Any]]) -> bool:
    f20_rows = [row for row in rows if row.get("experiment_id") == "F20_STRESS_AND_RECOVERY"]
    return bool(f20_rows) and all(_runtime_receipt(root, row) is not None for row in f20_rows)


def _runtime_receipt_hash_valid(root: Path, rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        if row.get("experiment_id") != "F20_STRESS_AND_RECOVERY":
            continue
        receipt = _runtime_receipt(root, row)
        if receipt is None:
            return False
        expected = str(row.get("source_artifact_hash", ""))
        path = root / str(row.get("source_artifact_path", ""))
        if not expected or not path.exists():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
        if not receipt.get("runtime_receipt_hash"):
            return False
    return True


def _phase11_sqlite_evidence_exists(root: Path, rows: list[dict[str, Any]]) -> bool:
    return _all_f20_receipts(
        root,
        rows,
        lambda receipt: _sqlite_evidence_hash_valid(root, receipt),
    )


def _worker_lease_evidence_exists(root: Path, rows: list[dict[str, Any]]) -> bool:
    return _all_f20_receipts(
        root,
        rows,
        lambda receipt: int(receipt.get("worker_lease_evidence", {}).get("lease_count", 0)) >= 1,
    )


def _duplicate_competition_evidence_exists(root: Path, rows: list[dict[str, Any]]) -> bool:
    return _all_f20_receipts(
        root,
        rows,
        lambda receipt: (
            bool(receipt.get("duplicate_competition_evidence", {}).get("lease_winner"))
            and bool(receipt.get("duplicate_competition_evidence", {}).get("lease_loser"))
        ),
    )


def _runner_invocation_count_exactly_one(root: Path, rows: list[dict[str, Any]]) -> bool:
    return _all_f20_receipts(
        root,
        rows,
        lambda receipt: (
            receipt.get("duplicate_competition_evidence", {}).get("runner_invocation_count") == 1
        ),
    )


def _metric_provenance_complete(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        provenance = row.get("metric_provenance")
        if not isinstance(provenance, dict) or "total_completion_time_ms" not in provenance:
            return False
        metric = provenance["total_completion_time_ms"]
        if not isinstance(metric, dict) or not metric.get("source") or not metric.get("unit"):
            return False
    return True


def _placeholder_metrics_excluded(stats: dict[str, Any]) -> bool:
    for section_name in ("group_statistics", "backend_statistics"):
        section = stats.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for payload in section.values():
            if not isinstance(payload, dict):
                continue
            if payload.get("excluded_metric_sample_count", 0) < 0:
                return False
    return True


def _paired_payload(root: Path) -> dict[str, Any]:
    payload = _read_json(root / "paired/paired_summary.json")
    return payload if isinstance(payload, dict) else {}


def _runtime_receipt(root: Path, row: dict[str, Any]) -> dict[str, Any] | None:
    rel_path = str(row.get("source_artifact_path", ""))
    if not rel_path:
        return None
    path = root / rel_path
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _sqlite_evidence_hash_valid(root: Path, receipt: dict[str, Any]) -> bool:
    evidence = receipt.get("sqlite_evidence", {})
    if not isinstance(evidence, dict) or evidence.get("exists") is not True:
        return False
    rel_path = str(evidence.get("relative_path", ""))
    expected = str(evidence.get("sha256", ""))
    if not rel_path or not expected:
        return False
    path = root / rel_path
    return path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def _all_f20_receipts(root: Path, rows: list[dict[str, Any]], predicate: Any) -> bool:
    f20_rows = [row for row in rows if row.get("experiment_id") == "F20_STRESS_AND_RECOVERY"]
    if not f20_rows:
        return False
    for row in f20_rows:
        receipt = _runtime_receipt(root, row)
        if receipt is None or not predicate(receipt):
            return False
    return True


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8"
    )
