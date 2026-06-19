"""Phase 12 最终实验评估的契约测试，确保论文封板只声明软件与仿真证据。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

import cloud_edge_robot_arm.final_evaluation.report as phase12_report
from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile
from cloud_edge_robot_arm.final_evaluation.registry import (
    ALLOWLISTED_RUNNERS,
    PHASE12_EXPERIMENT_IDS,
    build_experiment_plan,
    final_experiment_registry,
)
from cloud_edge_robot_arm.final_evaluation.report import (
    _demo_bundle_contains_secret,
    _write_demo_bundle,
)
from cloud_edge_robot_arm.final_evaluation.statistics import (
    compute_group_statistics,
    paired_difference_summary,
)


def test_phase12_registry_defines_f01_to_f20_without_hardware_runners() -> None:
    """注册表必须覆盖 F01-F20，并且 runner allowlist 不含真实硬件入口。"""

    registry = final_experiment_registry()

    assert [item.experiment_id for item in registry] == PHASE12_EXPERIMENT_IDS
    assert len(registry) == 20
    assert all(item.hardware_claim == "software_or_simulation_only" for item in registry)
    assert not any("HARDWARE" in runner or "REAL_ROBOT" in runner for runner in ALLOWLISTED_RUNNERS)
    assert all(
        item.research_question in {f"RQ{index}" for index in range(1, 8)} for item in registry
    )


def test_phase12_suite_config_has_smoke_validation_and_full_profiles() -> None:
    """YAML 配置必须显式给出 smoke、validation 和 full 三种样本规模。"""

    payload = yaml.safe_load(Path("configs/phase12/final_experiment_suite.yaml").read_text())

    assert payload["schema_version"] == "phase12.final_experiment_suite.v1"
    assert set(payload["profiles"]) == {"smoke", "validation", "full"}
    assert payload["profiles"]["smoke"]["seeds"] == [0]
    assert payload["profiles"]["validation"]["seed_count"] >= 3
    assert payload["profiles"]["full"]["baseline_seed_count"] >= 30
    assert payload["hardware_claims"] == {
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
        "highest_real_hardware_acceptance_level": "NONE",
    }


def test_phase12_plan_expands_smoke_and_full_without_claiming_blocked_backends() -> None:
    """smoke 能快速展开，full 保留足够样本量且环境阻塞后端不会被当作通过。"""

    smoke = build_experiment_plan(Phase12Profile.SMOKE)
    full = build_experiment_plan(Phase12Profile.FULL)

    assert smoke.profile == Phase12Profile.SMOKE
    assert smoke.run_count > 0
    assert full.run_count > smoke.run_count
    assert full.baseline_seed_count >= 30
    assert any(item.status_if_unavailable == "BLOCKED_BY_ENV" for item in full.experiments)
    assert smoke.hardware_claims.real_controller_contacted is False
    assert smoke.hardware_claims.hardware_write_operations == []


def test_phase12_statistics_report_ci_effect_size_and_blocked_counts() -> None:
    """统计汇总必须包含样本量、置信区间、effect size 和 blocked 计数。"""

    rows = [
        _measured_row("PCSC", 100.0, "SUCCESS"),
        _measured_row("PCSC", 140.0, "SUCCESS"),
        _measured_row("ETEAC", 80.0, "SUCCESS"),
        _measured_row("ETEAC", 90.0, "BLOCKED_BY_ENV"),
    ]

    summary = compute_group_statistics(rows, group_key="group", metric_key="value")

    assert summary["PCSC"]["sample_count"] == 2
    assert summary["PCSC"]["confidence_interval_95"] is not None
    assert summary["ETEAC"]["blocked_by_env_count"] == 1
    assert "effect_size_vs_overall" in summary["PCSC"]


def test_phase12_paired_difference_keeps_failed_and_blocked_samples() -> None:
    """配对差异不能静默删除失败或 BLOCKED_BY_ENV 样本。"""

    pairs = [
        {
            "pairing_key": "a",
            "left_value": 10.0,
            "right_value": 8.0,
            "left_status": "SUCCESS",
            "right_status": "SUCCESS",
            "left_authoritative": True,
            "right_authoritative": True,
        },
        {
            "pairing_key": "b",
            "left_value": 12.0,
            "right_value": 0.0,
            "left_status": "FAILED",
            "right_status": "BLOCKED_BY_ENV",
        },
    ]

    result = paired_difference_summary(pairs)

    assert result["pair_count"] == 2
    assert result["usable_pair_count"] == 1
    assert result["blocked_by_env_count"] == 1
    assert result["failed_pair_count"] == 1
    assert result["mean_delta"] == 2.0


def _measured_row(group: str, value: float, status: str) -> dict[str, object]:
    """构造明确可进入论文统计的 measured 测试样本。"""

    return {
        "group": group,
        "value": value,
        "status": status,
        "authoritative_for_thesis": True,
        "metric_provenance": {
            "value": {
                "source": "MEASURED",
                "source_field": "test.value",
                "source_artifact": "test",
                "unit": "ms",
            }
        },
    }


def test_phase12_smoke_pipeline_generates_thesis_and_verification_artifacts(
    tmp_path: Path,
) -> None:
    """smoke 管线必须生成原始运行、聚合、统计、图表、表格、论文材料和验收摘要。"""

    output = tmp_path / "phase12"
    commands = [
        [
            sys.executable,
            "scripts/run_phase12_experiments.py",
            "--profile",
            "smoke",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/analyze_phase12_results.py",
            "--profile",
            "smoke",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/export_phase12_thesis_assets.py",
            "--profile",
            "smoke",
            "--output",
            str(output),
        ],
        [
            sys.executable,
            "scripts/verify_phase12.py",
            "--smoke",
            "--output",
            str(output / "verification"),
            "--artifact-root",
            str(output),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr + completed.stdout

    summary = json.loads((output / "verification/phase12_summary.json").read_text())

    assert summary["status"] == "PHASE12_EXPERIMENT_SUITE_READY"
    assert summary["full_profile_claimed"] is False
    assert summary["real_controller_contacted"] is False
    assert summary["hardware_motion_observed"] is False
    assert summary["hardware_write_operations"] == []
    assert summary["unsafe_command_execution_count"] == 0
    assert (output / "runs/raw_runs.jsonl").exists()
    assert (output / "aggregates/phase12_aggregate.json").exists()
    assert (output / "statistics/phase12_statistics.json").exists()
    assert (output / "plots/png/success_rate_comparison.png").exists()
    assert (output / "plots/svg/success_rate_comparison.svg").exists()
    assert (output / "tables/csv/t2_mode_baseline.csv").exists()
    assert (output / "tables/latex/t2_mode_baseline.tex").exists()
    assert (output / "reports/phase12_smoke_report.md").exists()
    assert (output / "demo_bundle/defense_demo_script.md").exists()


def test_demo_bundle_secret_flag_is_derived_from_bundle_content(tmp_path: Path) -> None:
    """答辩包 secret 标记必须来自文件内容扫描，不能固定写 false。"""

    demo = tmp_path / "demo_bundle"
    demo.mkdir()
    (demo / "safe.md").write_text("公开演示材料\n", encoding="utf-8")
    (demo / "leak.md").write_text("Authorization: Bearer abcdefgh123456\n", encoding="utf-8")

    assert _demo_bundle_contains_secret(demo) is True


def test_demo_bundle_summary_secret_flag_is_not_hardcoded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """demo_summary.json 的 contains_secret 必须反映生成后的答辩包内容。"""

    original_files = {
        "safe.md": "公开演示材料\n",
        "leak.md": "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz\n",
    }
    monkeypatch.setattr(
        phase12_report,
        "_demo_bundle_files",
        lambda: original_files,
    )

    _write_demo_bundle(
        tmp_path,
        {"run_count": 1, "hardware_claims": {}},
        data_authority="VALIDATION_ACCEPTED_DATA",
        verifier_gated_authoritative_thesis_run_count=1,
    )

    summary = json.loads((tmp_path / "demo_bundle/demo_summary.json").read_text())

    assert summary["contains_secret"] is True
