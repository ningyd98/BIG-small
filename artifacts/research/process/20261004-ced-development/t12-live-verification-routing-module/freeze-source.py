import ast,difflib,hashlib,json,pathlib,shutil,tempfile
root=pathlib.Path('/home/ningyd/文档/ChatGPT/BIGsmall')
out=root/'artifacts/research/process/20261004-ced-development/t12-live-verification-routing-module'
base=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository/fix-round-1'
base_map=json.loads((base/'source-hashes.json').read_text());assert len(base_map)==772
owned=[f'src/cloud_edge_robot_arm/repositories/event_autonomy/{p}.py' for p in ['protocol','memory','sqlite','visual_verification']]+['tests/test_visual_verification_repository.py']
new=owned[-2:]; assert not any(p in base_map for p in new)
for rel in base_map:
 data=(base/'source'/rel).read_bytes();assert hashlib.sha256(data).hexdigest()==base_map[rel]
 target=out/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_bytes(data)
for rel in owned:
 data=(root/rel).read_bytes();target=out/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
manifest={p.relative_to(out/'source').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source').rglob('*') if p.is_file()}
assert len(manifest)==774
for rel in set(base_map)-set(owned):assert manifest[rel]==base_map[rel],rel
ast_checks={}
for rel in owned[:3]:
 a=ast.parse((out/'baseline'/rel).read_text());b=ast.parse((out/'source'/rel).read_text())
 oldcls=next(x for x in a.body if isinstance(x,ast.ClassDef));newcls=next(x for x in b.body if isinstance(x,ast.ClassDef))
 oldmethods={n.name:n for n in oldcls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 newmethods={n.name:n for n in newcls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 allowed={'__init__'} if rel.endswith('/memory.py') else {'_create_schema'} if rel.endswith('/sqlite.py') else set()
 for name,n in oldmethods.items():
  if name not in allowed:assert ast.dump(n,include_attributes=False)==ast.dump(newmethods[name],include_attributes=False),(rel,name)
 ast_checks[rel]=dict(unchanged_legacy_methods=len(oldmethods)-len(allowed),allowed_incremental_methods=sorted(allowed),new_methods=sorted(set(newmethods)-set(oldmethods)))
(out/'source-hashes.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
(out/'ownership.json').write_text(json.dumps(dict(owned=owned,new_files=new,base_manifest_sha256=hashlib.sha256((base/'source-hashes.json').read_bytes()).hexdigest(),frozen_source_files=len(manifest),unchanged_basis_files=769,scope='SOURCE_ROUTE_ONLY',mode_scope='NOT_INCLUDED',verification_router_changed=False,actual_calls=0),indent=2)+'\n')
(out/'legacy-ast-isolation.json').write_text(json.dumps(ast_checks,indent=2,sort_keys=True)+'\n')
diff=[]
for rel in owned:
 before=(base/'source'/rel).read_text().splitlines(keepends=True) if rel in base_map else []
 after=(out/'source'/rel).read_text().splitlines(keepends=True)
 diff.extend(difflib.unified_diff(before,after,fromfile='a/'+rel,tofile='b/'+rel))
(out/'review-package.diff').write_text(''.join(diff))
overlay=pathlib.Path(tempfile.mkdtemp(prefix='visual-verification-frozen-'))
shutil.copytree(out/'source',overlay,dirs_exist_ok=True)
for rel,want in manifest.items():
 p=overlay/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==want
 if p.suffix=='.py':ast.parse(p.read_text(),filename=rel)
python=root/'.venv/bin/python';ruff=root/'.venv/bin/ruff';mypy=root/'.venv/bin/mypy'
tests=['tests/test_visual_verification_repository.py','tests/test_visual_owner_repository.py','tests/test_visual_owner_registration.py','tests/test_recovery_lifecycle_module.py','tests/test_verified_recovery_lifecycle.py']
setup=dict(cwd=str(overlay),source_copy=str(out/'source'),environment=dict(PYTHONPATH=f'{overlay}/src:{overlay}',PYTHONDONTWRITEBYTECODE='1'),commands={
'cpu':[str(python),'-m','pytest','-q','-p','no:cacheprovider','--confcutdir=.',*tests],
'ruff':[str(ruff),'check',*owned],
'format':[str(ruff),'format','--check',*owned],
'mypy':[str(mypy),'--no-incremental','--cache-dir',str(overlay/'mypy-cold'),*owned[:4]],
'cold-imports':[str(python),'-c','import cloud_edge_robot_arm.repositories.event_autonomy.protocol; import cloud_edge_robot_arm.repositories.event_autonomy.memory; import cloud_edge_robot_arm.repositories.event_autonomy.sqlite; import cloud_edge_robot_arm.repositories.event_autonomy.visual_verification; print("cold imports PASS; no providers instantiated")']},manifest_sha256=hashlib.sha256((out/'source-hashes.json').read_bytes()).hexdigest(),scope='SOURCE_ROUTE_ONLY',actual_calls=0)
(out/'frozen-overlay-setup.json').write_text(json.dumps(setup,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(overlay=str(overlay),manifest=setup['manifest_sha256'],count=len(manifest),ast_isolation='PASS'),indent=2))
