"""Count thesis narrative and check it against the editable and printed editions."""

import argparse
import collections
import hashlib
import json
import re
import subprocess
import unicodedata
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CHAPTER = re.compile(r"^第[一二三四五六七]章\s")
CAPTION = re.compile(r"^[图表]\s+[A\d]+-\d+　")
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
LIMITS = (30_000, 50_000)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return (
        "".join(unicodedata.normalize("NFKC", text).split())
        .replace("\u00ad", "")
        .replace("\u200b", "")
    )


def han(text):
    return "".join(HAN.findall(text))


def source_paragraphs(text):
    chapters = {}
    active = None
    fence = None
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = []
        for line in block.splitlines():
            marker = re.match(r"^(?:`{3,}|~{3,})", line)
            if marker:
                fence = None if fence == marker.group() else marker.group()
                continue
            if fence is None:
                lines.append(line)
        block = "\n".join(lines).strip()
        if block.startswith("# "):
            title = block[2:].strip()
            active = title if CHAPTER.match(title) else None
            if active:
                chapters[active] = []
        elif (
            active
            and block
            and not block.startswith(("#", "|", "{{figure:", "!["))
            and not CAPTION.match(block)
        ):
            chapters[active].append(block)
    if len(chapters) != 7:
        raise ValueError("The source must contain the seven ordered chapters.")
    return chapters


def word_paragraphs(path):
    chapters, active = {}, None
    with ZipFile(path) as archive:
        if failed := archive.testzip():
            raise ValueError(f"Invalid Word package part {failed}")
        body = ElementTree.fromstring(archive.read("word/document.xml")).find(f"{WORD}body")
        extended = ElementTree.fromstring(archive.read("docProps/app.xml"))
    for p in body.findall(f"{WORD}p"):
        style = p.find(f"{WORD}pPr/{WORD}pStyle")
        name = style.get(f"{WORD}val", "") if style is not None else ""
        text = "".join(node.text or "" for node in p.iter(f"{WORD}t"))
        if name == "Heading1":
            active = text if CHAPTER.match(text) else None
            if active:
                chapters[active] = []
        elif (
            active
            and text
            and name in {"FirstParagraph", "BodyText", "Normal", ""}
            and not CAPTION.match(text)
        ):
            chapters[active].append(text)
    properties = {
        n.tag.rsplit("}", 1)[-1]: int(n.text)
        for n in extended
        if n.tag.rsplit("}", 1)[-1] in {"Words", "Characters", "CharactersWithSpaces", "Pages"}
    }
    all_printed = "".join(node.text or "" for node in body.iter(f"{WORD}t"))
    return chapters, properties, len(han(all_printed))


def printed_pages(path):
    raw = subprocess.check_output(["pdftotext", "-layout", path, "-"]).decode("utf-8")
    pages = []
    for page in raw.split("\f"):
        if not page.strip():
            continue
        lines = [
            line
            for line in page.splitlines()
            if line.strip() and normalized(line) != "BIGsmall/云边协同机械臂"
        ]
        if lines and re.fullmatch(r"\s*\d+\s*", lines[-1]):
            lines.pop()
        pages.append(lines)
    return pages


def compare_chapters(source, word, pages):
    titles = [*source, "参考文献"]
    starts = {}
    for title in titles:
        hits = [
            i for i, page in enumerate(pages) if page and normalized(page[0]) == normalized(title)
        ]
        if len(hits) != 1:
            raise ValueError(f"Cannot locate chapter heading {title!r} once in the PDF: {hits}")
        starts[title] = hits[0]
    results = []
    for title, following in pairwise(titles):
        markdown, paragraphs = source[title], word[title]
        printable = normalized(
            "".join(line for page in pages[starts[title] : starts[following]] for line in page)
        )
        offset = 0
        missing = []
        for i, p in enumerate(paragraphs, 1):
            phrase = normalized(p)
            location = printable.find(phrase, offset)
            if location < 0:
                missing.append({"paragraph": i, "starts": p[:18]})
            else:
                offset = location + len(phrase)
        source_han = [han(p) for p in markdown]
        word_han = [han(p) for p in paragraphs]
        source_text = [normalized(p.replace("`", "").replace("**", "")) for p in markdown]
        results.append(
            {
                "chapter": title,
                "source_han": sum(map(len, source_han)),
                "word_han": sum(map(len, word_han)),
                "paragraphs": len(paragraphs),
                "source_and_word_paragraphs_han_identical": source_han == word_han,
                "source_and_word_visible_paragraphs_identical": source_text
                == [normalized(p) for p in paragraphs],
                "all_word_paragraphs_printed_in_order_after_nfkc": not missing,
                "missing": missing,
                "first_page": starts[title] + 1,
                "source_narrative_han_sha256": digest("\n".join(source_han).encode()),
            }
        )
    return results


