"""Phase 12 报告和论文素材导出。

导出内容全部来自 raw/aggregate/statistics artifact，文档只引用计算结果，不手工编造数值。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.final_evaluation.plots import export_plots
from cloud_edge_robot_arm.final_evaluation.tables import export_tables


def export_thesis_assets(output_root: Path, *, profile: str) -> dict[str, Any]:
    """导出图表、表格、报告、论文素材和答辩包。"""

    aggregate = _read_json(output_root / "aggregates/phase12_aggregate.json")
    statistics = _read_json(output_root / "statistics/phase12_statistics.json")
    plots = export_plots(output_root, aggregate)
    tables = export_tables(output_root, aggregate, statistics)
    reports = _write_reports(output_root, profile, aggregate, statistics)
    demo = _write_demo_bundle(output_root, aggregate)
    return {
        "profile": profile,
        "plot_count": len(plots),
        "table_file_count": len(tables),
        "reports": reports,
        "demo_bundle": demo,
    }


def _write_reports(
    output_root: Path, profile: str, aggregate: dict[str, Any], statistics: dict[str, Any]
) -> list[str]:
    reports_dir = output_root / "reports"
    thesis_dir = output_root / "thesis"
    reports_dir.mkdir(parents=True, exist_ok=True)
    thesis_dir.mkdir(parents=True, exist_ok=True)
    run_count = aggregate.get("run_count", 0)
    blocked = aggregate.get("blocked_by_env_count", 0)
    unsafe = aggregate.get("unsafe_command_execution_count", 0)
    synthetic = aggregate.get("synthetic_sample_count", 0)
    actual = aggregate.get("actual_run_count", 0)
    adapter_attempts = aggregate.get("adapter_attempt_count", actual)
    runtime_invocations = aggregate.get("runtime_invocation_count", actual)
    runtime_completions = aggregate.get("runtime_completion_count", actual)
    blocked_before_runtime = aggregate.get("blocked_before_runtime_count", 0)
    authoritative = aggregate.get("authoritative_thesis_run_count", 0)
    verification = _read_optional_json(output_root / "verification/phase12_summary.json")
    profile_note = _profile_note(profile, verification)
    thesis_status = str(verification.get("thesis_status", "")) if verification else ""
    report = (
        f"# Phase 12 {profile} 实验报告\n\n"
        f"- 运行总数：{run_count}\n"
        f"- synthetic pipeline samples：{synthetic}\n"
        f"- adapter attempts：{adapter_attempts}\n"
        f"- runtime invocations：{runtime_invocations}\n"
        f"- runtime completions：{runtime_completions}\n"
        f"- blocked before runtime：{blocked_before_runtime}\n"
        f"- authoritative thesis runs：{authoritative}\n"
        f"- 环境阻塞：{blocked}\n"
        f"- unsafe_command_execution_count：{unsafe}\n"
        f"- 状态语义：{profile_note}\n"
        "- 硬件声明：未接触真实控制器，未观察到物理运动。\n"
    )
    (reports_dir / f"phase12_{profile}_report.md").write_text(report, encoding="utf-8")
    thesis_files = {
        "experiment_design.md": (
            "# 实验设计\n\n"
            "Phase 12 固定 RQ1-RQ7 和 F01-F20。smoke 仅验证管线；validation "
            "调用 actual software runners；full 才可形成最终论文统计结论。\n"
        ),
        "experiment_environment.md": (
            "# 实验环境\n\n环境摘要和 source tree hash 由 manifest 记录。\n"
        ),
        "experiment_results.md": (
            "# 实验结果\n\n"
            f"本次 profile `{profile}` 自动生成 {run_count} 条运行记录，"
            f"其中 BLOCKED_BY_ENV={blocked}，authoritative_for_thesis={authoritative}。\n\n"
            f"{profile_note}\n" + (f"\n- thesis_status：{thesis_status}\n" if thesis_status else "")
        ),
        "discussion.md": (
            "# 讨论\n\n"
            "PCSC 与 ETEAC 的差异主要体现为云端调用与通信次数；AUTO 的收益需要 full "
            "profile 多 seed 统计支持。无真实机械臂验证时，不能声明 sim-to-real 实证完成。\n"
        ),
        "validity_threats.md": _validity_text(),
        "reproducibility.md": (
            "# 可复现性\n\n每个 run 记录 commit、tree hash、config hash 和 environment hash。\n"
        ),
        "system_contribution_summary.md": (
            "# 系统贡献总结\n\n系统贡献限于软件、仿真、dry-run、运行证据和模型控制中心。\n"
        ),
        "defense_demo_script.md": (
            "# 答辩演示脚本\n\n5-10 分钟演示按架构、工作台、模型控制、实验图表和安全边界展开。\n"
        ),
    }
    for name, text in thesis_files.items():
        (thesis_dir / name).write_text(text, encoding="utf-8")
    (reports_dir / "statistics_snapshot.json").write_text(
        json.dumps(statistics, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return [
        str((reports_dir / f"phase12_{profile}_report.md").relative_to(output_root)),
        *[str((thesis_dir / name).relative_to(output_root)) for name in thesis_files],
    ]


def _write_demo_bundle(output_root: Path, aggregate: dict[str, Any]) -> dict[str, Any]:
    demo = output_root / "demo_bundle"
    demo.mkdir(parents=True, exist_ok=True)
    files = {
        "architecture_diagram.md": "# 项目架构图\n\n云端规划、边缘安全、仿真运行时和证据闭环。\n",
        "pcsc_eteac_timeline.md": (
            "# PCSC / ETEAC 时间线\n\n展示监督、事件触发、恢复和重规划事件。\n"
        ),
        "dashboard_screenshots.md": "# 控制台截图清单\n\n截图由现场演示时从 `/console` 生成。\n",
        "experiment_figures.md": "# 实验图表\n\n见 `plots/png` 和 `plots/svg`。\n",
        "key_tables.md": "# 关键表格\n\n见 `tables/markdown`。\n",
        "safetyshield_example.md": "# SafetyShield 示例\n\n急停和过期遥测保持 fail-closed。\n",
        "network_recovery_demo.md": "# 网络故障恢复演示\n\n基于 F07/F20 的事件序列。\n",
        "backend_comparison.md": "# MuJoCo / Isaac 对比\n\nIsaac 不可用时显示 BLOCKED_BY_ENV。\n",
        "model_control_center_demo.md": (
            "# 模型控制中心演示\n\n展示 profile、Ollama 状态和 dry-run。\n"
        ),
        "reproducibility.md": (
            "# 复现说明\n\n使用 run_manifest、config_hash 和 source_tree_hash 复现。\n"
        ),
        "defense_demo_script.md": (
            "# 5-10 分钟答辩演示脚本\n\n1. 架构；2. 工作台；3. 实验；4. 安全边界；5. 局限。\n"
        ),
    }
    for name, text in files.items():
        (demo / name).write_text(text, encoding="utf-8")
    (demo / "demo_summary.json").write_text(
        json.dumps(
            {
                "file_count": len(files),
                "run_count": aggregate.get("run_count", 0),
                "contains_secret": False,
                "real_controller_contacted": False,
                "hardware_motion_observed": False,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"path": "demo_bundle", "file_count": len(files) + 1}


def _profile_note(profile: str, verification: dict[str, Any] | None = None) -> str:
    if verification:
        status = str(verification.get("status", "UNKNOWN"))
        thesis_status = str(verification.get("thesis_status", "UNKNOWN"))
        readiness = str(verification.get("full_profile_readiness_status", "UNKNOWN"))
        if status.endswith("_WITH_RUNTIME_EVIDENCE_GAPS") or thesis_status == (
            "THESIS_PACKAGE_INCOMPLETE"
        ):
            return (
                f"{status}；thesis_status={thesis_status}；"
                f"full_profile_readiness_status={readiness}。当前 evidence 仍有 gap，"
                "不得声明 validation accepted、full ready 或最终论文证据 accepted。"
            )
        if status:
            return (
                f"{status}；thesis_status={thesis_status}；"
                f"full_profile_readiness_status={readiness}。"
            )
    if profile == "smoke":
        return (
            "PHASE12_THESIS_ASSET_PIPELINE_READY；数据为 PIPELINE TEST DATA，不得作为论文最终结论。"
        )
    if profile == "validation":
        return (
            "VALIDATION_ANALYSIS_PENDING_VERIFICATION；数据来自 actual software runner "
            "validation，但尚未读取 verifier summary。不得在 verifier 通过前声明 validation "
            "analysis accepted。"
        )
    return (
        "PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED 仅在 full profile 样本策略和 "
        "authoritative evidence 全部满足时成立。"
    )


def _validity_text() -> str:
    return """# 有效性威胁

## 内部有效性

seed、仿真 determinism、worker 调度、cache、timeout 和环境版本都可能影响实验结果。

## 外部有效性

当前任务集中于小型机械臂仿真；仿真不等于真机，不同机器人泛化尚未验证。

## 构念有效性

成功率不能覆盖全部安全性，通信次数也不等于真实通信成本。

## 结论有效性

样本量、多重检验、非独立样本、环境阻塞和模型随机性会限制统计结论。

没有真实硬件实验时，论文不能声明完成 sim-to-real 实证。
"""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)
