"""Join the physical pin counterfactual to original capture IDs and verify archived pairs."""

import base64
import gzip
import io
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import font_manager
from matplotlib import pyplot as plt
from PIL import Image

from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_trials import PRIVATE, write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def verified_history(folder):
    source = folder / "original-camera-alias.public.json"
    facts = pinned(source, "ec17f1628e6c4938befa730dd100ba627aed08b94de653d89871cc55a8f5b851")
    raw = ROOT / PRIVATE / "batches/train-full-04/cvfix-t02/instance"
    receipts = read(
        folder.parent / "round-g1-complete-cv-repair-20261125/train-full-04.public.json"
    )
    (status,) = [case for case in receipts["cases"] if case["id"] == "cvfix-t02"]
    receipt = pinned(raw / "receipt.json", status["receipt_sha256"])
    capture = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    index = pinned(raw / "pixel-index.json", capture["index_sha256"])
    frames = {f["frame_id"]: f for f in index["frames"]}
    steps, delta, bound = [], [], []
    for row in facts["actual_recorded_exposures"]:
        # This source field holds the native frame ID; its content digest is in the pixel index.
        original = frames[row["original_source_checksum"]]
        assert original["physics_step"] == row["step"]
        assert sha(raw / original["file"]) == original["file_sha256"]
        steps.append(row["step"])
        delta.append(1000 * row["peak_depth_delta_m"])
        bound.append(
            {k: original[k] for k in ("physics_step", "frame_id", "checksum_sha256", "file_sha256")}
        )
    assert steps == sorted(set(steps))
    paired = ROOT / PRIVATE / "carried-surface-native-pairs-01"
    assert sha(paired / "physically_added_tip.xml") == facts["physical_tip_xml_sha256"]
    checked = []
    for step in (1504, 2104, 2112):
        imgs = []
        for mode in (0, 1):
            p = paired / f"{step}-{mode}.json.gz"
            assert sha(p) == facts["raw_pairs"][p.name]
            frame = RGBDObservation.model_validate_json(gzip.decompress(p.read_bytes()))
            color = np.asarray(
                Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))).convert("RGB")
            )
            imgs.append((axial(frame), color))
        dz = np.abs(imgs[0][0] - imgs[1][0])
        rgb_error = np.abs(imgs[0][1].astype(int) - imgs[1][1].astype(int))
        differing = np.any(rgb_error > 0, axis=-1)
        entry = facts["actual_recorded_exposures"][steps.index(step)]
        assert float(dz.max()) == entry["peak_depth_delta_m"]
        assert int(np.count_nonzero(dz)) == entry["different_depth_pixels"]
        assert int(differing.sum()) == entry["different_rgb_pixels"]
        checked.append(
            dict(
                physics_step=step,
                changed_rgb_pixel_uv=np.argwhere(differing)[:, ::-1].tolist(),
                rgb_max_channel_difference=int(rgb_error.max()),
                depth_max_difference_mm=float(dz.max()) * 1000,
                at_original_pixel_rgb=[x[1][122, 171].tolist() for x in imgs],
            )
        )
    return (
        np.array(steps),
        np.array(delta),
        dict(
            source_sha256=sha(source),
            historical_capture_sha256=receipt["capture_sha256"],
            joined_original_frames=bound,
            independently_decoded_pairs=checked,
            equal_depth_images=int(
                sum(x["exact_native_depth"] for x in facts["actual_recorded_exposures"])
            ),
        ),
    )


def render(folder):
    steps, values, facts = verified_history(folder)
    font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    matplotlib.rcParams.update({"font.family": "Noto Sans CJK JP", "axes.unicode_minus": False})
    fig, (ax, detail) = plt.subplots(
        1, 2, figsize=(9.6, 3.65), width_ratios=[2.0, 1], layout="constrained"
    )
    for a, mask, title in (
        (ax, np.ones(len(steps), dtype=bool), "从首帧到原停机帧"),
        (detail, steps >= 1920, "抬升末段局部"),
    ):
        a.scatter(steps[mask], values[mask], s=12, color="#176276", linewidths=0)
        a.set_title(title, loc="left", fontsize=11)
        a.set_xlabel("原试次物理步")
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="y", alpha=0.25)
        a.axvline(2112, lw=0.8, color="#ae4a27", alpha=0.7)
    ax.set_ylabel("有针与无针的最大深度差（毫米）")
    ax.annotate(
        "22.45 mm",
        (120, values[0]),
        xytext=(0, -19),
        textcoords="offset points",
        fontsize=9,
        color="#164858",
    )
    detail.annotate(
        "2112 步 · 0 mm",
        (2112, 0),
        xytext=(-8, 12),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color="#983c22",
    )
    fig.suptitle("同一根静止细针在原顶视相机中的深度差", fontsize=14, x=0.02, ha="left")
    out = folder / "native-pin-history.png"
    with out.open("xb") as f:
        fig.savefig(f, format="png", dpi=150)
    plt.close(fig)
    write_once(folder / "native-pin-history.public.json", dict(facts, figure_sha256=sha(out)))
    print(len(steps), facts["equal_depth_images"], facts["independently_decoded_pairs"][-1])


if __name__ == "__main__":
    render(Path(__file__).resolve().parent)
