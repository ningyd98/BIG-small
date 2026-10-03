from pathlib import Path
import json,re,html
base=Path(__file__).parent.parent
refs=json.loads((base/'sources/verified_references.json').read_text())
def name(s):
    if isinstance(s,dict):
        fam=s.get('family',''); given=s.get('given','')
    else:
        fam,given=(s.split(',',1)+[''])[:2]
    return fam.upper()+' '+''.join(x[0].upper() for x in re.findall(r'[A-Za-zÀ-ž]+',given))
def authors(d):
    arr=d.get('authors',[]); vals=[name(x) for x in arr[:3]]
    if d['id']==17: vals=['SHA L']
    if d['id']==24: vals=['ZHAO W','PEÑA QUERALTA J','WESTERLUND T']
    if d['id']==16: vals=['PHYSICAL INTELLIGENCE','BLACK K','BROWN N']
    if d['id']==7: vals=['YATES R D','SUN Y','BROWN III D R']
    return ', '.join(vals)+(', et al' if len(arr)>3 else '')
entries=[]
for d in refs:
    i=d['id']; url=d['url']; title=html.unescape(d.get('title',[''])[0]);title=title.replace('$\\pi_{0.5}$','π₀.₅')
    if i==21:
        text='GARCÍA J, FERNÁNDEZ F. A Comprehensive Survey on Safe Reinforcement Learning[J]. Journal of Machine Learning Research, 2015, 16(42): 1437–1480.'
    elif i==31:
        text='PINEAU J, VINCENT-LAMARRE P, SINHA K, et al. Improving Reproducibility in Machine Learning Research (A Report from the NeurIPS 2019 Reproducibility Program)[J]. Journal of Machine Learning Research, 2021, 22(164): 1–20.'
    elif 'arxiv' in d:
        year=d['date'][0][:4];text=f'{authors(d)}. {title}[EB/OL]. arXiv:{d["arxiv"]}, {year} [2026-10-02].'
    else:
        year=1996 if i==20 else d['year']['date-parts'][0][0];venue=html.unescape(d['venue'][0]);pages=d.get('pages')
        if i==6:venue='Proceedings of the 51st IEEE Conference on Decision and Control (CDC)'
        if i==32:pages='1-26'
        journal=bool(d.get('volume'))
        text=f'{authors(d)}. {title}[{"J" if journal else "C"}]. {venue}, {year}'
        if d.get('volume'):text+=', '+d['volume']+('('+d['issue']+')' if d.get('issue') else '')
        if i==28:text+=': eabm6074'
        elif pages:text+=': '+pages.replace('-','–')
        text+='.'
        text+=' DOI: '+d['doi']+'.'
    entries.append({'id':i,'text':text,'url':url,'metadata_url':d['metadata_url']})
entries.extend([
{'id':33,'text':'机器人控制方法、装置及存储介质[Z]. 用户提供的专利文稿：1555_PN363626_定稿.docx，版本日期未注明，参阅日期 2026-10-02. 未确认公开申请号及授权状态。','url':'/home/ningyd/.codex/attachments/69dd2b56-5852-45db-b513-3159d687aeec/1555_PN363626_定稿.docx'},
{'id':34,'text':'BIG-small 项目资料[Z]. docs/architecture.md；artifacts/deployment/final_acceptance.json 及关联验证报告. 仓库快照 396325729364d1014eb0c7beed9eb1aa11936ed7，2026-10-02.','url':'/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/deployment/final_acceptance.json'}])
(base/'sources/bibliography.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2))
p=base/'开题报告.md';s=p.read_text();s=s.split('## 参考文献')[0]+'## 参考文献\n\n'
s+='\n\n'.join(f'[{d["id"]}] {d["text"]} [{"原始来源" if d["id"]<=32 else "资料文件"}]({d["url"]})' for d in entries)+'\n'
p.write_text(s)
for d in entries:print(f'[{d["id"]}] {d["text"]}')
body=s.split('## 参考文献')[0];cites=set(map(int,re.findall(r'\[(\d+)\]',body)))
print('BODY_CJK',len(re.findall('[\u4e00-\u9fff]',body)),'REFERENCES',len(entries),'UNUSED',set(range(1,35))-cites,'UNDEFINED',cites-set(range(1,35)))
