"""Draw the first matched pair using raw, fixed-camera RGB crops from the static cross-check."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from scripts.graduation.g1_dual_cross_readback import PLAN
from scripts.graduation.g1_mount_figure import CROP
from scripts.graduation.g1_mount_screen_verify import raw_frame
from scripts.graduation.perception_io import pinned, read, sha, write
from scripts.graduation.proposal_camera import rgb


def figure(cross, public):
    seal = read(cross / "capture-seal.json")
    roles = pinned(cross / "roles.json", seal["roles_sha256"])["roles"]
    frames = pinned(cross / "pixels/index.json", seal["index_sha256"])["frames"]
    checks = read(public / "cross-readback.public.json")
    assert checks["plan_sha256"] == PLAN and checks["capture_seal_sha256"] == sha(
        cross / "capture-seal.json"
    )
    plan = pinned(public / "plan.json", PLAN)
    records = []
    panels = [(role, side) for role in ("previous", "refused") for side in ("Y", "X")]
    x0, y0, x1, y1 = CROP
    with plt.rc_context({"font.family": "Noto Sans CJK JP", "axes.unicode_minus": False}):
        fig, axes = plt.subplots(2, 4, figsize=(9.6, 4.7))
        fig.subplots_adjust(left=0.13, right=0.985, bottom=0.12, top=0.81, wspace=0.07, hspace=0.39)
        fig.text(
            0.13, 0.955, "最后有效反馈与首拒姿态的两侧复拍", fontsize=15, weight="bold", va="top"
        )
        fig.text(0.13, 0.88, "最后有效反馈姿态", fontsize=11)
        fig.text(0.56, 0.88, "8 个物理步后的首拒姿态", fontsize=11)
        for i, case in enumerate(plan["source_cases"][:2]):
            if case["case"] != ("m01-original", "m01-selected")[i]:
                raise ValueError("figure sources differ from first allocated pair")
            for j, (role, side) in enumerate(panels):
                name = f"{case['case']}/{role}/{side}/normal"
                frame, digest, subject = raw_frame(cross, roles, frames, name)
                (check,) = [
                    r for r in checks["poses"] if r["case"] == case["case"] and r["role"] == role
                ]
                normal = check["measurements"][side]["normal"]
                if (
                    normal["rgbd_file_sha256"] != digest
                    or subject["source_episode"] != case["episode"]
                    or subject["step"] != check["physics_step"]
                ):
                    raise ValueError("figure packet differs from checked source pose")
                usable = normal["usable"]
                ax = axes[i, j]
                ax.imshow(rgb(frame)[y0:y1, x0:x1], interpolation="nearest")
                ax.set(xticks=[], yticks=[])
                for spine in ax.spines.values():
                    spine.set_visible(False)
                ax.set_xlabel(
                    f"+{side}  ·  " + ("有效" if usable else "失标"),
                    size=10,
                    color="#075647" if usable else "#96290e",
                    labelpad=2,
                )
                if j == 0:
                    ax.set_ylabel(
                        f"m01\n原装 +{case['source_side']}\n{check['physics_step']} → "
                        + str(case["original_feedback"]["rejected_feedback"]["physics_step"])
                        + " 步",
                        rotation=0,
                        va="center",
                        ha="right",
                        labelpad=8,
                        fontsize=9,
                    )
                records.append(
                    {
                        "case": case["case"],
                        "episode": case["episode"],
                        "role": name,
                        "state_sha256": subject["state_sha256"],
                        "physics_step": subject["step"],
                        "rgbd_sha256": digest,
                        "frame_id": frame.frame_id,
                        "usable": usable,
                    }
                )
        fig.text(
            0.13,
            0.025,
            "同一列使用相同安装、原分辨率裁剪。每行的左右半部来自相隔 8 步的两个姿态。",
            fontsize=8.5,
        )
        path = public / "refusal-comparison.png"
        if path.exists():
            raise FileExistsError(path)
        fig.savefig(path, dpi=155, facecolor="white", metadata={"Software": "Matplotlib"})
        plt.close(fig)
    write(
        public / "figure.public.json",
        {
            "plan_sha256": PLAN,
            "capture_seal_sha256": checks["capture_seal_sha256"],
            "first_two_preregistered_source_cases": records,
            "crop_xyxy_half_open": CROP,
            "png_sha256": sha(path),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cross", type=Path)
    parser.add_argument("public", type=Path)
    args = parser.parse_args()
    figure(args.cross, args.public)
