"""Archived-only worker-owner source/compiler independent review."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent
ROOT=PACKAGE.parents[4]
expected={'source-hashes.json':'f0c84833daf10c8378b8658155b4995b3e9451037cb85a61aa0a70ac155ccfa4','report.md':'37c79cefb6cc47a455bb9110fb34b71a8a5b82bde9b75c1abff7526fe8cf3791','artifact-hashes.json':'120aba8a1b0c9fda92a2cc4b8c449fd35ce454301a3b2d6f9bd90d826303372c'}
for name,digest in expected.items():
 assert hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest()==digest,name
artifact=json.loads((PACKAGE/'artifact-hashes.json').read_bytes())
assert len(artifact)==807
for name,digest in artifact.items():
 assert hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest()==digest,name
manifest=json.loads((PACKAGE/'source-hashes.json').read_bytes());assert len(manifest)==774
owner=json.loads((PACKAGE/'ownership.json').read_bytes());assert len(owner['owned'])==2
base=PACKAGE.parent/'t12-owner-repository-fix-round-1'
# The supplied base772 was copied without replacement; the exact hash set is
# checked against the package's recorded baseline manifest, never live imports.
baseline_file=PACKAGE/'baseline-source-hashes.json'
if baseline_file.exists():
 baseline=json.loads(baseline_file.read_bytes());assert len(baseline)==772
 assert all(manifest[name]==digest for name,digest in baseline.items())
 assert set(manifest)-set(baseline)==set(owner['owned'])
overlay=Path(tempfile.mkdtemp(prefix='independent-worker-owner-774-'))
asts=0
for name,digest in manifest.items():
 relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
 source=PACKAGE/'source'/name
 assert not any(p.is_symlink() for p in (source,*source.parents))
 payload=source.read_bytes();assert hashlib.sha256(payload).hexdigest()==digest,name
 if name.endswith('.py'): ast.parse(payload,filename=name);asts+=1
 target=overlay/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
(overlay/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
commands=json.loads((PACKAGE/'frozen-overlay-setup.json').read_bytes())['exact_argv']
commands['mypy']=list(commands['mypy']);commands['mypy'][commands['mypy'].index('--cache-dir')+1]=str(overlay/'.independent-cold-mypy')
commands['owned-cpu']=['.venv/bin/python','-m','pytest','-q','-p','no:cacheprovider','-o','pythonpath=src','--confcutdir=.','tests/test_visual_worker_owner.py']
env=dict(os.environ);env['PYTHONPATH']='src:.'
results={}
for label,command in commands.items():
 with (HERE/f'{label}.log').open('w') as handle:
  result=subprocess.run(command,cwd=overlay,env=env,stdout=handle,stderr=subprocess.STDOUT)
 results[label]=result.returncode;print(label,result.returncode,flush=True)
(HERE/'setup.json').write_text(json.dumps({'overlay':str(overlay),'commands':commands,'results':results,'source_count':len(manifest),'artifact_original_count':len(artifact),'python_ast_count':asts,'expected_top_hashes':expected,'live_source_overlays':[]},indent=2,sort_keys=True)+'\n')
assert all(value==0 for value in results.values()),results
