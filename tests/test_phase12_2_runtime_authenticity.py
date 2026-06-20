"""Phase 12.2 runtime authenticity and full-profile readiness tests.

中文说明：这些测试约束 validation 级实验必须区分 adapter 尝试、真实 runtime
调用、环境阻塞和论文可用证据，防止把环境检查或占位指标误当作实际运行结果。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from csv import DictReader
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import cloud_edge_robot_arm.final_evaluation.runner as phase12_runner
from cloud_edge_robot_arm.final_evaluation import validation as phase12_validation
from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_path,
)
from cloud_edge_robot_arm.final_evaluation.adapters.phase8 import Phase8ExperimentRunnerAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.simulation_runtime import Phase11RuntimeAdapter
from cloud_edge_robot_arm.final_evaluation.aggregation import aggregate_results
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    EnvironmentStatus,
    ExecutionSource,
    HardwareClaims,
    MetricProvenance,
    MetricSource,
    Phase12Backend,
    Phase12Profile,
    Phase12RunManifest,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.final_evaluation.plots import export_plots
from cloud_edge_robot_arm.final_evaluation.report import export_thesis_assets
from cloud_edge_robot_arm.final_evaluation.runner import (
    _authoritative_for_thesis,
    _event,
    _hardware_claims_from_results,
    _normalize_source_artifact_hashes,
    _result_from_adapter,
    run_phase12_experiments,
)
from cloud_edge_robot_arm.final_evaluation.statistics import (
    compute_group_statistics,
    paired_difference_summary,
)
from cloud_edge_robot_arm.final_evaluation.tables import export_tables


def test_blocked_environment_rows_are_not_runtime_execution(tmp_path: Path) -> None:
    """Isaac/MoveIt environment blockers must not be counted as runtime invocations."""

    output = tmp_path / "phase12_2"
    summary = run_phase12_experiments(Phase12Profile.VALIDATION, output)
    rows = _read_jsonl(output / "runs/raw_runs.jsonl")
    blocked = [row for row in rows if row["status"] == "BLOCKED_BY_ENV"]

    assert blocked
    assert summary["blocked_before_runtime_count"] == len(blocked)
    assert all(row["adapter_attempted"] is True for row in blocked)
    assert all(row["environment_check_completed"] is True for row in blocked)
    assert all(row["runtime_invoked"] is False for row in blocked)
    assert all(row["runtime_completed"] is False for row in blocked)
    assert all(row["authoritative_for_thesis"] is False for row in blocked)
    blocked_sources = {row["execution_source"] for row in blocked}
    assert "PHASE9_2_ISAAC_ENVIRONMENT_CHECK" in blocked_sources
    assert "PHASE10_MOVEIT_ENVIRONMENT_CHECK" in blocked_sources
    assert "PHASE9_2_ISAAC_ACTUAL_RUN" not in blocked_sources
    assert "PHASE10_MOVEIT_RUNTIME_ACTUAL" not in blocked_sources
    assert summary["actual_run_count_semantics"] == "runtime_invocation_compatibility_alias"
    assert _as_int(summary["actual_run_count"]) == _as_int(summary["runtime_invocation_count"])
    assert _as_int(summary["runtime_invocation_count"]) < _as_int(summary["adapter_attempt_count"])
    run_summary = json.loads((output / "runs/run_summary.json").read_text(encoding="utf-8"))
    assert run_summary["actual_run_count_semantics"] == summary["actual_run_count_semantics"]


def test_validation_summary_reports_adapter_backend_counts(tmp_path: Path) -> None:
    """Backend breakdown must include blocked adapter attempts, not only runtime invocations."""

    output = tmp_path / "phase12_2"
    _run_validation_pipeline(output)
    rows = _read_jsonl(output / "runs/raw_runs.jsonl")
    verification = json.loads(
        (output / "verification/phase12_summary.json").read_text(encoding="utf-8")
    )
    expected_adapter_counts = dict(
        Counter(str(row["backend"]) for row in rows if row["adapter_attempted"] is True)
    )
    expected_runtime_counts = dict(
        Counter(str(row["backend"]) for row in rows if row["runtime_invoked"] is True)
    )

    assert verification["adapter_backend_counts"] == expected_adapter_counts
    assert verification["runtime_backend_counts"] == expected_runtime_counts
    assert (
        sum(verification["adapter_backend_counts"].values())
        == verification["adapter_attempt_count"]
    )
    assert (
        sum(verification["runtime_backend_counts"].values())
        == verification["runtime_invocation_count"]
    )
    assert verification["adapter_backend_counts"] != verification["runtime_backend_counts"]


def test_phase12_sensitive_text_scan_ignores_sqlite3_runtime_databases(tmp_path: Path) -> None:
    """Phase 12 verifier must not decode SQLite runtime DBs as text artifacts."""

    root = tmp_path / "phase12_artifacts"
    root.mkdir()
    binary_secret_like_payload = (
        b"SQLite format 3\x00binary " + b"Auth" + b"orization" + b": bearer-not-a-text-artifact"
    )
    (root / "runtime.sqlite3").write_bytes(binary_secret_like_payload)
    (root / "summary.json").write_text('{"status": "ok"}\n', encoding="utf-8")

    assert phase12_validation._contains_sensitive_text(root) is False


def test_hardware_boundary_rejects_top_level_real_controller_contact() -> None:
    """Hardware boundary checks must reject legacy top-level hardware contact claims."""

    row = _row("top-level-hardware-contact")
    row["real_controller_contacted"] = True

    assert phase12_validation._all_false([row], "real_controller_contacted") is False


def test_hardware_boundary_rejects_top_level_hardware_write_operations() -> None:
    """Hardware write checks must reject legacy top-level write-operation claims."""

    row = _row("top-level-hardware-write")
    row["hardware_write_operations"] = ["servo_enable"]

    assert phase12_validation._all_empty([row], "hardware_write_operations") is False


def test_metric_provenance_excludes_placeholder_and_adapter_derived_statistics() -> None:
    """Only measured/event-derived metric values enter thesis statistics by default."""

    rows = [
        _row(
            "measured",
            metric_value=100.0,
            provenance_source="MEASURED",
            authoritative=True,
        ),
        _row(
            "event",
            metric_value=120.0,
            provenance_source="EVENT_DERIVED",
            authoritative=True,
        ),
        _row(
            "adapter",
            metric_value=10_000.0,
            provenance_source="ADAPTER_DERIVED",
            authoritative=True,
        ),
        _row(
            "placeholder",
            metric_value=20_000.0,
            provenance_source="CONSTANT_PLACEHOLDER",
            authoritative=True,
        ),
    ]

    stats = compute_group_statistics(
        rows, group_key="control_mode", metric_key="total_completion_time_ms"
    )

    assert stats["PCSC"]["sample_count"] == 2
    assert stats["PCSC"]["valid_metric_sample_count"] == 2
    assert stats["PCSC"]["excluded_metric_sample_count"] == 2
    assert stats["PCSC"]["mean"] == 110.0


def test_metric_statistics_require_row_level_authority() -> None:
    """Measured metrics from non-authoritative rows must not enter thesis statistics."""

    rows = [
        _row(
            "authoritative",
            metric_value=100.0,
            provenance_source="MEASURED",
            authoritative=True,
        ),
        _row(
            "not-authoritative",
            metric_value=999.0,
            provenance_source="MEASURED",
            authoritative=False,
        ),
    ]

    stats = compute_group_statistics(
        rows, group_key="control_mode", metric_key="total_completion_time_ms"
    )

    assert stats["PCSC"]["sample_count"] == 1
    assert stats["PCSC"]["mean"] == 100.0
    assert stats["PCSC"]["excluded_metric_sample_count"] == 1


def test_verifier_rejects_statistics_without_metric_exclusion_counts() -> None:
    """Verifier must require explicit valid/excluded metric counts for thesis statistics."""

    stats = {
        "group_statistics": {
            "PCSC": {
                "sample_count": 1,
                "mean": 100.0,
            }
        }
    }

    assert phase12_validation._placeholder_metrics_excluded(stats) is False


def test_verifier_rejects_inconsistent_metric_sample_counts() -> None:
    """Metric sample counts must balance so excluded placeholders cannot be hidden."""

    stats = {
        "group_statistics": {
            "PCSC": {
                "sample_count": 5,
                "valid_metric_sample_count": 5,
                "excluded_metric_sample_count": 5,
            }
        }
    }

    assert phase12_validation._placeholder_metrics_excluded(stats) is False


def test_verifier_rejects_metric_provenance_without_source_artifact_or_field() -> None:
    """Measured/event-derived metrics must identify their source artifact and source field."""

    row = _row("missing-provenance-source")
    metric = cast("dict[str, dict[str, str]]", row["metric_provenance"])["total_completion_time_ms"]
    metric["source_artifact"] = ""
    metric["source_field"] = ""

    assert phase12_validation._metric_provenance_complete([row]) is False


def test_paired_difference_requires_both_sides_authoritative() -> None:
    """Successful paired rows are usable only when both backend evidence sides are authoritative."""

    summary = paired_difference_summary(
        [
            {
                "left_status": "SUCCESS",
                "right_status": "SUCCESS",
                "left_value": 100.0,
                "right_value": 120.0,
                "left_authoritative": True,
                "right_authoritative": False,
            }
        ]
    )

    assert summary["usable_pair_count"] == 0
    assert summary["usable_authoritative_pair_count"] == 0
    assert summary["failed_pair_count"] == 1
    assert summary["paired_backend_experiment_accepted"] is False


def test_f20_uses_real_phase11_runtime_receipts(tmp_path: Path) -> None:
    """F20 must create SQLite, lease, attempt, duplicate competition and recovery evidence."""

    output = tmp_path / "phase12_2"
    run_phase12_experiments(Phase12Profile.VALIDATION, output)
    rows = _read_jsonl(output / "runs/raw_runs.jsonl")
    f20_rows = [row for row in rows if row["experiment_id"] == "F20_STRESS_AND_RECOVERY"]

    assert f20_rows
    assert all(row["runtime_invoked"] is True for row in f20_rows)
    assert all(row["runtime_completed"] is True for row in f20_rows)
    for row in f20_rows:
        receipt_path = output / str(row["source_artifact_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["runner"] == "PHASE11_SIMULATION_RUNTIME"
        assert receipt["sqlite_evidence"]["exists"] is True
        sqlite_path = output / receipt["sqlite_evidence"]["relative_path"]
        assert sqlite_path.exists()
        assert (
            hashlib.sha256(sqlite_path.read_bytes()).hexdigest()
            == receipt["sqlite_evidence"]["sha256"]
        )
        assert receipt["worker_lease_evidence"]["lease_count"] >= 1
        assert receipt["duplicate_competition_evidence"]["runner_invocation_count"] == 1
        assert receipt["duplicate_competition_evidence"]["lease_winner"]
        assert receipt["duplicate_competition_evidence"]["lease_loser"]
        assert receipt["recovery_evidence"]["lease_expired"] is True
        assert receipt["artifact_atomicity"]["evidence_consistency_present"] is True
        assert receipt["runtime_receipt_hash"]


def test_paired_summary_marks_isaac_blocked_as_not_accepted(tmp_path: Path) -> None:
    """Blocked Isaac rows keep pair structure but do not create usable authoritative pairs."""

    output = tmp_path / "phase12_2"
    _run_validation_pipeline(output)
    paired = json.loads((output / "paired/paired_summary.json").read_text(encoding="utf-8"))
    verification = json.loads(
        (output / "verification/phase12_summary.json").read_text(encoding="utf-8")
    )

    assert paired["paired_row_structure_complete"] is True
    assert paired["expected_pair_count"] > 0
    assert paired["usable_authoritative_pair_count"] == 0
    assert paired["blocked_pair_count"] > 0
    assert paired["paired_backend_experiment_accepted"] is False
    assert verification["checks"]["adapter_attempts_verified"] is True
    assert "actual_runner_invocation_verified" not in verification["checks"]
    assert verification["adapter_attempt_count"] == verification["run_count"]
    assert verification["actual_run_count_semantics"] == "runtime_invocation_compatibility_alias"
    assert verification["actual_run_count"] == verification["runtime_invocation_count"]
    assert verification["runtime_invocation_count"] < verification["adapter_attempt_count"]
    assert verification["checks"]["paired_backend_acceptance_status_correct"] is True
    assert "paired_backend_experiment_accepted" not in verification["checks"]
    assert verification["paired_backend_experiment_accepted"] is False
    assert verification["usable_authoritative_pair_count"] == 0
    assert verification["blocked_pair_count"] == paired["blocked_pair_count"]
    _assert_validation_status_matches_provenance(verification)


def test_verifier_rejects_runtime_gap_when_runtime_receipt_missing(tmp_path: Path) -> None:
    """Validation verifier must report runtime evidence gaps instead of accepted status."""

    output = tmp_path / "phase12_2"
    _run_validation_pipeline(output)
    raw_path = output / "runs/raw_runs.jsonl"
    rows = _read_jsonl(raw_path)
    for row in rows:
        if row["experiment_id"] == "F20_STRESS_AND_RECOVERY":
            row["source_artifact_path"] = ""
            row["source_artifact_hash"] = ""
            break
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase12.py",
            "--validation",
            "--artifact-root",
            str(output),
            "--output",
            str(output / "verification_gap"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    summary = json.loads((output / "verification_gap/phase12_summary.json").read_text())
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
    assert summary["checks"]["runtime_receipt_hash_valid"] is False


def test_verifier_rejects_runtime_receipt_with_invalid_internal_hash(tmp_path: Path) -> None:
    """F20 runtime receipt must verify its internal stable payload hash, not only file hash."""

    receipt_path = tmp_path / "source_evidence/f20/phase11_runtime_actual_run.json"
    receipt_path.parent.mkdir(parents=True)
    receipt = {
        "runner": "PHASE11_SIMULATION_RUNTIME",
        "run_id": "f20-runtime",
        "runtime_receipt_hash": "not-the-canonical-payload-hash",
        "sqlite_evidence": {
            "exists": True,
            "relative_path": "source_evidence/f20/runtime.sqlite3",
            "sha256": "sqlite-hash",
            "tables": {"simulation_jobs": 1},
        },
        "worker_lease_evidence": {"lease_count": 1},
        "duplicate_competition_evidence": {
            "lease_winner": "worker-a",
            "lease_loser": "worker-b",
            "runner_invocation_count": 1,
        },
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    row = {
        "experiment_id": "F20_STRESS_AND_RECOVERY",
        "source_artifact_path": "source_evidence/f20/phase11_runtime_actual_run.json",
        "source_artifact_hash": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }

    assert phase12_validation._runtime_receipt_hash_valid(tmp_path, [row]) is False


def test_verifier_rejects_recovery_receipt_without_required_transitions() -> None:
    """F20 recovery evidence must prove stale lease interruption and requeue transitions."""

    receipt = _minimal_f20_receipt()
    receipt["recovery_evidence"] = {
        "lease_expired": True,
        "final_status": "SUCCEEDED",
        "attempt_count": 2,
        "transitions": [["RUNNING", "SUCCEEDED"]],
    }

    assert phase12_validation._recovery_evidence_valid(receipt) is False


def test_verifier_rejects_runtime_receipt_without_terminal_artifact_paths() -> None:
    """F20 runtime receipt must list the terminal artifact set, not only summary booleans."""

    receipt = _minimal_f20_receipt()
    main_job = cast("dict[str, object]", receipt["main_job"])
    main_job["artifact_paths"] = {
        "job": "phase11_1/runtime/f20/job.json",
        "result": "phase11_1/runtime/f20/result.json",
    }

    assert phase12_validation._terminal_artifact_paths_valid(receipt) is False


def test_verifier_rejects_duplicate_competition_with_same_winner_and_loser() -> None:
    """Duplicate worker competition evidence must prove that two distinct workers competed."""

    receipt = _minimal_f20_receipt()
    duplicate = cast("dict[str, object]", receipt["duplicate_competition_evidence"])
    duplicate["lease_loser"] = duplicate["lease_winner"]

    assert phase12_validation._duplicate_competition_evidence_valid(receipt) is False


def test_full_profile_rejects_when_paired_backend_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """full profile 不能在 paired backend 未验收时输出最终接受状态。"""

    root = tmp_path / "phase12_full"
    _write_minimal_full_artifact(root, paired_accepted=False)
    _patch_minimal_full_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.FULL,
        artifact_root=root,
        output_dir=root / "verification",
        require_full=True,
    )

    assert summary["paired_backend_experiment_accepted"] is False
    assert summary["checks"]["paired_backend_acceptance_status_correct"] is False
    assert summary["status"] == "PHASE12_REJECTED"
    assert summary["project_status"] == "NOT_CLOSED"


def test_full_profile_ready_status_matches_full_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """full profile 被最终接受时 readiness 字段也必须保持一致。"""

    root = tmp_path / "phase12_full"
    _write_minimal_full_artifact(root, paired_accepted=True)
    _patch_minimal_full_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.FULL,
        artifact_root=root,
        output_dir=root / "verification",
        require_full=True,
    )

    assert summary["status"] == "PHASE12_FINAL_EVALUATION_ACCEPTED"
    assert summary["full_profile_readiness_status"] == "PHASE12_FULL_PROFILE_READY"
    assert summary["project_status"] == "BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED"


def test_validation_acceptance_uses_readiness_only_full_profile_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validation accepted 只能说明 full 前置就绪，不能伪装成 full profile 已接受。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["status"] == "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
    assert summary["project_status"] == "NOT_CLOSED"
    assert summary["full_profile_claimed"] is False
    assert summary["full_profile_readiness_status"] == "PHASE12_FULL_PROFILE_PREREQUISITES_READY"
    assert summary["full_profile_execution_status"] == "NOT_RUN"


def test_summary_hardware_claims_are_derived_from_raw_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """summary 顶层硬件字段必须反映 raw runs，而不是固定写成安全值。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    raw_path = root / "runs/raw_runs.jsonl"
    rows = _read_jsonl(raw_path)
    rows[0]["real_controller_contacted"] = True
    rows[0]["hardware_write_operations"] = ["servo_enable"]
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["real_controller_contacted_false"] is False
    assert summary["checks"]["hardware_write_operations_empty"] is False
    assert summary["real_controller_contacted"] is True
    assert summary["hardware_write_operations"] == ["servo_enable"]
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"


