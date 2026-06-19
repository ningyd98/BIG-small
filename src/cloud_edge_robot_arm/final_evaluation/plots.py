"""Phase 12 图表导出。

图表使用轻量 SVG/PNG 占位渲染：SVG 包含真实聚合数值，PNG 为可打开的 1x1 安全位图。
正式论文可用 SVG 复核数据，避免手工改图。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

PLOT_NAMES = [
    "success_rate_comparison",
    "completion_time_box",
    "cloud_invocation_bar",
    "communication_count_bar",
    "network_latency_sensitivity",
    "packet_loss_sensitivity",
    "local_recovery_effect",
    "replanning_count_comparison",
    "safety_intervention_count",
    "mode_overall_comparison",
    "mujoco_isaac_paired_scatter",
    "backend_delta_distribution",
    "planner_latency",
    "planner_valid_contract_rate",
    "ablation_comparison",
    "stress_recovery_timeline",
    "failure_composition",
]


def export_plots(output_root: Path, aggregate: dict[str, Any]) -> list[str]:
    """生成 PNG 和 SVG 图表资产，返回相对路径列表。"""

    png_dir = output_root / "plots/png"
    svg_dir = output_root / "plots/svg"
    png_dir.mkdir(parents=True, exist_ok=True)
    svg_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    mode_data = aggregate.get("by_mode", {})
    for name in PLOT_NAMES:
        title = _title(name)
        svg = _svg(title, mode_data)
        svg_path = svg_dir / f"{name}.svg"
        png_path = png_dir / f"{name}.png"
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(PNG_1X1)
        exported.extend(
            [str(svg_path.relative_to(output_root)), str(png_path.relative_to(output_root))]
        )
    (output_root / "plots/plot_index.json").write_text(
        json.dumps({"plots": exported, "plot_count": len(exported)}, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return exported


def _title(name: str) -> str:
    mapping = {
        "success_rate_comparison": "成功率对比图",
        "completion_time_box": "总耗时箱线图",
        "cloud_invocation_bar": "云端调用次数柱状图",
        "communication_count_bar": "通信次数对比图",
        "network_latency_sensitivity": "网络延迟敏感性曲线",
        "packet_loss_sensitivity": "丢包敏感性曲线",
        "local_recovery_effect": "本地恢复效果图",
        "replanning_count_comparison": "重规划次数对比图",
        "safety_intervention_count": "安全干预次数图",
        "mode_overall_comparison": "PCSC / ETEAC / AUTO 综合对比",
        "mujoco_isaac_paired_scatter": "MuJoCo / Isaac 配对散点图",
        "backend_delta_distribution": "后端差异分布图",
        "planner_latency": "Planner 延迟图",
        "planner_valid_contract_rate": "Planner 契约有效率图",
        "ablation_comparison": "消融实验对比图",
        "stress_recovery_timeline": "压力恢复时间线",
        "failure_composition": "失败类型组成图",
    }
    return mapping[name]


def _svg(title: str, mode_data: object) -> str:
    data = json.dumps(mode_data, ensure_ascii=False, sort_keys=True)[:900]
    subtitle = "单位：按图题对应指标；包含失败和环境阻塞样本。"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" role="img">'
        f"<title>{title}</title>"
        '<rect width="960" height="540" fill="#ffffff"/>'
        f'<text x="48" y="64" font-size="28" fill="#111827">{title}</text>'
        f'<text x="48" y="108" font-size="16" fill="#374151">{subtitle}</text>'
        f'<text x="48" y="154" font-size="12" fill="#4b5563">{data}</text>'
        "</svg>"
    )
