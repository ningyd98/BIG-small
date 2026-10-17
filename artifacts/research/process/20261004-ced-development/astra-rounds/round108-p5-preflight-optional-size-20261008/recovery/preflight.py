import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round107-p5-boundary-fixture-recovery-20261008')
p=json.loads((r/'plan.json').read_text()); a=json.loads((r/'root-activation.json').read_text())
checks=[]
cache={}
def read(path):
 if str(path) not in cache:
  cache[str(path)]=path.read_bytes()
 return cache[str(path)]
if type(a) is not dict or type(a.get('checks')) is not list:
 raise ValueError('invalid activation checks shape')

for name,expected in [('plan.md','189531443138d82e6ffc2c7c7f1b72261bae521693d82acd5e8ab458bd1131c8'),('plan.json','b541a22c8612a6de566d6ce757f60f568081d88e434178e31f961afaa8602aec'),('root-activation.json','bf389fd200a48c60f71302efdd7233bca83e0a0aa5a5d13d618c611b58777b5f')]:
 actual=hashlib.sha256(read(r/name)).hexdigest(); checks.append({'path':str(r/name),'match':actual==expected,'actual':actual})
for x in a['checks']:
 if type(x) is not dict or type(x.get('path')) is not str or not x['path']:
  raise ValueError('invalid activation path')
 expected_sha=x.get('expected_sha256')
 if type(expected_sha) is not str or len(expected_sha)!=64 or any(c not in '0123456789abcdefABCDEF' for c in expected_sha):
  raise ValueError('invalid expected_sha256')
 expected_size=x.get('expected_bytes')
 if expected_size is not None and (type(expected_size) is not int or expected_size<0):
  raise ValueError('invalid declared expected_bytes')
 path=Path(x['path']); data=read(path); actual=hashlib.sha256(data).hexdigest()
 sha_match=actual==expected_sha
 size_match=expected_size is None or len(data)==expected_size
 checks.append({'path':str(path),'match':sha_match and size_match,'actual':actual,'actual_bytes':len(data),'sha_match':sha_match,'size_match':size_match,'size_requirement':'UNDECLARED' if expected_size is None else 'DECLARED'})
checks.extend({'path':s,'absent':not Path(s).exists(),'match':not Path(s).exists()} for s in a['new_outputs_absent'])
h=r.parent/'round108-p5-preflight-optional-size-20261008'
for name, expected in [('plan.md','42c7a06d48885b60f1facc39aaa7c6a050a7311be04e78d1c16b3c9f05fc9189'),('plan.json','092217d9f09a8b0c6ba8878e27ac7c8c1d4ce828c672195f242e47aae48b10ae'),('root-activation.json','fd4946217add3dfb9e838328d6c8e50dfbaadbba8f142581efe48ffc4927fc90')]:
 actual=hashlib.sha256(read(h/name)).hexdigest()
 checks.append({'path':str(h/name),'match':actual==expected,'actual':actual})
for row in json.loads(read(h/'plan.json'))['inputs']:
 data=read(Path(row['path']))
 checks.append({'path':row['path'],'match':hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']})
for row in json.loads(read(r/'startup-stop/source-freeze.json'))['sources']:
 data=read(Path(row['path']))
 checks.append({'path':row['path'],'match':hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']})
budget=json.loads(read(r/'startup-stop/budget.json'))
checks.append({'path':'unused_budget','match':budget['active_commands']==[] and all(v==0 for v in budget['used'].values()) and budget['remaining']==json.loads(read(h/'plan.json'))['budget']['inherited_remaining']})
checks.append({'path':str(r/'implementation'),'match':not (r/'implementation').exists()})
print('CHECKS',len(checks),'ALL_MATCH',all(x['match'] for x in checks))
assert all(x['match'] for x in checks)
i=r/'implementation'; i.mkdir()
(i/'input-check.json').write_text(json.dumps({'at_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'status':'INPUTS_MATCH'},ensure_ascii=False,indent=2)+'\n')
for x in p['scope']['modified_python']:
 q=i/'source-before'/x; q.parent.mkdir(parents=True,exist_ok=True); q.write_bytes(read(Path(x)))
(i/'progress.md').write_text('# R107 进度\n\nR108 metadata前置实际检查全部匹配，数量见 input-check.json；三Python before已保存，三fixture及GREEN/temp原先缺席。开始限定语义修订，未运行验证。\n')
print('METADATA_RECOVERED; original R107 six budgets unused')