def test_validation_accepts_committed_sqlite_receipt_without_ignored_db_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """仓库 evidence 只要求 SQLite receipt 元数据，不依赖被 gitignore 排除的 DB 文件。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_f20_validation_artifact(root, include_sqlite_binary=False)
    _patch_minimal_f20_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["status"] == "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
    assert summary["checks"]["phase11_sqlite_evidence_exists"] is True
    assert summary["phase11_sqlite_binary_present_locally"] is False
    assert summary["phase11_sqlite_local_hash_valid"] is True


def test_validation_reports_corrupt_local_ignored_sqlite_without_blocking_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本机 ignored DB 残留损坏时必须显式报告，但不伪装成仓库 bundle 缺失。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_f20_validation_artifact(root, include_sqlite_binary=True)
    sqlite_path = root / "source_evidence/f20/phase11_runtime/runtime.sqlite3"
    sqlite_path.write_bytes(b"corrupt-local-residue")
    _patch_minimal_f20_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["status"] == "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
    assert summary["checks"]["phase11_sqlite_evidence_exists"] is True
    assert summary["phase11_sqlite_binary_present_locally"] is True
    assert summary["phase11_sqlite_local_hash_valid"] is False


def test_verifier_rejects_when_failed_or_blocked_counts_do_not_match_raw_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """aggregate 不能把 raw runs 中的失败或阻塞样本静默删掉。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=0, aggregate_failed=0)
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["failed_or_blocked_not_deleted"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"


def test_verifier_rejects_plot_index_without_rendering_source_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """plot_index 必须声明 SVG 数据来源和 PNG 占位语义，旧 artifact 不能通过验收。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    root.joinpath("plots/plot_index.json").write_text(
        json.dumps({"data_authority": "AUTHORITATIVE_THESIS_DATA"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["plot_index_semantics_valid"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"


def test_verifier_rejects_capability_table_that_claims_accepted_without_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺少 capability_statuses 时，T1 表格不能用 ACCEPTED 通过验收。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    root.joinpath("tables/csv/t1_system_capability.csv").write_text(
        "capability,hardware_claim,status\n"
        "Simulation Workbench,none,ACCEPTED\n"
        "Model Control Center,none,ACCEPTED\n"
        "Real Robot,none,NOT_STARTED\n",
        encoding="utf-8",
    )
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["capability_table_semantics_valid"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"


def test_verifier_rejects_validation_evidence_from_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validation evidence 的 provenance 必须来自 clean worktree。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    _write_provenance(root, worktree_clean=False)
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["source_tree_provenance_present"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
    assert summary["verifier_gated_authoritative_thesis_run_count"] == 0
    integrity = json.loads(
        root.joinpath("verification/run_integrity_verification.json").read_text(encoding="utf-8")
    )
    assert integrity["authoritative_thesis_run_count"] == 1
    assert integrity["verifier_gated_authoritative_thesis_run_count"] == 0


def test_validation_report_uses_gap_status_when_verifier_rejected_evidence(tmp_path: Path) -> None:
    """validation 报告必须复用 verifier 状态，不能在 gaps 上写 accepted。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    verification_dir = root / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    verification_dir.joinpath("phase12_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS",
                "thesis_status": "THESIS_PACKAGE_INCOMPLETE",
                "full_profile_readiness_status": "PHASE12_FULL_PROFILE_NOT_READY",
                "checks": {"source_tree_provenance_present": False},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    export_thesis_assets(root, profile="validation")

    report = root.joinpath("reports/phase12_validation_report.md").read_text(encoding="utf-8")
    results = root.joinpath("thesis/experiment_results.md").read_text(encoding="utf-8")
    assert "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED" not in report
    assert "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED" not in results
    assert "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS" in report
    assert "THESIS_PACKAGE_INCOMPLETE" in results


def test_validation_report_without_verifier_summary_does_not_claim_acceptance(
    tmp_path: Path,
) -> None:
    """导出顺序早于 verifier 时，validation 报告不能预先声明 accepted。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)

    export_thesis_assets(root, profile="validation")

    report = root.joinpath("reports/phase12_validation_report.md").read_text(encoding="utf-8")
    results = root.joinpath("thesis/experiment_results.md").read_text(encoding="utf-8")
    assert "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED" not in report
    assert "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED" not in results
    assert "VALIDATION_ANALYSIS_PENDING_VERIFICATION" in report


def test_validation_gap_exports_do_not_mark_plots_or_tables_authoritative(
    tmp_path: Path,
) -> None:
    """validation gaps 下图表和表格不能标为论文权威数据。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    _write_gap_verification_summary(root)

    export_thesis_assets(root, profile="validation")

    plot_index = json.loads(root.joinpath("plots/plot_index.json").read_text(encoding="utf-8"))
    demo_summary = json.loads(
        root.joinpath("demo_bundle/demo_summary.json").read_text(encoding="utf-8")
    )
    table = root.joinpath("tables/csv/t2_mode_baseline.csv").read_text(encoding="utf-8")
    assert plot_index["data_authority"] == "VALIDATION_GAP_DATA"
    assert plot_index["verifier_gated_authoritative_thesis_run_count"] == 0
    assert demo_summary["data_authority"] == "VALIDATION_GAP_DATA"
    assert demo_summary["verifier_gated_authoritative_thesis_run_count"] == 0
    assert "VALIDATION_GAP_DATA" in table
    assert "AUTHORITATIVE_THESIS_DATA" not in table


def test_inconsistent_verifier_summary_does_not_mark_validation_assets_accepted(
    tmp_path: Path,
) -> None:
    """verifier status 未接受时，单独的 thesis_status 不能把资产标为 accepted。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    verification_dir = root / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    verification_dir.joinpath("phase12_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE12_REJECTED",
                "thesis_status": "PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED",
                "full_profile_readiness_status": "PHASE12_FULL_PROFILE_NOT_READY",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    export_thesis_assets(root, profile="validation")

    plot_index = json.loads(root.joinpath("plots/plot_index.json").read_text(encoding="utf-8"))
    demo_summary = json.loads(
        root.joinpath("demo_bundle/demo_summary.json").read_text(encoding="utf-8")
    )
    results = root.joinpath("thesis/experiment_results.md").read_text(encoding="utf-8")
    assert plot_index["data_authority"] == "PENDING_VERIFICATION_DATA"
    assert plot_index["verifier_gated_authoritative_thesis_run_count"] == 0
    assert demo_summary["data_authority"] == "PENDING_VERIFICATION_DATA"
    assert demo_summary["verifier_gated_authoritative_thesis_run_count"] == 0
    assert "verifier_gated_authoritative_for_thesis=0" in results


def test_verifier_rejects_demo_summary_with_exaggerated_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """demo summary 不能单独宣称 full authority 或虚增 verifier-gated 样本数。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    root.joinpath("demo_bundle/demo_summary.json").write_text(
        json.dumps(
            {
                "data_authority": "AUTHORITATIVE_THESIS_DATA",
                "verifier_gated_authoritative_thesis_run_count": 999,
                "contains_secret": False,
                "real_controller_contacted": False,
                "hardware_motion_observed": False,
                "hardware_write_operations": [],
                "highest_real_hardware_acceptance_level": "NONE",
                "real_robot_validation": "NOT_STARTED",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["demo_summary_semantics_valid"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"


def test_verifier_rejects_validation_thesis_docs_with_final_acceptance_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validation 级 thesis 文档不能越级声明 full/project accepted。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    root.joinpath("thesis/experiment_results.md").write_text(
        "\n".join(
            [
                "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED",
                "PHASE12_FINAL_EVALUATION_ACCEPTED",
                "PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED",
                "BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED",
            ]
        ),
        encoding="utf-8",
    )
    _patch_minimal_validation_verifier(monkeypatch)

    summary = phase12_validation.verify_phase12(
        profile=Phase12Profile.VALIDATION,
        artifact_root=root,
        output_dir=root / "verification",
    )

    assert summary["checks"]["thesis_docs_semantics_valid"] is False
    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
    assert summary["thesis_status"] == "THESIS_PACKAGE_INCOMPLETE"


def test_validation_gap_report_gates_authoritative_thesis_run_count(
    tmp_path: Path,
) -> None:
    """整体验证未通过时，报告不能把行级 authoritative 标记当作论文可用样本。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    _write_gap_verification_summary(root)
    aggregate_path = root / "aggregates/phase12_aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["authoritative_thesis_run_count"] = 1
    aggregate_path.write_text(json.dumps(aggregate, sort_keys=True) + "\n", encoding="utf-8")

    export_thesis_assets(root, profile="validation")

    report = root.joinpath("reports/phase12_validation_report.md").read_text(encoding="utf-8")
    results = root.joinpath("thesis/experiment_results.md").read_text(encoding="utf-8")
    assert "authoritative thesis runs：1" not in report
    assert "verifier-gated thesis runs：0" in report
    assert "row-level runtime-complete runs：1" in report
    assert "verifier_gated_authoritative_for_thesis=0" in results


def test_thesis_export_hardware_claims_are_derived_from_aggregate(tmp_path: Path) -> None:
    """报告和 demo summary 的硬件声明必须来自 aggregate，不能固定写安全值。"""

    root = tmp_path / "phase12_validation"
    _write_minimal_validation_artifact(root, aggregate_blocked=1, aggregate_failed=1)
    aggregate_path = root / "aggregates/phase12_aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["hardware_claims"] = {
        "real_controller_contacted": True,
        "hardware_motion_observed": True,
        "hardware_write_operations": ["brake_release"],
        "highest_real_hardware_acceptance_level": "LEVEL_0",
        "real_robot_validation": "LEVEL_0_PASSED",
    }
    aggregate_path.write_text(json.dumps(aggregate, sort_keys=True) + "\n", encoding="utf-8")

    export_thesis_assets(root, profile="validation")

    report = root.joinpath("reports/phase12_validation_report.md").read_text(encoding="utf-8")
    demo_summary = json.loads(
        root.joinpath("demo_bundle/demo_summary.json").read_text(encoding="utf-8")
    )
    assert "real_controller_contacted=True" in report
    assert "hardware_motion_observed=True" in report
    assert "hardware_write_operations=['brake_release']" in report
    assert demo_summary["real_controller_contacted"] is True
    assert demo_summary["hardware_motion_observed"] is True
    assert demo_summary["hardware_write_operations"] == ["brake_release"]
    assert demo_summary["highest_real_hardware_acceptance_level"] == "LEVEL_0"


def test_direct_plot_and_table_export_defaults_to_pending_verification(
    tmp_path: Path,
) -> None:
    """直接导出图表/表格时没有 verifier 结果，不能默认标为论文权威数据。"""

    aggregate = {
        "authoritative_thesis_run_count": 3,
        "synthetic_sample_count": 0,
        "authoritative_by_mode": {
            "PCSC": {
                "run_count": 5,
                "authoritative_run_count": 3,
                "success_rate": 1.0,
            }
        },
    }

    export_plots(tmp_path, aggregate)
    export_tables(tmp_path, aggregate, {"paired_results": {}})

    plot_index = json.loads(tmp_path.joinpath("plots/plot_index.json").read_text())
    table = tmp_path.joinpath("tables/csv/t2_mode_baseline.csv").read_text()
    table_rows = list(DictReader(table.splitlines()))
    assert plot_index["data_authority"] == "PENDING_VERIFICATION_DATA"
    assert plot_index["svg_data_source"] == "aggregate_payload"
    assert plot_index["png_rendering_mode"] == "placeholder_preview"
    assert plot_index["png_contains_metric_data"] is False
    assert "PENDING_VERIFICATION_DATA" in table
    assert "authoritative_n" in table
    assert table_rows[0]["authoritative_n"] == "3"
    assert table_rows[0]["n"] == "5"
    assert "AUTHORITATIVE_THESIS_DATA" not in table


def test_direct_capability_table_does_not_default_to_accepted_without_evidence(
    tmp_path: Path,
) -> None:
    """缺少 capability_statuses 时，T1 不能默认把系统能力写成 ACCEPTED。"""

    aggregate = {
        "authoritative_thesis_run_count": 3,
        "synthetic_sample_count": 0,
        "authoritative_by_mode": {
            "PCSC": {
                "run_count": 5,
                "authoritative_run_count": 3,
                "success_rate": 1.0,
            }
        },
    }

    export_tables(tmp_path, aggregate, {"paired_results": {}})

    rows = list(
        DictReader(
            tmp_path.joinpath("tables/csv/t1_system_capability.csv").read_text().splitlines()
        )
    )
    statuses = {row["capability"]: row["status"] for row in rows}
    assert statuses["Simulation Workbench"] == "UNKNOWN"
    assert statuses["Model Control Center"] == "UNKNOWN"
    assert statuses["Real Robot"] == "NOT_STARTED"


def test_aggregate_counts_runtime_semantics_not_adapter_attempts() -> None:
    """Aggregates must separate adapter attempts from actual runtime invocation."""

    rows = [
        _row("runtime", runtime_invoked=True, runtime_completed=True),
        _row(
            "blocked",
            status="BLOCKED_BY_ENV",
            source="PHASE9_2_ISAAC_ENVIRONMENT_CHECK",
            runtime_invoked=False,
            runtime_completed=False,
            authoritative=False,
        ),
    ]

    aggregate = aggregate_results(Phase12Profile.VALIDATION, rows)

    assert aggregate.adapter_attempt_count == 2
    assert aggregate.runtime_invocation_count == 1
    assert aggregate.runtime_completion_count == 1
    assert aggregate.blocked_before_runtime_count == 1


def test_aggregate_hardware_claims_are_derived_from_raw_runs() -> None:
    """aggregate 硬件声明必须来自 raw runs，不能固定写成默认安全值。"""

    row = _row("hardware-claim")
    row["real_controller_contacted"] = True
    row["hardware_claims"] = {
        "real_controller_contacted": False,
        "hardware_motion_observed": True,
        "hardware_write_operations": ["brake_release"],
        "highest_real_hardware_acceptance_level": "LEVEL_0",
        "real_robot_validation": "LEVEL_0_PASSED",
    }

    aggregate = aggregate_results(Phase12Profile.VALIDATION, [row])

    assert aggregate.hardware_claims.real_controller_contacted is True
    assert aggregate.hardware_claims.hardware_motion_observed is True
    assert aggregate.hardware_claims.hardware_write_operations == ["brake_release"]
    assert aggregate.hardware_claims.highest_real_hardware_acceptance_level == "LEVEL_0"
    assert aggregate.hardware_claims.real_robot_validation == "LEVEL_0_PASSED"


def test_runner_event_hardware_claim_is_derived_from_result_row() -> None:
    """runner event 里的硬件状态必须来自结果行，不能固定写 false。"""

    manifest = Phase12RunManifest(
        run_id="event-hardware-claim",
        experiment_id="F01_PC_SC_BASELINE",
        research_question="RQ1",
        profile=Phase12Profile.VALIDATION,
        backend=Phase12Backend.MOCK,
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        repetition=0,
        source_commit="commit",
        source_tree_hash="tree",
        worktree_clean=True,
        config_hash="config",
        environment_hash="env",
        planner_provider="MOCK",
        model_name="mock",
    )
    adapter_result = Phase12AdapterResult(
        status=Phase12RunStatus.SUCCESS,
        task_success=True,
        metrics={
            "task_completion_rate": 1.0,
            "total_completion_time_ms": 100.0,
            "result_hash": "result",
            "artifact_hash": "artifact",
        },
        events=[],
        execution_source=ExecutionSource.PHASE8_ACTUAL_RUN,
        actual_runner_invoked=True,
        adapter_attempted=True,
        environment_check_completed=True,
        runtime_invoked=True,
        runtime_completed=True,
        authoritative_for_thesis=True,
        blocker_stage=BlockerStage.NONE,
        source_artifact_path="source_evidence/runtime.json",
        source_artifact_hash="hash",
        source_verifier="test",
        environment_status=EnvironmentStatus.READY,
        hardware_claims=HardwareClaims(
            hardware_motion_observed=True,
            hardware_write_operations=["joint_command"],
        ),
    )
    result = _result_from_adapter(manifest, adapter_result, authoritative_for_thesis=True)

    event = _event(result)

    assert event["hardware_motion_observed"] is True
    assert event["hardware_write_operations"] == ["joint_command"]


def test_runner_summary_hardware_claim_is_derived_from_result_rows() -> None:
    """run summary/provenance 的硬件声明必须从结果行汇总，不能固定默认安全值。"""

    manifest = Phase12RunManifest(
        run_id="summary-hardware-claim",
        experiment_id="F01_PC_SC_BASELINE",
        research_question="RQ1",
        profile=Phase12Profile.VALIDATION,
        backend=Phase12Backend.MOCK,
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        repetition=0,
        source_commit="commit",
        source_tree_hash="tree",
        worktree_clean=True,
        config_hash="config",
        environment_hash="env",
        planner_provider="MOCK",
        model_name="mock",
    )
    result = _result_from_adapter(
        manifest,
        Phase12AdapterResult(
            status=Phase12RunStatus.SUCCESS,
            task_success=True,
            metrics={
                "task_completion_rate": 1.0,
                "total_completion_time_ms": 100.0,
                "result_hash": "result",
                "artifact_hash": "artifact",
            },
            events=[],
            execution_source=ExecutionSource.PHASE8_ACTUAL_RUN,
            actual_runner_invoked=True,
            adapter_attempted=True,
            environment_check_completed=True,
            runtime_invoked=True,
            runtime_completed=True,
            authoritative_for_thesis=True,
            blocker_stage=BlockerStage.NONE,
            source_artifact_path="source_evidence/runtime.json",
            source_artifact_hash="hash",
            source_verifier="test",
            environment_status=EnvironmentStatus.READY,
            hardware_claims=HardwareClaims(
                real_controller_contacted=True,
                hardware_motion_observed=True,
                hardware_write_operations=["brake_release", "joint_command"],
                highest_real_hardware_acceptance_level="LEVEL_1",
                real_robot_validation="LEVEL_1_FAILED",
            ),
        ),
        authoritative_for_thesis=True,
    )

    claims = _hardware_claims_from_results([result])

    assert claims.real_controller_contacted is True
    assert claims.hardware_motion_observed is True
    assert claims.hardware_write_operations == ["brake_release", "joint_command"]
    assert claims.highest_real_hardware_acceptance_level == "LEVEL_1"
    assert claims.real_robot_validation == "LEVEL_1_FAILED"


def test_runner_writes_summary_and_provenance_hardware_claims_from_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner 写出的 summary/provenance 必须保留结果行硬件 claim。"""

    class HardwareClaimAdapter:
        runner_kind = "PHASE8_EXPERIMENT_RUNNER"

        def capability(self) -> dict[str, object]:
            return {}

        def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
            return EnvironmentStatus.READY

        def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
            receipt = context.output_root / "source_evidence" / context.run_id / "receipt.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text('{"receipt":"hardware-claim"}\n', encoding="utf-8")
            return Phase12AdapterResult(
                status=Phase12RunStatus.SUCCESS,
                task_success=True,
                metrics={
                    "task_completion_rate": 1.0,
                    "total_completion_time_ms": 100.0,
                    "result_hash": "result",
                    "artifact_hash": "artifact",
                },
                events=[],
                execution_source=ExecutionSource.PHASE8_ACTUAL_RUN,
                actual_runner_invoked=True,
                adapter_attempted=True,
                environment_check_completed=True,
                runtime_invoked=True,
                runtime_completed=True,
                authoritative_for_thesis=True,
                blocker_stage=BlockerStage.NONE,
                source_artifact_path=receipt.relative_to(context.output_root).as_posix(),
                source_artifact_hash=sha256_path(receipt),
                source_verifier="test",
                environment_status=EnvironmentStatus.READY,
                hardware_claims=HardwareClaims(
                    real_controller_contacted=True,
                    hardware_motion_observed=True,
                    hardware_write_operations=["trajectory_send"],
                    highest_real_hardware_acceptance_level="LEVEL_2",
                    real_robot_validation="LEVEL_2_FAILED",
                ),
            )

        def collect_evidence(self, context: Phase12RunContext) -> dict[str, object]:
            return {}

        def cancel(self, run_id: str) -> None:
            return None

        def result_source(self) -> ExecutionSource:
            return ExecutionSource.PHASE8_ACTUAL_RUN

    monkeypatch.setattr(
        phase12_runner,
        "build_experiment_plan",
        lambda profile: SimpleNamespace(
            experiments=[
                SimpleNamespace(
                    experiment_id="F01_PC_SC_BASELINE",
                    research_question="RQ1",
                    scenario_ids=["S01_NORMAL_STATIC"],
                    backends=[Phase12Backend.MOCK],
                    control_modes=["PCSC"],
                    runner_kind="PHASE8_EXPERIMENT_RUNNER",
                    validation_seed_count=1,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        phase12_runner,
        "runner_adapter_registry",
        lambda: {"PHASE8_EXPERIMENT_RUNNER": HardwareClaimAdapter()},
    )

    run_phase12_experiments(Phase12Profile.VALIDATION, tmp_path)

    summary = json.loads((tmp_path / "runs/run_summary.json").read_text(encoding="utf-8"))
    provenance = json.loads((tmp_path / "manifests/provenance.json").read_text(encoding="utf-8"))
    assert summary["hardware_claims"]["real_controller_contacted"] is True
    assert summary["hardware_claims"]["hardware_motion_observed"] is True
    assert summary["hardware_claims"]["hardware_write_operations"] == ["trajectory_send"]
    assert summary["hardware_claims"]["highest_real_hardware_acceptance_level"] == "LEVEL_2"
    assert summary["hardware_claims"]["real_robot_validation"] == "LEVEL_2_FAILED"
    assert provenance["hardware_claims"] == summary["hardware_claims"]


def test_group_payload_reports_authoritative_run_count() -> None:
    """Group summaries must expose authoritative sample counts separately from audit totals."""

    rows = [
        _row("authoritative-success", authoritative=True),
        _row("non-authoritative-success", authoritative=False),
    ]

    aggregate = aggregate_results(Phase12Profile.VALIDATION, rows)

    assert aggregate.by_mode["PCSC"]["run_count"] == 2
    assert aggregate.by_mode["PCSC"]["success_count"] == 2
    assert aggregate.by_mode["PCSC"]["authoritative_run_count"] == 1
    assert aggregate.authoritative_by_mode["PCSC"]["run_count"] == 1
    assert aggregate.authoritative_by_mode["PCSC"]["authoritative_run_count"] == 1


def test_legacy_actual_runner_flag_cannot_create_fake_runtime_count() -> None:
    """旧兼容字段不能绕过 runtime_invoked 语义制造真实运行数量。"""

    blocked_environment_check = _row(
        "legacy-env-check",
        status="BLOCKED_BY_ENV",
        source="PHASE9_2_ISAAC_ENVIRONMENT_CHECK",
        runtime_invoked=False,
        runtime_completed=False,
        authoritative=False,
    )
    blocked_environment_check["actual_runner_invoked"] = True
    rows = [blocked_environment_check]

    aggregate = aggregate_results(Phase12Profile.VALIDATION, rows)

    assert aggregate.adapter_attempt_count == 1
    assert aggregate.actual_run_count == 0
    assert aggregate.runtime_invocation_count == 0
    assert aggregate.runtime_completion_count == 0
    assert aggregate.blocked_before_runtime_count == 1


def test_planner_provider_is_explicit_and_latency_measured(tmp_path: Path) -> None:
    """Planner comparison must not infer provider from control mode or use fixed latency."""

    output = tmp_path / "phase12_2"
    run_phase12_experiments(Phase12Profile.VALIDATION, output)
    rows = [
        row
        for row in _read_jsonl(output / "runs/raw_runs.jsonl")
        if row["experiment_id"] == "F16_PLANNER_PROVIDER_COMPARISON"
    ]

    providers = Counter(row["planner_provider"] for row in rows)
    assert {"MOCK", "RULE_BASED", "OPENAI_COMPATIBLE", "OLLAMA"}.issubset(providers)
    assert all(row["response_latency_ms"] != 80.0 for row in rows if row["runtime_completed"])
    assert all(
        row["runtime_invoked"] is False
        for row in rows
        if row["planner_provider"] in {"OPENAI_COMPATIBLE", "OLLAMA"}
    )
    assert all(
        row["status"] == "BLOCKED_BY_ENV"
        for row in rows
        if row["planner_provider"] in {"OPENAI_COMPATIBLE", "OLLAMA"}
    )


def test_dirty_provenance_cannot_mark_row_authoritative_for_thesis() -> None:
    """dirty worktree provenance 下，单行也不能写成论文权威样本。"""

    manifest = _manifest_like(worktree_clean=False)
    result = _result_from_adapter(manifest, _successful_adapter_result())

    assert result.runtime_completed is True
    assert result.authoritative_for_thesis is False


def test_authority_requires_verified_source_artifact_hash(tmp_path: Path) -> None:
    """行级论文 authority 必须绑定实际 source evidence 文件和匹配 hash。"""

    manifest = _manifest_like(worktree_clean=True)
    adapter_result = _successful_adapter_result()

    assert _authoritative_for_thesis(manifest, adapter_result, output_root=tmp_path) is False

    receipt = tmp_path / adapter_result.source_artifact_path
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"status":"ok"}\n', encoding="utf-8")

    assert _authoritative_for_thesis(manifest, adapter_result, output_root=tmp_path) is False

    matching_result = Phase12AdapterResult(
        **{
            **adapter_result.__dict__,
            "source_artifact_hash": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        }
    )

    assert _authoritative_for_thesis(manifest, matching_result, output_root=tmp_path) is True


def test_runner_normalizes_source_artifact_hashes_before_writing_rows(tmp_path: Path) -> None:
    """raw row 写出前必须以磁盘最终 source evidence hash 为准。"""

    manifest = _manifest_like(worktree_clean=True).model_copy(
        update={
            "source_artifact_path": "source_evidence/test/receipt.json",
            "source_artifact_hash": "stale-hash",
        },
        deep=True,
    )
    result = _result_from_adapter(
        manifest,
        _successful_adapter_result(),
        authoritative_for_thesis=False,
    ).model_copy(
        update={
            "source_artifact_path": "source_evidence/test/receipt.json",
            "source_artifact_hash": "stale-hash",
        },
        deep=True,
    )
    receipt = tmp_path / "source_evidence/test/receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"final":"content"}\n', encoding="utf-8")

    manifests, results = _normalize_source_artifact_hashes(tmp_path, [manifest], [result])

    expected = hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert manifests[0].source_artifact_hash == expected
    assert results[0].source_artifact_hash == expected


def test_phase8_adapter_rerun_uses_isolated_runtime_workspace(tmp_path: Path) -> None:
    """Phase8 adapter 重跑同一 run_id 时不得复用旧 SQLite runtime state。"""

    context = Phase12RunContext(
        run_id="phase12-repeat",
        experiment_id="F01_PC_SC_BASELINE",
        scenario_id="S01_NORMAL_STATIC",
        backend=Phase12Backend.MOCK,
        control_mode="PCSC",
        seed=0,
        repetition=0,
        output_root=tmp_path,
    )
    adapter = Phase8ExperimentRunnerAdapter()

    first = adapter.run(context)
    second = adapter.run(context)

    assert first.runtime_completed is True
    assert second.runtime_completed is True
    receipt = json.loads((tmp_path / second.source_artifact_path).read_text(encoding="utf-8"))
    assert receipt["runtime_workspace"] == "source_evidence/phase12-repeat/runtime_workspace"


def test_phase8_adapter_closes_runtime_workspace_sqlite_handles(tmp_path: Path) -> None:
    """Phase8 adapter 运行后不得在当前进程留下 runtime workspace SQLite fd。"""

    context = Phase12RunContext(
        run_id="phase12-fd-clean",
        experiment_id="F01_PC_SC_BASELINE",
        scenario_id="S01_NORMAL_STATIC",
        backend=Phase12Backend.MOCK,
        control_mode="PCSC",
        seed=0,
        repetition=0,
        output_root=tmp_path,
    )

    result = Phase8ExperimentRunnerAdapter().run(context)

    assert result.runtime_completed is True
    assert _sqlite_fd_targets(tmp_path / "source_evidence/phase12-fd-clean") == []


def test_phase11_runtime_adapter_rerun_uses_fresh_sqlite_repository(tmp_path: Path) -> None:
    """Phase11 runtime adapter 重跑同一 run_id 时不得复用旧 runtime.db。"""

    context = Phase12RunContext(
        run_id="phase12-runtime-repeat",
        experiment_id="F20_STRESS_AND_RECOVERY",
        scenario_id="S15_SQLITE_RESTART_DURING_RUN",
        backend=Phase12Backend.MOCK,
        control_mode="AUTO",
        seed=0,
        repetition=0,
        output_root=tmp_path,
    )
    adapter = Phase11RuntimeAdapter()

    first = adapter.run(context)
    second = adapter.run(context)

    assert first.runtime_completed is True
    assert second.runtime_completed is True
    receipt = json.loads((tmp_path / second.source_artifact_path).read_text(encoding="utf-8"))
    assert receipt["sqlite_evidence"]["exists"] is True


def _run_validation_pipeline(output: Path) -> None:
    commands = [
        [
            sys.executable,
            "scripts/run_phase12_experiments.py",
            "--profile",
            "validation",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/analyze_phase12_results.py",
            "--profile",
            "validation",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/export_phase12_thesis_assets.py",
            "--profile",
            "validation",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/verify_phase12.py",
            "--validation",
            "--artifact-root",
            str(output),
            "--output",
            str(output / "verification"),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr + completed.stdout


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _sqlite_fd_targets(root: Path) -> list[str]:
    if not Path("/proc/self/fd").exists():
        return []
    targets: list[str] = []
    root_text = str(root)
    for fd in Path("/proc/self/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if root_text in target and ".sqlite3" in target:
            targets.append(target)
    return sorted(targets)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected int, got {value!r}")
    return value


def _manifest_like(*, worktree_clean: bool) -> Phase12RunManifest:
    return Phase12RunManifest(
        run_id="phase12-test",
        experiment_id="F01_PC_SC_BASELINE",
        research_question="RQ1",
        profile=Phase12Profile.VALIDATION,
        backend=Phase12Backend.MOCK,
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        repetition=0,
        source_commit="commit",
        source_tree_hash="tree",
        worktree_clean=worktree_clean,
        config_hash="config",
        environment_hash="environment",
        planner_provider="NONE",
        model_name="",
    )


def _successful_adapter_result() -> Phase12AdapterResult:
    provenance = {
        "total_completion_time_ms": MetricProvenance(
            source=MetricSource.MEASURED,
            source_field="test.duration",
            source_artifact="source_evidence/test/receipt.json",
            unit="ms",
        )
    }
    return Phase12AdapterResult(
        status=Phase12RunStatus.SUCCESS,
        task_success=True,
        metrics={
            "task_completion_rate": 1.0,
            "total_completion_time_ms": 10.0,
            "completed_without_cloud_after_start": True,
        },
        events=[],
        execution_source=ExecutionSource.PHASE8_ACTUAL_RUN,
        actual_runner_invoked=True,
        adapter_attempted=True,
        environment_check_completed=True,
        runtime_invoked=True,
        runtime_completed=True,
        authoritative_for_thesis=True,
        blocker_stage=BlockerStage.NONE,
        source_artifact_path="source_evidence/test/receipt.json",
        source_artifact_hash="hash",
        source_verifier="test",
        environment_status=EnvironmentStatus.READY,
        metric_provenance=provenance,
    )


def _write_minimal_full_artifact(root: Path, *, paired_accepted: bool) -> None:
    rows_dir = root / "runs"
    aggregate_dir = root / "aggregates"
    stats_dir = root / "statistics"
    manifests_dir = root / "manifests"
    paired_dir = root / "paired"
    for path in [
        rows_dir,
        aggregate_dir,
        stats_dir,
        manifests_dir,
        paired_dir,
        root / "plots/png",
        root / "plots/svg",
        root / "tables/csv",
        root / "tables/latex",
        root / "thesis",
        root / "demo_bundle",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    row = _row(
        "full-paired-sample",
        source="PHASE9_MUJOCO_ACTUAL_RUN",
        runtime_invoked=True,
        runtime_completed=True,
        authoritative=True,
    )
    row["profile"] = "full"
    row["experiment_id"] = "F15_MUJOCO_ISAAC_PAIRED"
    rows_dir.joinpath("raw_runs.jsonl").write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    aggregate_dir.joinpath("phase12_aggregate.json").write_text(
        json.dumps(
            {
                "unsafe_command_execution_count": 0,
                "blocked_by_env_count": 0,
                "failed_count": 0,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    stats_dir.joinpath("phase12_statistics.json").write_text(
        json.dumps({"group_statistics": {"PCSC": _minimal_metric_counts()}}) + "\n",
        encoding="utf-8",
    )
    _write_provenance(root, worktree_clean=True)
    paired_dir.joinpath("paired_summary.json").write_text(
        json.dumps({"paired_backend_experiment_accepted": paired_accepted}) + "\n",
        encoding="utf-8",
    )
    root.joinpath("plots/png/success_rate_comparison.png").write_bytes(b"png")
    root.joinpath("plots/svg/success_rate_comparison.svg").write_text("<svg />")
    _write_plot_index(root)
    root.joinpath("tables/csv/t2_mode_baseline.csv").write_text("metric,value\n")
    root.joinpath("tables/csv/t1_system_capability.csv").write_text(
        "capability,hardware_claim,status\n"
        "Simulation Workbench,none,UNKNOWN\n"
        "Model Control Center,none,UNKNOWN\n"
        "Real Robot,none,NOT_STARTED\n",
        encoding="utf-8",
    )
    root.joinpath("tables/latex/t2_mode_baseline.tex").write_text(
        "\\begin{tabular}{}\\end{tabular}"
    )
    root.joinpath("thesis/experiment_results.md").write_text("full results")
    _write_demo_summary(root, data_authority="AUTHORITATIVE_THESIS_DATA")


def _write_minimal_validation_artifact(
    root: Path, *, aggregate_blocked: int, aggregate_failed: int
) -> None:
    _write_minimal_artifact_common(root)
    rows = [
        _row("runtime-success"),
        _row(
            "blocked-env",
            status="BLOCKED_BY_ENV",
            source="PHASE9_2_ISAAC_ENVIRONMENT_CHECK",
            runtime_invoked=False,
            runtime_completed=False,
            authoritative=False,
        ),
        _row(
            "runtime-failed",
            status="FAILED",
            runtime_invoked=True,
            runtime_completed=False,
            authoritative=False,
        ),
    ]
    root.joinpath("runs/raw_runs.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    root.joinpath("aggregates/phase12_aggregate.json").write_text(
        json.dumps(
            {
                "unsafe_command_execution_count": 0,
                "blocked_by_env_count": aggregate_blocked,
                "failed_count": aggregate_failed,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    root.joinpath("paired/paired_summary.json").write_text(
        json.dumps({"paired_backend_experiment_accepted": False}) + "\n",
        encoding="utf-8",
    )


def _write_minimal_f20_validation_artifact(root: Path, *, include_sqlite_binary: bool) -> None:
    """构造只覆盖 F20 receipt 语义的最小 validation artifact。"""

    _write_minimal_artifact_common(root)
    receipt_path = root / "source_evidence/f20/phase11_runtime_actual_run.json"
    sqlite_rel = "source_evidence/f20/phase11_runtime/runtime.sqlite3"
    sqlite_hash = hashlib.sha256(b"sqlite-bytes").hexdigest()
    receipt = _minimal_f20_receipt()
    receipt["sqlite_evidence"] = {
        "exists": True,
        "relative_path": sqlite_rel,
        "relative_name": "runtime.sqlite3",
        "sha256": sqlite_hash,
        "tables": {"simulation_jobs": 3, "simulation_job_events": 10},
    }
    receipt["runtime_receipt_hash"] = _stable_payload_hash(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    if include_sqlite_binary:
        sqlite_path = root / sqlite_rel
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite_path.write_bytes(b"sqlite-bytes")
    row = _row(
        "f20-runtime",
        source="PHASE11_RUNTIME_ACTUAL",
        runtime_invoked=True,
        runtime_completed=True,
        authoritative=True,
    )
    row["experiment_id"] = "F20_STRESS_AND_RECOVERY"
    row["source_artifact_path"] = "source_evidence/f20/phase11_runtime_actual_run.json"
    row["source_artifact_hash"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    blocked_receipt = root / "source_evidence/f20/blocked_env.json"
    blocked_receipt.write_text(
        json.dumps({"status": "BLOCKED_BY_ENV", "stage": "ENVIRONMENT_CHECK"}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    blocked = _row(
        "f20-blocked",
        status="BLOCKED_BY_ENV",
        source="PHASE9_2_ISAAC_ENVIRONMENT_CHECK",
        runtime_invoked=False,
        runtime_completed=False,
        authoritative=False,
    )
    blocked["experiment_id"] = "F15_MUJOCO_ISAAC_PAIRED"
    blocked["source_artifact_path"] = "source_evidence/f20/blocked_env.json"
    blocked["source_artifact_hash"] = hashlib.sha256(blocked_receipt.read_bytes()).hexdigest()
    root.joinpath("runs/raw_runs.jsonl").write_text(
        json.dumps(row, sort_keys=True) + "\n" + json.dumps(blocked, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    root.joinpath("aggregates/phase12_aggregate.json").write_text(
        json.dumps(
            {
                "unsafe_command_execution_count": 0,
                "blocked_by_env_count": 1,
                "failed_count": 0,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    root.joinpath("paired/paired_summary.json").write_text(
        json.dumps({"paired_backend_experiment_accepted": False}) + "\n",
        encoding="utf-8",
    )


def _minimal_f20_receipt() -> dict[str, object]:
    return {
        "runner": "PHASE11_SIMULATION_RUNTIME",
        "run_id": "f20-runtime",
        "main_job": {
            "status": "SUCCEEDED",
            "terminal_artifacts_present": True,
            "evidence_consistency_present": True,
            "artifact_paths": _minimal_terminal_artifact_paths(),
        },
        "recovery_evidence": {
            "lease_expired": True,
            "final_status": "SUCCEEDED",
            "attempt_count": 2,
            "transitions": [
                ["RUNNING", "INTERRUPTED"],
                ["INTERRUPTED", "RECOVERY_PENDING"],
                ["RECOVERY_PENDING", "QUEUED"],
            ],
        },
        "duplicate_competition_evidence": {
            "attempt_count": 1,
            "competing_worker_ids": ["worker-a", "worker-b"],
            "final_status": "SUCCEEDED",
            "lease_count": 1,
            "lease_winner": "worker-a",
            "lease_loser": "worker-b",
            "runner_invocation_count": 1,
        },
        "worker_lease_evidence": {
            "lease_count": 1,
            "heartbeat_observed": True,
            "released_lease_count": 1,
        },
    }


def _minimal_terminal_artifact_paths() -> dict[str, str]:
    return {
        "run_manifest": "phase11_1/runtime/f20/run_manifest.json",
        "job": "phase11_1/runtime/f20/job.json",
        "runtime_job": "phase11_1/runtime/f20/runtime_job.json",
        "attempts": "phase11_1/runtime/f20/attempts.jsonl",
        "leases": "phase11_1/runtime/f20/leases.jsonl",
        "lease_history": "phase11_1/runtime/f20/lease_history.jsonl",
        "events": "phase11_1/runtime/f20/events.jsonl",
        "state_transitions": "phase11_1/runtime/f20/state_transitions.jsonl",
        "metrics": "phase11_1/runtime/f20/metrics.json",
        "result": "phase11_1/runtime/f20/result.json",
        "provenance": "phase11_1/runtime/f20/provenance.json",
        "resource_usage": "phase11_1/runtime/f20/resource_usage.json",
        "cancellation": "phase11_1/runtime/f20/cancellation.json",
        "recovery": "phase11_1/runtime/f20/recovery.json",
        "evidence_consistency": "phase11_1/runtime/f20/evidence_consistency.json",
    }


def _write_minimal_artifact_common(root: Path) -> None:
    for path in [
        root / "runs",
        root / "aggregates",
        root / "statistics",
        root / "manifests",
        root / "paired",
        root / "plots/png",
        root / "plots/svg",
        root / "tables/csv",
        root / "tables/latex",
        root / "thesis",
        root / "demo_bundle",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    root.joinpath("statistics/phase12_statistics.json").write_text(
        json.dumps({"group_statistics": {"PCSC": _minimal_metric_counts()}}) + "\n",
        encoding="utf-8",
    )
    root.joinpath("manifests/provenance.json").write_text(
        json.dumps({"source_tree_hash": "tree", "worktree_clean": True}) + "\n",
        encoding="utf-8",
    )
    root.joinpath("plots/png/success_rate_comparison.png").write_bytes(b"png")
    root.joinpath("plots/svg/success_rate_comparison.svg").write_text("<svg />")
    _write_plot_index(root)
    root.joinpath("tables/csv/t2_mode_baseline.csv").write_text("metric,value\n")
    root.joinpath("tables/csv/t1_system_capability.csv").write_text(
        "capability,hardware_claim,status\n"
        "Simulation Workbench,none,UNKNOWN\n"
        "Model Control Center,none,UNKNOWN\n"
        "Real Robot,none,NOT_STARTED\n",
        encoding="utf-8",
    )
    root.joinpath("tables/latex/t2_mode_baseline.tex").write_text(
        "\\begin{tabular}{}\\end{tabular}"
    )
    root.joinpath("thesis/experiment_results.md").write_text("results")
    _write_demo_summary(root)


def _write_provenance(root: Path, *, worktree_clean: bool) -> None:
    root.joinpath("manifests/provenance.json").write_text(
        json.dumps({"source_tree_hash": "tree", "worktree_clean": worktree_clean}) + "\n",
        encoding="utf-8",
    )


def _write_plot_index(root: Path) -> None:
    root.joinpath("plots/plot_index.json").write_text(
        json.dumps(
            {
                "data_authority": "AUTHORITATIVE_THESIS_DATA",
                "svg_data_source": "aggregate_payload",
                "png_rendering_mode": "placeholder_preview",
                "png_contains_metric_data": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_demo_summary(root: Path, *, data_authority: str = "VALIDATION_ACCEPTED_DATA") -> None:
    root.joinpath("demo_bundle/demo_summary.json").write_text(
        json.dumps(
            {
                "data_authority": data_authority,
                "verifier_gated_authoritative_thesis_run_count": 1,
                "contains_secret": False,
                "real_controller_contacted": False,
                "hardware_motion_observed": False,
                "hardware_write_operations": [],
                "highest_real_hardware_acceptance_level": "NONE",
                "real_robot_validation": "NOT_STARTED",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_gap_verification_summary(root: Path) -> None:
    verification_dir = root / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    verification_dir.joinpath("phase12_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS",
                "thesis_status": "THESIS_PACKAGE_INCOMPLETE",
                "full_profile_readiness_status": "PHASE12_FULL_PROFILE_NOT_READY",
                "checks": {"source_tree_provenance_present": False},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _stable_payload_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _minimal_metric_counts() -> dict[str, int]:
    return {
        "sample_count": 1,
        "valid_metric_sample_count": 1,
        "excluded_metric_sample_count": 0,
    }


def _assert_validation_status_matches_provenance(verification: Mapping[str, object]) -> None:
    """validation 状态必须跟 provenance 是否来自 clean worktree 保持一致。"""

    checks = cast("Mapping[str, object]", verification["checks"])
    if checks["source_tree_provenance_present"]:
        assert verification["status"] == "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
        assert (
            verification["full_profile_readiness_status"]
            == "PHASE12_FULL_PROFILE_PREREQUISITES_READY"
        )
        assert verification["full_profile_execution_status"] == "NOT_RUN"
    else:
        assert (
            verification["status"]
            == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
        )
        assert verification["full_profile_readiness_status"] == "PHASE12_FULL_PROFILE_NOT_READY"
        assert verification["full_profile_execution_status"] == "NOT_RUN"


def _patch_minimal_full_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        phase12_validation,
        "PHASE12_EXPERIMENT_IDS",
        ["F15_MUJOCO_ISAAC_PAIRED"],
    )
    monkeypatch.setattr(
        phase12_validation,
        "final_experiment_registry",
        lambda: [
            SimpleNamespace(
                experiment_id="F15_MUJOCO_ISAAC_PAIRED",
                runner_kind="PHASE9_2_ISAAC",
            )
        ],
    )
    monkeypatch.setattr(
        phase12_validation,
        "build_experiment_plan",
        lambda profile: SimpleNamespace(
            run_count=1,
            seed_count=1,
            repetitions=1,
            experiments=[],
        ),
    )
    monkeypatch.setattr(phase12_validation, "_source_artifact_hash_verified", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_sample_policy_satisfied", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_paired_run_completeness", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_stress_task_count_satisfied", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_runtime_receipts_exist", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_runtime_receipt_hash_valid", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_phase11_sqlite_evidence_exists", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_worker_lease_evidence_exists", lambda *_: True)
    monkeypatch.setattr(
        phase12_validation,
        "_duplicate_competition_evidence_exists",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_runner_invocation_count_exactly_one",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_terminal_artifact_paths_valid_for_rows",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_recovery_evidence_valid_for_rows",
        lambda *_: True,
    )


def _patch_minimal_validation_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        phase12_validation,
        "PHASE12_EXPERIMENT_IDS",
        ["F01_PC_SC_BASELINE"],
    )
    monkeypatch.setattr(
        phase12_validation,
        "final_experiment_registry",
        lambda: [
            SimpleNamespace(
                experiment_id="F01_PC_SC_BASELINE",
                runner_kind="PHASE8_EXPERIMENT_RUNNER",
            )
        ],
    )
    monkeypatch.setattr(
        phase12_validation,
        "build_experiment_plan",
        lambda profile: SimpleNamespace(
            run_count=3,
            seed_count=1,
            repetitions=1,
            experiments=[],
        ),
    )
    monkeypatch.setattr(phase12_validation, "_source_artifact_hash_verified", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_sample_policy_satisfied", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_paired_run_completeness", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_stress_task_count_satisfied", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_runtime_receipts_exist", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_runtime_receipt_hash_valid", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_phase11_sqlite_evidence_exists", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_worker_lease_evidence_exists", lambda *_: True)
    monkeypatch.setattr(
        phase12_validation,
        "_duplicate_competition_evidence_exists",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_runner_invocation_count_exactly_one",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_terminal_artifact_paths_valid_for_rows",
        lambda *_: True,
    )
    monkeypatch.setattr(
        phase12_validation,
        "_recovery_evidence_valid_for_rows",
        lambda *_: True,
    )


def _patch_minimal_f20_validation_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        phase12_validation,
        "PHASE12_EXPERIMENT_IDS",
        ["F20_STRESS_AND_RECOVERY"],
    )
    monkeypatch.setattr(
        phase12_validation,
        "final_experiment_registry",
        lambda: [
            SimpleNamespace(
                experiment_id="F20_STRESS_AND_RECOVERY",
                runner_kind="PHASE11_SIMULATION_RUNTIME",
            )
        ],
    )
    monkeypatch.setattr(
        phase12_validation,
        "build_experiment_plan",
        lambda profile: SimpleNamespace(
            run_count=1,
            seed_count=1,
            repetitions=1,
            experiments=[],
        ),
    )
    monkeypatch.setattr(phase12_validation, "_sample_policy_satisfied", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_paired_run_completeness", lambda *_: True)
    monkeypatch.setattr(phase12_validation, "_stress_task_count_satisfied", lambda *_: True)


def _row(
    run_id: str,
    *,
    status: str = "SUCCESS",
    source: str = "PHASE8_ACTUAL_RUN",
    metric_value: float = 100.0,
    provenance_source: str = "MEASURED",
    runtime_invoked: bool = True,
    runtime_completed: bool = True,
    authoritative: bool = True,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "experiment_id": "F01_PC_SC_BASELINE",
        "research_question": "RQ1",
        "profile": "validation",
        "backend": "MOCK",
        "scenario_id": "S01_NORMAL_STATIC",
        "control_mode": "PCSC",
        "seed": 0,
        "repetition": 0,
        "status": status,
        "task_success": status == "SUCCESS",
        "task_completion_rate": 1.0 if status == "SUCCESS" else 0.0,
        "total_completion_time_ms": metric_value,
        "unsafe_command_execution_count": 0,
        "execution_source": source,
        "adapter_attempted": True,
        "environment_check_completed": True,
        "runtime_invoked": runtime_invoked,
        "runtime_completed": runtime_completed,
        "authoritative_for_thesis": authoritative,
        "source_artifact_path": "source_evidence/runtime/receipt.json",
        "source_artifact_hash": "hash",
        "source_verifier": "test",
        "environment_status": "READY" if status != "BLOCKED_BY_ENV" else "BLOCKED_BY_ENV",
        "blocker_stage": "" if status != "BLOCKED_BY_ENV" else "ENVIRONMENT_CHECK",
        "metric_provenance": {
            "total_completion_time_ms": {
                "source": provenance_source,
                "source_field": "test.metric",
                "source_artifact": "source_evidence/runtime/receipt.json",
                "unit": "ms",
            }
        },
        "hardware_claims": {
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "hardware_write_operations": [],
            "highest_real_hardware_acceptance_level": "NONE",
            "real_robot_validation": "NOT_STARTED",
        },
    }
