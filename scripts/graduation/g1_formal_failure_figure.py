"""Draw actual feedback frames on a common crop with board projections and observed IDs."""

from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scripts.graduation.g1_formal_failure_timeline import PLAN_SHA, RAW, ROOT, ROUND, require
from scripts.graduation.perception_io import pinned, read, sha, write

CROP = (141, 73, 227, 149)
PAPER_HALF_M = 0.05
SCALE = 2
MARKER_COLORS = {7: "#36e2df", 8: "#ffbf3d"}
PAPER = "#f6f5f0"
INK = "#18272d"
MUTED = "#4b6067"
ERROR = "#a32e29"
GOOD = "#155b48"
ARMS = {"original": "原单标", "dual": "低位双标"}
PHASES = {"MOVE_ABOVE": "上方移动", "APPROACH": "接近"}
ROLE_LABELS = {
    "first_accepted": "首次有效",
    "first_partial_or_refused": "首次缺码或拒绝",
    "middle_of_stopping_stage": "停机动作中段",
    "last_accepted": "末次有效",
    "first_refused": "首拒",
}


def font(size, bold=False):
    weight = "Bold" if bold else "Regular"
    return ImageFont.truetype(
        f"/usr/share/fonts/opentype/noto/NotoSansCJK-{weight}.ttc", size, index=2
    )


def label(draw, xy, value, size=16, color=INK, bold=False):
    draw.text(xy, value, font=font(size, bold), fill=color, anchor="lt")


def project_board(geometry, state, registration):
    camera = geometry["camera"]
    world_object = np.eye(4)
    world_object[:3, :3] = np.reshape(state["object_geom_rotation_row_major"], (3, 3))
    world_object[:3, 3] = state["object_geom_position_m"]
    transform = (
        np.linalg.inv(np.reshape(camera["camera_to_world"], (4, 4)))
        @ world_object
        @ np.reshape(registration, (4, 4))
    )
    square = np.array([[-1, 1], [1, 1], [1, -1], [-1, -1]]) * PAPER_HALF_M
    xyz = np.column_stack((square, np.zeros(4), np.ones(4))) @ transform.T
    fx, fy, cx, cy = camera["intrinsics"]
    uv = xyz[:, :2] / xyz[:, 2, None] * [fx, fy] + [cx, cy]
    require(
        np.all(xyz[:, 2] > 0) and np.all(uv >= CROP[:2]) and np.all(uv < CROP[2:]),
        "board outside annotated crop",
    )
    return uv


def mark_board(image, quad, marker):
    xy = (quad - CROP[:2]) * SCALE + (SCALE - 1) / 2
    center = xy.mean(axis=0)
    # Short ticks sit just outside the paper so the original print/margin pixels remain legible.
    xy = xy + (xy - center) / np.linalg.norm(xy - center, axis=1)[:, None] * 2.2
    draw = ImageDraw.Draw(image)
    for i, p in enumerate(xy):
        for j in ((i - 1) % 4, (i + 1) % 4):
            delta = xy[j] - p
            end = p + delta / np.linalg.norm(delta) * 7
            draw.line([tuple(p), tuple(end)], fill=MARKER_COLORS[marker], width=2)


