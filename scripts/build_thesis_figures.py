#!/usr/bin/env python
"""构建论文图表索引并复制 validation SVG 图。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build thesis figure assets.")
    parser.add_argument(
        "--validation-root",
        type=Path,
        default=Path("artifacts/phase12_2_clean/validation"),
    )
    parser.add_argument("--output", type=Path, default=Path("thesis/figures"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for name, title, body in _diagram_specs():
        path = args.output / "svg" / f"{name}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_diagram_svg(title, body), encoding="utf-8")
        copied.append({"path": str(path), "type": "svg", "data_source": "design_diagram"})
    for subdir in ("svg", "png"):
        source = args.validation_root / "plots" / subdir
        target = args.output / subdir
        target.mkdir(parents=True, exist_ok=True)
        if source.exists():
            for item in sorted(source.glob("*")):
                if item.is_file():
                    shutil.copy2(item, target / item.name)
                    copied.append(
                        {
                            "path": str(target / item.name),
                            "type": subdir,
                            "data_source": (
                                "aggregate_payload" if subdir == "svg" else "placeholder_preview"
                            ),
                        }
                    )
    index = {"figure_file_count": len(copied), "figures": copied}
    (args.output / "figure_index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _diagram_specs() -> list[tuple[str, str, list[str]]]:
    """返回论文设计图，均为结构说明，不包含伪造性能数据。"""

    return [
        (
            "system_architecture",
            "系统总体架构图",
            [
                "Cloud Planner",
                "TaskContract",
                "Edge Runtime",
                "SafetyShield",
                "Simulation Evidence",
            ],
        ),
        (
            "pcsc_flow",
            "PCSC 流程图",
            ["Telemetry Upload", "Cloud Supervision", "KEEP/UPDATE/PAUSE", "ACK", "Edge Execute"],
        ),
        (
            "eteac_flow",
            "ETEAC 流程图",
            [
                "Initial Contract",
                "Edge Event Detection",
                "Local Recovery",
                "FailureSummary",
                "Local Replan",
            ],
        ),
        (
            "auto_decision",
            "AUTO 决策图",
            ["Risk", "Network Quality", "Scene Dynamics", "Skill Cache", "Select PCSC/ETEAC"],
        ),
        (
            "llm_only_oneshot",
            "LLM-Only One-Shot 流程图",
            ["Task + Scene", "One Model Call", "TaskContract", "SafetyShield", "Simulation Only"],
        ),
        (
            "llm_only_reactive",
            "LLM-Only Reactive 流程图",
            [
                "Current State",
                "Model Call Per Step",
                "Contract Check",
                "SafetyShield",
                "Simulation Only",
            ],
        ),
        (
            "safetyshield_flow",
            "SafetyShield 流程图",
            ["Contract Candidate", "Freshness", "Workspace", "Collision", "Fail-Closed Decision"],
        ),
        (
            "edge_state_machine",
            "边缘状态机图",
            ["CREATED", "RUNNING", "RECOVERING", "COMPLETED/FAILED", "SAFETY_STOPPED"],
        ),
        (
            "local_replanning",
            "局部重规划流程图",
            ["FailureSummary", "Completed Steps Protection", "Replan Merge", "Validation", "Apply"],
        ),
        (
            "experiment_matrix",
            "实验矩阵图",
            ["F01-F20", "Backends", "Seeds/Repetitions", "Metrics", "Verifier"],
        ),
        (
            "phase_roadmap",
            "Phase 0-12 技术路线图",
            ["Contracts", "Safety", "Cloud/Edge", "Simulation", "Runtime", "Thesis Evidence"],
        ),
    ]


def _diagram_svg(title: str, body: list[str]) -> str:
    """生成简单可审计 SVG 流程图。"""

    width = 980
    height = 180 + 70 * len(body)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img">',
        f"<title>{title}</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="40" y="54" font-size="28" fill="#111827">{title}</text>',
    ]
    for index, label in enumerate(body):
        y = 100 + index * 70
        lines.extend(
            [
                f'<rect x="60" y="{y}" width="420" height="42" rx="6" '
                'fill="#eef2ff" stroke="#4338ca"/>',
                f'<text x="78" y="{y + 27}" font-size="16" fill="#111827">{label}</text>',
            ]
        )
        if index < len(body) - 1:
            lines.append(f'<text x="250" y="{y + 64}" font-size="22" fill="#374151">↓</text>')
    lines.append("</svg>")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
