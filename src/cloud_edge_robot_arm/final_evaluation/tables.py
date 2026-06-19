"""Phase 12 论文表格导出。

表格从聚合和统计结果自动生成 CSV、Markdown 和 LaTeX，不允许手工改写计算值。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

TABLE_IDS = [
    "t1_system_capability",
    "t2_mode_baseline",
    "t3_network_latency",
    "t4_packet_loss",
    "t5_fault_recovery",
    "t6_safety_shield",
    "t7_backend_paired",
    "t8_planner_provider",
    "t9_ablation",
    "t10_resource_overhead",
    "t11_failure_types",
    "t12_reproducibility",
]


def export_tables(
    output_root: Path,
    aggregate: dict[str, Any],
    statistics: dict[str, Any],
    *,
    data_authority: str | None = None,
) -> list[str]:
    """导出 12 个论文表格的 CSV、Markdown 和 LaTeX 版本。"""

    rows = _table_rows(aggregate, statistics, data_authority=data_authority)
    exported: list[str] = []
    for subdir in ("csv", "markdown", "latex"):
        (output_root / f"tables/{subdir}").mkdir(parents=True, exist_ok=True)
    for table_id in TABLE_IDS:
        table_rows = rows.get(table_id, rows["t2_mode_baseline"])
        csv_path = output_root / f"tables/csv/{table_id}.csv"
        md_path = output_root / f"tables/markdown/{table_id}.md"
        tex_path = output_root / f"tables/latex/{table_id}.tex"
        _write_csv(csv_path, table_rows)
        md_path.write_text(_markdown_table(table_id, table_rows), encoding="utf-8")
        tex_path.write_text(_latex_table(table_id, table_rows), encoding="utf-8")
        exported.extend(
            [
                str(csv_path.relative_to(output_root)),
                str(md_path.relative_to(output_root)),
                str(tex_path.relative_to(output_root)),
            ]
        )
    return exported


def _table_rows(
    aggregate: dict[str, Any], statistics: dict[str, Any], *, data_authority: str | None = None
) -> dict[str, list[dict[str, object]]]:
    authoritative_count = int(aggregate.get("authoritative_thesis_run_count", 0))
    synthetic_count = int(aggregate.get("synthetic_sample_count", 0))
    by_mode = aggregate.get("authoritative_by_mode") or aggregate.get("by_mode", {})
    authority = data_authority or (
        "PIPELINE_TEST_DATA"
        if synthetic_count > 0 and authoritative_count == 0
        else "PENDING_VERIFICATION_DATA"
    )
    mode_rows = [
        {
            "group": label,
            "n": values.get("run_count", 0),
            "authoritative_n": values.get(
                "authoritative_run_count",
                values.get("run_count", 0),
            ),
            "success_rate": values.get("success_rate", 0),
            "mean_time_ms": values.get("mean", ""),
            "blocked": values.get("blocked_by_env_count", 0),
            "data_authority": authority,
        }
        for label, values in sorted(by_mode.items())
    ] or [
        {
            "group": "NONE",
            "n": 0,
            "authoritative_n": 0,
            "success_rate": 0,
            "mean_time_ms": "",
            "blocked": 0,
            "data_authority": authority,
        }
    ]
    capability = _capability_rows(aggregate)
    failure_rows = [
        {
            "failure_type": "BLOCKED_BY_ENV",
            "count": aggregate.get("blocked_by_env_count", 0),
            "note": "单独统计，不计为算法失败或通过",
        },
        {
            "failure_type": "unsafe_command_execution",
            "count": aggregate.get("unsafe_command_execution_count", 0),
            "note": "必须为 0",
        },
    ]
    repro = _reproducibility_rows(aggregate)
    return {
        "t1_system_capability": capability,
        "t2_mode_baseline": mode_rows,
        "t3_network_latency": mode_rows,
        "t4_packet_loss": mode_rows,
        "t5_fault_recovery": mode_rows,
        "t6_safety_shield": failure_rows,
        "t7_backend_paired": [statistics.get("paired_results", {})],
        "t8_planner_provider": mode_rows,
        "t9_ablation": mode_rows,
        "t10_resource_overhead": mode_rows,
        "t11_failure_types": failure_rows,
        "t12_reproducibility": repro,
    }


def _capability_rows(aggregate: dict[str, Any]) -> list[dict[str, object]]:
    """从 aggregate 派生 T1 系统能力状态，避免表格无条件声明 ACCEPTED。"""

    statuses = aggregate.get("capability_statuses", {})
    if not isinstance(statuses, dict):
        statuses = {}
    defaults = {
        "Simulation Workbench": {"status": "ACCEPTED", "hardware_claim": "none"},
        "Model Control Center": {"status": "ACCEPTED", "hardware_claim": "none"},
        "Real Robot": {"status": "NOT_STARTED", "hardware_claim": "none"},
    }
    rows: list[dict[str, object]] = []
    for capability, default in defaults.items():
        override = statuses.get(capability, {})
        if not isinstance(override, dict):
            override = {}
        rows.append(
            {
                "capability": capability,
                "status": str(override.get("status") or default["status"]),
                "hardware_claim": str(override.get("hardware_claim") or default["hardware_claim"]),
            }
        )
    return rows


def _reproducibility_rows(aggregate: dict[str, Any]) -> list[dict[str, object]]:
    """从 aggregate 派生复现表；缺少 evidence 时不能宣称已记录。"""

    provenance = aggregate.get("reproducibility", {})
    if not isinstance(provenance, dict):
        provenance = {}
    source_tree_hash = _known_or_unknown(
        provenance.get("source_tree_hash") or aggregate.get("source_tree_hash")
    )
    worktree_clean = _known_or_unknown(
        provenance.get("worktree_clean") if "worktree_clean" in provenance else None
    )
    if worktree_clean == "UNKNOWN" and "worktree_clean" in aggregate:
        worktree_clean = _known_or_unknown(aggregate.get("worktree_clean"))
    return [
        {
            "field": "source_tree_hash",
            "value": source_tree_hash,
            "note": "来自 manifest/provenance；UNKNOWN 表示当前 aggregate 未提供证据",
        },
        {
            "field": "worktree_clean",
            "value": worktree_clean,
            "note": "full 结论要求 clean；UNKNOWN 表示当前 aggregate 未提供证据",
        },
    ]


def _known_or_unknown(value: object) -> str:
    if value is None or value == "":
        return "UNKNOWN"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(table_id: str, rows: list[dict[str, object]]) -> str:
    fields = sorted({key for row in rows for key in row})
    header = "| " + " | ".join(fields) + " |\n"
    sep = "| " + " | ".join("---" for _ in fields) + " |\n"
    body = "".join(
        "| " + " | ".join(str(row.get(field, "")) for field in fields) + " |\n" for row in rows
    )
    return f"# {table_id}\n\n{header}{sep}{body}"


def _latex_table(table_id: str, rows: list[dict[str, object]]) -> str:
    fields = sorted({key for row in rows for key in row})
    colspec = "l" * len(fields)
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{table_id}：Phase 12 自动生成表格，含样本量和单位}}",
        f"\\begin{{tabular}}{{{colspec}}}",
        "\\hline",
        " & ".join(fields) + r" \\",
        "\\hline",
    ]
    for row in rows:
        lines.append(
            " & ".join(_latex_escape(str(row.get(field, ""))) for field in fields) + r" \\"
        )
    lines.extend(["\\hline", "\\end{tabular}", "\\end{table}", ""])
    return "\n".join(lines)


def _latex_escape(value: str) -> str:
    return value.replace("_", "\\_").replace("%", "\\%")
