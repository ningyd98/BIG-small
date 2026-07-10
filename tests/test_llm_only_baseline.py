"""仅大模型基线框架测试。

测试目标是约束 fake provider 只能验证管线，不能被写成真实大模型 runtime evidence。
"""

from __future__ import annotations

import json
from pathlib import Path

from cloud_edge_robot_arm.experiments.llm_only.runner import (
    LLMOnlyProfile,
    LLMOnlyProvider,
    authoritative_model_performance_rows,
    run_llm_only_baseline,
)


def test_fake_provider_smoke_is_pipeline_ready_not_runtime_accepted(tmp_path: Path) -> None:
    """fake provider smoke 只能输出 pipeline ready，并保留 simulation-only 安全声明。"""

    output = tmp_path / "llm_only"
    summary = run_llm_only_baseline(
        profile=LLMOnlyProfile.SMOKE,
        provider=LLMOnlyProvider.FAKE,
        output_root=output,
    )

    assert summary["status"] == "LLM_ONLY_BASELINE_PIPELINE_READY"
    assert summary["runtime_status"] != "LLM_ONLY_BASELINE_RUNTIME_ACCEPTED"
    assert summary["model_runtime_type"] == "FAKE_PROVIDER_PIPELINE_TEST"
    assert summary["contains_secret"] is False
    assert summary["unsafe_command_execution_count"] == 0
    assert summary["real_controller_contacted"] is False
    assert summary["hardware_motion_observed"] is False
    assert summary["hardware_write_operations"] == []

    rows = [
        json.loads(line)
        for line in (output / "runs/llm_only_runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert rows
    assert all(row["safety_shield_checked"] is True for row in rows)
    assert all(row["hardware_execution"] is False for row in rows)
    assert all(row["model_runtime_type"] == "FAKE_PROVIDER_PIPELINE_TEST" for row in rows)


def test_fake_provider_validation_is_not_model_performance_evidence(tmp_path: Path) -> None:
    """validation+fake 不得生成真实模型性能结论。"""

    summary = run_llm_only_baseline(
        profile=LLMOnlyProfile.VALIDATION,
        provider=LLMOnlyProvider.FAKE,
        output_root=tmp_path / "llm_only_validation",
    )

    assert summary["status"] == "LLM_ONLY_BASELINE_PIPELINE_READY"
    assert summary["model_runtime_accepted"] is False
    assert summary["authoritative_for_model_performance"] is False


def test_fake_provider_rows_are_excluded_from_authoritative_model_performance(
    tmp_path: Path,
) -> None:
    """fake、PIPELINE_ONLY 和未 accepted 的模型数据必须全部排除出性能数据集。"""

    output = tmp_path / "llm_only"
    run_llm_only_baseline(
        profile=LLMOnlyProfile.SMOKE,
        provider=LLMOnlyProvider.FAKE,
        output_root=output,
    )
    rows = [
        json.loads(line)
        for line in (output / "runs/llm_only_runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert authoritative_model_performance_rows(rows) == []
