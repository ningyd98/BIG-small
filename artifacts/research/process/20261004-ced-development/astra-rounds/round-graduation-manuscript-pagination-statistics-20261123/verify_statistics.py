"""Read the four corrected OOXML properties and compare the surrounding package and pages."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from PIL import Image

NAME = "云边协同机械臂毕业设计"
APP = "docProps/app.xml"
TAGS = ("Words", "Characters", "CharactersWithSpaces", "Pages")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def properties(content):
    root = ElementTree.fromstring(content)
    return {tag: int(root.find(f"{{*}}{tag}").text) for tag in TAGS}


def mask_statistics(content):
    for tag in TAGS:
        needle = tag.encode()
        content, count = re.subn(
            b"(<" + needle + rb">)\d+(</" + needle + b">)", rb"\g<1>#\g<2>", content
        )
        if count != 1:
            raise ValueError(f"Expected a unique extended property {tag!r}.")
    return content


def verify(folder, proof, rendered):
    docx = folder / (NAME + ".docx")
    pdf = folder / (NAME + ".pdf")
    before = proof / "before.pdf"
    with ZipFile(proof / "before.docx") as source, ZipFile(docx) as final:
        assert source.namelist() == final.namelist()
        different = [k for k in source.namelist() if source.read(k) != final.read(k)]
        assert different == [APP]
        old, new = source.read(APP), final.read(APP)
        assert mask_statistics(old) == mask_statistics(new)
        old_values, values = properties(old), properties(new)
        parts = len(source.namelist())
    with ZipFile(proof / "layout.odt") as odt:
        node = ElementTree.fromstring(odt.read("meta.xml")).find(".//{*}document-statistic")
    stats = {k.rsplit("}", 1)[-1]: int(v) for k, v in node.attrib.items()}
    contents = subprocess.check_output(["pdftotext", "-layout", pdf, "-"])
    assert contents == subprocess.check_output(["pdftotext", "-layout", before, "-"])
    pdf_pages = [page for page in contents.split(b"\x0c") if page.strip()]
    assert values == {
        "Words": stats["word-count"],
        "Characters": stats["non-whitespace-character-count"],
        "CharactersWithSpaces": stats["character-count"],
        "Pages": len(pdf_pages),
    }
    pixels = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "150", "-png", before, Path(tmp) / "page"], check=True)
        images = {int(p.stem.split("-")[1]): p for p in Path(tmp).glob("page-*.png")}
        assert len(images) == values["Pages"]
        for number in range(1, values["Pages"] + 1):
            with (
                Image.open(images[number]) as first,
                Image.open(rendered / f"page-{number}.png") as second,
            ):
                a, b = first.convert("RGB"), second.convert("RGB")
                assert a.size == b.size and a.tobytes() == b.tobytes(), number
                pixels.append(sha(a.tobytes()))
    return {
        "original_word_properties": old_values,
        "new_word_properties": values,
        "odt_formatter_statistics": stats,
        "package_parts": parts,
        "only_modified_part": APP,
        "remaining_app_xml_bytes_identical": True,
        "all_pdf_page_text_equal_before_and_after": True,
        "all_pre_update_pdf_and_reopened_word_page_pixels_equal": True,
        "page_rgb_sha256": pixels,
        "per_page_extracted_text_sha256": [sha(p) for p in pdf_pages],
        "before_docx_sha256": sha((proof / "before.docx").read_bytes()),
        "final_docx_sha256": sha(docx.read_bytes()),
        "before_pdf_sha256": sha(before.read_bytes()),
        "final_pdf_sha256": sha(pdf.read_bytes()),
        "odt_sha256": sha((proof / "layout.odt").read_bytes()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--edition",
        type=Path,
        nargs=3,
        action="append",
        required=True,
        metavar=("WORD_PDF_DIR", "STATISTICS_PROOF_DIR", "REOPENED_WORD_PAGES"),
    )
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if len(args.edition) != 2 or args.edition[0] == args.edition[1]:
        ap.error("Two independent editions are required.")
    results = [verify(*paths) for paths in args.edition]
    identical = (
        results[0]["new_word_properties"] == results[1]["new_word_properties"]
        and results[0]["page_rgb_sha256"] == results[1]["page_rgb_sha256"]
    )
    report = {
        "schema": "graduation.manuscript.word-properties.v1",
        "builds": results,
        "pass": identical,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Word statistics:", results[0]["new_word_properties"], "independent repeat:", identical)
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
