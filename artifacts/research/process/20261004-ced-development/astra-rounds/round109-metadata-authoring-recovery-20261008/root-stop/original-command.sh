.venv/bin/python - <<'PY'
from pathlib import Path
import json,hashlib
b=Path('artifacts/research/process/20261004-ced-development/astra-rounds');r=b/'round108-p5-preflight-optional-size-20261008'
for x in sorted((r/'recovery').glob('*')):
 print(x.name,x.stat().st_size,hashlib.sha256(x.read_bytes()).hexdigest())
 if x.suffix=='.json' and ('result' in x.name or 'report' in x.name):print(x.read_text())
p=b/'round107-p5-boundary-fixture-recovery-20261008/implementation/input-check.json'
d=json.loads(p.read_text());print('input_check_keys',list(d))
PY
