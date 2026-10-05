"""真实样本的本地RGB、深度色条与有效掩码；未知量纲不标作米。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.datasets.external.models import DatasetSample, backproject_depth


def save_preview(sample: DatasetSample, output: Path) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sample.rgb).save(output / "rgb.png")
    Image.fromarray(sample.depth_valid_mask.astype(np.uint8) * 255).save(output / "valid_mask.png")
    np.save(output / "depth_raw.npy", sample.depth_raw, allow_pickle=False)
    metric = sample.depth_m is not None
    depth = sample.depth_m if sample.depth_m is not None else sample.depth_raw
    if sample.depth_m is not None:
        np.save(output / "depth_m.npy", sample.depth_m, allow_pickle=False)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    axes[0].imshow(sample.rgb)
    axes[0].set_title("RGB")
    colors = axes[1].imshow(np.ma.masked_where(~sample.depth_valid_mask, depth), cmap="viridis")
    axes[1].set_title("Depth (m)" if metric else "Raw depth (unit unverified)")
    fig.colorbar(colors, ax=axes[1], label="m" if metric else "raw value; unit unknown")
    axes[2].imshow(sample.depth_valid_mask, cmap="gray", vmin=0, vmax=1)
    axes[2].set_title("Valid depth mask")
    for ax in axes:
        ax.axis("off")
    fig.savefig(output / "preview.png", dpi=120)
    plt.close(fig)
    if sample.capabilities["camera_geometry"]:
        np.save(output / "pointcloud.npy", backproject_depth(sample), allow_pickle=False)
    overlay = sample.rgb.astype(np.float32).copy()
    instances = sample.annotations.get("instances", [])
    oracle_overlay = False
    palette = [(255, 60, 60), (50, 220, 80), (60, 120, 255), (220, 180, 40)]
    for instance in instances:
        mask = instance.get("visible_mask", {})
        if mask.get("available") and mask.get("path"):
            with Image.open(mask["path"]) as image:
                pixels = np.asarray(image)
            if pixels.shape == sample.rgb.shape[:2]:
                selected = pixels > 0
                color = palette[int(instance["instance_id"]) % len(palette)]
                overlay[selected] = 0.6 * overlay[selected] + 0.4 * np.asarray(color)
                oracle_overlay = True
    positions = []
    if sample.K_rgb is not None:
        for instance in instances:
            transform = instance.get("model_to_camera")
            if not transform or transform.get("to_frame") != "camera":
                continue
            center = np.asarray(transform["matrix"], dtype=float)[:3, 3]
            if center[2] <= 0:
                continue
            projected = sample.K_rgb @ center
            u, v = projected[:2] / projected[2]
            if 0 <= u < sample.rgb.shape[1] and 0 <= v < sample.rgb.shape[0]:
                positions.append((u, v, f"obj={instance['obj_id']} inst={instance['instance_id']}"))
                oracle_overlay = True
    if oracle_overlay:
        figure, ax = plt.subplots(figsize=(7, 5), layout="constrained")
        ax.imshow(overlay.astype(np.uint8))
        for u, v, label in positions:
            ax.scatter([u], [v], s=20, color="yellow")
            ax.text(u, v, label, color="yellow", fontsize=7)
        ax.set_title("Oracle / evaluation annotations (offline)")
        ax.axis("off")
        figure.savefig(output / "oracle_overlay.png", dpi=120)
        plt.close(figure)
    metadata = {
        "dataset_id": sample.dataset_id,
        "source_revision": sample.source_revision,
        "source_file": sample.source_file,
        "source_sha256": sample.source_sha256,
        "frame_index": sample.frame_index,
        "camera_id": sample.camera_id,
        "episode_id": sample.episode_id,
        "scene_id": sample.scene_id,
        "timestamp": sample.timestamp,
        "time_basis": sample.time_basis,
        "depth_unit": "m" if metric else "raw_unit_unknown",
        "depth_scale_m": sample.depth_scale_m,
        "depth_scale_evidence": sample.depth_scale_evidence,
        "depth_valid_ratio": float(sample.depth_valid_mask.mean()),
        "rgb_shape": list(sample.rgb.shape),
        "depth_shape": list(sample.depth_raw.shape),
        "depth_raw_dtype": str(sample.depth_raw.dtype),
        "capabilities": sample.capabilities,
        "source": "dataset_replay",
        "execution_verified": False,
        "oracle_overlay": oracle_overlay,
        "preview": str((output / "preview.png").resolve()),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata
