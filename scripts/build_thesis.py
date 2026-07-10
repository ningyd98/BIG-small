#!/usr/bin/env python
"""装配论文源文件、注入 evidence 指标，并构建 Markdown、LaTeX、DOCX、PDF。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TITLE = "面向边缘智能场景的小型机械臂云边协同控制系统的设计"
EN_TITLE = (
    "Design of a Cloud-Edge Collaborative Control System for Small Robotic Arms "
    "in Edge Intelligence Scenarios"
)
CHAPTER_SLUGS = [
    "introduction",
    "related_work",
    "requirements_architecture",
    "collaboration_modes",
    "contract_safety",
    "recovery_replanning",
    "implementation",
    "experiment_design",
    "results",
    "engineering_management",
    "innovation_limitations",
    "conclusion",
]
REPRODUCIBLE_EPOCH = "1704067200"
REPRODUCIBLE_ZIP_DATETIME = (2024, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class BuildArtifact:
    """记录构建产物的验证状态。"""

    status: str
    path: str
    sha256: str
    size_bytes: int
    pages: int | None = None
    reason: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build thesis deliverables.")
    parser.add_argument("--generated", type=Path, default=Path("thesis/generated"))
    parser.add_argument("--source", type=Path, default=Path("docs/thesis/manuscript"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/thesis_report"))
    args = parser.parse_args()
    metrics = _read_json(args.generated / "thesis_metrics.json")
    trace = _read_json(args.generated / "claim_evidence.json")
    missing = _read_json(args.generated / "missing_data_report.json")
    figure_index = _load_figure_index(args.generated / "figure_index.json")
    table_index = _read_json(args.generated / "thesis_tables.json")
    references = _load_reference_keys(Path("thesis/references.bib"))
    docs_dir = Path("docs/thesis")
    thesis_dir = Path("thesis")
    chapters_dir = thesis_dir / "chapters"
    build_dir = args.output / "build"
    logs_dir = args.output / "logs"
    for directory in [docs_dir, thesis_dir, chapters_dir, args.output, build_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    context = _render_context(metrics, trace, missing, figure_index, table_index, references)
    sources = _load_manuscript_sources(args.source)
    manuscript = _render_manuscript(sources, context)
    _write_docs(docs_dir, manuscript, metrics, trace, missing)
    _write_latex(thesis_dir, chapters_dir, sources, context)
    report_md = args.output / "论文报告.md"
    report_tex = args.output / "论文报告.tex"
    report_md.write_text(manuscript, encoding="utf-8")
    report_tex.write_text((thesis_dir / "main.tex").read_text(encoding="utf-8"), encoding="utf-8")
    build_status = _build_outputs(report_md, thesis_dir / "main.tex", args.output, logs_dir)
    (docs_dir / "论文自检报告.md").write_text(
        _self_check_report(metrics, build_status),
        encoding="utf-8",
    )
    (args.output / "build_status.json").write_text(
        json.dumps(build_status, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(build_status, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manuscript_sources(source_dir: Path) -> list[dict[str, str]]:
    """按 manifest 顺序加载章节源文件，防止章节遗漏、重复或排序漂移。"""

    manifest_path = source_dir / "manifest.json"
    payload = _read_json(manifest_path)
    seen: set[str] = set()
    chapters: list[dict[str, str]] = []
    for section in [*payload.get("chapters", []), *payload.get("appendices", [])]:
        section_id = str(section["id"])
        if section_id in seen:
            raise ValueError(f"duplicate manuscript section id: {section_id}")
        seen.add(section_id)
        rel_path = Path(str(section["path"]))
        path = source_dir / rel_path
        content = path.read_text(encoding="utf-8")
        chapters.append(
            {
                "id": section_id,
                "title": str(section["title"]),
                "path": str(rel_path),
                "content": content,
            }
        )
    expected_prefixes = [
        "00",
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    ]
    actual_prefixes = [item["id"] for item in chapters[:13]]
    if len(actual_prefixes) >= 13 and actual_prefixes != expected_prefixes:
        raise ValueError(f"unexpected manuscript chapter order: {actual_prefixes}")
    return chapters


def _load_figure_index(generated_index: Path) -> list[dict[str, str]]:
    """优先使用完整论文图索引，缺失时回退到 evidence 图索引。"""

    thesis_index = Path("thesis/figures/figure_index.json")
    if thesis_index.exists():
        data = _read_json(thesis_index)
        figures = data.get("figures") if isinstance(data, dict) else data
        if isinstance(figures, list):
            return [
                _normalize_figure(item, idx + 1)
                for idx, item in enumerate(figures)
                if isinstance(item, dict)
            ]
    data = _read_json(generated_index)
    if isinstance(data, list):
        return [
            _normalize_figure(item, idx + 1)
            for idx, item in enumerate(data)
            if isinstance(item, dict)
        ]
    return []


def _normalize_figure(item: dict[str, Any], index: int = 1) -> dict[str, str]:
    path = str(item.get("path", ""))
    name = str(item.get("name") or item.get("title") or Path(path).stem or "unnamed_figure")
    data_source = str(item.get("data_source", "unknown"))
    formal_allowed = bool(item.get("formal_allowed", data_source != "placeholder_preview"))
    return {
        "figure_no": str(item.get("figure_no", f"图{index}")),
        "name": name,
        "path": path,
        "type": str(item.get("type", Path(path).suffix.lstrip(".") or "unknown")),
        "data_source": data_source,
        "authority_level": str(
            item.get("authority_level", "L4" if data_source == "aggregate_payload" else "L1")
        ),
        "source_hash": str(item.get("source_hash", "")),
        "formal_allowed": str(formal_allowed).lower(),
    }


def _load_reference_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    return re.findall(r"@\w+\{([^,]+),", path.read_text(encoding="utf-8"))


def _render_context(
    metrics: dict[str, Any],
    trace: list[dict[str, Any]],
    missing: dict[str, Any],
    figure_index: list[dict[str, str]],
    table_index: list[dict[str, Any]],
    references: list[str],
) -> dict[str, str]:
    llm = metrics.get("llm_only", {})
    context: dict[str, str] = {
        key: str(value) for key, value in metrics.items() if not isinstance(value, (dict, list))
    }
    context.update(
        {
            "title": TITLE,
            "en_title": EN_TITLE,
            "rq_list": _rq_text(),
            "experiment_list": _f_list(metrics),
            "baseline_list": _b_list(),
            "figures": _figure_markdown(figure_index),
            "tables": _table_markdown(table_index),
            "trace_table": _trace_markdown_rows(trace),
            "backend_counts": str(metrics.get("backend_counts", {})),
            "runtime_backend_counts": str(metrics.get("runtime_backend_counts", {})),
            "source_counts": str(metrics.get("source_counts", {})),
            "mode_rows": str(metrics.get("by_mode", {})),
            "status_counts": str(metrics.get("status_counts", {})),
            "expected_pair_count": str(metrics.get("paired", {}).get("expected_pair_count")),
            "usable_authoritative_pair_count": str(
                metrics.get("paired", {}).get("usable_authoritative_pair_count")
            ),
            "blocked_pair_count": str(metrics.get("paired", {}).get("blocked_pair_count")),
            "paired_backend_experiment_accepted": str(
                metrics.get("paired", {}).get("paired_backend_experiment_accepted")
            ),
            "llm_status": str(llm.get("status", "NOT_AVAILABLE")),
            "llm_model_runtime_type": str(llm.get("model_runtime_type", "NOT_AVAILABLE")),
            "llm_runtime_status": str(llm.get("runtime_status", "NOT_AVAILABLE")),
            "llm_model_runtime_accepted": str(llm.get("model_runtime_accepted", False)),
            "reference_count": str(len(references)),
            "reference_citations": "; ".join(f"[@{key}]" for key in references[:10]),
            "required_follow_up": "\n".join(
                f"- {item}" for item in missing.get("required_follow_up", [])
            ),
            "llm_only_runtime_blocker": json.dumps(
                missing.get("llm_only_runtime", "BLOCKED_BY_ENV"), ensure_ascii=False, indent=2
            ),
        }
    )
    return context


def _render_manuscript(sources: list[dict[str, str]], context: dict[str, str]) -> str:
    rendered = [_render_template(item["content"], context) for item in sources]
    return "\n\n".join(part.rstrip() for part in rendered).rstrip() + "\n"


def _render_template(text: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return context.get(key, match.group(0))

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", repl, text)


def _figure_markdown(figures: list[dict[str, str]]) -> str:
    formal_figures = [item for item in figures if item.get("formal_allowed") == "true"]
    return "\n".join(
        (
            f"- {item['figure_no']} {item['name']}：{item['path']}"
            f"（source={item['data_source']}，authority={item['authority_level']}，"
            f"formal_allowed={item['formal_allowed']}）"
        )
        for item in formal_figures
    )


def _table_markdown(tables: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {idx + 1}. {item['name']}：{item['path']}，行数 {item['row_count']}"
        for idx, item in enumerate(tables)
    )


def _trace_markdown_rows(trace: list[dict[str, Any]]) -> str:
    return "\n".join(
        (
            "| {章节} | {结论} | {指标} | {数值} | {source file} | "
            "{authority_level} | {limitations} |"
        ).format(**item)
        for item in trace
    )


def _join_wrapped(items: list[str]) -> str:
    return "\n".join(items)


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _docx_paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{_xml_escape(text)}</w:t></w:r></w:p>"


def _long_xml_line(*parts: str) -> str:
    return "".join(parts)


def _latex_abstract(context: dict[str, str]) -> str:
    return (
        "\\chapter*{摘要}\n"
        f"本文 validation 级证据包含 {context['run_count']} 条记录；"
        "full profile 尚未完成。\\par\n"
    )


def _latex_english_abstract(context: dict[str, str]) -> str:
    return (
        "\\chapter*{Abstract}\n"
        f"The current validation evidence contains {context['run_count']} records. "
        "The full profile remains future work.\\par\n"
    )


def _rq_text() -> str:
    return "\n".join(
        [
            "- RQ1：与 PCSC 相比，ETEAC 是否能在保证成功率和安全性的前提下降低云端调用和通信开销？",
            "- RQ2：AUTO 是否能在不同网络和故障条件下获得更优综合性能？",
            "- RQ3：边缘本地恢复和局部重规划是否能降低任务失败率和云端完整重规划次数？",
            "- RQ4：SafetyShield 和 HardwareExecutionGate 是否能保持 fail-closed？",
            "- RQ5：MuJoCo 和 Isaac Sim 的实验趋势是否一致，gap 来自哪些指标？",
            "- RQ6：不同 planner/provider 是否影响规划成功率、延迟、修复次数和契约有效率？",
            "- RQ7：技能缓存、风险评估、AUTO 选择器和局部恢复分别贡献什么？",
            (
                "- RQ8：与 LLM-Only Decision Baseline 相比，云边协同架构能否在"
                "成功率、时延、鲁棒性、通信、安全、恢复和复现性方面取得更好的"
                "综合表现？当前 RQ8 是待真实模型运行补充的假设。"
            ),
        ]
    )


def _f_list(metrics: dict[str, Any]) -> str:
    experiments = metrics.get("experiment_status", {})
    return "\n".join(f"- {key}：{value}" for key, value in sorted(experiments.items()))


def _b_list() -> str:
    return "\n".join(
        [
            "- B01_LLM_ONLY_ONESHOT：一次模型调用生成完整 TaskContract，异常时失败或整体重试。",
            (
                "- B02_LLM_ONLY_REACTIVE：每一步或异常后调用模型生成下一动作，"
                "仍经过契约校验和 SafetyShield。"
            ),
            (
                "- B03_PIPELINE_ONLY_PAIRED_DESIGN：fake provider 仅验证配对分析管线；"
                "真实 runtime accepted 前不得写成性能比较。"
            ),
            (
                "- B03_REAL_RUNTIME_PAIRED_COMPARISON：仅在 REAL_LLM_RUNTIME 或 "
                "LOCAL_LLM_RUNTIME accepted 后启用。"
            ),
        ]
    )


def _write_docs(
    docs_dir: Path,
    manuscript: str,
    metrics: dict[str, Any],
    trace: list[dict[str, Any]],
    missing: dict[str, Any],
) -> None:
    docs = {
        "论文报告_完整版.md": manuscript,
        "论文摘要.md": manuscript.split("# 第一章")[0],
        "论文大纲.md": _outline(),
        "研究问题与实验对应表.md": _rq_mapping(metrics),
        "证据追踪矩阵.md": _trace_markdown(trace),
        "结论边界说明.md": _boundary(metrics),
        "文献缺口清单.md": _literature_gap(),
        "full_profile后续更新说明.md": _full_update_plan(missing),
        "仅大模型基线设计.md": _llm_design(),
        "大模型与云边协同对比实验.md": _llm_comparison_design(),
        "大模型实验环境阻塞说明.md": _llm_blockers(missing),
        "大模型对比结果模板.md": _llm_result_template(),
        "大模型实验复现指南.md": _llm_reproduction(),
    }
    for name, text in docs.items():
        (docs_dir / name).write_text(text, encoding="utf-8")


def _outline() -> str:
    chapters = [
        "绪论",
        "相关技术与研究现状",
        "需求分析与总体架构",
        "双模式云边协同机制",
        "任务契约和安全执行",
        "边缘自治和局部重规划",
        "系统实现和仿真平台",
        "实验设计",
        "实验结果与分析",
        "工程管理分析",
        "创新点、局限性和后续工作",
        "结论",
    ]
    return "# 论文大纲\n\n" + "\n".join(f"{idx + 1}. {name}" for idx, name in enumerate(chapters))


def _rq_mapping(metrics: dict[str, Any]) -> str:
    return "# 研究问题与实验对应表\n\n" + _f_list(metrics) + "\n\n" + _b_list()


def _trace_markdown(trace: list[dict[str, Any]]) -> str:
    lines = [
        "# 证据追踪矩阵",
        "",
        "| 章节 | 结论 | 指标 | 数值 | source file | source field | authority | limitations |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in trace:
        lines.append(
            f"| {row['章节']} | {row['结论']} | {row['指标']} | {row['数值']} | "
            f"{row['source file']} | {row['source field']} | {row['authority_level']} | "
            f"{row['limitations']} |"
        )
    return "\n".join(lines) + "\n"


def _boundary(metrics: dict[str, Any]) -> str:
    return f"""# 结论边界说明

