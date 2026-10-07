import hashlib,json
from pathlib import Path
A=Path('artifacts/research/process/20261004-ced-development');pr=A/'astra-rounds/round67-oc2-green-partials';p=json.loads((pr/'plan.json').read_text());base=A/'astra-repair-execution/OC2/implementation/task2-3';dest=base/'round67'
def pin(path):
 raw=Path(path).read_bytes();return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
expected=dict(p['input_pins']);expected[str(pr/'plan.md')]={'sha256':'62bc42d4e638fb3e0f7d423f3d6752c0e8818c2ed1adfd926e8cf71f549f2f47','bytes':39566};expected[str(pr/'plan.json')]={'sha256':'3b9af379e4d64dded875f976b47b6e7e6476976d67977ccfdcbce5e34389aea2','bytes':54412}
authorization=base/'root-round67-authorization.json';current_authorization=pin(authorization)
if current_authorization['sha256']!='67050b537de55e5e95a2357a63e040ae7c123faa965369ed0d2230659d31dc6a':raise SystemExit('authorization drift')
checks={name:{'expected':wanted,'actual':pin(name),'match':pin(name)==wanted} for name,wanted in expected.items()};bad=[name for name,row in checks.items() if not row['match']];print('inputs',len(checks),'bad',bad)
missing=p['observed_missing_files'];print('observed_missing_files',missing)
if bad:raise SystemExit(2)
for name in missing:
 if Path(name).exists():raise SystemExit('previous missing path unexpectedly present')
dest.mkdir(exist_ok=False)
(dest/'preflight.json').write_text(json.dumps({'status':'PASS_INPUTS_BEFORE_ROUND67','checks':checks,'authorization':current_authorization,'source_before':{name:pin(name) for name in p['scope']['repair_allowlist']},'observed_missing_files':missing},indent=2)+'\n')
for name,value in p.items():
 if name not in {'input_pins','observed_missing_files','plan_md_sha256'}:print(name,json.dumps(value,ensure_ascii=False,indent=2))
print('preflight',pin(dest/'preflight.json'))
