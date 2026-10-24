"""R339: compare full native slide text, including nested groups, without editing PPTX."""
import collections
import hashlib
import json
import posixpath
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BUILD = Path(__file__).resolve().parent
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round339-proposal-student-wording-text-qa-20261024'
NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def body_text(tx):
    paragraphs = []
    for paragraph in tx.findall('a:p', NS):
        chunks = []
        for child in paragraph:
            if child.tag == '{' + NS['a'] + '}br':
                chunks.append('\n')
            else:
                chunks.extend(t.text or '' for t in child.findall('.//a:t', NS))
        paragraphs.append(''.join(chunks))
    return '\n'.join(paragraphs)


def resolve_target(owner, target):
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))


def relationships(z, owner):
    parent, filename = posixpath.split(owner)
    relpath = posixpath.join(parent, '_rels', filename + '.rels')
    if relpath not in z.namelist():
        return {}
    return {r.attrib['Id']: r.attrib for r in ET.fromstring(z.read(relpath))}


def extract(p):
    slides = []
    with ZipFile(p) as z:
        root = ET.fromstring(z.read('ppt/presentation.xml'))
        prels = relationships(z, 'ppt/presentation.xml')
        for sid in root.findall('p:sldIdLst/p:sldId', NS):
            rid = sid.get('{' + NS['r'] + '}id')
            part = resolve_target('ppt/presentation.xml', prels[rid]['Target'])
            s = ET.fromstring(z.read(part))
            shape_bodies = s.findall('.//p:sp/p:txBody', NS)
            native_tables = s.findall('.//a:tbl', NS)
            table_bodies = [tx for tbl in native_tables for tx in tbl.findall('.//a:tc/a:txBody', NS)]
            accounted = {id(t) for tx in shape_bodies + table_bodies for t in tx.findall('.//a:t', NS)}
            all_text_nodes = s.findall('.//a:t', NS)
            rels = relationships(z, part)
            image_hashes = []
            for blip in s.findall('.//p:pic/p:blipFill/a:blip', NS):
                rid = blip.get('{' + NS['r'] + '}embed')
                target = resolve_target(part, rels[rid]['Target'])
                image_hashes.append(hashlib.sha256(z.read(target)).hexdigest())
            slides.append({
                'part': part,
                'texts': [body_text(tx) for tx in shape_bodies],
                'tables': [[[body_text(c.find('a:txBody', NS)) for c in row.findall('a:tc', NS)] for row in tbl.findall('a:tr', NS)] for tbl in native_tables],
                'imageHashes': image_hashes,
                'uncoveredTextNodes': [t.text for t in all_text_nodes if id(t) not in accounted],
                'groupCount': len(s.findall('.//p:grpSp', NS)),
            })
    return slides


