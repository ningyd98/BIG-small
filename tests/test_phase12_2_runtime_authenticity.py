"""Phase 12.2 runtime authenticity and full-profile readiness tests.

中文说明：这些测试约束 validation 级实验必须区分 adapter 尝试、真实 runtime
调用、环境阻塞和论文可用证据，防止把环境检查或占位指标误当作实际运行结果。
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from cloud_edge_robot_arm.final_evaluation import validation as phase12_validation
from cloud_edge_robot_arm.final_evaluation.aggregation import aggregate_results
from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile
from cloud_edge_robot_arm.final_evaluation.runner import run_phase12_experiments
from cloud_edge_robot_arm.final_evaluation.statistics import compute_group_statistics


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
    assert _as_int(summary["actual_run_count"]) == _as_int(summary["runtime_invocation_count"])
    assert _as_int(summary["runtime_invocation_count"]) < _as_int(summary["adapter_attempt_count"])


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
    assert verification["runtime_invocation_count"] < verification["adapter_attempt_count"]
    assert verification["checks"]["paired_backend_acceptance_status_correct"] is True
    assert "paired_backend_experiment_accepted" not in verification["checks"]
    assert verification["paired_backend_experiment_accepted"] is False
    assert verification["usable_authoritative_pair_count"] == 0
    assert verification["blocked_pair_count"] == paired["blocked_pair_count"]
    assert verification["status"] == "PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED"
    assert verification["full_profile_readiness_status"] == "PHASE12_FULL_PROFILE_READY"


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


def test_full_profile_rejects_when_paired_backend_is_not_accepted(
    tmp_path: Path, monkeypatch
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


def test_full_profile_ready_status_matches_full_acceptance(tmp_path: Path, monkeypatch) -> None:
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


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected int, got {value!r}")
    return value


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
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    stats_dir.joinpath("phase12_statistics.json").write_text(
        json.dumps({"group_statistics": {"PCSC": {"sample_count": 1}}}) + "\n",
        encoding="utf-8",
    )
    manifests_dir.joinpath("provenance.json").write_text(
        json.dumps({"source_tree_hash": "tree", "worktree_clean": True}) + "\n",
        encoding="utf-8",
    )
    paired_dir.joinpath("paired_summary.json").write_text(
        json.dumps({"paired_backend_experiment_accepted": paired_accepted}) + "\n",
        encoding="utf-8",
    )
    root.joinpath("plots/png/success_rate_comparison.png").write_bytes(b"png")
    root.joinpath("plots/svg/success_rate_comparison.svg").write_text("<svg />")
    root.joinpath("tables/csv/t2_mode_baseline.csv").write_text("metric,value\n")
    root.joinpath("tables/latex/t2_mode_baseline.tex").write_text(
        "\\begin{tabular}{}\\end{tabular}"
    )
    root.joinpath("thesis/experiment_results.md").write_text("full results")
    root.joinpath("demo_bundle/demo_summary.json").write_text("{}\n")


def _patch_minimal_full_verifier(monkeypatch) -> None:
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
