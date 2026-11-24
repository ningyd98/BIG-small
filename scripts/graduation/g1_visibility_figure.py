"""Render the eight first-refusal frames and overlay their sealed current-pixel fits."""

import argparse
import base64
import gzip
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scripts.graduation.g1_formal_failure_figure import CROP, MARKER_COLORS, label
from scripts.graduation.perception_io import pinned, read, sha, write


def verified_gzip(path, digest):
    if sha(path) != digest:
        raise ValueError("historical pixel seal mismatch")
    with gzip.open(path, "rt", encoding="utf8") as stream:
        return json.load(stream)


def figure(round_dir, blind, old):
    summary = read(round_dir / "replay-historical.public.json")
    manifest_file = old / "originals-manifest.json"
    originals = pinned(manifest_file, summary["originals_manifest_sha256"])["files"]
    detections = verified_gzip(blind, summary["worker_sha256"][0])["frames"]
    canvas = Image.new("RGB", (1130, 750), "#f7f7f4")
    draw = ImageDraw.Draw(canvas)
    label(draw, (22, 21), "八次首次拒绝时，相机实际看到了什么", 32, bold=True)
    label(
        draw,
        (23, 71),
        "同一原始反馈，局部放大三倍。青色与黄色角标分别表示新算法定位的 ID 7 与 ID 8。",
        18,
    )
    sources = {}
    for row, mode in enumerate(("original", "dual")):
        for col in range(4):
            slot = f"f{col + 1:02d}-{mode}"
            stop = summary["anchors"][slot]["first_refused"]
            frame = detections[stop["frame_id"]]
            raw = old / "trials" / slot / "instance"
            ip = raw / "pixel-index.json"
            index = pinned(ip, originals[str(ip.relative_to(old))]["sha256"])
            (item,) = (r for r in index["frames"] if r["frame_id"] == stop["frame_id"])
            packet = pinned(raw / item["file"], stop["file_sha256"])
            if not (
                frame["checksum_sha256"] == stop["checksum_sha256"] == packet["checksum_sha256"]
            ):
                raise ValueError("unmatched refusal frame")
            with Image.open(io.BytesIO(base64.b64decode(packet["rgb_png_base64"]))) as im:
                crop = im.convert("RGB").crop(CROP)
            zoom = 3
            view = crop.resize((crop.width * zoom, crop.height * zoom), Image.Resampling.NEAREST)
            overlay = ImageDraw.Draw(view)
            for marker in frame["candidates"]:
                color = MARKER_COLORS.get(marker["id"], "#f25e35")
                quad = (np.asarray(marker["ordered_corners_px"]) - CROP[:2]) * zoom + (zoom - 1) / 2
                center = quad.mean(axis=0)
                for i, corner in enumerate(quad):
                    p = corner + 3 * (corner - center) / np.linalg.norm(corner - center)
                    for j in ((i - 1) % 4, (i + 1) % 4):
                        delta = quad[j] - corner
                        overlay.line(
                            [tuple(p), tuple(p + 7 * delta / np.linalg.norm(delta))],
                            fill=color,
                            width=2,
                        )
            x, y = 22 + col * 279, 115 + row * 314
            title = "原单标" if mode == "original" else "低位双标"
            label(
                draw,
                (x, y),
                f"{col + 1:02d}  {title}  ·  第 {stop['physics_step']} 步",
                18,
                bold=True,
            )
            canvas.paste(view, (x, y + 32))
            prior = stop["previous_disagreement_mm"]
            before = "未识别" if prior is None else f"分歧 {prior:.2f} mm"
            current = stop["disagreement_mm"]
            ids = "、".join(str(i) for i in frame["usable_ids"])
            after = (
                f"分歧 {current:.2f} mm"
                if current is not None
                else f"有效码 {ids}"
                if ids
                else "未识别"
            )
            label(draw, (x, y + 271), f"{before} → {after}", 17, color="#223c37")
            sources[slot] = {
                k: stop[k] for k in ("frame_id", "file_sha256", "checksum_sha256", "physics_step")
            }
    output = round_dir / "repaired-first-refusals.png"
    with output.open("xb") as stream:
        canvas.save(stream, "PNG")
    write(
        round_dir / "first-refusal-figure.public.json",
        {
            "sources": sources,
            "figure_sha256": sha(output),
            "reader_sha256": sha(blind),
            "crop_xyxy": list(CROP),
            "scale": zoom,
            "overlay": "Measured grids from blind pixel pass",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("round_dir", "blind", "old"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    figure(args.round_dir, args.blind, args.old)
