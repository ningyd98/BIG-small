"""Measure inline thesis figures in Word, PDF device traces, and independently rendered pages.

Use --edition NAME DOCX PDF PNG_DIRECTORY once per edition; use --final twice for
the independently built documents for release. Requires Pillow, NumPy, ReportLab,
MuPDF's mutool, and Poppler's pdfimages, pdftoppm and pdftotext. Inputs are read-only.
"""

import argparse
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import PIL
import reportlab
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

# Bounds are fractions of the frozen source PNG, in left/top/right/bottom order.
# No region is positioned from the observed PDF content.
ROIS = {
    "2-1": {
        "cloud": (0.012, 0.09, 0.299, 0.474),
        "edge": (0.351, 0.09, 0.647, 0.474),
        "device": (0.697, 0.09, 0.992, 0.474),
        "cloud-edge arrow": (0.303, 0.241, 0.353, 0.309),
        "edge-device arrow": (0.647, 0.241, 0.699, 0.309),
        "return path": (0.215, 0.448, 0.858, 0.685),
        "run record": (0.01, 0.666, 0.467, 0.971),
        "record-evaluator arrow": (0.468, 0.786, 0.528, 0.846),
        "independent evaluator": (0.530, 0.666, 0.993, 0.971),
    },
    "3-1": {
        "axial label": (0, 0, 0.332, 0.099),
        "left label": (0.332, 0, 0.665, 0.099),
        "right label": (0.665, 0, 1, 0.099),
        "axial complete field": (0.003, 0.104, 0.328, 0.929),
        "left complete field": (0.336, 0.104, 0.660, 0.929),
        "right complete field": (0.669, 0.104, 0.994, 0.929),
        "axial interior texture": (0.048, 0.23, 0.282, 0.789),
        "left interior texture": (0.379, 0.23, 0.617, 0.789),
        "right interior texture": (0.713, 0.23, 0.951, 0.789),
        "capture label": (0, 0.931, 0.90, 1),
    },
    "3-2": {
        "coverage bars and counts": (0.099, 0.069, 0.457, 0.698),
        "coverage view names": (0.005, 0.074, 0.101, 0.698),
        "coverage ticks and units": (0.080, 0.747, 0.478, 0.992),
        "conditional error bars and values": (0.617, 0.069, 0.886, 0.698),
        "conditional error view names": (0.514, 0.074, 0.623, 0.698),
        "10 mm threshold": (0.896, 0.035, 0.932, 0.772),
        "conditional error ticks and units": (0.598, 0.747, 0.995, 0.992),
    },
    "6-1": {
        "zero candidates": (0.004, 0.018, 0.273, 0.197),
        "one candidate": (0.004, 0.218, 0.259, 0.395),
        "two candidates": (0.004, 0.422, 0.969, 0.600),
        "three candidates": (0.004, 0.627, 0.271, 0.800),
        "axis ticks and units": (0.034, 0.790, 0.992, 0.995),
    },
}

