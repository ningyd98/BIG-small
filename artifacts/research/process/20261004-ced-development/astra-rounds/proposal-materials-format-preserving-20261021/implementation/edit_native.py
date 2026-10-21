from pathlib import Path
from lxml import etree as E
from copy import deepcopy
import json,difflib,hashlib
build=Path('/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build')
source=build/'native/开题报告-2501220176 宁业栋.fodt'
tree=E.parse(str(source));ns={'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0','text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
paragraphs=tree.xpath('//office:body//text:p | //office:body//text:h',namespaces=ns)
changes=json.loads((build/'docx-change-map.json').read_text())['changes']
def nodes(e):
    if E.QName(e).namespace!=ns['text']:return []
    if E.QName(e).localname=='s':
        return [(e,'virtual',' '*int(e.get('{'+ns['text']+'}c','1')))]
    result=[]
    if e.text:result.append((e,'text',e.text))
    for child in e:
        result.extend(nodes(child))
        if child.tail:result.append((child,'tail',child.tail))
    return result
def setvalue(node,kind,value):
    if kind=='virtual':
        raise ValueError('Replacement overlaps a fixed space element; retain the source and review this case')
    setattr(node,kind,value)
def replace(p,start,end,replacement):
    parts=nodes(p);offset=0; selected=[]
    for e,kind,value in parts:
        stop=offset+len(value)
        if stop>start and offset<end:selected.append((e,kind,value,offset,stop))
        offset=stop
    if start==end:
        offset=0
        for i,(e,kind,value) in enumerate(parts):
            stop=offset+len(value)
            if offset<=start<stop or (i==len(parts)-1 and start==stop):
                k=start-offset;setvalue(e,kind,value[:k]+replacement+value[k:]);return
            offset=stop
        raise ValueError('Missing insertion point')
    assert selected
    e,k,v,a,b=selected[0];last,lk,lv,c,d=selected[-1]
    prefix=v[:max(0,start-a)];suffix=lv[min(len(lv),end-c):]
    setvalue(e,k,prefix+replacement+(suffix if len(selected)==1 else ''))
    for te,tk,tv,ta,tb in selected[1:]:setvalue(te,tk,'')
    if len(selected)>1:setvalue(last,lk,suffix)
before=deepcopy(tree)
for change in changes:
    p=paragraphs[change['paragraph']]
    old=''.join(value for _,_,value in nodes(p));new=change['after']
    assert old==change['before'],change['paragraph']
    for tag,a,b,c,d in reversed(difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes()):
        if tag!='equal':replace(p,a,b,new[c:d])
    assert ''.join(value for _,_,value in nodes(p))==new
def strip_visible(t):
    for p in t.xpath('//office:body//text:p | //office:body//text:h',namespaces=ns):
        for e,k,v in nodes(p):
            if k!='virtual':setattr(e,k,None)
    return E.tostring(t,method='c14n')
assert strip_visible(before)==strip_visible(deepcopy(tree)),'Non-text native XML changed'
target=build/'native/开题报告-2501220176 宁业栋_修改版.fodt'
tree.write(str(target),encoding='UTF-8',xml_declaration=True)
(build/'native-change-proof.json').write_text(json.dumps({'original':str(source),'candidate':str(target),'paragraphsModified':len(changes),'stylesGeometryAndMediaIdentical':True,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
print(target)
