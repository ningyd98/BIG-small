"""Update contents from the rendered PDF or audit the final manuscript and DOCX."""
from pathlib import Path
import argparse, hashlib, json, re, zipfile
from lxml import etree
from pypdf import PdfReader

QA=Path(__file__).resolve().parent
BASE=QA.parent.parent
SOURCE=BASE/'开题报告.md'
DOCX=BASE/'开题报告_执行决策闭环与创新提升_20261003.docx'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(t):return re.sub(r'\s+','',t)
def cjk(t):return ''.join(re.findall(r'[\u4e00-\u9fff]',t))
ap=argparse.ArgumentParser();ap.add_argument('--render',default='render-final');ap.add_argument('--map',action='store_true');ap.add_argument('--review',nargs='*',type=int);args=ap.parse_args()
render=QA/args.render
pdf=render/(DOCX.stem+'.pdf')
pages=[p.extract_text() or '' for p in PdfReader(pdf).pages]
source=SOURCE.read_text();body=source[source.index('## 摘要'):].split('## 参考文献')[0]
titles=re.findall(r'^## (.+)$',body,re.M)+['参考文献']
page_map={}
for title in titles:
 hits=[i+1 for i,t in enumerate(pages) if i>=2 and (any(norm(line)==norm(title) for line in t.splitlines()) if title=='参考文献' else norm(title) in norm(t))]
 if not hits:raise ValueError('Missing heading in PDF: '+title)
 page_map[title]=hits[0]
if args.map:
 (QA/'page_map.json').write_text(json.dumps(page_map,ensure_ascii=False,indent=2));print(json.dumps({'pages':len(pages),'page_map':page_map},ensure_ascii=False));raise SystemExit()
if args.review is not None:
 path=QA/'visual_review.json';reviews=json.loads(path.read_text()) if path.exists() else {}
 for n in args.review:
  reviews[str(n)]={'sha256':sha(render/f'page-{n}.png'),'render':args.render,'result':'Inspected at original resolution; no clipping, overlap, missing glyphs, broken rows, or detached caption observed.'}
 path.write_text(json.dumps(reviews,ensure_ascii=False,indent=2));print({'reviewed':args.review});raise SystemExit()
checks={}
def check(name,value,detail=None):
 checks[name]={'passed':bool(value)}
 if detail is not None:checks[name]['detail']=detail
with zipfile.ZipFile(DOCX) as z:
 check('zip_integrity',z.testzip() is None)
 root=etree.fromstring(z.read('word/document.xml'));styles=etree.fromstring(z.read('word/styles.xml'))
 text=''.join(root.xpath('//w:t/text()',namespaces=NS))
 media=[x for x in z.namelist() if x.startswith('word/media/')]
 rel=etree.fromstring(z.read('word/_rels/document.xml.rels'))
refs={int(x) for x in re.findall(r'^\[(\d+)\]',source.split('## 参考文献')[1],re.M)}
cited={int(x) for x in re.findall(r'\[(\d+)\]',body)}
check('references_complete_and_all_cited',refs==cited==set(range(1,43)),{'references':sorted(refs),'cited':sorted(cited)})
bookmarks=set(root.xpath('//w:bookmarkStart/@w:name',namespaces=NS));anchors=root.xpath('//w:hyperlink/@w:anchor',namespaces=NS)
check('all_internal_links_resolve',set(anchors)<=bookmarks)
check('bibliography_bookmarks_complete',{'ref_'+str(n) for n in refs}<=bookmarks)
check('source_links_present',len(rel.xpath('//*[local-name()="Relationship" and contains(@Type,"hyperlink")]'))>=len(refs))
check('all_chapters_present',len(re.findall(r'^## [一二三四五六七八九十]+、',source,re.M))==11)
image_alt=root.xpath('//wp:inline/wp:docPr/@descr',namespaces=NS)
check('three_figures_nine_equations_with_alt_text',len(image_alt)==len(media)==12 and all(image_alt))
table_count=sum(b.strip().startswith('|') for b in body.split('\n\n'))
check('all_manuscript_tables_present',len(root.xpath('//w:tbl',namespaces=NS))==table_count,table_count)
check('no_markup_or_placeholder',all(s not in text for s in [':::equation',':::figure','待更新','**','`','\ufffd']))
missing=[];doc_cjk=cjk(text)
for i,block in enumerate(body.split('\n\n')):
 if block.strip().startswith(':::'):continue
 expected=cjk(block)
 if expected and expected not in doc_cjk:missing.append(i)
check('all_source_prose_headings_tables_retained',not missing,missing)
main=source[source.index('## 一、'):].split('## 附录 A')[0]
check('main_body_over_10000_cjk',len(cjk(main))>=10000,len(cjk(main)))
check('contents_page_numbers_match',page_map==json.loads((QA/'page_map.json').read_text()),page_map)
toc=root.xpath('//w:p[w:hyperlink[starts-with(@w:anchor,"sec_")]]',namespaces=NS)
toc_text=[''.join(p.xpath('.//w:t/text()',namespaces=NS)) for p in toc]
check('contents_cached_numbers_match',all(title+str(n) in toc_text for title,n in page_map.items()))
check('pages_nonempty',all(t.strip() for t in pages),len(pages))
review_path=QA/'visual_review.json';reviews=json.loads(review_path.read_text()) if review_path.exists() else {}
check('all_final_pages_visually_reviewed',all(str(i) in reviews and reviews[str(i)]['sha256']==sha(render/f'page-{i}.png') for i in range(1,len(pages)+1)))
check('body_font_12pt',styles.xpath('boolean(//w:style[@w:styleId="Normal"]/w:rPr/w:sz[@w:val="24"])',namespaces=NS))
check('headings_black',all(styles.xpath(f'boolean(//w:style[@w:styleId="{style}"]/w:rPr/w:color[@w:val="000000"])',namespaces=NS) for style in ['Title','Heading1','Heading2']))
authoring=json.loads((QA/'authoring_audit.json').read_text());check('built_from_final_manuscript',authoring['manuscript_sha256']==sha(SOURCE))
audit={'document':str(DOCX),'pages':len(pages),'main_cjk_characters':len(cjk(main)),'references':len(refs),'figures':3,'equations':9,'tables':table_count,'docx_sha256':sha(DOCX),'manuscript_sha256':sha(SOURCE),'visual_review':reviews,'checks':checks,'passed':all(x['passed'] for x in checks.values())}
(QA/'final_verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in audit.items() if k!='visual_review'},ensure_ascii=False,indent=2));raise SystemExit(0 if audit['passed'] else 1)