def repetition_review(chapters):
    paragraphs = [
        (f"{ch.split()[0]}-{i}", normalized(p))
        for ch, ps in chapters.items()
        for i, p in enumerate(ps, 1)
    ]
    sentence_positions = collections.defaultdict(list)
    fingerprints = []
    for key, para in paragraphs:
        for sentence in re.split(r"[。！？!?]", para):
            if len(han(sentence)) >= 25:
                sentence_positions[sentence].append(key)
        fingerprints.append((key, {para[i : i + 7] for i in range(len(para) - 6)}))
    candidates = []
    for i, (a, left) in enumerate(fingerprints):
        for b, right in fingerprints[:i]:
            if min(len(left), len(right)) < 40:
                continue
            overlap = len(left & right) / min(len(left), len(right))
            if overlap >= 0.35:
                candidates.append([a, b, round(overlap, 4)])
    return {
        "duplicate_paragraphs": [
            p[:40] for p, n in collections.Counter(p for _, p in paragraphs).items() if n > 1
        ],
        "repeated_sentences_25_han_or_more": [
            {"opening": s[:40], "locations": loc}
            for s, loc in sentence_positions.items()
            if len(loc) > 1
        ],
        "similar_paragraphs_7gram_overlap_at_least_035": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--word", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.source.read_text()
    source = source_paragraphs(raw)
    word, properties, printed_han = word_paragraphs(args.word)
    if list(word) != list(source):
        raise ValueError("Word and Markdown chapter order differs.")
    pages = printed_pages(args.pdf)
    chapters = compare_chapters(source, word, pages)
    total = sum(c["source_han"] for c in chapters)
    refs = [int(v) for v in re.findall(r"(?m)^\[(\d+)\]\s", raw)]
    cited = sorted(
        {
            int(n)
            for paragraphs in source.values()
            for p in paragraphs
            for n in re.findall(r"\[(\d+)\]", p)
        }
    )
    repetition = repetition_review(source)
    result = {
        "schema": "graduation.manuscript-length.v1",
        "definition": (
            "Narrative in chapters 1–7 excluding headings, captions, tables, code, "
            "front and end matter. Counts ideographs U+3400–4DBF, U+4E00–9FFF, U+F900–FAFF."
        ),
        "source_sha256": digest(args.source.read_bytes()),
        "docx_sha256": digest(args.word.read_bytes()),
        "pdf_sha256": digest(args.pdf.read_bytes()),
        "chapter_narrative_han": total,
        "word_document_body_all_printable_han": printed_han,
        "source_all_han": len(han(raw)),
        "source_all_nonwhitespace_characters": len("".join(raw.split())),
        "source_all_characters_including_whitespace": len(raw),
        "pdf_pages": len(pages),
        "docx_app_properties": properties,
        "chapters": chapters,
        "references": refs,
        "cited_in_body": cited,
        "repetition_review": repetition,
        "length_in_range": LIMITS[0] <= total <= LIMITS[1]
        and LIMITS[0] <= printed_han <= LIMITS[1],
        "full_text_verified": all(
            x["source_and_word_visible_paragraphs_identical"]
            and x["source_and_word_paragraphs_han_identical"]
            and x["all_word_paragraphs_printed_in_order_after_nfkc"]
            for x in chapters
        ),
    }
    result["pass"] = (
        result["length_in_range"]
        and result["full_text_verified"]
        and not repetition["duplicate_paragraphs"]
        and refs == cited == list(range(1, 15))
        and properties["Pages"] == len(pages)
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{total} narrative Han, {printed_han} printable Han, "
        f"{len(pages)} pages, pass={result['pass']}"
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
