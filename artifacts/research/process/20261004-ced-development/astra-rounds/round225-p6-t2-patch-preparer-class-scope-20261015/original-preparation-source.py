from pathlib import Path
import hashlib,json,difflib,collections
root=Path("/home/ningyd/文档/ChatGPT/BIGsmall")
d=Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round222-p6-t2-local-lease-dispatch-patch-recovery-20261015")
plan=json.loads((d/'plan.json').read_bytes())
failure=json.loads((d/'original-author-patch-failure.json').read_bytes())
patch=failure['exact_patch']
units=[];current=None;part=[]
def flush():
 if part and any(x.startswith(('+','-')) for x in part):
  units.append({'path':current,'old':''.join(x[1:] for x in part if not x.startswith('+')),'new':''.join(x[1:] for x in part if not x.startswith('-'))})
for line in patch.splitlines(keepends=True):
 if line.startswith('*** Update File: '):
  flush();part=[];current=line[len('*** Update File: '):].strip()
 elif line.startswith('@@'):
  flush();part=[]
 elif line.startswith('***'):
  flush();part=[]
 elif current is not None and line[:1] in (' ','+','-'):part.append(line)
mapping=['__init__','_check_ingress','_local_read_scope','_local_read_scope','_local_read_scope','heartbeat_lease','_owns_artifact_publication','_active_job_cancelled','_raise_if_cancelled_or_timed_out']
assert len(units)==len(mapping)==9
pairs={v['source']['path']:v for v in plan['current_and_archive_pins']}
def region(text,name):
 lines=text.splitlines(keepends=True);starts=[i for i,x in enumerate(lines) if x.startswith('    def '+name+'(')]
 assert len(starts)==1,(name,len(starts))
 start=starts[0];end=len(lines)
 for i in range(start+1,len(lines)):
  line=lines[i]
  if line.startswith(('    def ','    @')) or (line.strip() and not line[0].isspace()):end=i;break
 return ''.join(lines[:start]),''.join(lines[start:end]),''.join(lines[end:])
originals={};afters={};changes=[]
for unit,name in zip(units,mapping):
 path=unit['path'];unit['function']=name
 if path not in originals:
  pin=pairs[path]['archive'];b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'];originals[path]=b.decode();afters[path]=b.decode()
 prefix,body,suffix=region(afters[path],name)
 assert body.count(unit['old'])==1,(name,unit['old'])
 body=body.replace(unit['old'],unit['new'],1);afters[path]=prefix+body+suffix
 changes.append(unit)
order=[('operational_lease.py',['__init__','_check_ingress']),('sqlite_repository.py',['heartbeat_lease','_local_read_scope']),('worker.py',['_owns_artifact_publication','_active_job_cancelled','_raise_if_cancelled_or_timed_out'])]
corrected=['*** Begin Patch\n']
for basename,names in order:
 matches=[p for p in originals if Path(p).name==basename];assert len(matches)==1;path=matches[0];corrected.append('*** Update File: '+path+'\n')
 for name in names:
  old=region(originals[path],name)[1].splitlines(keepends=True);new=region(afters[path],name)[1].splitlines(keepends=True);corrected.append('@@\n')
  for tag,i,j,a,b in difflib.SequenceMatcher(a=old,b=new,autojunk=False).get_opcodes():
   if tag=='equal':corrected.extend(' '+s for s in old[i:j])
   else:
    corrected.extend('-'+s for s in old[i:j]);corrected.extend('+'+s for s in new[a:b])
corrected.append('*** End Patch');corrected=''.join(corrected)
for marker in ('+','-'):
 original_lines=collections.Counter(x for x in patch.splitlines() if x.startswith(marker))
 corrected_lines=collections.Counter(x for x in corrected.splitlines() if x.startswith(marker))
 assert original_lines==corrected_lines,marker
expected={path:{'before':pairs[path]['source'],'before_archive':pairs[path]['archive'],'after_text':text,'after_bytes':len(text.encode()),'after_sha256':hashlib.sha256(text.encode()).hexdigest()} for path,text in afters.items()}
out=d/'implementation';out.mkdir(parents=True,exist_ok=True)
with (out/'corrected-patch.txt').open('xb') as f:f.write(corrected.encode())
state={'expected':expected,'edit_units':changes}
with (out/'prepared-text-values.json').open('xb') as f:f.write((json.dumps(state,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'corrected_patch':{'path':str(out/'corrected-patch.txt'),'bytes':len(corrected.encode()),'sha256':hashlib.sha256(corrected.encode()).hexdigest()},'prepared_values':{'path':str(out/'prepared-text-values.json'),'bytes':(out/'prepared-text-values.json').stat().st_size,'sha256':hashlib.sha256((out/'prepared-text-values.json').read_bytes()).hexdigest()},'edit_units':len(units),'function_regions':7,'live_product_writes':0,'patch_executions':0},ensure_ascii=False))
