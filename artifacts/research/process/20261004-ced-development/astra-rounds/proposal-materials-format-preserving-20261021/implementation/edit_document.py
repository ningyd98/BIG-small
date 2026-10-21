import json, re, hashlib, difflib
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E

root=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
out=root/'output/doc/20261021-proposal-revision'
build=out/'.build'
build.mkdir(parents=True,exist_ok=True)
source=Path('/tmp/bigsmall-proposal-review-20261021/开题报告-2501220176 宁业栋.docx')
mapping=json.loads(Path('/tmp/bigsmall-proposal-edit-20261021/revisions.json').read_text())
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(source) as z:
    original=z.read('word/document.xml')
    tree=E.fromstring(original)
    paragraphs=tree.xpath('//w:p',namespaces=ns)
    changes=[]
    def replace_span(p,start,end,replacement):
        nodes=p.xpath('.//w:t',namespaces=ns)
        offset=0; selected=[]
        for t in nodes:
            text=t.text or ''; stop=offset+len(text)
            if stop>start and offset<end:
                selected.append((t,offset,stop))
            offset=stop
        if start==end:
            offset=0
            for j,t in enumerate(nodes):
                text=t.text or ''; stop=offset+len(text)
                if (offset<=start<stop) or (start==stop and j==len(nodes)-1):
                    k=start-offset;t.text=text[:k]+replacement+text[k:];return
                offset=stop
            raise ValueError(('Insertion anchor',start,end))
        if not selected: raise ValueError(('No text span',start,end))
        first,a,b=selected[0]
        prefix=(first.text or '')[:max(0,start-a)]
        last,c,d=selected[-1]
        suffix=(last.text or '')[min(len(last.text or ''),end-c):]
        first.text=prefix+replacement+(suffix if first is last else '')
        for t,_,_ in selected[1:]:t.text=''
        if first is not last:last.text=suffix
    for index in sorted(set(map(int,mapping['document']))|set(map(int,mapping['document_substrings']))):
        p=paragraphs[index]
        before=''.join(p.xpath('.//w:t/text()',namespaces=ns))
        after=mapping['document'].get(str(index),before)
        for a,b in mapping['document_substrings'].get(str(index),[]):
            assert after.count(a)==1,(index,a)
            after=after.replace(a,b)
        edits=difflib.SequenceMatcher(None,before,after,autojunk=False).get_opcodes()
        for tag,a,b,c,d in reversed(edits):
            if tag!='equal':replace_span(p,a,b,after[c:d])
        actual=''.join(p.xpath('.//w:t/text()',namespaces=ns))
        assert actual==after,(index,actual,after)
        changes.append({'paragraph':index,'before':before,'after':after,'beforeCharacters':len(before),'afterCharacters':len(after)})
    def structural_xml(xml):
        t=E.fromstring(xml)
        for e in t.xpath('//w:t',namespaces=ns):e.text=''
        return E.tostring(t,method='c14n')
    edited=E.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)
    assert structural_xml(original)==structural_xml(edited),'Non-text document change'
    candidate=build/'开题报告-2501220176 宁业栋_修改版.docx'
    with ZipFile(candidate,'w') as target:
        for member in z.infolist():
            target.writestr(member,edited if member.filename=='word/document.xml' else z.read(member.filename))
    report={'source':str(source),'candidate':str(candidate),'nonTextStructurePreserved':True,'allOtherPartsPreserved':True,'changes':changes}
    (build/'docx-change-map.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'candidate':str(candidate),'changedParagraphs':len(changes),'characterDelta':sum(x['afterCharacters']-x['beforeCharacters'] for x in changes),'nonTextStructurePreserved':True},ensure_ascii=False))
