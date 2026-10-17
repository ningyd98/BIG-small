import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
r=Path('artifacts/research/process/20261004-ced-development/astra-rounds/round107-p5-boundary-fixture-recovery-20261008')
p=json.loads((r/'plan.json').read_text()); a=json.loads((r/'root-activation.json').read_text())
checks=[]
for name,expected in [('plan.md','189531443138d82e6ffc2c7c7f1b72261bae521693d82acd5e8ab458bd1131c8'),('plan.json','b541a22c8612a6de566d6ce757f60f568081d88e434178e31f961afaa8602aec'),('root-activation.json','bf389fd200a48c60f71302efdd7233bca83e0a0aa5a5d13d618c611b58777b5f')]:
 actual=hashlib.sha256((r/name).read_bytes()).hexdigest(); checks.append({'path':str(r/name),'match':actual==expected,'actual':actual})
for x in a['checks']:
 path=Path(x['path']); actual=hashlib.sha256(path.read_bytes()).hexdigest(); checks.append({'path':str(path),'match':actual==x['expected_sha256'] and path.stat().st_size==x['expected_bytes'],'actual':actual})
checks.extend({'path':s,'absent':not Path(s).exists(),'match':not Path(s).exists()} for s in a['new_outputs_absent'])
print('CHECKS',len(checks),'ALL_MATCH',all(x['match'] for x in checks))
assert all(x['match'] for x in checks)
i=r/'implementation'; i.mkdir()
(i/'input-check.json').write_text(json.dumps({'at_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'status':'INPUTS_MATCH'},ensure_ascii=False,indent=2)+'\n')
for x in p['scope']['modified_python']:
 q=i/'source-before'/x; q.parent.mkdir(parents=True,exist_ok=True); q.write_bytes(Path(x).read_bytes())
(i/'progress.md').write_text('# R107 进度\n\n计划/授权与67激活检查重新匹配；三Python before已保存，三fixture及GREEN/temp原先缺席。开始限定语义修订，未运行验证。\n')
print('inputs44compact',json.dumps(p['inputs'][:28],ensure_ascii=False,separators=(',',':')))
