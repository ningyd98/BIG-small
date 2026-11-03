"""Run the normal API generation commands entirely in fresh stage outputs."""
from pathlib import Path
import difflib
import hashlib
import json
import os
import subprocess
import sys

ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D=Path(os.environ['R413_STAGE_DIR'])
NODE=str(ROOT/'cache/node-v22.23.3-linux-x64/bin/node')
PY=str(ROOT/'.venv/bin/python')
commands=[
 [PY,str(ROOT/'scripts/export_dashboard_openapi.py'),'--output',str(D/'openapi.json')],
 [NODE,str(ROOT/'dashboard/node_modules/openapi-typescript/bin/cli.js'),str(D/'openapi.json'),'-o',str(D/'schema.d.ts')],
 [NODE,str(ROOT/'dashboard/node_modules/prettier/bin/prettier.cjs'),'--write',str(D/'openapi.json'),str(D/'schema.d.ts')],
]
for i,argv in enumerate(commands):
 with (D/f'step-{i+1}.invocation.json').open('x') as f:json.dump({'argv':argv,'timeout_s':300},f,indent=2)
 if i==2:
  for name in ['openapi.json','schema.d.ts']:
   with (D/(name+'.unformatted')).open('xb') as f:f.write((D/name).read_bytes())
 with (D/f'step-{i+1}.stdout').open('xb') as out,(D/f'step-{i+1}.stderr').open('xb') as err:
  completed=subprocess.run(argv,stdout=out,stderr=err,stdin=subprocess.DEVNULL,timeout=300,cwd=ROOT/'dashboard')
 with (D/f'step-{i+1}.exit.json').open('x') as f:json.dump({'returncode':completed.returncode},f)
 if completed.returncode:sys.exit(completed.returncode)
rows=[]
for name in ['openapi.json','schema.d.ts']:
 original=ROOT/'dashboard/src/api/generated'/name
 generated=D/name
 left=original.read_bytes();right=generated.read_bytes()
 rows.append({'name':name,'equal':left==right,'original_sha256':hashlib.sha256(left).hexdigest(),
              'generated_sha256':hashlib.sha256(right).hexdigest()})
 with (D/(name+'.diff')).open('x') as f:
  f.writelines(difflib.unified_diff(left.decode().splitlines(True),right.decode().splitlines(True),fromfile=str(original),tofile=str(generated)))
with (D/'comparison.json').open('x') as f:json.dump(rows,f,indent=2)
print(json.dumps(rows))
sys.exit(0 if all(r['equal'] for r in rows) else 1)
