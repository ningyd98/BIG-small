"""Plot the two sealed, pre-motion observations and the registered integer offset grid."""

import base64
import gzip
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image
from scripts.graduation.perception_io import pinned

HERE = Path(__file__).resolve().parent
INPUT = Path("experiments/results/g1-cv-grasp-validation-20261125/capture-v2/blind")
DIRECTIONS = ("object_X", "object_Y", "existing_tool_closure_axis")
STATES = {"BLOCKED": 0, "UNKNOWN": 1, "CLEAR": 2}
COLORS = ("#ab5552", "#ebbc60", "#397960")


def pixel(frame, position):
    matrix = np.asarray(frame["camera_to_world"]).reshape(4, 4)
    x, y, z = (np.linalg.inv(matrix) @ [*position, 1])[:3]
    fx, fy, cx, cy = frame["intrinsics"]
    return np.array([fx * x / z + cx, fy * y / z + cy])


def draw():
    public = pinned(
        HERE / "sweep-prospective.public.json",
        "9254aa055b99ee17e566b305fe5966de2410ecef9417c2c13baa6c825d3bb4ec",
    )
    final = pinned(
        HERE.parent / "round-g1-cv-sweep-route-binding-20261125/route-candidates.public.json",
        "3194a5948488ad57303c64829fff68e94637a5b8cbef9fedc6f555492b830ad8",
    )
    predictions = {
        r["frame_id"]: r
        for r in json.loads(gzip.decompress(base64.b64decode(final["data_base64"])))
    }
    plt.rcParams.update({"font.family": ["Noto Sans CJK JP", "DejaVu Sans"], "font.size": 10})
    fig = plt.figure(figsize=(10.8, 5.25), layout="constrained")
    axes = fig.subplots(2, 2, gridspec_kw={"width_ratios": (1, 2.2)})
    for i, summary in enumerate(public["frames"]):
        row = predictions[summary["frame_id"]]
        token = summary["anonymous_id"]
        packet = pinned(INPUT / token / "frame.json", summary["frame_sha256"])
        assert packet["frame_id"] == row["frame_id"] == summary["frame_id"]
        rgb = Image.open(io.BytesIO(base64.b64decode(packet["rgb_png_base64"]))).convert("RGB")
        center = np.asarray(row["marker"]["grasp_world_m"])
        best = summary["ranked_nominal_best"]["candidate_id"]
        item = next(e for e in row["candidates"] if e["candidate_id"] == best)
        rot = np.reshape(row["marker"]["rotation_object_to_world"], (3, 3))
        p = pixel(packet, center)
        q = pixel(packet, center + rot @ item["offset_object_m"])
        image, matrix = axes[i]
        image.imshow(rgb, interpolation="nearest")
        image.plot(*p, "o", mfc="none", mec="white", mew=1.7, ms=9)
        image.plot(*q, "+", color="#ffd152", mew=2, ms=12)
        image.set(xlim=(p[0] - 38, p[0] + 38), ylim=(p[1] + 23, p[1] - 23))
        image.set_axis_off()
        image.set_title(f"摆放 {token}     单帧 RGB 局部", loc="left", fontsize=12)
        samples = {(e["direction"], e["tangent_mm"]): e for e in row["candidates"]}
        grid = [
            [STATES[samples[(direction, n)]["full_physical_clearance"]] for n in range(-49, 50)]
            for direction in DIRECTIONS
        ]
        matrix.imshow(
            grid,
            cmap=ListedColormap(COLORS),
            vmin=0,
            vmax=2,
            aspect="auto",
            interpolation="nearest",
            extent=(-49.5, 49.5, 2.5, -0.5),
        )
        matrix.axvline(0, color="white", lw=1.1, ls="--")
        matrix.set(
            yticks=(0, 1, 2),
            yticklabels=("物体系 X 对夹", "物体系 Y 对夹", "原固定方向"),
            xticks=(-49, -35, -21, 0, 21, 35, 49),
        )
        matrix.tick_params(axis="both", length=0, pad=6)
        for spine in matrix.spines.values():
            spine.set_visible(False)
        matrix.set_title(
            f"居中与偏移候选     图示偏移 +{item['tangent_mm']:.0f} mm", loc="left", fontsize=12
        )
    axes[1, 1].set_xlabel("沿夹持面的偏移 (mm)")
    fig.suptitle("两个静止摆放的 RGB-D 抓点初筛", x=0.04, ha="left", fontsize=17, weight="bold")
    handles = [
        Line2D([], [], marker="o", mec="#383d43", mfc="none", color="none", label="原中央抓点"),
        Line2D([], [], marker="+", ms=11, mew=2, color="#d3a330", ls="none", label="偏移示例"),
        Patch(color=COLORS[0], label="筛除"),
        Patch(color=COLORS[1], label="几何可夹，通路未证"),
    ]
    fig.legend(handles=handles, ncol=4, loc="outside lower center", frameon=False)
    fig.savefig(HERE / "screen.public.png", dpi=140, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    draw()