- 当前状态：{metrics["status"]}，项目状态：{metrics["project_status"]}。
- full profile execution：{metrics["full_profile_execution_status"]}。
- 真实控制器接触：{metrics["real_controller_contacted"]}。
- 物理运动：{metrics["hardware_motion_observed"]}。
- 硬件写操作：{metrics["hardware_write_operations"]}。
- 最高真实硬件等级：{metrics["highest_real_hardware_acceptance_level"]}。
- fake provider 不代表真实大模型效果。
"""


def _literature_gap() -> str:
    topics = [
        "云边协同机器人",
        "快慢双系统",
        "事件触发控制",
        "LLM for robotics",
        "LLM-only agent control",
        "机器人安全",
        "Sim2Real",
        "MuJoCo",
        "Isaac Sim",
        "ROS 2",
        "MoveIt",
        "边缘自治",
        "工程证据链",
    ]
    return "# 文献缺口清单\n\n" + "\n".join(
        f"- {topic}：待人工进一步扩展学校格式条目；仓库级 references.bib 已纳入核验候选。"
        for topic in topics
    )


def _full_update_plan(missing: dict[str, Any]) -> str:
    return "# full_profile 后续更新说明\n\n" + "\n".join(
        f"- {item}" for item in missing.get("required_follow_up", [])
    )


def _llm_design() -> str:
    return """# 仅大模型基线设计

