from pathlib import Path
import ast,difflib,hashlib,json,shutil,sys
import pytest
root=Path.cwd();a=root/'artifacts/research/process/20261004-ced-development/t13-role-conditional-planning';owned=['src/cloud_edge_robot_arm/cloud/replanning/role_conditional_planning.py','tests/test_role_conditional_planning.py'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.path[:0]=[str(root/'src'),str(root)]
pre={str(p.relative_to(root)):sha(p) for folder in ('src','tests','scripts') for p in (root/folder).rglob('*.py')}
tests=['tests/test_role_conditional_planning.py','tests/test_conditional_repair_intent.py','tests/test_role_visual_repair.py']
code=pytest.main([*tests,'-q'])
if code:raise SystemExit(code)
imports=set(owned+tests+['pyproject.toml'])
for module in list(sys.modules.values()):
 f=getattr(module,'__file__',None)
 if not f:continue
 p=Path(f).resolve()
 try:rel=str(p.relative_to(root))
 except ValueError:continue
 if rel.startswith(('src/','tests/','scripts/')) and p.suffix=='.py':imports.add(rel)
drift=[p for p in imports if p in pre and sha(root/p)!=pre[p]]
if drift:raise RuntimeError('imported source changed during verification '+repr(drift))
owner=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository/fix-round-1'
pure=root/'artifacts/research/process/20261004-ced-development/t13-conditional-planning-module/fix-round-1'
source=a/'source';source.mkdir(exist_ok=False)
base=json.loads((owner/'source-hashes.json').read_text())
for rel,h in base.items():
 p=owner/'source'/rel
 if sha(p)!=h:raise RuntimeError('owner base archive drift '+rel)
 q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
puremanifest=json.loads((pure/'source-hashes.json').read_text())
for rel in json.loads((pure/'ownership.json').read_text())['owned']:
 if sha(pure/'source'/rel)!=puremanifest[rel] or sha(root/rel)!=puremanifest[rel]:raise RuntimeError('pure conditional reference drift '+rel)
 q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(pure/'source'/rel,q)
for rel in imports:
 p=root/rel;q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
manifest={str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*')) if p.is_file()}
for rel in manifest:
 if rel.endswith('.py'):ast.parse((source/rel).read_bytes(),filename=rel)
(a/'source-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
(a/'scoped-source-hashes.json').write_text(json.dumps({p:manifest[p] for p in sorted(imports)},indent=2)+'\n')
(a/'ownership.json').write_text(json.dumps({'owned':owned,'read_only_tested_references':sorted(imports-set(owned)),'scope':'PLANNING_ONLY','actual_calls':0,'frozen_files':len(manifest),'owner_base_manifest_sha256':sha(owner/'source-hashes.json'),'conditional_fix1_manifest_sha256':sha(pure/'source-hashes.json')},indent=2)+'\n')
(a/'baseline-hashes.json').write_text(json.dumps({p:None for p in owned},indent=2)+'\n')
(a/'freeze-setup.json').write_text(json.dumps({'tests':tests,'exitcode':int(code),'imports':sorted(imports),'import_source_drift':drift,'frozen_files':len(manifest),'scoped_files':len(imports),'owned_existing_file_edits':[],'owner_source_five_match':all(sha(root/p)==base[p] for p in json.loads((owner.parent/'ownership.json').read_text())['owned'])},indent=2)+'\n')
diff=[]
for rel in owned:diff.extend(difflib.unified_diff([], (source/rel).read_text().splitlines(True),fromfile='/dev/null',tofile='b/'+rel))
(a/'review-package.diff').write_text(''.join(diff))
print('FROZEN',len(manifest),'scoped',len(imports),'manifest',sha(a/'source-hashes.json'))
