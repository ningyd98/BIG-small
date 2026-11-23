"Reconstruct the defense playback from authenticated, unmodified development-01 camera captures."

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, __version__

ROOT = Path(__file__).resolve().parents[2]
ROUND = "round-graduation-pickplace-playback-20261123"
PLAN_DIR = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds" / ROUND
PLAN_SHA = "d27ee253162f07d0a0e098b507fe9d9242ce449a4a1f6c369ddabf35c9696dcc"
PLAN_MD_SHA = "b4b3e3694b87fc9dc7b3d12a3fe834afe23e8dc86e958d23dc4ff10e3086d57b"
RGB_INVENTORY_SHA = "ec1cfdaa37aa44b2917649fbe8e237c7da5d297616aa8802a0037f1b3c24bf4b"
EPISODE = "8a7766ac134b42d6b9c359110c5694c1"
TRIAL = "development-01"
ACTION_TITLES = (
    "移至目标上方",
    "下降接近",
    "闭合夹爪抓取",
    "抬升方块",
    "持物搬运",
    "下降放置",
    "打开夹爪释放",
    "垂直退避",
    "后续退避",
)
SIZE = (1016, 662)
CAMERA = (24, 103, 664, 583)
FONTS = [
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]
BG = "#f4f4ee"
INK = "#152923"
MUTED = "#4c6357"
LINE = "#bdc9bd"
ACCENT = "#146347"
PALE = "#dce9dc"
WHITE = "#ffffff"
GOLD = "#e9bb68"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def font(size, bold=False):
    return ImageFont.truetype(str(FONTS[int(bold)]), size, index=2)


def plan_and_trial(batch):
    file = PLAN_DIR / "plan.json"
    require(
        sha(file) == PLAN_SHA and sha(PLAN_DIR / "plan.md") == PLAN_MD_SHA, "changed Astra plan"
    )
    plan = read(file)
    summary = None
    for row in plan["inputs"]:
        p = Path(row["path"])
        if p.is_absolute():
            original_batch = next(parent for parent in p.parents if parent.name == batch.name)
            p = batch / p.relative_to(original_batch)
        else:
            p = ROOT / p
        require(
            p.stat().st_size == row["bytes"] and sha(p) == row["sha256"], f"input changed: {p.name}"
        )
        if p.name == "final-batch-summary.json":
            summary = read(p)
    require(summary is not None, "missing batch summary")
    freeze = read(batch / "freeze.json")
    cohort = summary["development_fresh"]
    expected = (
        cohort["assigned"],
        cohort["component_complete"]["successes"],
        cohort["physical_success"]["successes"],
    )
    require(expected == (20, 5, 5), "development denominator changed")
    rows = [r for r in summary["trials"] if r["cohort"] == "FRESH_INDEPENDENT"]
    assigned = freeze["allocation"]["development"]
    require(
        [r["assignment_id"] for r in rows] == [r["assignment_id"] for r in assigned]
        and len(rows) == 20,
        "allocation order mismatch",
    )
    trial = rows[0]
    require(
        trial["assignment_id"] == TRIAL
        and trial["audit_route"] == "STRICT"
        and trial["component_completed"]
        and trial["independent_physical_success"],
        "first assigned trial does not meet the frozen selection",
    )
    root = batch / "native" / TRIAL
    audit_file = batch / "receipts" / f"{TRIAL}.audit.json"
    audit = read(audit_file)
    ep = read(root / "component/episode.json")
    config = read(root / "scene-assignment.json")
    require(
        audit["episode_id"] == ep["episode_id"] == EPISODE
        and audit["job_id"] == "job-db7111f090e84abf"
        and audit["audit_status"] == "VERIFIED"
        and audit["physical"]["success"]
        and config["seed"] == assigned[0]["pose_seed"] == 1657582353,
        "success, identity or seed mismatch",
    )
    require(
        trial["independent_audit_sha256"] == sha(audit_file)
        and trial["archive_manifest_sha256"]
        == audit["manifest_sha256"]
        == sha(root / "evidence-manifest.json"),
        "audit or manifest binding changed",
    )
    for phase in ("begin", "end"):
        fn = batch / "receipts" / f"{TRIAL}.{phase}.json"
        receipt = read(fn)
        require(
            receipt["id"] == TRIAL
            and receipt["seed"] == config["seed"]
            and trial[phase + "_sha256"] == audit[phase + "_sha256"] == sha(fn)
            and receipt["freeze_sha256"] == sha(batch / "freeze.json"),
            f"{phase} receipt mismatch",
        )
    fields = ("step_id", "skill", "start_step", "controller_return_step")
    for index, action in enumerate(plan["actions"]):
        require(
            all(action[k] == audit["actions"][index][k] == ep["actions"][index][k] for k in fields),
            "physical action order or boundary changed",
        )
    return plan, root, audit, trial