class TrialFrames:
    def __init__(self, case, timeline, original_files):
        self.case = case
        self.rows = timeline
        self.sources = {}
        self.images = {}
        self.root = RAW / "trials" / case["id"]

        def original(path):
            return pinned(path, original_files[str(path.relative_to(RAW))]["sha256"])

        allocation = original(self.root / "allocation.json")
        self.geometry = allocation["geometry"]
        files = self.root / "instance"
        seal = original(files / "acquisition-seal.json")
        self.states = pinned(files / "offline-truth.json", seal["truth_sha256"])["samples"]
        self.transforms = {7: self.geometry["marker_to_object"]}
        if case["arm"] == "dual":
            self.transforms = {
                int(k): v["object_T_marker"]
                for k, v in self.geometry["development_dual"]["markers"].items()
            }

    def image(self, row):
        ident = row["frame_id"]
        if ident in self.images:
            return self.images[ident]
        record = pinned(self.root / "instance" / row["file"], row["file_sha256"])
        require(
            record["frame_id"] == ident and record["checksum_sha256"] == row["checksum_sha256"],
            "foreign image",
        )
        with Image.open(
            io.BytesIO(base64.b64decode(record["rgb_png_base64"], validate=True))
        ) as rgb:
            require(rgb.size == (320, 240), "unexpected camera resolution")
            width, height = CROP[2] - CROP[0], CROP[3] - CROP[1]
            image = (
                rgb.convert("RGB")
                .crop(CROP)
                .resize((width * SCALE, height * SCALE), Image.Resampling.NEAREST)
            )
        state = self.states[row["physics_step"]]
        require(
            state["episode_id"] == record["episode_id"]
            and state["physics_step"] == row["physics_step"],
            "foreign figure state",
        )
        boards = {}
        for marker, registration in self.transforms.items():
            quad = project_board(self.geometry, state, registration)
            mark_board(image, quad, marker)
            boards[str(marker)] = quad.tolist()
        self.sources[ident] = {
            "source_sha256": row["file_sha256"],
            "step": row["physics_step"],
            "registered_board_corners_source_px": boards,
        }
        self.images[ident] = image
        return image


def status(row):
    if row["usable"]:
        return "+".join(str(i) for i in row["usable_ids"]) + " 有效"
    if row["reason"] == "dual_marker_grasp_conflict":
        return "7+8 抓取点冲突"
    return "失标"


def key_frames(trial):
    events = defaultdict(list)
    for role, frame in trial.case["anchors"].items():
        events[frame["frame_id"]].append(role)
    if len(events) < 5:
        for distance in (8, 4, 2):
            f = trial.rows[-distance - 1]
            if f["frame_id"] not in events:
                events[f["frame_id"]].append("距首拒 " + str(8 * distance) + " 步")
            if len(events) == 5:
                break
    selected = []
    for f in trial.rows:
        roles = events.get(f["frame_id"])
        if not roles:
            continue
        if set(roles) == {"first_partial_or_refused", "first_refused"}:
            caption = "首次失标即停机" if not f["usable_ids"] else "首次冲突即停机"
        else:
            caption = " · ".join(ROLE_LABELS.get(k, k) for k in roles)
        selected.append((f, caption))
    require(len(selected) == 5, "expected five distinct time-ordered panels")
    return selected


def legend(draw, y):
    label(draw, (28, y), "角标标出同一步的板面投影", 14, MUTED)
    draw.line((240, y + 8, 262, y + 8), fill=MARKER_COLORS[7], width=4)
    label(draw, (269, y), "ID7", 14, MUTED)
    draw.line((315, y + 8, 337, y + 8), fill=MARKER_COLORS[8], width=4)
    label(draw, (344, y), "ID8", 14, MUTED)
    label(draw, (403, y), "图下标签来自原始图像的识别结果。", 14, MUTED)


def storyboards(trials, output):
    products = {}
    for arm, name in ARMS.items():
        canvas = Image.new("RGB", (1092, 926), PAPER)
        draw = ImageDraw.Draw(canvas)
        label(draw, (28, 21), name + "从有效反馈到首拒", 30, bold=True)
        legend(draw, 67)
        layouts = {}
        for i, trial in enumerate(t for t in trials if t.case["arm"] == arm):
            top = 103 + i * 204
            label(draw, (27, top + 36), trial.case["group"], 20, bold=True)
            label(draw, (27, top + 69), PHASES[trial.case["actual_stop"]["skill"]], 15, MUTED)
            draw.line((26, top - 8, 1061, top - 8), fill="#cfdbda")
            frames = key_frames(trial)
            layouts[trial.case["id"]] = []
            for j, (row, caption) in enumerate(frames):
                left = 113 + j * 190
                label(draw, (left, top), caption, 14)
                canvas.paste(trial.image(row), (left, top + 22))
                label(
                    draw,
                    (left, top + 180),
                    f"{row['physics_step']} 步 · {status(row)}",
                    14,
                    GOOD if row["usable"] else ERROR,
                    not row["usable"],
                )
                layouts[trial.case["id"]].append({"frame_id": row["frame_id"], "caption": caption})
        path = output / (arm + "-timeline.png")
        with path.open("xb") as stream:
            canvas.save(stream, format="PNG", optimize=True)
        products[path.name] = {"sha256": sha(path), "panels": layouts}
    return products


