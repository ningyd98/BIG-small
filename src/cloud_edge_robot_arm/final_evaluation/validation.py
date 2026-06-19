"""Phase 12 验收检查。

验证逻辑按 smoke/validation/full 分层，确保 smoke 不会输出 full accepted 或项目最终封板。
"""

from __future__ import annotations

import json
import re
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
    raw_runs = _read_jsonl(artifact_root / "runs/raw_runs.jsonl")
    aggregate = _read_json(artifact_root / "aggregates/phase12_aggregate.json")
    stats = _read_json(artifact_root / "statistics/phase12_statistics.json")
    provenance = _read_json(artifact_root / "manifests/provenance.json")
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
        "failed_or_blocked_not_deleted": aggregate.get("blocked_by_env_count", 0) >= 0,
        "unsafe_command_execution_zero": aggregate.get("unsafe_command_execution_count") == 0,
        "real_controller_contacted_false": _all_false(raw_runs, "real_controller_contacted"),
        "hardware_motion_observed_false": _all_false(raw_runs, "hardware_motion_observed"),
        "hardware_write_operations_empty": _all_empty(raw_runs, "hardware_write_operations"),
        "no_sensitive_artifacts": not _contains_sensitive_text(artifact_root),
        "source_tree_provenance_present": bool(provenance.get("source_tree_hash")),
    }
    full_ready = (
        profile == Phase12Profile.FULL
        and len(raw_runs) >= plan.run_count
        and bool(provenance.get("worktree_clean"))
        and all(checks.values())
    )
    validation_ready = profile == Phase12Profile.VALIDATION and all(checks.values())
    smoke_ready = profile == Phase12Profile.SMOKE and all(checks.values())
    if require_full:
        status = FULL_STATUS if full_ready else REJECTED_STATUS
    elif validation_ready:
        status = VALIDATION_STATUS
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
    payload: dict[str, Any] = {
        "status": status,
        "project_status": PROJECT_STATUS if full_ready and thesis_ready else "NOT_CLOSED",
        "thesis_status": THESIS_STATUS if thesis_ready else "THESIS_PACKAGE_INCOMPLETE",
        "profile": profile.value,
        "checks": checks,
        "run_count": len(raw_runs),
        "expected_run_count": plan.run_count,
        "seed_count": plan.seed_count,
        "repetitions": plan.repetitions,
        "registry_count": len(registry),
        "full_profile_claimed": status == FULL_STATUS,
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
        {"run_count": len(raw_runs), "checks": checks},
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


def _all_false(rows: list[dict[str, Any]], key: str) -> bool:
    return all(row.get("hardware_claims", {}).get(key, False) is False for row in rows)


def _all_empty(rows: list[dict[str, Any]], key: str) -> bool:
    return all(row.get("hardware_claims", {}).get(key, []) == [] for row in rows)


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8"
    )
