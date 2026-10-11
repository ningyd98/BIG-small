from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import hashlib,json
base=Path('/tmp/bigsmall-opening-application-20261011')
ref=base/'开题报告-2101210559丁亚伟.docx'
final=Path('/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application/开题申请表_集成电路工程_20261024.docx')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(ref) as z:a={n:z.read(n) for n in z.namelist()}
with ZipFile(final) as z:b={n:z.read(n) for n in z.namelist()}
x=E.fromstring(a['word/document.xml']);y=E.fromstring(b['word/document.xml'])
t='\n'.join(y.xpath('//w:t/text()',namespaces=ns))
old=E.fromstring(ZipFile(base/'iteration-01.docx').read('word/document.xml'))
oldtext='\n'.join(old.xpath('//w:t/text()',namespaces=ns))
checks={
'same_part_inventory':set(a)==set(b),
'preserve_parts_unchanged':all(a[n]==b.get(n) for n in a if n not in ['word/document.xml','word/styles.xml','docProps/core.xml']),
'section_geometry_unchanged':E.tostring(x.find('w:body/w:sectPr',ns))==E.tostring(y.find('w:body/w:sectPr',ns)),
'primary_table_grid_unchanged':E.tostring(x.find('w:body',ns)[19].find('w:tblGrid',ns))==E.tostring(y.find('w:body/w:tbl/w:tblGrid',ns)),
'text_unchanged_after_pagination':t==oldtext,
'required_facts':all(s in t for s in ['面向边缘智能场景的小型机械臂云边协同控制系统的设计','2026年10月24日','集成电路工程','202611505816.9','机器人控制方法、装备及存储介质','一、选题意义','二、研究内容','三、论文架构','四、成果展示','五、进度安排','不能仅依据申请号认定达标']),
'seven_chapter_outline':all('第'+n+'章' in t for n in '一二三四五六七'),
'no_sample_identity':not any(s in t for s in ['丁亚伟','2101210559','北京大学']),
'no_original_drawings_visible':not y.xpath('//w:drawing|//w:pict',namespaces=ns),
'reference_unchanged':hashlib.sha256(ref.read_bytes()).hexdigest()=='b322171190e2ef86b4a649c9bea16913e7b1cd1db1d55e4e6a43c3ce9a33f0d7'
}
out={'checks':checks,'all_checks_pass':all(checks.values()),'changed_parts':[n for n in a if n in b and a[n]!=b[n]],'final_sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'final_bytes':final.stat().st_size}
(base/'final-structure-check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
