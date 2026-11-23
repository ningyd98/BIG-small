"""Typeset the seven-chapter manuscript and its evidence figures as DOCX and PDF."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.styles import BabelFish

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "docs/thesis/graduation-20261123/manuscript.md"
TITLE = "面向边缘智能场景的小型机械臂云边协同控制系统的设计"
FILE = "云边协同机械臂毕业设计"
SERIF, SANS = "Noto Serif CJK SC", "Noto Sans CJK SC"
INK, MUTED, TEAL = "1C2D3D", "455D6A", "195E67"
CAPTIONS = {
    "architecture": "图 2-1　云端候选、边缘准入、端侧执行与独立评价的数据流。",
    "views": "图 3-1　同一探索摆放 P2 在三个已登记视角的 RGB 首帧。初始高度偏移为零。",
    "perception": ("图 3-2　三种机位的留出结果。左为顶心覆盖率，右为有效帧误差，虚线为 10 mm。"),
    "evidence": "图 6-1　冻结正式首组 LIFT 全段颜色候选数。统计单位为物理步位置，共 2,041 个。",
}


def text_style(style, name: str, size: float, color: str) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    fonts = style.element.get_or_add_rPr().rFonts
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + key), name)
        fonts.attrib.pop(qn("w:" + key + "Theme"), None)


def new_style(doc, name, font=SANS, size=10, color=MUTED):
    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    text_style(style, font, size, color)
    return style


def margins_and_fonts(doc) -> None:
    # Pandoc emits title-cased OOXML names for built-in headings and captions.
    # Round-trip these names through Word's canonical style-name mapping.
    for style in doc.styles:
        if style.type == WD_STYLE_TYPE.PARAGRAPH:
            style.name = BabelFish.ui2internal(style.name)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin, section.right_margin = Cm(2.55), Cm(2.55)
    section.top_margin, section.bottom_margin = Cm(2.25), Cm(2.05)
    section.header_distance, section.footer_distance = Cm(1), Cm(0.95)
    section.different_first_page_header_footer = True
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.add_run("BIGsmall　/　云边协同机械臂")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    for key in ("Header", "Footer"):
        if key not in doc.styles:
            doc.styles.add_style(key, WD_STYLE_TYPE.PARAGRAPH)
        text_style(doc.styles[key], SANS, 8.5, MUTED)
    header.style, footer.style = doc.styles["Header"], doc.styles["Footer"]
    for key in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if key not in doc.styles:
            continue
        style = doc.styles[key]
        text_style(style, SERIF, 10.5, INK)
        pf = style.paragraph_format
        pf.space_before, pf.space_after = Pt(0), Pt(4)
        pf.line_spacing = Pt(15.5)
        pf.widow_control = True
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for i in range(1, 4):
        style = doc.styles[f"Heading {i}"]
        text_style(style, SANS, (20, 14, 12)[i - 1], INK if i == 1 else TEAL)
        style.font.bold = True
        pf = style.paragraph_format
        pf.space_before, pf.space_after = Pt(0 if i == 1 else 7), Pt(10 if i == 1 else 4)
        pf.keep_with_next = True
        if i == 1:
            pf.page_break_before = True
    for name in ("Caption", "Image Caption", "Table Caption"):
        if name in doc.styles:
            text_style(doc.styles[name], SANS, 9, MUTED)
            doc.styles[name].font.italic = False
    if "Verbatim Char" in doc.styles:
        text_style(doc.styles["Verbatim Char"], SANS, 9.5, INK)
    if "Source Code" in doc.styles:
        code = doc.styles["Source Code"]
        text_style(code, "DejaVu Sans Mono", 9.5, INK)
        code.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        code.paragraph_format.line_spacing = Pt(15)
        code.paragraph_format.keep_together = True
    text_style(doc.styles["Title"], SANS, 25, "000000")
    doc.styles["Title"].font.bold = True
    props = doc.styles["Title"].element.get_or_add_pPr()
    for border in props.findall(qn("w:pBdr")):
        props.remove(border)


def cover_and_contents(doc, headings):
    anchor = doc.paragraphs[0]
    cover = new_style(doc, "Cover category", SANS, 14, TEAL)
    cover.paragraph_format.space_before, cover.paragraph_format.space_after = Pt(88), Pt(30)
    anchor.insert_paragraph_before("工程硕士学位论文　研究阶段稿", cover)
    title = anchor.insert_paragraph_before(TITLE, "Title")
    title.paragraph_format.line_spacing = 1.2
    title.paragraph_format.space_after = Pt(15)
    sub = new_style(doc, "English title", SANS, 13)
    anchor.insert_paragraph_before(
        "Design of a Cloud–Edge Collaborative Control System for a Small Robotic Arm "
        "in Edge Intelligence Applications",
        sub,
    )
    author = new_style(doc, "Cover author", SERIF, 13, INK)
    author.paragraph_format.space_before, author.paragraph_format.space_after = Pt(68), Pt(12)
    anchor.insert_paragraph_before("宁业栋　　集成电路工程", author)
    anchor.insert_paragraph_before("研究方向　嵌入式智能系统与云边端协同控制", sub)
    anchor.insert_paragraph_before("工程与实验版本　2026 年 11 月 23 日", sub)
    toc_head = anchor.insert_paragraph_before("目　录", "Heading 1")
    toc_head.paragraph_format.space_after = Pt(26)
    toc = new_style(doc, "Chapter contents", SANS, 12, INK)
    fmt = toc.paragraph_format
    fmt.space_after = Pt(12)
    fmt.tab_stops.add_tab_stop(Cm(15.65), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    return [anchor.insert_paragraph_before(h + "\t0", toc) for h in headings]


def layout_tables(doc):
    references = new_style(doc, "Thesis references", SERIF, 10, INK)
    fmt = references.paragraph_format
    fmt.line_spacing, fmt.space_after = Pt(15), Pt(4)
    fmt.first_line_indent, fmt.left_indent = Cm(-0.55), Cm(0.55)
    fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for para in doc.paragraphs:
        if re.match(r"^\[\d+\]\s", para.text):
            para.style = references
    for table in doc.tables:
        contents = list(table.rows)
        count = len(table.columns)
        if not contents or count == 0:
            continue
        lengths = [max(len(r.cells[i].text) for r in contents) for i in range(count)]
        weights = [min(8.2, max(2.3, val**0.51)) for val in lengths]
        widths = [Cm(15.80 * v / sum(weights)) for v in weights]
        table.autofit = False
        for col, width in zip(table.columns, widths, strict=True):
            col.width = width
        for i, row in enumerate(contents):
            props = row._tr.get_or_add_trPr()
            props.append(OxmlElement("w:cantSplit"))
            if i == 0:
                props.append(OxmlElement("w:tblHeader"))
            for cell, width in zip(row.cells, widths, strict=True):
                cell.width = width
                if i == 0:
                    shading = OxmlElement("w:shd")
                    shading.set(qn("w:fill"), "DEE9EA")
                    cell._tc.get_or_add_tcPr().append(shading)
                for para in cell.paragraphs:
                    fmt = para.paragraph_format
                    fmt.space_before, fmt.space_after = Pt(2), Pt(2)
                    fmt.line_spacing = 1.15
                    fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    fmt.keep_with_next = False
                    for run in para.runs:
                        run.font.name = SANS
                        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), SANS)
                        run.font.size = Pt(9.0)
                        if i == 0:
                            run.bold = True
    for para in doc.paragraphs:
        following = para._p.getnext()
        if para.style.name == "Heading 2" and para.text.startswith("1.3 "):
            # Present the three research questions and the chapter guide together.
            para.paragraph_format.page_break_before = True
        elif para._p.xpath(".//w:drawing"):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # An inline image needs its natural height when body text uses exact leading.
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.keep_with_next = True
        elif para.text.startswith("表 ") and following is not None and following.tag == qn("w:tbl"):
            para.paragraph_format.keep_with_next = True
        elif para.style.name in ("Caption", "Image Caption"):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.space_after = Pt(8)


def normalized(s: str) -> str:
    return "".join(unicodedata.normalize("NFKC", s).split()).replace("\u200b", "")


def convert(soffice: str, docx: Path, folder: Path, profile: Path) -> Path:
    folder.mkdir(exist_ok=True)
    subprocess.run(
        [
            soffice,
            "-env:UserInstallation=" + profile.as_uri(),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            folder,
            docx,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    pdf = folder / docx.with_suffix(".pdf").name
    if not pdf.is_file():
        raise RuntimeError("LibreOffice produced no PDF")
    return pdf


def chapter_pages(pdf, headings):
    data = subprocess.check_output(["pdftotext", "-layout", pdf, "-"]).decode()
    pages = [p for p in data.split("\f") if p.strip()]
    numbers = []
    for heading in headings:
        matches = []
        for i, page in enumerate(pages, 1):
            if i <= 2:
                continue
            lines = [
                n for ln in page.splitlines() if (n := normalized(ln)) and "BIGsmall/" not in n
            ]
            if lines and normalized(heading) == lines[0]:
                matches.append(i)
        if len(matches) != 1:
            raise ValueError(f"expected a single chapter start for {heading}: {matches}")
        numbers.append(matches[0])
    return numbers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--plot-python", default=sys.executable, help="Python with matplotlib and Noto CJK fonts"
    )
    parser.add_argument("--soffice", default="soffice")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="graduation-manuscript-") as scratch:
        tmp = Path(scratch)
        env = dict(os.environ, MPLCONFIGDIR=str(tmp / "mpl"))
        subprocess.run(
            [args.plot_python, ROOT / "scripts/graduation/figures.py", tmp], check=True, env=env
        )
        content = MANUSCRIPT.read_text()
        study = (
            ROOT
            / "artifacts/research/process/20261004-ced-development/astra-rounds"
            / ("round-graduation-integration-20261123")
        )
        montage = json.loads((study / "perception.public.json").read_text())[
            "calibration_views_figure"
        ]
        pixels = (study / montage["filename"]).read_bytes()
        if hashlib.sha256(pixels).hexdigest() != montage["sha256"]:
            raise ValueError("calibration camera panels differ from the sealed view montage")
        (tmp / "views.png").write_bytes(pixels)
        headings = re.findall(r"^# (.+)$", content, re.MULTILINE)
        if (
            headings[:2] != ["摘要", "Abstract"]
            or len(headings) != 11
            or headings[9] != "参考文献"
            or not headings[10].startswith("附录")
            or not all(
                h.startswith("第" + n + "章")
                for n, h in zip("一二三四五六七", headings[2:9], strict=True)
            )
        ):
            raise ValueError(f"unexpected thesis headings: {headings}")
        for key, caption in CAPTIONS.items():
            token = "{{figure:" + key + "}}"
            if content.count(token) != 1:
                raise ValueError(f"missing or duplicate {token}")
            figure = f"![{caption}]({key}.png){{width=15.2cm}}"
            content = content.replace(token, figure)
        (tmp / "input.md").write_text(content)
        intermediate = tmp / "body.docx"
        subprocess.run(
            [
                "pandoc",
                "-f",
                "markdown-smart",
                "--resource-path",
                tmp,
                tmp / "input.md",
                "-o",
                intermediate,
            ],
            cwd=tmp,
            check=True,
        )
        doc = Document(intermediate)
        doc.core_properties.title, doc.core_properties.author = TITLE, "宁业栋"
        doc.core_properties.subject = "集成电路工程 · 云边端协同控制"
        margins_and_fonts(doc)
        entries = cover_and_contents(doc, headings)
        layout_tables(doc)
        word = output / (FILE + ".docx")
        draft = tmp / word.name
        doc.save(draft)
        first = convert(args.soffice, draft, tmp / "proof", tmp / "profile")
        numbers = chapter_pages(first, headings)
        for entry, title, number in zip(entries, headings, numbers, strict=True):
            entry.text = f"{title}\t{number}"
        doc.save(word)
        pdf = convert(args.soffice, word, output, tmp / "profile")
        if chapter_pages(pdf, headings) != numbers:
            raise ValueError("table of contents changed pagination")
        print(pdf, word)


if __name__ == "__main__":
    main()