TABLE_ANCHORS = {
    "2-1": ("RGB-D观测", "相机→端侧视觉"),
    "6-1": ("旧版2s周期先导", "120个开发场景"),
    "6-2": ("探索", "18/18,4.694"),
    "6-3": ("完整执行且独立物理成功", "01、05、11、17、19"),
    "6-4": ("固定工具中心点,完整抓放", "5,013"),
    "6-5": ("移至上方", "120/835/2,040"),
    "A-1": ("20位姿抓放及模型", "final-batch-summary.json"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return "".join(unicodedata.normalize("NFKC", text).split()).replace("\u200b", "")


def doc_text(element):
    return "".join(t.text or "" for t in element.iterfind(".//{*}t"))


def capture(*args):
    return subprocess.run(args, check=True, capture_output=True).stdout


def read_word(path, frozen):
    images, tables = {}, {}
    with ZipFile(path) as doc:
        body = ET.fromstring(doc.read("word/document.xml")).find(".//{*}body")
        rel = ET.fromstring(doc.read("word/_rels/document.xml.rels"))
        targets = {x.get("Id"): x.get("Target") for x in rel}
        for i, element in enumerate(body):
            inline = element.find(".//{*}inline")
            if inline is not None:
                caption = doc_text(body[i + 1])
                key = re.match(r"图\s*([0-9]-[0-9])", caption).group(1)
                assert not doc_text(element).strip() and key not in images
                embed = next(
                    v for k, v in inline.find(".//{*}blip").attrib.items() if k.endswith("}embed")
                )
                media = "word/" + targets[embed]
                data = doc.read(media)
                assert sha(data) == frozen[key]["media_sha256"]
                with Image.open(io.BytesIO(data)) as raw:
                    alpha = raw.convert("RGBA")
                    source = Image.new("RGB", raw.size, "white")
                    source.paste(alpha, mask=alpha.getchannel("A"))
                extent = inline.find("{*}extent")
                size_pt = [int(extent.get(k)) / 12700 for k in ("cx", "cy")]
                spacing = element.find(".//{*}spacing")
                images[key] = (
                    source,
                    {
                        "media": media,
                        "docx_png_sha256": sha(data),
                        "source_px": list(source.size),
                        "word_extent_pt": size_pt,
                        "caption": caption,
                        "word_spacing": {k.split("}")[-1]: v for k, v in spacing.attrib.items()}
                        if spacing is not None
                        else {},
                    },
                )
            if element.tag.endswith("}tbl"):
                title = doc_text(body[i - 1])
                key = re.match(r"表\s*([0-9A]-[0-9])", title).group(1)
                row = element.findall("{*}tr")[1]
                values = normalized(doc_text(row))
                assert all(normalized(part) in values for part in TABLE_ANCHORS[key])
                tables[key] = title
        assert images.keys() == frozen.keys() and tables.keys() == TABLE_ANCHORS.keys()
        return images, tables, sha(doc_text(body).encode())


def image_pages(pdf):
    records = capture("pdfimages", "-list", pdf).decode().splitlines()[2:]
    return {
        (int(a[3]), int(a[4])): int(a[0]) for row in records if (a := row.split())[2] == "image"
    }


def bounding_box(points):
    x, y = zip(*points, strict=True)
    return min(x), min(y), max(x), max(y)


def transform_box(matrix, points):
    a, b, c, d, e, f = map(float, matrix.split())
    return bounding_box([(a * x + c * y + e, b * x + d * y + f) for x, y in points])


def intersection(a, b):
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def trace_image(pdf, page_number, size):
    page = ET.fromstring(
        capture("mutool", "draw", "-F", "trace", "-o", "-", pdf, str(page_number))
    ).find("page")
    page_box = tuple(map(float, page.get("mediabox").split()))
    assert page_box[:2] == (0, 0)
    clips, matches = [], []
    unit = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for e in page.iter():
        if e.tag == "pop_clip":
            clips.pop()
        elif e.tag == "clip_path":
            assert all(c.tag in ("moveto", "lineto", "closepath") for c in e)
            points = [(float(c.get("x")), float(c.get("y"))) for c in e if c.tag != "closepath"]
            # Refuse a non-rectangular clipping path instead of using its bounding box.
            assert (
                len(set(points)) == 4
                and len({x for x, _ in points}) == len({y for _, y in points}) == 2
            )
            rectangle = transform_box(e.get("transform"), points)
            clips.append(
                (
                    "clip_path",
                    rectangle,
                    intersection(clips[-1][2] if clips else page_box, rectangle),
                )
            )
        elif e.tag == "clip_image_mask":
            rectangle = transform_box(e.get("transform"), unit)
            clips.append(
                (
                    "clip_image_mask",
                    rectangle,
                    intersection(clips[-1][2] if clips else page_box, rectangle),
                )
            )
        elif e.tag == "fill_image" and tuple(int(e.get(k)) for k in ("width", "height")) == size:
            matrix = e.get("transform")
            a, b, c, d, _, _ = map(float, matrix.split())
            assert a > 0 and d > 0 and b == c == 0
            rectangle = transform_box(matrix, unit)
            matches.append(
                (
                    rectangle,
                    intersection(rectangle, clips[-1][2] if clips else page_box),
                    page_box,
                    matrix,
                    [{"type": kind, "rectangle_pt": raw} for kind, raw, _ in clips],
                )
            )
    assert len(matches) == 1 and not clips
    return matches[0]


def visible_lines(pdf):
    pages = ET.fromstring(capture("pdftotext", "-bbox", pdf, "-")).findall(".//{*}page")
    result = []
    for p in pages:
        rows = {}
        for word in p.findall(".//{*}word"):
            box = tuple(float(word.get(k)) for k in ("xMin", "yMin", "xMax", "yMax"))
            rows.setdefault(round(box[1], 1), []).append((box, word.text or ""))
        lines = []
        for _, tokens in sorted(rows.items()):
            tokens.sort(key=lambda t: t[0][0])
            box = bounding_box([p for t, _ in tokens for p in (t[:2], t[2:])])
            lines.append((normalized("".join(t for _, t in tokens)), box))
        result.append(lines)
    return result


def table_check(pages, key, title):
    token, anchors = normalized(title), [normalized(text) for text in TABLE_ANCHORS[key]]
    caption = [n for n, page in enumerate(pages, 1) if token in normalized(page)]
    assert len(caption) == 1
    data = [
        (n, i)
        for n, page in enumerate(pages, 1)
        for i, ln in enumerate(page.splitlines())
        if all(a in normalized(ln) for a in anchors)
    ]
    assert len(data) == 1
    n, line = data[0]
    has_order = caption[0] == n and token in normalized("".join(pages[n - 1].splitlines()[:line]))
    return {
        "title": title,
        "title_page": caption[0],
        "first_data_page": n,
        "first_row_anchors": list(TABLE_ANCHORS[key]),
        "ordered_same_page": has_order,
    }


def document_index(pages, headings):
    entries = []
    toc = pages[1].splitlines()
    for h in headings:
        key = normalized(h)
        hits = [
            n
            for n, page in enumerate(pages[2:], 3)
            if any(normalized(ln) == key for ln in page.splitlines())
        ]
        numbers = [
            int(m.group(1))
            for ln in toc
            if (m := re.fullmatch(re.escape(key) + r"\.+(\d+)", normalized(ln)))
        ]
        assert len(hits) == len(numbers) == 1 and hits == numbers
        entries.append({"heading": h, "toc_page": numbers[0], "observed_page": hits[0]})
    references = pages[entries[-2]["observed_page"] - 1 : entries[-1]["observed_page"] - 1]
    ids = [int(i) for page in references for i in re.findall(r"(?m)^\s*\[(\d+)\]", page)]
    assert ids == list(range(1, 15))
    return entries, ids


def luminance(image):
    return np.asarray(
        image.convert("L").filter(ImageFilter.GaussianBlur(radius=1)), dtype=np.float64
    )


def correlation(ref, obs, indices):
    x, y = ref[indices], obs[indices]
    if len(x) < 20:
        raise ValueError("ROI has fewer than 20 source foreground pixels")
    a, b = x - x.mean(), y - y.mean()
    denom = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum()) / denom if denom else 0.0


def source_only_raster(source, page_box, box, dpi):
    # The reference page consists solely of the original lossless RGB pixels at
    # their traced position. It has no text, layout clips, or target PDF objects.
    # Use the page renderer's own sampling kernel on both sides so a 1 px dashed
    # line or a small label is not scored on differences between two resamplers.
    pdf = io.BytesIO()
    canvas = Canvas(pdf, pagesize=page_box[2:], invariant=True)
    x0, y0, x1, y1 = box
    canvas.drawImage(ImageReader(source), x0, page_box[3] - y1, x1 - x0, y1 - y0)
    canvas.showPage()
    canvas.save()
    png = subprocess.run(
        ["pdftoppm", "-singlefile", "-r", str(dpi), "-png", "-"],
        input=pdf.getvalue(),
        capture_output=True,
        check=True,
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGB")


def pixel_scores(source, page, page_box, box, dpi, regions, *, pillow_diagnostic=False):
    scale = dpi / 72
    px = [v * scale for v in box]
    left, top, right, bottom = (
        math.floor(px[0]),
        math.floor(px[1]),
        math.ceil(px[2]),
        math.ceil(px[3]),
    )
    width, height = right - left, bottom - top
    sx, sy = source.width / (px[2] - px[0]), source.height / (px[3] - px[1])
    base = (sx, 0, sx * (left - px[0]), 0, sy, sy * (top - px[1]))
    if pillow_diagnostic:
        ref_im = source.transform(
            (width, height),
            Image.Transform.AFFINE,
            base,
            Image.Resampling.BICUBIC,
            fillcolor="white",
        )
    else:
        ref_page = source_only_raster(source, page_box, box, dpi)
        assert ref_page.size == page.size
        ref_im = ref_page.crop((left, top, right, bottom))
    ref = luminance(ref_im)
    foreground = ref < 247
    # Choose a single (x,y) registration on the whole figure; ROIs inherit it.
    # An outer margin makes smoothing invariant under cropping the observed page window.
    field = luminance(page.crop((left - 4, top - 4, right + 4, bottom + 4)))
    options = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            obs = field[4 + dy : 4 + dy + height, 4 + dx : 4 + dx + width]
            options.append((correlation(ref, obs, foreground), -abs(dx) - abs(dy), dx, dy))
    _, _, dx, dy = max(options)
    obs = field[4 + dy : 4 + dy + height, 4 + dx : 4 + dx + width]
    actual = page.crop((left + dx, top + dy, right + dx, bottom + dy))
    scores = {}
    for name, region in {"whole_image": (0, 0, 1, 1), **regions}.items():
        x0, y0, x1, y1 = region
        x_start, y_start = round(x0 * width), round(y0 * height)
        x_end, y_end = round(x1 * width), round(y1 * height)
        area = np.s_[y_start:y_end, x_start:x_end]
        mask = foreground[area]
        scores[name] = {
            "source_rect_px": [
                round(x0 * source.width),
                round(y0 * source.height),
                round(x1 * source.width),
                round(y1 * source.height),
            ],
            "registered_rect_px": [x_start, y_start, x_end, y_end],
            "source_foreground_px": int(mask.sum()),
            "gray_pearson": round(correlation(ref[area], obs[area], mask), 6),
        }
    return (
        {
            "page_from_pdf_scale_px_per_pt": scale,
            "unregistered_page_crop_px": [left, top, right, bottom],
            "source_from_crop_affine": base,
            "reference_projection_rgb_sha256": sha(ref_im.tobytes()),
            "registered_translation_px": [dx, dy],
            "regions": scores,
        },
        ref_im,
        actual,
    )


def contact_sheet(source, actual, page, box, dest):
    # Save an actual page crop including the caption as well as the unaltered source.
    source = source.convert("RGB")
    actual = actual.convert("RGB")
    detail = page.crop(box).convert("RGB")
    width = max(source.width, actual.width, detail.width)
    sheet = Image.new(
        "RGB", (width + 12, 3 * 22 + source.height + actual.height + detail.height), "white"
    )
    label = ImageDraw.Draw(sheet)
    y = 0
    for title, im in [
        ("Projected source", source),
        ("Observed full page raster", actual),
        ("Observed figure/caption neighborhood", detail),
    ]:
        label.text((5, y + 3), title, fill="#162d41")
        y += 22
        sheet.paste(im, (5, y))
        y += im.height
    sheet.save(dest)


def measure_edition(docx, pdf, pngs, frozen, headings, evidence):
    images, tables, word_text_hash = read_word(docx, frozen)
    pages = capture("pdftotext", "-layout", pdf, "-").decode().split("\f")
    if not pages[-1].strip():
        pages.pop()
    lines = visible_lines(pdf)
    page_ids = image_pages(pdf)
    assert len(page_ids) == len(images) and len(pages) == len(lines)
    manifest = []
    with Image.open(pngs / "page-1.png") as first:
        dpi = round(first.info["dpi"][0])
    with tempfile.TemporaryDirectory(prefix="pdf-direct-", dir=evidence) as scratch:
        prefix = Path(scratch) / "page"
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", pdf, prefix], check=True, capture_output=True
        )
        direct = {int(path.stem.split("-")[-1]): path for path in Path(scratch).glob("page-*.png")}
        assert len(direct) == len(pages)
        for i in range(1, len(pages) + 1):
            path = pngs / f"page-{i}.png"
            with Image.open(path) as im, Image.open(direct[i]) as actual_pdf:
                rgb = sha(im.convert("RGB").tobytes())
                pdf_rgb = sha(actual_pdf.convert("RGB").tobytes())
                manifest.append(
                    {
                        "page": i,
                        "size_px": list(im.size),
                        "png_sha256": sha(path.read_bytes()),
                        "rgb_sha256": rgb,
                        "direct_pdf_rgb_sha256": pdf_rgb,
                        "docx_and_direct_pdf_pixels_equal": rgb == pdf_rgb,
                    }
                )
    assert len(list(pngs.glob("page-*.png"))) == len(pages)
    results = {}
    for key, (source, metadata) in images.items():
        n = page_ids[source.size]
        box, visible, page_box, matrix, clips = trace_image(pdf, n, source.size)
        w, h = box[2] - box[0], box[3] - box[1]
        cw, ch = visible[2] - visible[0], visible[3] - visible[1]
        loss = [visible[0] - box[0], visible[1] - box[1], box[2] - visible[2], box[3] - visible[3]]
        caption = normalized(metadata["caption"])
        caps = [(text, r) for text, r in lines[n - 1] if text == caption]
        assert len(caps) == 1
        cap_box = caps[0][1]
        gap = cap_box[1] - box[3]
        overlaps = [
            text
            for text, r in lines[n - 1]
            if r[0] < box[2] - 1 and r[2] > box[0] + 1 and r[1] < box[3] - 1 and r[3] > box[1] + 1
        ]
        with Image.open(pngs / f"page-{n}.png") as pg:
            dpi = round(pg.info["dpi"][0])
            assert (
                abs(pg.width - page_box[2] * dpi / 72) <= 1
                and abs(pg.height - page_box[3] * dpi / 72) <= 1
            )
            pixel, expected, observed = pixel_scores(
                source, pg.convert("RGB"), page_box, box, dpi, ROIS[key]
            )
            diagnostic, _, _ = pixel_scores(
                source, pg.convert("RGB"), page_box, box, dpi, ROIS[key], pillow_diagnostic=True
            )
            x0, y0, x1, y1 = pixel["unregistered_page_crop_px"]
            contact = evidence / f"figure-{key}.png"
            contact_sheet(
                expected,
                observed,
                pg,
                (x0 - 12, y0 - 12, x1 + 12, math.ceil(cap_box[3] * dpi / 72) + 12),
                contact,
            )
        best_min = min(s["gray_pearson"] for s in pixel["regions"].values())
        correct_geometry = cw / w >= 0.99 and ch / h >= 0.99 and max(loss) <= 1
        raster_ok = best_min >= 0.90
        expected_size = (
            abs(h - metadata["word_extent_pt"][1]) <= 0.1
            and abs(w - metadata["word_extent_pt"][0]) <= 0.1
        )
        results[key] = {
            **metadata,
            "page": n,
            "dpi": dpi,
            "image_matrix_trace": matrix,
            "active_clip_stack": clips,
            "page_box_pt": page_box,
            "intended_box_pt": box,
            "effective_box_pt": visible,
            "intended_size_pt": [w, h],
            "effective_size_pt": [cw, ch],
            "coverage_x_y": [cw / w, ch / h],
            "missing_ltrb_pt": loss,
            "caption_box_pt": cap_box,
            "caption_gap_pt": gap,
            "body_lines_over_full_rect": len(overlaps),
            "full_caption_same_page": True,
            "geometry_pass": correct_geometry,
            "minimum_gray_pearson": best_min,
            "raster_pass": raster_ok,
            "pass": bool(
                correct_geometry and raster_ok and gap >= 0 and not overlaps and expected_size
            ),
            "evidence_sha256": sha(contact.read_bytes()),
            "alternative_pillow_bicubic": {
                "registered_translation_px": diagnostic["registered_translation_px"],
                "region_gray_pearson": {
                    name: value["gray_pearson"] for name, value in diagnostic["regions"].items()
                },
            },
            **pixel,
        }
    toc, refs = document_index(pages, headings)
    cover_items = [
        "面向边缘智能场景的小型机械臂云边协同控制系统的设计",
        "工程硕士学位论文",
        "研究阶段稿",
        "宁业栋",
        "集成电路工程",
    ]
    assert all(t in normalized(pages[0]) for t in cover_items)
    return {
        "cover_items": cover_items,
        "docx_sha256": sha(docx.read_bytes()),
        "pdf_sha256": sha(pdf.read_bytes()),
        "word_visible_text_sha256": word_text_hash,
        "all_page_geometry_and_rasters": manifest,
        "page_count": len(pages),
        "toc_and_actual_starts": toc,
        "reference_numbers": refs,
        "tables": {k: table_check(pages, k, t) for k, t in tables.items()},
        "figures": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--edition",
        required=True,
        nargs=4,
        action="append",
        metavar=("LABEL", "DOCX", "PDF", "PAGES"),
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--final", required=True, action="append")
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("plan.json"))
    parser.add_argument("--manuscript", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    frozen = {fig["id"]: fig for fig in plan["frozen_figures"]}
    manuscript = args.manuscript.read_bytes()
    assert sha(manuscript) == next(
        value for key, value in plan["inputs_sha256"].items() if key.endswith("/manuscript.md")
    )
    headings = re.findall(r"(?m)^# (.+)$", manuscript.decode())
    editions = {}
    for label, docx, pdf, pages in args.edition:
        assert Path(label).name == label and label not in editions
        evidence = args.evidence_dir / label
        evidence.mkdir(exist_ok=True, parents=True)
        editions[label] = measure_edition(
            Path(docx), Path(pdf), Path(pages), frozen, headings, evidence
        )
    assert len(args.final) == 2
    old = editions[args.baseline]
    a, b = (editions[k] for k in args.final)
    original_detected = all(
        not f["raster_pass"] and not f["geometry_pass"] for f in old["figures"].values()
    )
    figures_ok = all(f["pass"] for edition in (a, b) for f in edition["figures"].values())
    tables_ok = all(
        f["ordered_same_page"] for edition in (a, b) for f in edition["tables"].values()
    )
    pdf_matches_docx = all(
        p["docx_and_direct_pdf_pixels_equal"]
        for edition in editions.values()
        for p in edition["all_page_geometry_and_rasters"]
    )
    text_equal = len({edition["word_visible_text_sha256"] for edition in editions.values()}) == 1
    repeatable = (
        a["figures"] == b["figures"]
        and a["tables"] == b["tables"]
        and a["toc_and_actual_starts"] == b["toc_and_actual_starts"]
        and a["all_page_geometry_and_rasters"] == b["all_page_geometry_and_rasters"]
    )
    result = {
        "round": plan["round"],
        "plan_json_sha256": sha(args.plan.read_bytes()),
        "manuscript_sha256": sha(manuscript),
        "verifier_sha256": sha(Path(__file__).read_bytes()),
        "thresholds": {
            "visible_width_and_height": 0.99,
            "max_missing_each_side_pt": 1,
            "nonwhite_gray_pearson": 0.9,
        },
        "metric": (
            "A separately created unclipped source-only PDF contains the frozen RGB PNG at the "
            "traced affine and page size. The same Poppler renderer resamples both the source and "
            "the target page. Both grayscale images use Gaussian radius 1 px. Pearson uses only "
            "source gray <247. A single translation is chosen on the whole image among the 25 "
            "integer offsets in [-2,2] per axis and fixed for every named ROI. Constant observed "
            "content scores zero. The supplementary Pillow bicubic diagnostic uses the same "
            "threshold, definition and regions with a different reference resampling kernel."
        ),
        "environment": {
            "python": sys.version.split()[0],
            "pillow": PIL.__version__,
            "numpy": np.__version__,
            "reportlab": reportlab.Version,
            "mutool": subprocess.run(
                ["mutool", "-v"], capture_output=True, text=True
            ).stderr.strip(),
            "pdftoppm": subprocess.run(
                ["pdftoppm", "-v"], capture_output=True, text=True
            ).stderr.splitlines()[0],
        },
        "coordinates": (
            "Top-left origin, L,T,R,B. Source-region pixel coordinates and 150 dpi crop-local "
            "coordinates are both reported."
        ),
        "editions": editions,
        "baseline": args.baseline,
        "final_editions": args.final,
        "old_damage_detected_in_all": original_detected,
        "final_figures_pass": figures_ok,
        "final_tables_pass": tables_ok,
        "all_docx_visible_text_equal": text_equal,
        "final_rendered_pages_and_results_identical": repeatable,
        "all_direct_pdf_and_word_page_pixels_equal": pdf_matches_docx,
        "pass": bool(
            original_detected
            and figures_ok
            and tables_ok
            and text_equal
            and repeatable
            and pdf_matches_docx
        ),
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
