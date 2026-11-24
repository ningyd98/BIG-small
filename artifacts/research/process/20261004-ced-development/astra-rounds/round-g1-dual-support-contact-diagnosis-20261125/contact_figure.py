"""Draw the actual terminal RGB, the matched static renders and the contact in object axes."""

import argparse
import base64
import gzip
import io
import json
from pathlib import Path

import cv2
import matplotlib
import numpy as np
from contact_geometry import BEAM, LEFT, ROUND, TRIALS, prior
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


def project(points, frame):
    t = np.asarray(frame["camera_to_world"]).reshape(4, 4)
    camera = (np.asarray(points) - t[:3, 3]) @ t[:3, :3]
    return camera[:, :2] / camera[:, 2:] * frame["intrinsics"][:2] + frame["intrinsics"][2:]


def vertices(q):
    return (prior.SIGNS * np.asarray(q["h"])) @ np.asarray(q["r"]).T + q["c"]


def outline(ax, q, frame, color, style="-"):
    xy = project(vertices(q), frame)
    hull = cv2.convexHull(np.float32(xy)).reshape(-1, 2)
    ax.plot(*np.vstack((hull, hull[0])).T, color=color, ls=style, lw=1.4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private_render", type=Path)
    parser.add_argument("output", type=Path)
    a = parser.parse_args()
    data = json.loads(
        gzip.decompress((ROUND / "local-contact-geometry.public.json.gz").read_bytes())
    )
    renders = prior.read(ROUND / "local-render.public.json")["independent_renders"]
    d = data["trajectories"]["trajectory-30"]
    state = {q["step"]: q for q in d["poses"]["30"]["states"]}
    frame = prior.read(TRIALS[30] / "instance" / d["frames"][-1]["file"])
    terminal = np.asarray(Image.open(io.BytesIO(base64.b64decode(frame["rgb_png_base64"]))))
    cp = [c for c in state[1228]["contacts"] if c["geom_names"] == [LEFT, BEAM]]
    plt.rcParams.update(
        {
            "font.family": ["Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.unicode_minus": False,
        }
    )
    fig = plt.figure(figsize=(13.2, 7.8), layout="constrained")
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.15])
    fig.suptitle(
        "左指在两种装配共用的 ID7 横梁段内发生首碰",
        fontsize=18,
        fontweight="bold",
        x=0.045,
        ha="left",
    )
    center = project([c["midpoint_world_m"] for c in cp], frame).mean(axis=0)
    yellow = "#f9cf4d"
    blue = "#3296cd"
    teal = "#107562"
    rose = "#a3373d"
    for i, step in enumerate((1228, 1227, 1228)):
        ax = fig.add_subplot(gs[0, i])
        record = state[step]
        if i == 0:
            rgb = terminal
            title = "原始终帧 0146 · 第 1228 步"
        else:
            key = f"mount30-step{step}"
            p = a.private_render / f"{key}-rgb.npy"
            assert prior.sha(p) == renders[key]["files"][p.name]
            rgb = np.load(p, allow_pickle=False)
            title = f"同姿态重渲染 · 第 {step} 步"
        ax.imshow(rgb, interpolation="nearest")
        u, v = center
        ax.set_xlim(u - 26, u + 30)
        ax.set_ylim(v + 18, v - 18)
        if i == 0:
            ax.add_patch(Rectangle((u - 2.6, v - 3), 5.2, 6, fill=False, ec=yellow, lw=1.4))
            ax.annotate(
                "接触点投影",
                (u + 2.6, v - 2),
                xytext=(u + 8, v - 9),
                color="white",
                bbox=dict(fc="#282828", ec="none", pad=1.5),
                arrowprops=dict(arrowstyle="-", color=yellow),
            )
        else:
            finger, beam = record["pairs"]["left_beam"]["boxes"]
            outline(ax, finger, frame, blue)
            outline(ax, beam, frame, yellow, "--")
        ax.set_title(title, fontweight="bold", fontsize=11.5)
        ax.set_xlabel("原图横坐标（px）")
        if i == 0:
            ax.set_ylabel("原图纵坐标（px）")
        if i == 2:
            ax.legend(
                [Line2D([], [], color=blue), Line2D([], [], color=yellow, ls="--")],
                ["左指盒投影", "横梁盒投影"],
                loc="lower right",
                fontsize=8,
                framealpha=0.88,
            )
    ax = fig.add_subplot(gs[1, :2])
    final = state[1228]
    part = final["pairs"]["left_beam"]
    ob = final["object_pose"]
    fc = (vertices(part["boxes"][0]) - ob["c"]) @ np.asarray(ob["r"]) * 1000
    hull = cv2.convexHull(np.float32(fc[:, [1, 0]])).reshape(-1, 2)
    ax.fill(*hull.T, color="#aab9c8", alpha=0.65, lw=0, label="左指盒俯视投影")
    ax.add_patch(
        Rectangle((35, -4), 36, 8, fc="#b9e0d6", ec=teal, lw=1.8, label="两种装配共有梁段")
    )
    ax.add_patch(
        Rectangle(
            (71, -4), 15, 8, fc="#eee1cc", ec="#ae8c55", lw=1.4, ls="--", label="+30 新增远端"
        )
    )
    ax.axvline(35, color=teal, ls=":", lw=1)
    for i, c in enumerate(cp):
        x, y, z = c["geom2_surface_object_mm"]
        ax.plot(y, x, "o", mfc="white", mec=rose, ms=5, zorder=4)
        delta = [(-3.5, -3.2), (1.1, -3.2), (-0.9, 4.3)][i]
        ax.annotate(
            f"P{i + 1}",
            (y, x),
            xytext=(y + delta[0], x + delta[1]),
            color=rose,
            weight="bold",
            arrowprops=dict(arrowstyle="-", color=rose, lw=0.9),
        )
    ax.set_xlim(29, 91)
    ax.set_ylim(-12, 12)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("物体局部 Y（mm），沿横梁向外")
    ax.set_ylabel("物体局部 X（mm）")
    ax.set_title(
        "第 1228 步 · 三个梁表面接触点均位于共有段，Z = 19 mm", fontsize=12, fontweight="bold"
    )
    ax.legend(loc="upper right", fontsize=8, ncols=2, framealpha=0.92)
    ax = fig.add_subplot(gs[1, 2])
    steps = sorted(state)
    for name, color, label in [
        ("left_beam", rose, "左指–ID7 横梁"),
        ("right_plate", teal, "右指–ID8 载板"),
    ]:
        distances = []
        for step in steps:
            pair = state[step]["pairs"][name]
            distances.append(
                pair["nearest_disjoint"]["distance_mm"]
                if not pair["contact_count"]
                else pair["largest_signed_gap_mm"]
            )
        ax.plot(steps, distances, "o-", color=color, label=label, markersize=3.6)
    ax.axhline(0, ls=":", color="#373737")
    ax.grid(axis="y", color="#ddd", alpha=0.7)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title("+30 实际轨迹的固定姿态间距", fontsize=12, fontweight="bold")
    ax.set_xlabel("物理步（240 Hz）")
    ax.set_ylabel("分离净距 / 穿透深度（mm）")
    if a.output.exists():
        raise FileExistsError(a.output)
    fig.savefig(a.output, dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