def main():
    plan = json.loads((ROUND / 'plan.json').read_text())
    preconditions = [{'path': i['path'], 'expected': i['sha256'], 'actual': sha(i['path'])} for i in plan['inputs']]
    if any(i['actual'] != i['expected'] for i in preconditions):
        raise RuntimeError('Frozen R339 input changed; stop before comparison')
    meta = json.loads((BUILD / 'evidence/input.json').read_text())
    edits = json.loads((BUILD / 'edits.json').read_text())
    source = extract(meta['frozenInput'])
    final_path = ROOT / 'output/pptx/20261024-student-wording/开题报告-宁业栋-学生口吻优化.pptx'
    actual = extract(final_path)
    expected = json.loads(json.dumps(source))
    for e in edits['textboxes']:
        texts = expected[e['slide'] - 1]['texts']
        if texts.count(e['old']) != 1:
            raise RuntimeError(f"Ambiguous authorized text on slide {e['slide']}")
        texts[texts.index(e['old'])] = e['text']
    for e in edits['tables']:
        tables = expected[e['slide'] - 1]['tables']
        if len(tables) != 1:
            raise RuntimeError(f"Ambiguous table on slide {e['slide']}")
        tables[0] = e['values']
    pages = []
    for i, (s, e, a) in enumerate(zip(source, expected, actual), 1):
        pages.append({
            'slide': i,
            'allTextsExactWithMultiplicity': collections.Counter(e['texts']) == collections.Counter(a['texts']),
            'expectedEmptyTextboxes': e['texts'].count(''),
            'actualEmptyTextboxes': a['texts'].count(''),
            'allOrderedTableValuesExact': e['tables'] == a['tables'],
            'imageByteHashesExactWithMultiplicity': collections.Counter(s['imageHashes']) == collections.Counter(a['imageHashes']),
            'allNativeTextCarriersCovered': not s['uncoveredTextNodes'] and not a['uncoveredTextNodes'],
            'sourceGroupCount': s['groupCount'],
            'actualGroupCount': a['groupCount'],
            'missingTexts': dict(collections.Counter(e['texts']) - collections.Counter(a['texts'])),
            'extraTexts': dict(collections.Counter(a['texts']) - collections.Counter(e['texts'])),
        })
    vf = json.loads((BUILD / 'evidence/final-validation.json').read_text())
    checks = {
        'allFrozenInputsUnchanged': all(i['actual'] == i['expected'] for i in preconditions),
        'originalAttachmentUnchanged': sha(meta['path']) == meta['sha256'],
        'sourceAndFinalSlideCount12': len(source) == len(actual) == 12,
        'allExpectedTextsExactWithMultiplicity': all(p['allTextsExactWithMultiplicity'] for p in pages),
        'allOrderedTableValuesExact': all(p['allOrderedTableValuesExact'] for p in pages),
        'allSlideImageBytesPreserved': all(p['imageByteHashesExactWithMultiplicity'] for p in pages),
        'allNativeTextCarriersCovered': all(p['allNativeTextCarriersCovered'] for p in pages),
        'finalMatchesReviewedCandidate': sha(final_path) == sha(BUILD / 'student-wording-candidate.pptx'),
        'sameArtifactAsPassingFinalizer': sha(final_path) == vf['finalSha256'] and vf['packageIntegrity']['status'] == 'pass' and vf['presentationLayout']['findingCount'] == 0 and vf['firstPartyImport']['passed'],
        'unchangedPagesRenderIdentical': all(sha(BUILD / f'source-render/slide-{i}.png') == sha(BUILD / f'render/slide-{i}.png') for i in [1, 2, 12]),
    }
    result = {
        'status': 'pass' if all(checks.values()) else 'needs_review',
        'plan': str(ROUND / 'plan.json'),
        'planSha256': sha(ROUND / 'plan.json'),
        'originalFailure': {'path': str(BUILD / 'evidence/delivery-qa.json'), 'sha256': sha(BUILD / 'evidence/delivery-qa.json'), 'historicalStatus': 'needs_review, preserved unchanged'},
        'diagnostic': {'path': str(BUILD / 'evidence/text-qa-diagnostic.json'), 'sha256': sha(BUILD / 'evidence/text-qa-diagnostic.json')},
        'correction': 'Recursively traverse nested groups. Preserve every paragraph, break, Unicode string and empty textbox; compare exact text multiplicities, table order and raw image bytes.',
        'checks': checks, 'perSlide': pages, 'inputPreconditions': preconditions,
        'finalPath': str(final_path), 'finalSha256': sha(final_path),
        'visualReviewReuse': 'All 12 source/candidate slides inspected. Final file remains byte-identical to reviewed candidate. No new render or finalizer run.',
        'layoutWarnings': '18 retained watermark edge objects on slides 2 and 12, intentional source bleed. Both complete page renders are identical to original.',
        'nativePowerPointChecked': False,
        'acceptanceBoundary': 'PPT editorial delivery only; no product tests, physical experiment or formal research acceptance.',
    }
    target = BUILD / 'evidence/delivery-qa-recursive.json'
    if target.exists():
        raise RuntimeError('R339 comparison receipt already exists; preserve the single-run record')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': checks, 'receipt': str(target), 'finalSha256': result['finalSha256']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
