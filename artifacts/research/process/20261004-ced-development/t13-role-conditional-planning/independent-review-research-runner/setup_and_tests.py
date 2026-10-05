"""Independent archived-only provider review; no live production overlays."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ROOT = PACKAGE.parents[4]
EXPECTED = {'source-hashes.json':'6bf11ea1413350a3f7769b579949f66fcb8e5fae98accafc4f90621131562149', 'scoped-source-hashes.json':'75a7db308c4f884f057aadd34cf37c105d90b95ce0f7904fee45932becb07737', 'report.md':'24a5bc43a5ef81b37c2eac71a94ba0defd935f35ddc97d047b38127c63f1e6dc'}
for name,digest in EXPECTED.items():
    assert hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest()==digest,name
manifest=json.loads((PACKAGE/'source-hashes.json').read_bytes())
scoped=json.loads((PACKAGE/'scoped-source-hashes.json').read_bytes())
assert len(manifest)==776 and len(scoped)==144
assert all(manifest[name]==digest for name,digest in scoped.items())
overlay=Path(tempfile.mkdtemp(prefix='independent-t13-conditional-776-'))
asts=0
for name,digest in manifest.items():
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    source=PACKAGE/'source'/name
    assert not any(p.is_symlink() for p in (source,*source.parents))
    payload=source.read_bytes()
    assert hashlib.sha256(payload).hexdigest()==digest,name
    if name.endswith('.py'):
        ast.parse(payload,filename=name);asts+=1
    target=overlay/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
(overlay/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
python=str(overlay/'.venv/bin/python')
owned=json.loads((PACKAGE/'ownership.json').read_bytes())['owned']
common=[python,'-m','pytest','-q','-p','no:cacheprovider','-o',f'pythonpath={overlay}/src:{overlay}',f'--confcutdir={overlay}']
commands={
 'owned-cpu':common+['tests/test_role_conditional_planning.py'],
 'related-cpu':common+json.loads((PACKAGE/'freeze-setup.json').read_bytes())['tests'],
 'ruff':[str(ROOT/'.venv/bin/ruff'),'check',*owned],
 'format':[str(ROOT/'.venv/bin/ruff'),'format','--check',*owned],
 'cold-mypy':[python,'-m','mypy','--no-incremental','--follow-imports=silent',owned[0]],
}
env=dict(os.environ);env['PYTHONPATH']=f'{overlay}/src:{overlay}'
results={}
for label,command in commands.items():
    with (HERE/f'{label}.log').open('w') as handle:
        result=subprocess.run(command,cwd=overlay,env=env,stdout=handle,stderr=subprocess.STDOUT)
    results[label]=result.returncode
    print(label,result.returncode,flush=True)
setup={'overlay':str(overlay),'source_count':len(manifest),'scoped_count':len(scoped),'python_ast_count':asts,'commands':commands,'results':results,'package_top_hashes':EXPECTED,'live_source_overlays':[],'actual_network_renderer_provider_actions':0}
(HERE/'setup.json').write_text(json.dumps(setup,indent=2,sort_keys=True)+'\n')
assert all(value==0 for value in results.values()),results