LLM-Only Decision Baseline 包括 B01 one-shot、B02 reactive、
B03_PIPELINE_ONLY_PAIRED_DESIGN 和 B03_REAL_RUNTIME_PAIRED_COMPARISON。
所有输出仍转为 TaskContract，并经过 SafetyShield 与 HardwareExecutionGate。当前 fake-provider
仅用于管线验证，不能用于真实大模型性能结论。
"""


def _llm_comparison_design() -> str:
    return """# 大模型与云边协同对比实验

配对组包括 LLM-Only One-Shot、LLM-Only Reactive、PCSC、ETEAC 和 AUTO。
控制变量包括场景、seed、repetition、后端、任务目标、安全策略、模型参数和超时时间。
fake provider 只能验证配对分析管线；真实 runtime accepted 前，
所有性能字段保持 NOT_AVAILABLE。
"""


def _llm_blockers(missing: dict[str, Any]) -> str:
    return "# 大模型实验环境阻塞说明\n\n" + json.dumps(
        missing.get("llm_only_runtime", "BLOCKED_BY_ENV"),
        ensure_ascii=False,
        indent=2,
    )


def _llm_result_template() -> str:
    return "\n".join(
        [
            "# 大模型对比结果模板",
            "",
            _markdown_row(
                [
                    "组别",
                    "runtime type",
                    "有效样本",
                    "成功率",
                    "平均时延",
                    "模型调用",
                    "token",
                    "成本",
                    "结论",
                ]
            ),
            _markdown_row(["---"] * 9),
            _markdown_row(
                [
                    "LLM-Only One-Shot",
                    "待补充",
                    "0",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "待真实模型运行",
                ]
            ),
            _markdown_row(
                [
                    "LLM-Only Reactive",
                    "待补充",
                    "0",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "NOT_AVAILABLE",
                    "待真实模型运行",
                ]
            ),
            "",
        ]
    )


def _llm_reproduction() -> str:
    return """# 大模型实验复现指南