def step_at(time, times, steps):
    # The bound is far below the 1/240 s interval. Ambiguous matches abort.
    lo = bisect.bisect_left(times, time - 1e-8)
    hi = bisect.bisect_right(times, time + 1e-8)
    require(hi == lo + 1, "no unique sampled physical time")
    return steps[lo]


def capture_kind(relative, actions, step):
    parts = relative.parts
    if parts[0] in {"before", "after"}:
        first = parts[0] == "before"
        return dict(
            role=parts[0],
            label="初始观测" if first else "最终观测",
            action_index=None,
            sample_index=None,
            view_variant=None,
        )
    group = parts[2]
    if parts[1] == "servo-frames":
        index = next(i for i, a in enumerate(actions) if a["step_id"] == group)
        a = actions[index]
        name = parts[3]
        require(
            a["start_step"] <= step <= a["controller_return_step"], "servo frame outside its action"
        )
        if name == "reference":
            return dict(
                role="reference",
                label="伺服参考",
                action_index=index,
                sample_index=None,
                view_variant=None,
            )
        m = re.fullmatch(r"sample-(\d+)(?:-view-(\d+))?", name)
        require(m, "invalid servo sample name")
        view = int(m[2]) if m[2] else 0
        return dict(
            role="servo",
            label="伺服采样" if not view else "伺服采样 · 补充视角",
            action_index=index,
            sample_index=int(m[1]),
            view_variant=view,
        )
    if group == "post-cloud":
        return dict(
            role="post-cloud",
            label="云规划返回后",
            action_index=None,
            sample_index=None,
            view_variant=None,
        )
    if group == "terminal-stability":
        return dict(
            role=group,
            label="末态稳定观测",
            action_index=None,
            sample_index=None,
            view_variant=None,
        )
    m = re.fullmatch(r"(pre|post)-(\d+)-([a-z_-]+)", group)
    require(m, "unknown stage checkpoint")
    index = int(m[2])
    a = actions[index]
    if m[3] == "camera-positioned":
        require(index == 4 and step == a["start_step"], "camera positioning boundary")
        role, label = "camera-positioned", "搬运前相机换位"
    else:
        require(m[3].upper() == a["skill"], "checkpoint skill mismatch")
        if m[1] == "pre":
            require(step == a["start_step"], "pre checkpoint outside dispatch step")
            role, label = "pre", "动作前关键帧"
        else:
            next_start = (
                actions[index + 1]["start_step"] if index + 1 < len(actions) else float("inf")
            )
            require(
                a["controller_return_step"] <= step <= next_start, "post checkpoint outside settle"
            )
            role, label = "post", "动作后关键帧"
    return dict(role=role, label=label, action_index=index, sample_index=None, view_variant=None)


