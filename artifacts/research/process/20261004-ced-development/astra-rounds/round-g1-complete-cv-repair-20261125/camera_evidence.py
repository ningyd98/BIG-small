"""Draw the actual G1 RGB frames and the registered detections used at selected boundaries."""

import argparse
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from scripts.graduation.g1_complete_trials import PRIVATE, ROUND, write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha


def photo(raw, role, index, run, measured):
    if role == "reset":
        record = next(f for f in index["frames"] if f["label"] == "reset")
    else:
        boundary = next(f for f in run["frame_roles"] if f["label"] == role)
        record = next(f for f in index["frames"] if f["frame_id"] == boundary["frame_id"])
        assert boundary["checksum_sha256"] == record["checksum_sha256"]
    packet = pinned(raw / record["file"], record["file_sha256"])
    assert packet["frame_id"] == record["frame_id"]
    image = Image.open(io.BytesIO(base64.b64decode(packet["rgb_png_base64"]))).convert("RGB")
    image = image.resize((480, 360), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    mark = measured.get(packet["frame_id"], {}).get("measurement", {})
    if mark:
        assert mark["checksum"] == packet["checksum_sha256"]
    for side in mark.get("by_id", {}).values():
        if side["usable"]:
            points = [(round(x * 1.5), round(y * 1.5)) for x, y in side["ordered_corners_px"]]
            draw.line(points + points[:1], fill=(13, 218, 220), width=2)
    return image, {
        k: record[k] for k in ("frame_id", "physics_step", "checksum_sha256", "file_sha256")
    }


def render(label, roles, stem):
    directory = ROOT / PRIVATE / "batches" / label
    batch = read(directory / "allocation.json")
    font = ImageFont.truetype("DejaVuSans.ttf", 18)
    bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 21)
    data = []
    canvas = Image.new("RGB", (24 + 496 * len(roles), 90 + 412 * len(batch["cases"])), "#fafafa")
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), "G1  |  Native overhead camera", font=bold, fill="#20252a")
    draw.text(
        (16, 45),
        f"{label}  |  Cyan outlines mark usable detections on each original image.",
        font=font,
        fill="#424852",
    )
    for i, case in enumerate(batch["cases"]):
        raw = directory / case["id"] / "instance"
        seal = read(raw / "acquisition-seal.json")
        index = pinned(raw / "pixel-index.json", seal["index_sha256"])
        run = pinned(raw / "run.json", seal["run_sha256"])
        vision = read(raw / "online-vision-seal.json")
        assert vision["acquisition_sha256"] == sha(raw / "acquisition-seal.json")
        frames = pinned(raw / "online-vision.json", vision["online_vision_sha256"])["frames"]
        for j, role in enumerate(roles):
            cell, meta = photo(raw, role, index, run, frames)
            x, y = 16 + 496 * j, 88 + 412 * i
            draw.text(
                (x, y),
                f"{case['id']}   {role}   step {meta['physics_step']}",
                font=font,
                fill="#22272c",
            )
            canvas.paste(cell, (x, y + 29))
            data.append(dict(id=case["id"], role=role, **meta))
    out = ROOT / ROUND / (stem + ".png")
    encoded = io.BytesIO()
    canvas.save(encoded, format="PNG")
    if out.exists():
        assert out.read_bytes() == encoded.getvalue()
    else:
        with out.open("xb") as stream:
            stream.write(encoded.getvalue())
    write_once(
        out.with_suffix(".public.json"),
        dict(batch_sha256=sha(directory / "allocation.json"), image_sha256=sha(out), sources=data),
    )
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("stem", type=lambda s: Path(s).name)
    parser.add_argument("roles", nargs="+")
    args = parser.parse_args()
    print(render(args.label, args.roles, args.stem))