本指南用于复现 LLM-Only Decision Baseline 的软件管线。默认命令只运行 fake provider smoke，
状态只能写为 `LLM_ONLY_BASELINE_PIPELINE_READY`，不得作为真实大模型性能证据。

## Fake Provider Smoke

```bash
# 运行 fake provider smoke，只验证 LLM-only 管线和证据脱敏，不代表真实大模型性能
python scripts/run_llm_only_baseline.py --profile smoke --provider fake
python scripts/analyze_llm_only_baseline.py
python scripts/verify_llm_only_baseline.py
```

输出目录为 `artifacts/thesis_baselines/llm_only/`。其中响应文件只保存 prompt hash、
response hash、运行等级和脱敏摘要，不保存 API key、Authorization header 或模型密钥。

## OpenAI-Compatible Validation

真实 OpenAI-compatible provider 需要用户显式配置 endpoint、model 和 API key。未配置或未授权时，
脚本必须输出 `LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV`，不得自动回退 fake，也不得调用收费服务。

## Ollama Validation

本地 Ollama provider 只在 daemon 可达且指定模型已安装时运行。脚本不会自动下载大型模型；
模型不存在时记录 `BLOCKED_BY_ENV`。所有实验仍然是 simulation-only，并且动作必须经过
TaskContract、SafetyShield 和 HardwareExecutionGate。