def loop(trials, output):
    lookup = {(t.case["group"], t.case["arm"]): t for t in trials}
    stills = []
    frames = {}
    for i in range(9):
        canvas = Image.new("RGB", (841, 570), PAPER)
        draw = ImageDraw.Draw(canvas)
        label(draw, (23, 15), "八次首停前的最后九帧反馈", 25, bold=True)
        label(
            draw, (475, 23), f"距各自首停 {(8 - i) * 8:2d} 步    ·    1 帧间隔 33.3 ms", 15, MUTED
        )
        legend(draw, 58)
        for col, group in enumerate(("f01", "f02", "f03", "f04")):
            left = 87 + col * 187
            label(draw, (left, 91), group, 19, bold=True)
            for r, arm in enumerate(ARMS):
                top = 120 + r * 205
                trial = lookup[(group, arm)]
                row = trial.rows[i - 9]
                require(
                    trial.rows[-1]["physics_step"] - row["physics_step"] == (8 - i) * 8,
                    "incompatible loop cadence",
                )
                if not col:
                    label(draw, (15, top + 65), ARMS[arm], 15, bold=True)
                canvas.paste(trial.image(row), (left, top))
                label(
                    draw,
                    (left, top + 160),
                    f"{row['physics_step']} 步 · {status(row)}",
                    14,
                    GOOD if row["usable"] else ERROR,
                    not row["usable"],
                )
                frames.setdefault(trial.case["id"], []).append(row["frame_id"])
        label(
            draw,
            (23, 538),
            "按各试次的首拒帧对齐。每格均取自控制器使用的原始反馈，循环慢放。",
            14,
            MUTED,
        )
        stills.append(canvas)
    path = output / "eight-stops.gif"
    with path.open("xb") as stream:
        stills[0].save(
            stream,
            format="GIF",
            save_all=True,
            append_images=stills[1:],
            duration=[550] * 8 + [1800],
            loop=0,
            disposal=2,
        )
    return {
        path.name: {"sha256": sha(path), "playback_ms": [550] * 8 + [1800], "frame_ids": frames}
    }


def main(timelines, output):
    require(not output.resolve().is_relative_to(RAW), "output overlaps frozen evidence")
    plan = pinned(ROUND / "plan.json", PLAN_SHA)
    manifest = RAW / "originals-manifest.json"
    original_files = pinned(manifest, plan["inputs_sha256"][str(manifest.relative_to(ROOT))])[
        "files"
    ]
    summary = read(timelines / "episode-timelines.public.json")
    require(summary["plan_sha256"] == PLAN_SHA, "wrong observation round")
    table = timelines / "feedback-timeline.public.json.gz"
    require(sha(table) == summary["feedback_table_sha256"], "wrong feedback table")
    with gzip.open(table, "rt") as handle:
        rows = json.load(handle)["rows"]
    trials = [
        TrialFrames(c, [r for r in rows if c["id"] == r["id"]], original_files)
        for c in summary["cases"]
    ]
    output.mkdir(parents=True, exist_ok=True)
    products = {**storyboards(trials, output), **loop(trials, output)}
    write(
        output / "figures.public.json",
        {
            "plan_sha256": PLAN_SHA,
            "timelines_sha256": sha(timelines / "episode-timelines.public.json"),
            "crop_source_xyxy_half_open": CROP,
            "native_size_px": [320, 240],
            "nearest_neighbor_zoom": SCALE,
            "overlay": (
                "Registered paper-plane projections from same-frame physics state. "
                "Short ticks are placed outside the paper."
            ),
            "figures": products,
            "sources": {t.case["id"]: t.sources for t in trials},
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timelines", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.timelines, args.output)
