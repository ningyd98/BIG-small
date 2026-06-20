"""Phase 12.1 验收状态和真实 runner 语义测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cloud_edge_robot_arm.final_evaluation.aggregation import aggregate_results
from cloud_edge_robot_arm.final_evaluation.models import (
    ExecutionSource,
    Phase12Profile,
)
from cloud_edge_robot_arm.final_evaluation.registry import (
    PHASE12_EXPERIMENT_IDS,
    build_experiment_plan,
    final_experiment_registry,
)
from cloud_edge_robot_arm.final_evaluation.runner import run_phase12_experiments


def test_smoke_marks_all_rows_as_synthetic_and_not_authoritative(tmp_path: Path) -> None:
    """smoke 只能生成 pipeline sample，不得作为论文权威数据。"""

    output = tmp_path / "phase12"
    summary = run_phase12_experiments(Phase12Profile.SMOKE, output)
    rows = _read_jsonl(output / "runs/raw_runs.jsonl")
    manifests = _read_jsonl(output / "manifests/run_manifests.jsonl")

    assert summary["synthetic_sample_count"] == len(rows)
    assert summary["actual_run_count"] == 0
    assert {row["execution_source"] for row in rows} == {
        ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE.value
    }
    assert all(row["actual_runner_invoked"] is False for row in rows)
    assert all(row["authoritative_for_thesis"] is False for row in rows)
    assert all(
        manifest["execution_source"] == "SYNTHETIC_PIPELINE_SAMPLE" for manifest in manifests
    )


def test_smoke_verifier_uses_pipeline_ready_thesis_status(tmp_path: Path) -> None:
    """smoke 不能输出 thesis evidence accepted。"""

    output = tmp_path / "phase12"
    _run_pipeline(output, "smoke", "--smoke")

    summary = json.loads((output / "verification/phase12_summary.json").read_text())

    assert summary["status"] == "PHASE12_EXPERIMENT_SUITE_READY"
    assert summary["thesis_status"] == "PHASE12_THESIS_ASSET_PIPELINE_READY"
    assert summary["project_status"] == "NOT_CLOSED"
    assert summary["synthetic_sample_count"] > 0
    assert summary["actual_run_count"] == 0
    assert summary["authoritative_thesis_run_count"] == 0


def test_smoke_verifier_writes_auditable_status_correction(tmp_path: Path) -> None:
    """smoke 历史错误状态必须用 correction artifact 审计保留，不得静默覆盖。"""

    output = tmp_path / "phase12"
    _run_pipeline(output, "smoke", "--smoke")

    correction = json.loads(
        (output / "verification/phase12_smoke_status_correction.json").read_text()
    )

    assert correction["supersedes"] == "7b4c9af artifacts/phase12/verification/phase12_summary.json"
    assert correction["previous_thesis_status"] == "PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED"
    assert correction["corrected_thesis_status"] == "PHASE12_THESIS_ASSET_PIPELINE_READY"
    assert "synthetic pipeline samples" in correction["correction_reason"]
    assert correction["original_artifact_retained"] is True


def test_legacy_smoke_rows_without_source_fields_are_corrected_as_synthetic(
    tmp_path: Path,
) -> None:
    """7b4c9af smoke rows lacked source fields and must be corrected as synthetic."""

    output = tmp_path / "phase12"
    _run_pipeline(output, "smoke", "--smoke")
    raw_path = output / "runs/raw_runs.jsonl"
    legacy_rows = []
    for row in _read_jsonl(raw_path):
        for key in (
            "execution_source",
            "actual_runner_invoked",
            "authoritative_for_thesis",
            "source_artifact_path",
            "source_artifact_hash",
            "source_verifier",
            "environment_status",
        ):
            row.pop(key, None)
        legacy_rows.append(row)
    raw_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in legacy_rows) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase12.py",
            "--smoke",
            "--output",
            str(output / "verification_legacy"),
            "--artifact-root",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    summary = json.loads((output / "verification_legacy/phase12_summary.json").read_text())
    assert summary["synthetic_sample_count"] == 90
    assert summary["status"] == "PHASE12_EXPERIMENT_SUITE_READY"
    assert summary["thesis_status"] == "PHASE12_THESIS_ASSET_PIPELINE_READY"


def test_validation_uses_actual_runners_but_gates_authority_on_provenance(
    tmp_path: Path,
) -> None:
    """validation 必须调用 actual runner，但 provenance 缺口不能升级为论文权威。"""

    output = tmp_path / "phase12"
    _run_generation_pipeline(output, "validation")
    provenance_path = output / "manifests/provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["worktree_clean"] = False
    provenance["source_tree_hash"] = ""
    provenance_path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")
    _run_verifier(output, "--validation")
    rows = _read_jsonl(output / "runs/raw_runs.jsonl")
    summary = json.loads((output / "verification/phase12_summary.json").read_text())

    assert summary["status"] == "PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS"
    assert summary["thesis_status"] == "THESIS_PACKAGE_INCOMPLETE"
    assert summary["synthetic_sample_count"] == 0
    assert summary["adapter_attempt_count"] == len(rows)
    assert summary["runtime_invocation_count"] < summary["adapter_attempt_count"]
    assert summary["blocked_before_runtime_count"] > 0
    assert summary["verifier_gated_authoritative_thesis_run_count"] == 0
    assert summary["checks"]["source_tree_provenance_present"] is False
    assert all(row["adapter_attempted"] is True for row in rows)
    assert all(row["runtime_invoked"] is False for row in rows if row["status"] == "BLOCKED_BY_ENV")
    assert all(row["execution_source"] != "SYNTHETIC_PIPELINE_SAMPLE" for row in rows)


def test_synthetic_rows_are_excluded_from_authoritative_statistics() -> None:
    """聚合时 synthetic pipeline sample 只能进管线审计，不进论文统计。"""

    rows = [
        _row("synthetic", authoritative=False, source="SYNTHETIC_PIPELINE_SAMPLE"),
        _row("actual", authoritative=True, source="PHASE8_ACTUAL_RUN"),
    ]

    aggregate = aggregate_results(Phase12Profile.SMOKE, rows)

    assert aggregate.run_count == 2
    assert aggregate.synthetic_sample_count == 1
    assert aggregate.authoritative_thesis_run_count == 1
    assert aggregate.authoritative_by_mode["PCSC"]["run_count"] == 1
    assert aggregate.authoritative_by_mode["PCSC"]["mean"] == 200.0


def test_registry_has_sample_policy_and_adapter_mapping_for_all_experiments() -> None:
    """F01-F20 必须都有 sample_policy 和 allowlisted adapter 映射。"""

    registry = final_experiment_registry()
    plan = build_experiment_plan(Phase12Profile.FULL)

    assert [item.experiment_id for item in registry] == PHASE12_EXPERIMENT_IDS
    assert all(item.sample_policy.seed_count >= 20 for item in registry)
    assert (
        next(
            item for item in registry if item.experiment_id == "F20_STRESS_AND_RECOVERY"
        ).sample_policy.task_count
        >= 100
    )
    assert (
        next(
            item for item in registry if item.experiment_id == "F15_MUJOCO_ISAAC_PAIRED"
        ).sample_policy.pairing_required
        is True
    )
    assert all(item.runner_kind in plan.runner_mapping for item in registry)
    assert not any("HARDWARE" in key or "REAL_ROBOT" in key for key in plan.runner_mapping)


def _run_pipeline(output: Path, profile: str, verify_flag: str) -> None:
    _run_generation_pipeline(output, profile)
    _run_verifier(output, verify_flag)


def _run_generation_pipeline(output: Path, profile: str) -> None:
    commands = [
        [
            sys.executable,
            "scripts/run_phase12_experiments.py",
            "--profile",
            profile,
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/analyze_phase12_results.py",
            "--profile",
            profile,
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/export_phase12_thesis_assets.py",
            "--profile",
            profile,
            "--output",
            str(output),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr + completed.stdout


def _run_verifier(output: Path, verify_flag: str) -> None:
    command = [
        sys.executable,
        "scripts/verify_phase12.py",
        verify_flag,
        "--output",
        str(output / "verification"),
        "--artifact-root",
        str(output),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _row(run_id: str, *, authoritative: bool, source: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "experiment_id": "F01_PC_SC_BASELINE",
        "research_question": "RQ1",
        "profile": "smoke",
        "backend": "MOCK",
        "scenario_id": "S01_NORMAL_STATIC",
        "control_mode": "PCSC",
        "seed": 0,
        "repetition": 0,
        "status": "SUCCESS",
        "task_success": True,
        "task_completion_rate": 1.0,
        "total_completion_time_ms": 200.0 if authoritative else 100.0,
        "unsafe_command_execution_count": 0,
        "execution_source": source,
        "actual_runner_invoked": authoritative,
        "authoritative_for_thesis": authoritative,
        "hardware_claims": {
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "hardware_write_operations": [],
            "highest_real_hardware_acceptance_level": "NONE",
            "real_robot_validation": "NOT_STARTED",
        },
    }
