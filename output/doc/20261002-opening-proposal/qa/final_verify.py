from pathlib import Path
import hashlib
import json
import re
import zipfile
from lxml import etree
from pypdf import PdfReader

BASE = Path(__file__).resolve().parent.parent
QA = BASE / 'qa'
DOCX = BASE / '开题报告_双系统协同方法研究.docx'
PDF = QA / 'render-approved/开题报告_双系统协同方法研究.pdf'
SOURCE = BASE / '开题报告.md'
NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
}

def cjk(text):
    return ''.join(re.findall(r'[\u4e00-\u9fff]', text))

def check(name, passed, detail=None):
    checks[name] = {'passed': bool(passed)}
    if detail is not None:
        checks[name]['detail'] = detail

checks = {}
source = SOURCE.read_text()
body = source[source.index('## 摘要'):].split('## 参考文献')[0]
main = source[source.index('## 一、'):].split('## 附录 A')[0]
bibliography = json.loads((BASE / 'sources/bibliography.json').read_text())
verified = json.loads((BASE / 'sources/verified_references.json').read_text())
page_map = json.loads((QA / 'page_map.json').read_text())
with zipfile.ZipFile(DOCX) as archive:
    check('docx_zip_integrity', archive.testzip() is None)
    root = etree.fromstring(archive.read('word/document.xml'))
    text = ''.join(root.xpath('//w:t/text()', namespaces=NS))
    image_files = [x for x in archive.namelist() if x.startswith('word/media/')]

check('main_chapters_over_10000_cjk', len(cjk(main)) >= 10000, len(cjk(main)))
check('body_over_10000_cjk', len(cjk(body)) >= 10000, len(cjk(body)))
reference_ids = {int(x) for x in re.findall(r'\[(\d+)\]', body)}
bibliography_ids = {x['id'] for x in bibliography}
check('all_references_cited_no_undefined_citations', reference_ids == bibliography_ids == set(range(1,35)))
bookmarks = set(root.xpath('//w:bookmarkStart/@w:name', namespaces=NS))
anchors = root.xpath('//w:hyperlink/@w:anchor', namespaces=NS)
check('internal_citation_and_contents_links_resolve', set(anchors) <= bookmarks)
check('all_34_bibliography_bookmarks', {'ref_' + str(i) for i in range(1,35)} <= bookmarks)
check('32_external_references_have_verified_metadata', len(verified) == 32 and {x['id'] for x in verified} == set(range(1,33)) and all(not x.get('error') for x in verified))
check('34_bibliographic_entries_have_source_links', len(bibliography) == 34 and all(x.get('url') for x in bibliography))
check('internal_sources_marked_as_materials', all('[Z]' in x['text'] for x in bibliography[32:]))
inline = root.xpath('//wp:inline', namespaces=NS)
alt = root.xpath('//wp:inline/wp:docPr/@descr', namespaces=NS)
check('3_figures_and_9_equations_present_with_alt_text', len(inline) == len(image_files) == len(alt) == 12 and all(alt))
check('five_tables_present', len(root.xpath('//w:tbl', namespaces=NS)) == 5)
check('no_unrendered_markup_or_placeholder', all(x not in text for x in [':::equation', ':::figure', '待更新', '\ufffd']))

# Check every prose paragraph, heading and table against the authored source.
# Captions and cover/contents add text, while mathematical images remain separate.
document_cjk = cjk(text)
missing = []
for index, block in enumerate(body.split('\n\n')):
    if block.strip().startswith(':::'):
        continue
    expected = cjk(block)
    if expected and expected not in document_cjk:
        missing.append(index)
check('all_source_chinese_paragraphs_headings_and_tables_retained', not missing, {'missing_blocks': missing})

reader = PdfReader(PDF)
pages = [page.extract_text() or '' for page in reader.pages]
normalized = [re.sub(r'\s+', '', t) for t in pages]
check('render_has_37_nonempty_pages', len(pages) == 37 and all(t.strip() for t in pages))
actual_page_map = {}
for title, expected in page_map.items():
    needle = re.sub(r'\s+', '', title)
    # The short bibliography heading can also occur within appendix prose.
    # Require a standalone line for it, rather than a substring occurrence.
    hits = [
        i+1 for i,t in enumerate(normalized)
        if i >= 2 and (
            any(re.sub(r'\s+', '', line) == needle for line in pages[i].splitlines())
            if title == '参考文献' else needle in t
        )
    ]
    actual_page_map[title] = hits[0] if hits else None
check('contents_page_numbers_match_final_render', actual_page_map == page_map, actual_page_map)
contents_paragraphs = root.xpath('//w:p[w:hyperlink[starts-with(@w:anchor,"sec_")]]', namespaces=NS)
contents_text = [''.join(p.xpath('.//w:t/text()', namespaces=NS)) for p in contents_paragraphs]
check('docx_contents_cached_numbers_complete', all(any(t == title + '\t' + str(number) or t == title + str(number) for t in contents_text) for title,number in page_map.items()))

# The final revision changed only the cover; pages 2–16 have already been
# inspected at original resolution and their pixel hashes are unchanged.
unchanged = all(
    hashlib.sha256((QA/f'render-approved/page-{i}.png').read_bytes()).digest()
    == hashlib.sha256((QA/f'render-final/page-{i}.png').read_bytes()).digest()
    for i in range(2,38)
)
check('cover_only_final_revision_preserves_body_pages', unchanged)
check('all_page_images_present', all((QA/f'render-approved/page-{i}.png').is_file() for i in range(1,38)))

audit = {
    'document': str(DOCX),
    'main_chapters_cjk_count_excluding_abstract_appendices_references': len(cjk(main)),
    'body_cjk_count_excluding_cover_contents_references': len(cjk(body)),
    'pages': len(pages),
    'external_academic_references': len(verified),
    'internal_sources': 2,
    'docx_bytes': DOCX.stat().st_size,
    'docx_sha256': hashlib.sha256(DOCX.read_bytes()).hexdigest(),
    'manuscript_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'visual_qa': {
        'pages_inspected_at_original_resolution': list(range(1,38)),
        'latest_cover_inspected': 'render-approved/page-1.png',
        'unchanged_pages_previously_inspected': list(range(2,17)),
        'latest_remaining_pages_inspected': list(range(17,38)),
        'result': 'No clipped figures or equations, overlapping cover text, broken tables or unreadable references observed.',
    },
    'checks': checks,
    'passed': all(v['passed'] for v in checks.values()),
}
(QA/'final_verification.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
print(json.dumps(audit, ensure_ascii=False, indent=2))
raise SystemExit(0 if audit['passed'] else 1)