def inventory(root, actions):
    manifest = read(root / "evidence-manifest.json")["files"]
    catalog = {item["path"]: item for item in manifest}
    require(len(catalog) == len(manifest), "duplicate manifest path")
    samples = read(root / "component/physical-evidence.json")
    times = [s["sim_time_s"] for s in samples]
    steps = [s["physics_step"] for s in samples]
    require(
        len(samples) == 7769
        and steps == list(range(steps[0], steps[-1] + 1))
        and all(s["episode_id"] == EPISODE for s in samples)
        and all(b > a for a, b in zip(times, times[1:], strict=False)),
        "physical trace mismatch",
    )
    locations = sorted(
        [
            root / "before/observation.json",
            root / "after/observation.json",
            *(root / "component/frames").rglob("observation.json"),
            *(root / "component/servo-frames").rglob("observation.json"),
        ]
    )
    digest = hashlib.sha256()
    frames = []
    for metadata in locations:
        img = metadata.with_name("rgb.png")
        for p in (metadata, img):
            rel = p.relative_to(root).as_posix()
            record = catalog[rel]
            checksum = sha(p)
            require(
                p.stat().st_size == record["bytes"] and record["sha256"] == checksum,
                f"manifest mismatch: {rel}",
            )
            digest.update(f"{rel}\t{checksum}\n".encode())
        raw = read(metadata)
        path = metadata.relative_to(root)
        require(
            raw["rgb_sha256"] == checksum
            and raw["episode_id"] == EPISODE
            and (raw["width"], raw["height"], raw["source"]) == (320, 240, "mujoco_camera"),
            f"foreign camera metadata: {path}",
        )
        with Image.open(img) as source:
            require(
                source.size == (320, 240) and source.mode == "RGB", "original RGB format changed"
            )
            source.verify()
        step = step_at(raw["sim_time_s"], times, steps)
        kind = capture_kind(path, actions, step)
        frames.append(
            {
                **kind,
                "kind": "camera",
                "frame_id": raw["frame_id"],
                "observation_id": raw["observation_id"],
                "source_checksum_sha256": raw["checksum_sha256"],
                "metadata": path.as_posix(),
                "metadata_sha256": catalog[path.as_posix()]["sha256"],
                "rgb": img.relative_to(root).as_posix(),
                "rgb_sha256": checksum,
                "step": step,
                "sim_time_s": raw["sim_time_s"],
                "captured_at": raw["captured_at"],
            }
        )
    require(
        len(frames) == 820 and digest.hexdigest() == RGB_INVENTORY_SHA,
        "candidate inventory changed",
    )
    counts = Counter(f["role"] for f in frames)
    require(counts["servo"] == 790 and counts["reference"] == 7, "servo capture count changed")
    return frames, dict(zip(steps, times, strict=True))


def select_frames(frames, actions, physics_time):
    servo = defaultdict(list)
    selected = []
    for f in frames:
        if f["role"] == "servo":
            servo[f["action_index"]].append(f)
        elif f["role"] != "reference":
            selected.append(f)
    require(len(selected) == 23 and len(servo) == 7, "stage frame allocation changed")
    for seq in servo.values():
        seq.sort(key=lambda f: (f["sample_index"], f["view_variant"], f["captured_at"]))
        n = min(12, len(seq))
        indices = [round(k * (len(seq) - 1) / (n - 1)) for k in range(n)] if n > 1 else [0]
        for i in indices:
            selected.append(seq[i] | {"position_in_numeric_series": i, "series_size": len(seq)})
    selected.sort(key=lambda f: (f["step"], datetime.fromisoformat(f["captured_at"])))
    unique = []
    ids = {}
    aliases = []
    for f in selected:
        previous = ids.get(f["frame_id"])
        if previous:
            require(
                previous["source_checksum_sha256"] == f["source_checksum_sha256"]
                and previous["rgb_sha256"] == f["rgb_sha256"]
                and previous["step"] == f["step"],
                "reused frame identity with conflicting bytes",
            )
            aliases.append({"frame_id": f["frame_id"], "metadata": f["metadata"]})
            continue
        ids[f["frame_id"]] = f
        unique.append(f)
    cards = []
    for i in (2, 6):
        a = actions[i]
        pre = next(f for f in unique if f["role"] == "pre" and f["action_index"] == i)
        post = next(f for f in unique if f["role"] == "post" and f["action_index"] == i)
        require(
            not any(f["action_index"] == i and f["role"] in {"servo", "reference"} for f in frames),
            "unexpected in-action images in registered sampling gap",
        )
        cards.append(
            {
                "kind": "sampling_gap",
                "action_index": i,
                "role": "no_servo_archive",
                "label": "过程相机采样间隔",
                "step": a["controller_return_step"],
                "sim_time_s": physics_time[a["controller_return_step"]],
                "start_step": a["start_step"],
                "start_sim_s": physics_time[a["start_step"]],
                "pre_step": pre["step"],
                "post_step": post["step"],
                "pre_time_s": pre["sim_time_s"],
                "post_time_s": post["sim_time_s"],
                "pre_frame_id": pre["frame_id"],
                "post_frame_id": post["frame_id"],
                "pre_metadata": pre["metadata"],
                "post_metadata": post["metadata"],
                "duration_ms": 3000,
            }
        )
    for f in unique:
        role = f["role"]
        f["duration_ms"] = {
            "servo": 120,
            "before": 1250,
            "after": 1900,
            "camera-positioned": 800,
            "terminal-stability": 900,
        }.get(role, 470)
    all_rows = sorted(unique + cards, key=lambda f: (f["step"], f.get("captured_at", "")))
    for i, f in enumerate(all_rows):
        f["gif_index"] = i
        index = f["action_index"]
        f["action_id"] = actions[index]["step_id"] if index is not None else None
        f["skill"] = actions[index]["skill"] if index is not None else None
    return all_rows, aliases


