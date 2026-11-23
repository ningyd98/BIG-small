"""Render the thesis diagrams directly from the public experiment summaries."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

INK, BLUE, TEAL, GRAY = "#162D41", "#285B80", "#167570", "#556879"
ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
HERE = ROUND / "round-graduation-integration-20261123"


def architecture(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.1, 3.9))
    ax.set(xlim=(0, 10), ylim=(0, 6))
    ax.axis("off")

    def box(x, y, width, height, title, body, color):
        rect = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.08",
            facecolor="#F1F5F7",
            edgecolor=color,
            linewidth=1.3,
        )
        ax.add_patch(rect)
        ax.text(
            x + width / 2,
            y + height * 0.72,
            title,
            ha="center",
            va="center",
            color=color,
            weight="bold",
            fontsize=13,
        )
        ax.text(
            x + width / 2,
            y + height * 0.33,
            body,
            ha="center",
            va="center",
            color=INK,
            fontsize=10,
            linespacing=1.55,
        )

    def arrow(x1, y1, x2, y2):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={"arrowstyle": "-|>", "color": GRAY, "lw": 1.6},
        )

    box(0.15, 3.37, 2.65, 2, "云端规划", "任务与技能候选\ngpt-6.1-sol", BLUE)
    box(3.67, 3.37, 2.65, 2, "边缘决策", "证据、风险与预算\n重观测或局部修复", TEAL)
    box(7.2, 3.37, 2.65, 2, "端侧执行", "OpenCV · SafetyShield\n控制器与执行反馈", BLUE)
    arrow(2.93, 4.4, 3.54, 4.4)
    arrow(6.46, 4.4, 7.05, 4.4)
    box(0.15, 0.2, 4.40, 1.55, "已登记的运行记录", "帧、动作版本、准入和发送账本", GRAY)
    box(5.45, 0.2, 4.40, 1.55, "独立离线评价", "原件读回、物理判分和比对", GRAY)
    arrow(4.7, 0.98, 5.32, 0.98)
    ax.plot([8.52, 8.52, 2.36, 2.36], [3.25, 2.43, 2.43, 1.93], color=GRAY, lw=1.3)
    arrow(2.36, 2.1, 2.36, 1.82)
    fig.savefig(output / "architecture.png", dpi=220, bbox_inches="tight", pad_inches=0.09)
    plt.close(fig)


def calibration(repo: Path, output: Path) -> None:
    data = json.loads((repo / HERE / "perception.public.json").read_text())
    rows = data["holdout_by_view"]
    if {v["view"] for v in rows} != {"axial", "left", "right"}:
        raise ValueError("unexpected held-out camera assignments")
    labels = {"axial": "登记顶视", "left": "偏视 A", "right": "偏视 B"}
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 2.8), gridspec_kw={"wspace": 0.42})
    ys = list(range(len(rows)))
    for ax in axes:
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.set_yticks(ys, [labels[row["view"]] for row in rows])
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(2.65, -0.68)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.2)
    cover = [100 * r["observed"] / r["allocated"] for r in rows]
    axes[0].barh(ys, cover, color=TEAL, height=0.43)
    for y, r in enumerate(rows):
        axes[0].text(cover[y] + 2, y, f"{r['observed']}/{r['allocated']}", va="center", fontsize=9)
    axes[0].set(xlim=(0, 127), xticks=[0, 25, 50, 75, 100], xlabel="有效顶心覆盖率（%）")
    vals = [row["top_center_p90_mm"] for row in rows]
    lim = max([10] + [v for v in vals if v is not None])
    for y, v in enumerate(vals):
        if v is not None:
            axes[1].barh(y, v, color=BLUE, height=0.43)
        axes[1].text(
            (v or 0) + lim * 0.025,
            y,
            "无观测" if v is None else f"{v:.1f}",
            va="center",
            fontsize=10,
        )
    axes[1].axvline(10, linestyle="--", color=GRAY, linewidth=1)
    axes[1].set(xlim=(0, lim * 1.27), xlabel="条件三维误差 P90（mm）")
    fig.savefig(output / "perception.png", dpi=220, bbox_inches="tight", pad_inches=0.09)
    plt.close(fig)


def evidence(repo: Path, output: Path) -> None:
    path = repo / ROUND / "round-v10-phase7-20261123/vision.public.json"
    ranges = json.loads(path.read_text())["lift"]["color_multiplicity_step_ranges"]
    counts = [sum(end - start + 1 for start, end in ranges[str(n)]) for n in range(4)]
    fig, ax = plt.subplots(figsize=(8.1, 2.65))
    bars = ax.barh(range(4), counts, color=[GRAY, BLUE, TEAL, GRAY], height=0.52)
    ax.set_yticks(range(4), [f"{n} 个候选" for n in range(4)])
    ax.set(xlabel="物理步位置数（含首末两端）", xlim=(0, max(counts) * 1.15))
    ax.invert_yaxis()
    ax.bar_label(bars, padding=4)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", alpha=0.22)
    ax.set_axisbelow(True)
    fig.savefig(output / "evidence.png", dpi=220, bbox_inches="tight", pad_inches=0.09)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    font_manager.findfont("Noto Sans CJK SC", fallback_to_default=False)
    plt.rcParams.update(
        {
            "font.family": "Noto Sans CJK SC",
            "font.size": 11,
            "text.color": INK,
            "axes.labelcolor": INK,
            "xtick.color": GRAY,
            "ytick.color": INK,
        }
    )
    root = Path(__file__).resolve().parents[2]
    args.output.mkdir(parents=True, exist_ok=True)
    architecture(args.output)
    calibration(root, args.output)
    evidence(root, args.output)


if __name__ == "__main__":
    main()
