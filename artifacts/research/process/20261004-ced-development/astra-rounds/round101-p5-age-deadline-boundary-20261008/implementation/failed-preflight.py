import hashlib,json
from pathlib import Path
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round101-p5-age-deadline-boundary-20261008');p=json.loads((r/'plan.json').read_text())
c=[]
for i in p['input_pins']:
 b=Path(i['path']).read_bytes();c.append({**i,'match':len(b)==i['bytes'] and hashlib.sha256(b).hexdigest()==i['sha256']})
print(json.dumps({'all40match':all(i['match'] for i in c),'count':len(c),'module_absent':not Path(p['owned_paths'][0]).exists(),'mismatch':[i for i in c if not i['match']],'implementation_exists':(r/'implementation').exists(),'basetemp_exists':Path('/tmp/bigsmall-p5-r101-green').exists()},indent=2))
if not all(i['match'] for i in c) or (r/'implementation').exists() or Path('/tmp/bigsmall-p5-r101-green').exists():raise SystemExit(1)
e=r/'implementation';e.mkdir();(e/'source-before').mkdir()
for n in p['owned_paths']:
 q=Path(n)
 if q.exists():
  dst=e/'source-before'/n;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(q.read_bytes())
(e/'input-check.json').write_text(json.dumps(c,indent=2)+'\n')
(e/'progress.md').write_text('# R101 P5 software resumed\n\n40 input pins MATCH. NEW module absent; exclusive implementation and GREEN temp fresh. Source-before preserved. Adjusting exactly 32 CPU cases and typed policy map before implementation. Original R100 RED27 remains untouched and is not rerun.\n\nBudgets inherited: RED1/1; proof pending; Ruff/formatcheck/GREEN each0/1; formatter/mypy/actual/Git0.\n')
