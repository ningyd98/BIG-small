"""Draw a measured RGB crop, a registered plate section and the independently computed distances."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

import cv2
import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from contact_witness import FINGER, PLATE, SIGNS, TRIAL
from matplotlib.patches import Rectangle


def project(points, frame):
    t = np.asarray(frame["camera_to_world"]).reshape(4, 4)
    camera = (np.asarray(points) - t[:3, 3]) @ t[:3, :3]
    assert (camera[:, 2] > 0).all()
    return camera[:, :2] / camera[:, 2:] * frame["intrinsics"][:2] + frame["intrinsics"][2:]


def draw(doc, frame, output):
    image = Image.open(io.BytesIO(base64.b64decode(frame["rgb_png_base64"])))
    plt.rcParams.update(
        {
            "font.family": ["Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.unicode_minus": False,
        }
    )
    fig, axs = plt.subplots(
        1, 3, figsize=(14, 4.7), layout="constrained", gridspec_kw={"width_ratios": [1, 1.12, 1.20]}
    )
    fig.suptitle(
        "d02 第 1221 步  ·  张开的右指触及 ID8 载板内侧上沿",
        fontsize=17,
        fontweight="bold",
        x=0.045,
        ha="left",
    )
    v15, v30 = [doc["mounts"][off]["states"] for off in ("15", "30")]
    t15, t30 = v15[-1], v30[-1]
    contact = [c for c in t15["restored_contacts"] if c["geom_names"] == [FINGER, PLATE]]
    uv = project([c["midpoint_world_m"] for c in contact], frame)
    ax = axs[0]
    ax.imshow(image, interpolation="nearest")
    u0, v0 = uv.mean(axis=0)
    ax.set_xlim(u0 - 25, u0 + 27)
    ax.set_ylim(v0 + 23, v0 - 23)
    for i, (u, v) in enumerate(uv):
        ax.scatter(u, v, s=42, facecolors="none", edgecolors="#ffd24b", linewidths=1.7, zorder=2)
        target = (u - 11, v + 10) if i == 0 else (u + 7, v - 9)
        ax.annotate(
            f"P{i + 1}",
            (u, v),
            xytext=target,
            color="white",
            weight="bold",
            arrowprops={"arrowstyle": "-", "color": "#ffd24b"},
            bbox=dict(fc="#202020", ec="none", pad=1.4),
        )
    ax.set_title("原始 +15 mm 顶视 RGB\n黄圈为恢复接触点的标定投影")
    ax.set_xlabel("原图横坐标（px）")
    ax.set_ylabel("原图纵坐标（px）")
    ax = axs[1]
    plate = t15["plate_box"]
    R = np.array(plate["r"])
    half = np.asarray(plate["h"])
    base = np.array([-half[0], 0, half[2]]) @ R.T + plate["c"]

    def section(q):
        world = (SIGNS * q["h"]) @ np.asarray(q["r"]).T + q["c"]
        return ((world - base) @ R)[:, [0, 2]] * 1000

    projected = section(t15["finger_box"])
    hull = cv2.convexHull(np.float32(projected)).reshape(-1, 2)
    ax.fill(*hull.T, color="#535e6c", alpha=0.70, label="同姿态右指投影")
    for q, color, label, style in [
        (plate, "#a43d32", "原 +15 mm 载板", "-"),
        (t30["plate_box"], "#146e5b", "反事实 +30 mm 载板", "--"),
    ]:
        xy = section(q)
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        ax.add_patch(
            Rectangle(
                lo,
                *(hi - lo),
                facecolor="none",
                linestyle=style,
                linewidth=2.4,
                edgecolor=color,
                label=label,
            )
        )
    ax.scatter(0, 0, marker="o", s=24, facecolors="white", edgecolors="#a43d32", zorder=3)
    ax.set_xlim(-20, 39)
    ax.set_ylim(-10, 23)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("沿板径向（mm），0 为原板内沿")
    ax.set_ylabel("相对原板上表面高度（mm）")
    ax.set_title("原板局部 X–Z 投影\n两个接触点沿 Y 分开")
    ax.legend(fontsize=8, loc="upper right")
    ax = axs[2]
    for rows, color, label in [(v15, "#a43d32", "原 +15 mm"), (v30, "#146e5b", "反事实 +30 mm")]:
        selected = [row for row in rows if row["step"] in set(range(1160, 1217, 8)) | {1220, 1221}]
        ds = [
            row["disjoint_feature_distance"]["distance_mm"]
            if row["disjoint_feature_distance"]
            else min(
                c["signed_distance_mm"]
                for c in row["restored_contacts"]
                if c["geom_names"] == [FINGER, PLATE]
            )
            for row in selected
        ]
        ax.plot(
            [r["step"] for r in selected], ds, marker="o", markersize=3.8, label=label, color=color
        )
    ax.axhline(0, color="#747474", linewidth=0.8)
    ax.grid(axis="y", color="#ddd", alpha=0.55)
    ax.set_title("相同归档关节与物体位姿\n分离为正，穿透为负")
    ax.set_xlabel("物理步（240 Hz）")
    ax.set_ylabel("右指与板表面间距（mm）")
    ax.legend(fontsize=9)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    doc = json.loads(args.data.read_bytes())
    info = doc["real_frames"][-1]
    raw = (TRIAL / "instance" / info["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == info["file_sha256"]
    if args.output.exists():
        raise FileExistsError(args.output)
    draw(doc, json.loads(raw), args.output)


if __name__ == "__main__":
    main()
