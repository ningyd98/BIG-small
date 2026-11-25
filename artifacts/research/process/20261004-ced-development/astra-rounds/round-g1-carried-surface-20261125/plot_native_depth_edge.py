"""Show the unchanged RGB image and the local axial-depth samples at the native refusal."""

import base64
import io
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import font_manager
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def render(folder):
    plan = pinned(
        folder / "plan.json", "032a74e8216328e59810fa81cba368b3f53646b2711f3391dc3266fe51d80ba5"
    )
    failure = plan["observed_failure"]
    (source,) = [n for n in plan["input_sha256"] if n.endswith("/frames/0230.json")]
    packet = pinned(ROOT / source, plan["input_sha256"][source])
    frame = RGBDObservation.model_validate(packet)
    assert (
        frame.frame_id == failure["frame_id"]
        and frame.checksum_sha256 == failure["checksum_sha256"]
    )
    color = np.asarray(
        Image.open(io.BytesIO(base64.b64decode(packet["rgb_png_base64"]))).convert("RGB")
    )
    depth = axial(frame)
    x, y = failure["uv"]
    values = 1000 * depth[y, x - 4 : x + 5]
    font = font_manager.FontProperties(
        fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
    )
    matplotlib.rcParams.update({"font.family": font.get_name(), "axes.unicode_minus": False})
    fig, (whole, patch, row) = plt.subplots(
        1,
        3,
        figsize=(10.8, 3.7),
        layout="constrained",
        gridspec_kw={"width_ratios": [1.25, 1, 1.25]},
    )
    whole.imshow(color)
    whole.add_patch(Rectangle((x - 7.5, y - 7.5), 15, 15, fill=False, ec="#04d4e2", lw=1.5))
    whole.set_title("顶视相机原图", loc="left")
    whole.axis("off")
    vmin, vmax = np.quantile(depth[y - 7 : y + 8, x - 7 : x + 8], [0, 1]) * 1000
    patch.imshow(
        depth[y - 7 : y + 8, x - 7 : x + 8] * 1000,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
        extent=[x - 7.5, x + 7.5, y + 7.5, y - 7.5],
    )
    patch.axhline(y, color="white", lw=0.9, ls=(0, (2, 3)))
    patch.add_patch(Rectangle((x - 0.5, y - 0.5), 1, 1, fill=False, ec="#ff792d", lw=1.7))
    patch.set_title("深度图局部", loc="left")
    patch.set_xlabel("像素列 u")
    patch.set_ylabel("像素行 v")
    row.plot(np.arange(x - 4, x + 5), values, "o-", color="#226a78", lw=1.8)
    row.scatter([x], [values[4]], s=50, color="#ee6621", zorder=3)
    row.annotate(f"{values[4]:.1f} mm", (x, values[4]), xytext=(8, 8), textcoords="offset points")
    row.set_title(f"第 {y} 行的实测深度", loc="left")
    row.set_xlabel("像素列 u")
    row.set_ylabel("相机轴向深度（毫米）")
    row.grid(axis="y", alpha=0.25)
    for side in ("top", "right"):
        row.spines[side].set_visible(False)
    fig.suptitle("G1 第二个训练摆放 · 抬升反馈 · 试次物理步 2112", ha="left", x=0.015, fontsize=15)
    output = folder / "native-depth-edge.png"
    with output.open("xb") as f:
        fig.savefig(f, format="png", dpi=150)
    plt.close(fig)
    write_once(
        folder / "native-depth-edge.public.json",
        dict(
            file=source,
            file_sha256=plan["input_sha256"][source],
            checksum_sha256=frame.checksum_sha256,
            pixel_uv=[x, y],
            row_u=list(range(x - 4, x + 5)),
            axial_depth_mm=values.tolist(),
            figure_sha256=sha(output),
        ),
    )


if __name__ == "__main__":
    render(Path(__file__).resolve().parent)