def make_palette(root, rows):
    camera = [f for f in rows if f["kind"] == "camera"]
    sheet = Image.new("RGB", (12 * 160, ((len(camera) + 11) // 12) * 120))
    for i, f in enumerate(camera):
        with Image.open(root / f["rgb"]) as source:
            sheet.paste(
                source.resize((160, 120), Image.Resampling.NEAREST),
                ((i % 12) * 160, (i // 12) * 120),
            )
    colors = sheet.quantize(colors=207, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    values = colors.getpalette()[: 207 * 3]

    def rgb(hexcolor):
        return tuple(bytes.fromhex(hexcolor.lstrip("#")))

    for color in (BG, INK, MUTED, LINE, ACCENT, PALE, WHITE, GOLD):
        values.extend(rgb(color))
    for start, end in ((BG, INK), (BG, ACCENT), (INK, WHITE), (INK, GOLD), (PALE, ACCENT)):
        for n in range(1, 9):
            values.extend(
                round(a + (b - a) * n / 9) for a, b in zip(rgb(start), rgb(end), strict=True)
            )
    values += [0] * (768 - len(values))
    palette = Image.new("P", (1, 1))
    palette.putpalette(values)
    return palette


def render(root, row, fonts):
    canvas = Image.new("RGB", SIZE, BG)
    d = ImageDraw.Draw(canvas)

    def txt(pos, value, size, ink=INK, bold=False):
        d.text(pos, value, font=fonts[size, bold], fill=ink, anchor="lt")

    index = row["action_index"]
    role = row["role"]
    late = role in {"after", "terminal-stability"}
    txt((24, 20), "桌面机械臂抓放", 37, bold=True)
    txt((25, 70), "归档 RGB 相机画面", 18, MUTED)
    txt((695, 27), "开发位姿 01", 25, bold=True)
    txt((695, 70), "S01 /   MuJoCo 仿真", 18, MUTED)
    if row["kind"] == "camera":
        with Image.open(root / row["rgb"]) as source:
            canvas.paste(source.resize((640, 480), Image.Resampling.NEAREST), CAMERA[:2])
    else:
        d.rectangle(CAMERA, fill=INK)
        txt((53, 149), "相机采样间隔", 24, GOLD, True)
        txt((52, 201), ACTION_TITLES[index], 43, WHITE, True)
        txt((53, 286), "该动作没有保存过程相机图像。", 23, WHITE)
        txt((53, 330), "控制器执行", 17, GOLD)
        txt(
            (53, 361),
            f"第 {row['start_step']:,}–{row['step']:,} 步   "
            f"{row['start_sim_s']:.3f}–{row['sim_time_s']:.3f} s",
            22,
            WHITE,
        )
        txt((53, 421), "前后关键帧实际采集", 17, GOLD)
        txt(
            (53, 453),
            f"第 {row['pre_step']:,}–{row['post_step']:,} 步   "
            f"{row['pre_time_s']:.3f}–{row['post_time_s']:.3f} s",
            22,
            WHITE,
        )
        txt((53, 527), "下一帧为实际记录的动作后画面。", 18, WHITE)
    d.line((682, 103, 682, 583), fill=LINE, width=1)
    txt((703, 112), "动作顺序", 19, MUTED, True)
    for i, title in enumerate(ACTION_TITLES):
        y = 157 + 37 * i
        if i == index:
            d.rounded_rectangle((696, y - 6, 990, y + 25), radius=5, fill=PALE)
        tint = (
            ACCENT if i == index else (MUTED if late or (index is not None and i < index) else INK)
        )
        txt((709, y + 1), f"{i + 1:02d}", 16, tint)
        txt((751, y), title, 19, tint, i == index)
    d.line((702, 501, 989, 501), fill=LINE)
    txt((703, 520), row["label"], 19, ACCENT, True)
    txt((703, 552), f"{row['sim_time_s']:.3f} s  /  第 {row['step']:,} 步", 17, INK)
    d.line((24, 602, 990, 602), fill=LINE)
    txt((24, 623), "真实归档抽帧，非实时录像", 21, INK, True)
    txt((444, 626), "本批 20 个新开发位姿　组件成功 5/20　独立物理成功 5/20", 18, MUTED)
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--batch", type=Path, required=True, help="original p1-live-development-20261119 archive"
    )
    ap.add_argument("--gif", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    require(not args.gif.exists() and not args.manifest.exists(), "choose unused deliverable paths")
    plan, root, audit, trial = plan_and_trial(args.batch.resolve())
    actions = plan["actions"]
    candidates, clock = inventory(root, actions)
    rows, duplicates = select_frames(candidates, actions, clock)
    palette = make_palette(root, rows)
    fonts = {
        (s, b): font(s, b)
        for s in (16, 17, 18, 19, 21, 22, 23, 24, 25, 37, 43)
        for b in (False, True)
    }
    output = []
    for row in rows:
        im = render(root, row, fonts).quantize(palette=palette, dither=Image.Dither.NONE)
        output.append(im)
    with args.gif.open("xb") as stream:
        output[0].save(
            stream,
            format="GIF",
            save_all=True,
            append_images=output[1:],
            duration=[r["duration_ms"] for r in rows],
            loop=0,
            optimize=False,
            disposal=1,
        )
    cropped = 0
    with Image.open(args.gif) as gif:
        require(gif.size == SIZE and gif.n_frames == len(rows), "decoded GIF size/count mismatch")
        for index, (row, expected) in enumerate(zip(rows, output, strict=True)):
            gif.seek(index)
            require(gif.info["duration"] == row["duration_ms"], "GIF dwell time mismatch")
            actual = gif.convert("RGB")
            require(
                ImageChops.difference(actual, expected.convert("RGB")).getbbox() is None,
                f"decoded GIF differs from composed frame {index}",
            )
            if row["kind"] == "camera":
                with Image.open(root / row["rgb"]) as source:
                    roi = (
                        source.resize((640, 480), Image.Resampling.NEAREST)
                        .quantize(palette=palette, dither=Image.Dither.NONE)
                        .convert("RGB")
                    )
                require(
                    ImageChops.difference(actual.crop(CAMERA), roi).getbbox() is None,
                    f"camera pixel mismatch in frame {index}",
                )
                cropped += 1
    manifest = {
        "schema": "graduation.archived-camera-playback.v1",
        "trial": TRIAL,
        "episode_id": EPISODE,
        "seed": 1657582353,
        "job_id": audit["job_id"],
        "trial_condition": trial["condition"],
        "batch": {"assigned": 20, "component_success": 5, "independent_physical_success": 5},
        "scope": "One successful development simulation. No new physics, model or hardware calls.",
        "physical_outcome": {
            k: audit["physical"][k]
            for k in ("status", "evidence_samples", "measured_lift_m", "hold_s", "placed_stable_s")
        },
        "frozen_plan_sha256": PLAN_SHA,
        "original_audit_sha256": trial["independent_audit_sha256"],
        "archive_manifest_sha256": trial["archive_manifest_sha256"],
        "candidate_pairs": len(candidates),
        "all_candidate_rgb_and_metadata_sha256": RGB_INVENTORY_SHA,
        "source_files": 2 * len(candidates),
        "candidate_roles": dict(Counter(f["role"] for f in candidates)),
        "actions": actions,
        "camera_frames": cropped,
        "gap_cards": len(rows) - cropped,
        "output_frames": len(rows),
        "duplicate_aliases": duplicates,
        "timebase": (
            "Unique matching time in original per-step physical evidence. At the same step, "
            "archive capture time orders images. Card display duration is independent of "
            "physical time."
        ),
        "render": {
            "size": SIZE,
            "camera_rect_xyxy": CAMERA,
            "scale": "2x nearest-neighbor, full frame",
            "quantization": "shared palette, no dithering",
            "pillow_version": __version__,
            "font_sha256": {path.name: sha(path) for path in FONTS},
            "script_sha256": sha(Path(__file__)),
        },
        "decoded_sha256": sha(args.gif),
        "filename": args.gif.name,
        "total_display_ms": sum(r["duration_ms"] for r in rows),
        "rows": rows,
    }
    with args.manifest.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in (
                    "camera_frames",
                    "gap_cards",
                    "output_frames",
                    "total_display_ms",
                    "decoded_sha256",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
