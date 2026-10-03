import json, urllib.request, concurrent.futures, re, html
from pathlib import Path
from lxml import html as lh
out=Path(__file__).parent
refs={1:'10.1109/TASE.2014.2376492',2:'10.1109/JIOT.2016.2579198',3:'10.1109/JPROC.2019.2918951',4:'10.1109/JPROC.2006.887288',5:'10.1109/TAC.2007.904277',6:'10.1109/CDC.2012.6425820',7:'10.1109/JSAC.2021.3065072',8:'10.1109/ICRA.2011.5980391',17:'10.1109/MS.2001.936213',18:'10.1109/TAC.2016.2638961',19:'10.1609/aaai.v32i1.11797',20:'10.1109/LICS.1996.561342',22:'10.1109/IROS.2017.8202133',23:'10.1109/ICRA.2018.8460528',24:'10.1109/SSCI47803.2020.9308468',25:'10.1109/IROS.2012.6386109',27:'10.1109/LRA.2023.3270034',28:'10.1126/scirobotics.abm6074',29:'10.1109/MRA.2012.2205651',30:'10.1609/aaai.v32i1.11694',32:'10.1201/9780429246593'}
arx={9:'1709.00084',10:'2204.01691',11:'2207.05608',12:'2209.07753',13:'2307.05973',14:'2307.15818',15:'2406.09246',16:'2504.16054',26:'2108.10470'}
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Research-proposal-citation-audit/1.0'})
    return urllib.request.urlopen(req,timeout=40).read().decode('utf-8')
def cross(item):
    i,doi=item; url='https://api.crossref.org/works/'+doi
    try:
        d=json.loads(fetch(url))['message']; (out/f'ref-{i:02}-crossref.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
        return {'id':i,'doi':doi,'metadata_url':url,'title':d.get('title'),'authors':d.get('author'),'venue':d.get('container-title'),'year':d.get('published'),'volume':d.get('volume'),'issue':d.get('issue'),'pages':d.get('page'),'abstract':d.get('abstract'),'url':d.get('URL'),'verified_at':'2026-10-02'}
    except Exception as e:return {'id':i,'error':str(e),'doi':doi}
def ax(item):
    i,aid=item;url='https://arxiv.org/abs/'+aid
    try:
        raw=fetch(url);soup=lh.fromstring(raw);(out/f'ref-{i:02}-arxiv.html').write_text(raw)
        def metas(n):return soup.xpath('//meta[@name="'+n+'"]/@content')
        a=soup.xpath('//blockquote[contains(@class,"abstract")]')
        return {'id':i,'arxiv':aid,'metadata_url':url,'title':metas('citation_title'),'authors':metas('citation_author'),'date':metas('citation_date'),'abstract':a[0].text_content().strip() if a else '', 'url':url,'verified_at':'2026-10-02'}
    except Exception as e:return {'id':i,'error':str(e),'arxiv':aid}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    data=list(ex.map(cross,refs.items()))+list(ex.map(ax,arx.items()))
for i,url in [(21,'https://jmlr.org/papers/v16/garcia15a.html'),(31,'https://jmlr.org/papers/v22/20-303.html')]:
    try:
        raw=fetch(url);(out/f'ref-{i:02}-jmlr.html').write_text(raw)
        data.append({'id':i,'metadata_url':url,'url':url,'page_text':' '.join(lh.fromstring(raw).text_content().split()),'verified_at':'2026-10-02'})
    except Exception as e:data.append({'id':i,'error':str(e)})
data.sort(key=lambda x:x['id']);(out/'verified_references.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
for d in data: print(json.dumps({k:v for k,v in d.items() if k not in ['abstract','page_text']},ensure_ascii=False))
