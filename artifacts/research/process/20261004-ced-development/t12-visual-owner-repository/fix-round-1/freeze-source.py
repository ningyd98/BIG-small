from pathlib import Path
import ast,difflib,hashlib,json,shutil
root=Path.cwd();a=root/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository';fix=a/'fix-round-1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();old=json.loads((a/'source-hashes.json').read_text())
owned=['src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py','tests/test_visual_owner_repository.py']
for rel in json.loads((a/'ownership.json').read_text())['owned'][:3]:
 if sha(root/rel)!=old[rel]:raise RuntimeError('read-only repository drift '+rel)
source=fix/'source';source.mkdir(exist_ok=False)
for rel,h in old.items():
 p=a/'source'/rel
 if sha(p)!=h:raise RuntimeError('baseline drift '+rel)
 q=source/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for rel in owned:shutil.copy2(root/rel,source/rel)
manifest={rel:sha(source/rel) for rel in sorted(old)}
for rel in manifest:
 if rel.endswith('.py'):ast.parse((source/rel).read_bytes(),filename=rel)
(fix/'source-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
(fix/'ownership.json').write_text(json.dumps({'owned':owned,'read_only_repository_files':json.loads((a/'ownership.json').read_text())['owned'][:3],'base_manifest_sha256':sha(a/'source-hashes.json'),'scope':'DURABLE_BINDING_ONLY','mode_scope':'NOT_INCLUDED','actual_calls':0,'frozen_source_files':len(manifest)},indent=2)+'\n')
diff=[]
for rel in owned:
 diff.extend(difflib.unified_diff((a/'source'/rel).read_text().splitlines(True),(source/rel).read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(fix/'review-package.diff').write_text(''.join(diff))
print('FROZEN',len(manifest),sha(fix/'source-hashes.json'))
