from pathlib import Path
import json,hashlib,base64,difflib
R=Path('/home/ningyd/文档/ChatGPT/BIGsmall'); A=R/'artifacts/research/process/20261004-ced-development/astra-rounds'; D=A/'round287-p6-t2-runner-completion-marker-contract-20261017'; I=D/'implementation'
def pin(p):
 p=Path(p); b=p.read_bytes(); return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def check(rec):
 actual=pin(rec['path']); assert all(actual[k]==rec[k] for k in ('path','bytes','sha256')),rec['path']; return actual
def save(p,b):
 with Path(p).open('xb') as f: f.write(b)
 return pin(p)
def write(p,obj): return save(p,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode())
P=json.loads((D/'plan.json').read_bytes()); inputs=[check(v) for v in P['inputs']]
manifest=json.loads((D/'before/manifest.json').read_bytes())
for row in manifest['records']:
 check(row['original']); check(row['archive']); b=Path(row['original']['path']).read_bytes(); assert b==Path(row['archive']['path']).read_bytes()==base64.b64decode(row['base64']); assert Path(row['original']['path']).stat().st_mode==row['mode']==Path(row['archive']['path']).stat().st_mode
original=manifest['records'][0]; old=Path(original['archive']['path']).read_bytes(); candidate=I/'prepared-run-evidence-source.txt'; new=candidate.read_bytes()
assert pin(candidate)['sha256']=='c4865f0bea01accbbb5787b38fd790f4af3abfcf10d220384a43f1e15239b6ad'
markers=[(b'def behavior_resources_complete(summary):\n',b'\n\ndef main():'),(b'                cleanup = outcome["cleanup"]\n',b'                display = {"round": "R285"')]
newmarkers=[(b'def completion_marker_fact(container):\n',b'\n\ndef main():'),(b'                outcome["final_assessment"] = ',b'                display = {"round": "R285"')]
regions=[]; oldbounds=[]; newbounds=[]
for label,(left,right),(nleft,nright) in zip(('completion_helper','final_assessment_and_persistence'),markers,newmarkers):
 assert old.count(left)==old.count(right)==new.count(nleft)==new.count(nright)==1
 s=old.index(left); e=old.index(right,s); ns=new.index(nleft); ne=new.index(nright,ns)
 oldbounds.append((s,e)); newbounds.append((ns,ne)); regions.append({'label':label,'before':{'start_byte':s,'end_byte':e,'start_line':old[:s].count(b'\n')+1,'bytes':e-s,'sha256':hashlib.sha256(old[s:e]).hexdigest()},'after':{'start_byte':ns,'end_byte':ne,'start_line':new[:ns].count(b'\n')+1,'bytes':ne-ns,'sha256':hashlib.sha256(new[ns:ne]).hexdigest()}})
(s1,e1),(s2,e2)=oldbounds; (n1,m1),(n2,m2)=newbounds
assert old[:s1]==new[:n1] and old[e1:s2]==new[m1:n2] and old[e2:]==new[m2:]
assert new==old[:s1]+new[n1:m1]+old[e1:s2]+new[n2:m2]+old[e2:]
idx=json.loads(Path(P['inputs'][17]['path']).read_bytes()); sources=idx['sources']; protected=idx['authority_before']['protected']; assert len(sources)==27 and len(protected)==211
for row in sources:
 check(row); check(row['physical']); b=Path(row['path']).read_bytes(); assert b==base64.b64decode(row['base64'])==Path(row['physical']['path']).read_bytes(); assert Path(row['path']).stat().st_mode==row['mode']
for row in protected: check(row)
target=I/'run-evidence-corrected.py'; assert not target.exists() and not target.is_symlink()
limited=save(I/'limited.diff',''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile=original['original']['path'],tofile=str(target))).encode())
proof={'round':'R287','status':'SOURCE_ONLY_BYTE_SCOPE_PROVED','before':original,'candidate':pin(candidate),'target_before':None,'regions':regions,'unchanged_regions':[{'label':label,'bytes':len(part),'sha256':hashlib.sha256(part).hexdigest(),'exact_before_after':True} for label,part in [('prefix',old[:s1]),('between_helpers_and_final_assessment',old[e1:s2]),('suffix',old[e2:])]],'reconstruction_exact':True,'input_records':inputs,'current_sources':[{k:r[k] for k in ('path','bytes','sha256')} for r in sources],'protected':protected,'source_count':27,'protected_count':211,'runtime_executed':False,'limited_diff':limited}
proofpin=write(I/'source-regions-scope-proof.json',proof)
print(json.dumps({'candidate':pin(candidate),'candidate_lines':len(new.splitlines()),'before_manifest':pin(D/'before/manifest.json'),'scope_proof':proofpin,'limited_diff':limited,'input_count':len(inputs),'source_count':len(sources),'protected_count':len(protected),'target_before':None},ensure_ascii=False))
