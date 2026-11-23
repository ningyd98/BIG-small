"""Compare the actual pages, figures and tables in two independently built theses."""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

BASELINE = (
    Path(__file__).resolve().parent.parent / "round-graduation-manuscript-figure-layout-20261123"
)
NAME = "云边协同机械臂毕业设计"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_margins(pdf):
    layout = subprocess.check_output(["pdftotext", "-bbox", pdf, "-"])
    pages = []
    for page in ElementTree.fromstring(layout).findall(".//{*}page"):
        words = page.findall(".//{*}word")
        box = [
            min(float(w.get("xMin")) for w in words),
            min(float(w.get("yMin")) for w in words),
            max(float(w.get("xMax")) for w in words),
            max(float(w.get("yMax")) for w in words),
        ]
        width, height = float(page.get("width")), float(page.get("height"))
        if box[0] <= 12 or box[1] <= 9 or box[2] >= width - 12 or box[3] >= height - 9:
            raise ValueError(
                f"Printed words extend outside the inspected margins on page {len(pages) + 1}"
            )
        pages.append([round(value, 2) for value in box])
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--edition",
        type=Path,
        nargs=2,
        action="append",
        required=True,
        metavar=("WORD_PDF_DIR", "REOPENED_WORD_RASTER_DIR"),
    )
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.edition) != 2 or args.edition[0] == args.edition[1]:
        parser.error("Pass two independent document builds.")
    prior = json.loads((BASELINE / "verification.public.json").read_bytes())
    checker = BASELINE / "verify_layout.py"
    if sha(checker) != prior["verifier_sha256"] or not prior["old_damage_detected_in_all"]:
        raise ValueError("The frozen figure-verification control differs from its release.")
    spec = importlib.util.spec_from_file_location("graduation_figure_verifier", checker)
    checker_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker_module)
    plan = json.loads((BASELINE / "plan.json").read_bytes())
    frozen = {figure["id"]: figure for figure in plan["frozen_figures"]}
    headings = re.findall(r"(?m)^# (.+)$", args.source.read_text())
    builds = []
    for idx, (folder, pages) in enumerate(args.edition, 1):
        evidence = args.evidence_dir / f"edition-{idx}"
        evidence.mkdir(parents=True, exist_ok=True)
        pdf, word = folder / (NAME + ".pdf"), folder / (NAME + ".docx")
        run = checker_module.measure_edition(word, pdf, pages, frozen, headings, evidence)
        run["text_bounding_boxes_pt"] = page_margins(pdf)
        builds.append(run)
    first, second = builds
    measures = [
        "word_visible_text_sha256",
        "all_page_geometry_and_rasters",
        "page_count",
        "toc_and_actual_starts",
        "reference_numbers",
        "tables",
        "figures",
        "text_bounding_boxes_pt",
    ]
    repeat = {k: first[k] == second[k] for k in measures}
    checks = []
    for run in builds:
        checks.append(
            {
                "reopened_word_matches_pdf_pixels": all(
                    p["docx_and_direct_pdf_pixels_equal"]
                    for p in run["all_page_geometry_and_rasters"]
                ),
                "source_figures_visible_with_captions": all(
                    f["pass"] for f in run["figures"].values()
                ),
                "first_table_rows_on_caption_page": all(
                    t["ordered_same_page"] for t in run["tables"].values()
                ),
            }
        )
    report = {
        "schema": "graduation.expanded-thesis-render.v1",
        "source_sha256": sha(args.source),
        "old_negative_control_receipt_sha256": sha(BASELINE / "verification.public.json"),
        "figure_verifier_sha256": sha(checker),
        "identical_across_builds": repeat,
        "checks": checks,
        "builds": builds,
        "pass": all(repeat.values()) and all(all(result.values()) for result in checks),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{first['page_count']} pages, {len(first['figures'])} figures, "
        f"{len(first['tables'])} tables"
    )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