## 安全边界

LLM-only baseline 不连接真实控制器，不发送真实机械臂控制命令，不执行 MoveIt execute，
不发布 ROS trajectory。真实模型数据只有在 `REAL_LLM_RUNTIME` 或 `LOCAL_LLM_RUNTIME`
accepted evidence 存在时，才能写入性能比较章节。
"""


def _write_latex(
    thesis_dir: Path,
    chapters_dir: Path,
    sources: list[dict[str, str]],
    context: dict[str, str],
) -> None:
    for idx, source in enumerate(sources[1:13], start=1):
        title = source["title"].replace(f"第{_cn_number(idx)}章 ", "")
        body = _markdown_to_latex(_render_template(source["content"], context), title)
        path = chapters_dir / f"{idx:02d}_{CHAPTER_SLUGS[idx - 1]}.tex"
        path.write_text(body, encoding="utf-8")
    appendix = _markdown_to_latex(_render_template(sources[-1]["content"], context), "证据追踪矩阵")
    (thesis_dir / "appendix.tex").write_text("\\appendix\n" + appendix, encoding="utf-8")
    includes = "\n".join(
        f"\\include{{chapters/{idx:02d}_{CHAPTER_SLUGS[idx - 1]}}}" for idx in range(1, 13)
    )
    (thesis_dir / "main.tex").write_text(
        "\\documentclass[UTF8]{ctexbook}\n"
        "\\usepackage{geometry}\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{longtable}\n"
        "\\geometry{a4paper, margin=2.5cm}\n"
        f"\\title{{{TITLE}}}\n"
        "\\author{待填写}\n"
        "\\date{待填写}\n"
        "\\begin{document}\n\\maketitle\n\\tableofcontents\n"
        f"{_latex_abstract(context)}"
        f"{_latex_english_abstract(context)}"
        f"{includes}\n"
        "\\include{appendix}\n"
        "\\nocite{*}\n\\bibliographystyle{plain}\n\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )


def _cn_number(index: int) -> str:
    return ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"][index - 1]


def _markdown_to_latex(markdown: str, fallback_title: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    chapter_written = False
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            out.append("\\begin{verbatim}" if in_code else "\\end{verbatim}")
            continue
        if in_code:
            out.append(line)
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            if title.startswith("第") or title == "附录":
                out.append(f"\\chapter{{{_escape_latex(title)}}}")
                chapter_written = True
            continue
        if line.startswith("## "):
            out.append(f"\\section{{{_escape_latex(line[3:].strip())}}}")
            continue
        if line.startswith("### "):
            out.append(f"\\subsection{{{_escape_latex(line[4:].strip())}}}")
            continue
        if line.startswith("- "):
            out.append(f"\\noindent $\\bullet$ {_escape_latex(line[2:])}\\par")
            continue
        if line.startswith("|"):
            out.append(_escape_latex(line) + "\\par")
            continue
        if line.strip():
            out.append(_escape_latex(line) + "\\par")
        else:
            out.append("")
    if not chapter_written:
        out.insert(0, f"\\chapter{{{_escape_latex(fallback_title)}}}")
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out).rstrip() + "\n"


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _build_outputs(report_md: Path, main_tex: Path, output: Path, logs_dir: Path) -> dict[str, Any]:
    status: dict[str, Any] = {
        "markdown": str(report_md),
        "latex": str(output / "论文报告.tex"),
        "docx": "NOT_BUILT",
        "pdf": "NOT_BUILT",
        "commands": [],
        "tool_versions": _tool_versions(),
    }
    docx = output / "论文报告.docx"
    docx_result = _build_docx(report_md, docx, logs_dir)
    status["docx"] = docx_result.__dict__
    pdf = output / "论文报告.pdf"
    pdf_result = _build_pdf(main_tex, pdf, logs_dir)
    status["pdf"] = pdf_result.__dict__
    status["commands"] = [
        "python scripts/build_thesis.py",
        "xelatex -interaction=nonstopmode -halt-on-error main.tex",
    ]
    return status


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    version_args = {
        "pandoc": ["--version"],
        "xelatex": ["--version"],
        "bibtex": ["--version"],
        "pdfinfo": ["-v"],
        "pdftotext": ["-v"],
    }
    for command, args in version_args.items():
        path = shutil.which(command)
        if not path:
            versions[command] = "NOT_FOUND"
            continue
        run = subprocess.run([path, *args], text=True, capture_output=True, check=False)
        versions[command] = (
            (run.stdout or run.stderr).splitlines()[0] if (run.stdout or run.stderr) else path
        )
    return versions


def _build_docx(report_md: Path, docx: Path, logs_dir: Path) -> BuildArtifact:
    pandoc = shutil.which("pandoc")
    log_path = logs_dir / "docx_build.log"
    if pandoc:
        run = subprocess.run(
            [pandoc, str(report_md), "-o", str(docx)], text=True, capture_output=True, check=False
        )
        log_path.write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode != 0:
            return BuildArtifact("NOT_BUILT", str(docx), "", 0, reason=run.stderr[-500:])
    else:
        _write_minimal_docx(report_md, docx)
        log_path.write_text(
            "pandoc not found; used built-in minimal OOXML writer\n", encoding="utf-8"
        )
    validation = _validate_docx(docx)
    if validation:
        return BuildArtifact("BUILT_AND_VALIDATED", str(docx), _sha256(docx), docx.stat().st_size)
    return BuildArtifact(
        "BUILT_BUT_INVALID",
        str(docx),
        _sha256(docx),
        docx.stat().st_size,
        reason="DOCX validation failed",
    )


def _write_minimal_docx(report_md: Path, docx: Path) -> None:
    text = report_md.read_text(encoding="utf-8")
    body = "".join(_docx_paragraph(line) for line in text.splitlines()[:900])
    content_types = _long_xml_line(
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
""",
        """<Override PartName="/word/document.xml" """,
        """ContentType="application/vnd.openxmlformats-officedocument.""",
        """wordprocessingml.document.main+xml"/>
</Types>""",
    )
    rels = _long_xml_line(
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
""",
        """<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/""",
        """officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
    )
    document = _long_xml_line(
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>""",
        """<w:document xmlns:w="http://schemas.openxmlformats.org/""",
        f"""wordprocessingml/2006/main"><w:body>{body}""",
        """<w:sectPr/></w:body></w:document>""",
    )
    with zipfile.ZipFile(docx, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _zip_writestr(archive, "[Content_Types].xml", content_types)
        _zip_writestr(archive, "_rels/.rels", rels)
        _zip_writestr(archive, "word/document.xml", document)


def _zip_writestr(archive: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, REPRODUCIBLE_ZIP_DATETIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, text.encode("utf-8"))


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _validate_docx(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            text = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile):
        return False
    return TITLE in text and "摘要" in text and "结论" in text


def _build_pdf(main_tex: Path, pdf: Path, logs_dir: Path) -> BuildArtifact:
    xelatex = shutil.which("xelatex")
    bibtex = shutil.which("bibtex")
    log_path = logs_dir / "pdf_build.log"
    if not xelatex:
        log_path.write_text("xelatex not found\n", encoding="utf-8")
        return BuildArtifact("NOT_BUILT", str(pdf), "", 0, reason="xelatex not found")
    workdir = main_tex.parent
    for suffix in [".aux", ".bbl", ".blg", ".log", ".out", ".toc", ".pdf"]:
        candidate = workdir / f"{main_tex.stem}{suffix}"
        if candidate.exists():
            candidate.unlink()
    combined_log = ""
    commands = [
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
    ]
    if bibtex and (workdir / "references.bib").exists():
        commands.append([bibtex, main_tex.stem])
    commands.extend(
        [
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", main_tex.name],
        ]
    )
    for command in commands:
        env = os.environ.copy()
        env.update(
            {
                "FORCE_SOURCE_DATE": "1",
                "SOURCE_DATE_EPOCH": REPRODUCIBLE_EPOCH,
                "TZ": "UTC",
            }
        )
        run = subprocess.run(
            command,
            cwd=workdir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        combined_log += run.stdout + run.stderr
        if run.returncode != 0:
            log_path.write_text(combined_log, encoding="utf-8")
            return BuildArtifact("NOT_BUILT", str(pdf), "", 0, reason=combined_log[-800:])
    built = workdir / "main.pdf"
    if built.exists():
        shutil.copy2(built, pdf)
    log_path.write_text(combined_log, encoding="utf-8")
    pages = _pdf_pages(pdf)
    if pdf.exists() and pdf.stat().st_size > 0 and pages > 0 and _pdf_contains_text(pdf):
        return BuildArtifact(
            "BUILT_AND_VALIDATED", str(pdf), _sha256(pdf), pdf.stat().st_size, pages=pages
        )
    return BuildArtifact(
        "BUILT_BUT_INVALID",
        str(pdf),
        _sha256(pdf) if pdf.exists() else "",
        pdf.stat().st_size if pdf.exists() else 0,
        pages=pages,
        reason="PDF validation failed",
    )


def _pdf_pages(path: Path) -> int:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo or not path.exists():
        return 0
    run = subprocess.run([pdfinfo, str(path)], text=True, capture_output=True, check=False)
    match = re.search(r"Pages:\s+(\d+)", run.stdout)
    return int(match.group(1)) if match else 0


def _pdf_contains_text(path: Path) -> bool:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext or not path.exists():
        return False
    run = subprocess.run([pdftotext, str(path), "-"], text=True, capture_output=True, check=False)
    return TITLE[:8] in run.stdout and "摘要" in run.stdout and "结论" in run.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _self_check_report(metrics: dict[str, Any], build_status: dict[str, Any]) -> str:
    return f"""# 论文自检报告

- validation status：{metrics["status"]}
- thesis status：{metrics["thesis_status"]}
- project status：{metrics["project_status"]}
- full profile execution：{metrics["full_profile_execution_status"]}
- unsafe command execution count：{metrics["unsafe_command_execution_count"]}
- DOCX：{build_status["docx"]}
- PDF：{build_status["pdf"]}
- 说明：只有 build_status 中出现 BUILT_AND_VALIDATED 才表示实际构建和校验成功。
"""


if __name__ == "__main__":
    raise SystemExit(main())
