from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from copy import deepcopy
import json,hashlib
TMP=Path('/tmp/bigsmall-opening-three-sections-20261011')
REF=Path('/tmp/bigsmall-opening-application-20261011/开题报告-2101210559丁亚伟.docx')
OUT=Path('/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application/开题申请_三项正文_20261024.docx')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};W='{'+ns['w']+'}'
with ZipFile(REF) as z:parts={n:z.read(n) for n in z.namelist()}
root=E.fromstring(parts['word/document.xml']);body=root.find('w:body',ns)
source=deepcopy(body[19]);sect=deepcopy(body[-1]);rows=source.findall('w:tr',ns)
base=deepcopy(rows[5].findall('w:tc',ns)[1].findall('w:p',ns)[1])
c=json.loads((TMP/'content.json').read_text())
def el(name,**attrs):
 x=E.Element(W+name)
 for k,v in attrs.items():x.set(W+k,str(v))
 return x
def paragraph(text,indent=True,bold=False,align='both',size=21,space=50,title=False):
 p=deepcopy(base)
 for ch in list(p):p.remove(ch)
 pr=E.SubElement(p,W+'pPr')
 for x in [el('pStyle',val='Title' if title else 'Normal'),el('keepNext',val='1' if bold else '0'),el('keepLines',val='1'),el('widowControl',val='1'),el('snapToGrid',val='0'),el('spacing',before=0,after=space,line=320,lineRule='exact'),el('ind',firstLine=420 if indent else 0,start=0,end=0),el('jc',val=align)]:pr.append(x)
 r=E.SubElement(p,W+'r');rp=E.SubElement(r,W+'rPr')
 for x in [el('rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体',cs='Times New Roman'),el('color',val='000000'),el('sz',val=size),el('szCs',val=size)]:rp.append(x)
 if bold:rp.append(el('b'))
 t=E.SubElement(r,W+'t');t.text=text
 return p
def fill(cell,texts,label=False):
 for ch in list(cell):
  if ch.tag!=W+'tcPr':cell.remove(ch)
 cp=cell.find('w:tcPr',ns)
 for x in cp.findall('w:vAlign',ns):cp.remove(x)
 cp.append(el('vAlign',val='center' if label else 'top'))
 if not label:
  for m in cp.findall('w:tcMar',ns):cp.remove(m)
  mar=E.SubElement(cp,W+'tcMar');mar.append(el('top',w=60,type='dxa'));mar.append(el('bottom',w=60,type='dxa'))
 for text in texts:
  if isinstance(text,tuple):
   kind,text=text;cell.append(paragraph(text,indent=False,bold=kind=='heading',align='left'))
  else:cell.append(paragraph(text,indent=not label,align='center' if label else 'both'))
def row_from(index,label,texts):
 row=deepcopy(rows[index]);cells=row.findall('w:tc',ns)
 fill(cells[0],[label],label=True);fill(cells[1],texts)
 # Narrative rows are allowed to expand; source widths and borders are retained.
 pr=row.find('w:trPr',ns)
 if pr is not None:
  for x in list(pr):
   if x.tag in [W+'trHeight',W+'cantSplit']:pr.remove(x)
 return row
def table(rs):
 t=deepcopy(source)
 for r in t.findall('w:tr',ns):t.remove(r)
 for r in rs:t.append(r)
 return t
def pagebreak():
 p=el('p');pr=E.SubElement(p,W+'pPr');pr.append(el('keepNext',val='0'));pr.append(el('spacing',before=0,after=0,line=20,lineRule='exact'))
 r=E.SubElement(p,W+'r');r.append(el('br',type='page'));return p
for ch in list(body):body.remove(ch)
body.append(paragraph('论文开题报告申请表',indent=False,bold=True,align='center',size=30,space=200,title=True))
bg=[('note','（意义、国内外现状及立项依据，附主要参考文献）')]+c['background']+[('heading','主要参考文献')]+[('reference',v) for v in c['references']]
body.append(table([row_from(5,'技术背景',bg)]));body.append(pagebreak())
main=[('note','（研究、开发内容和目标，拟解决的关键问题和采取的方法、技术路线、设计方案及可行性分析等）')]+c['research'][:8]
body.append(table([row_from(6,'研究、开发方案',main)]));body.append(pagebreak())
cont=row_from(6,'',c['research'][8:])
sched=row_from(7,'进展计划',[('note','（总体安排、进度及预期成果形式）')]+c['schedule'])
body.append(table([cont,sched]));body.append(paragraph('',indent=False,space=0));body.append(sect)
parts['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
styles=E.fromstring(parts['word/styles.xml'])
if not styles.xpath('./w:style[@w:styleId="Title"]',namespaces=ns):
 st=el('style',type='paragraph',styleId='Title');styles.append(st)
 for x in [el('name',val='Title'),el('basedOn',val='Normal'),el('qFormat')]:st.append(x)
 pr=E.SubElement(st,W+'pPr');pr.append(el('keepNext'));pr.append(el('jc',val='center'))
 rp=E.SubElement(st,W+'rPr');rp.append(el('b'));rp.append(el('color',val='000000'));rp.append(el('sz',val=30))
parts['word/styles.xml']=E.tostring(styles,xml_declaration=True,encoding='UTF-8',standalone=True)
core=E.fromstring(parts['docProps/core.xml'])
for ch in list(core):
 if E.QName(ch).localname in ['creator','lastModifiedBy','title','subject','description','keywords']:core.remove(ch)
E.SubElement(core,'{http://purl.org/dc/elements/1.1/}title').text='论文开题报告申请表'
parts['docProps/core.xml']=E.tostring(core,xml_declaration=True,encoding='UTF-8',standalone=True)
OUT.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
 for n,data in parts.items():z.writestr(n,data)
(TMP/'word-text.txt').write_text('\n'.join(root.xpath('//w:t/text()',namespaces=ns)))
print(json.dumps({'output':str(OUT),'bytes':OUT.stat().st_size,'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()},ensure_ascii=False))
