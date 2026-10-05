from pathlib import Path
import ast,difflib,hashlib,json,os,shutil,sys
import pytest
root=Path.cwd(); artifact=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository'
sys.path[:0]=[str(root/'src'),str(root)]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
owned=json.loads((artifact/'ownership.json').read_text())['owned']
pre={str(p.relative_to(root)):sha(p) for base in ('src','tests','scripts') for p in (root/base).rglob('*.py')}
tests=['tests/test_visual_owner_repository.py','tests/test_visual_owner_registration.py','tests/test_verified_recovery_lifecycle.py','tests/test_replan_activation.py']
code=pytest.main([*tests,'-q'])
if code:raise SystemExit(code)
imports=set(owned+tests+['pyproject.toml'])
for module in list(sys.modules.values()):
 name=getattr(module,'__file__',None)
 if not name:continue
 p=Path(name).resolve()
 try:rel=str(p.relative_to(root))
 except ValueError:continue
 if rel.startswith(('src/','tests/','scripts/')) and p.suffix=='.py':imports.add(rel)
drift=[p for p in imports if p in pre and sha(root/p)!=pre[p]]
if drift:raise RuntimeError('source changed during scoped tests: '+repr(drift))
baseartifact=root/'artifacts/research/process/20261004-ced-development/t8b-module'
basehashes=json.loads((baseartifact/'fix-round-3-release-source-hashes.json').read_text())
base=baseartifact/'fix-round-3-release-source'
source=artifact/'source'
if source.exists():raise RuntimeError('source freeze already exists; do not overwrite')
source.mkdir()
for rel,h in basehashes.items():
 p=base/rel
 if sha(p)!=h:raise RuntimeError('invalid frozen base '+rel)
 q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for rel in imports:
 p=root/rel;q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
manifest={str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*')) if p.is_file()}
(artifact/'source-hashes.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
scoped={p:manifest[p] for p in sorted(imports)}
(artifact/'scoped-source-hashes.json').write_text(json.dumps(scoped,indent=2)+'\n')
setup={'base_manifest_sha256':sha(baseartifact/'fix-round-3-release-source-hashes.json'),'base_files':len(basehashes),'complete_frozen_files':len(manifest),'owned':owned,'scoped_imported_and_fixture_files':len(imports),'overlay':sorted(imports),'live_drift_during_test':drift,'test_paths':tests,'test_exitcode':int(code),'actual_model_capture_controller_calls':0,'scope':'DURABLE_BINDING_ONLY','mode_scope':'NOT_INCLUDED'}
(artifact/'freeze-setup.json').write_text(json.dumps(setup,indent=2)+'\n')
for rel in scoped:
 if rel.endswith('.py'):ast.parse((source/rel).read_bytes(),filename=rel)
diff=[]
for rel in owned:
 b=artifact/'baseline'/rel
 before=b.read_text() if b.exists() else ''
 after=(source/rel).read_text()
 diff.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(artifact/'review-package.diff').write_text(''.join(diff))
print('FREEZE',len(manifest),'scoped',len(imports),'manifest',sha(artifact/'source-hashes.json'))
