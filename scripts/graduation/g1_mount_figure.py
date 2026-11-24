"""Produce a fixed pixel crop from the first two preregistered poses and all three mounts."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from scripts.graduation.perception_io import pinned, read, sha, write
from scripts.graduation.proposal_camera import load_frame, rgb

CASES = ("t01-nominal", "t01-translated")
PANELS = (
    ("original", "原安装  +Y 100 mm"),
    ("r579", "候选  +X 100 mm"),
    ("component_v1", "组件候选  +Y 140 mm"),
)
CROP = (118, 65, 232, 154)  # x0, y0, x1, y1 in the original 320 × 240 frame


def make(screen, public, plan):
    receipt = read(screen / "capture-seal.json")
    index = pinned(screen / "pixels/index.json", receipt["index_sha256"])
    roles = pinned(screen / "roles.json", receipt["roles_sha256"])
    slots = read(plan)["source_terminal"]
    if tuple(row[0] for row in slots[:2]) != CASES:
        raise ValueError("figure rows do not match the first two preregistered terminal poses")
    with plt.rc_context({"font.family": "Noto Sans CJK JP", "axes.unicode_minus": False}):
        fig, axes = plt.subplots(2, 3, figsize=(8.4, 4.65))
        fig.subplots_adjust(
            left=0.16, right=0.985, top=0.88, bottom=0.08, wspace=0.025, hspace=0.10
        )
        records = []
        for idx, case in enumerate(CASES):
            _, step, role = slots[idx]
            state_ids = set()
            for col, (mount, title) in enumerate(PANELS):
                role_name = f"{case}/{mount}/normal"
                subject = roles["roles"][role_name]
                source = index["frames"][subject["key"]]
                frame = load_frame(screen / "pixels", source)
                if (
                    frame.checksum_sha256 != subject["checksum"]
                    or frame.frame_id != subject["frame_id"]
                    or frame.calibration_version != "f33940579c533afe"
                    or subject["step"] != step
                    or (frame.width, frame.height) != (320, 240)
                ):
                    raise ValueError("figure source is not the assigned nominal RGB-D acquisition")
                state_ids.add((subject["source_episode"], subject["state_sha256"]))
                x0, y0, x1, y1 = CROP
                ax = axes[idx, col]
                ax.imshow(rgb(frame)[y0:y1, x0:x1], interpolation="nearest")
                ax.set(xticks=[], yticks=[])
                for edge in ax.spines.values():
                    edge.set_visible(False)
                if idx == 0:
                    ax.set_title(title, fontsize=11, pad=8)
                if col == 0:
                    ax.set_ylabel(
                        f"{role.split('/')[0]}\n第 {step} 步",
                        rotation=0,
                        ha="right",
                        va="center",
                        labelpad=10,
                        fontsize=10,
                    )
                records.append(
                    {
                        "role": role_name,
                        "step": step,
                        "source_episode": subject["source_episode"],
                        "rgbd_file_sha256": source["sha256"],
                        "frame_checksum": frame.checksum_sha256,
                        "state_sha256": subject["state_sha256"],
                    }
                )
            if len(state_ids) != 1:
                raise ValueError("different physical poses joined in the same figure row")
        fig.text(
            0.16, 0.025, "固定顶视相机，三列截取原始 320 × 240 画面的同一像素范围。", fontsize=9
        )
        output = public / "mount-comparison.png"
        if output.exists():
            raise FileExistsError(output)
        fig.savefig(output, dpi=150, facecolor="white", metadata={"Software": "Matplotlib"})
        plt.close(fig)
    write(
        public / "figure.public.json",
        {
            "source_capture_seal_sha256": sha(screen / "capture-seal.json"),
            "source_screen_allocation_sha256": receipt["allocation_sha256"],
            "crop_xyxy_half_open_original_pixels": CROP,
            "selection": "first two preregistered poses",
            "rgbd_panels": records,
            "figure_sha256": sha(output),
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("screen", "public", "plan"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    make(args.screen, args.public, args.plan)
