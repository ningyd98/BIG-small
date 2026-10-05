from pathlib import Path
import ast,hashlib,json,shutil,tempfile
root=Path.cwd();a=root/'artifacts/research/process/20261004-ced-development/t8-raw-v3-module';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(a/'source-hashes.json')=='cdd6684f4dcf28e09ba0e6f2e36dc95c2640d594726d297781ef77d07bad8bc0'
assert sha(a/'report.md')=='d736c55ace79a67dbb9703799dda7e208fdcf900e57482303231186d82bacd2d'
manifest=json.loads((a/'source-hashes.json').read_text());assert len(manifest)==774
ownership=json.loads((a/'ownership.json').read_text());base=root/ownership['reference_source'];base_manifest=json.loads((base.parent/'source-hashes.json').read_text());assert len(base_manifest)==772
assert all(manifest[p]==h and sha(base/p)==h for p,h in base_manifest.items())
overlay=Path(tempfile.mkdtemp(prefix='raw-v3-independent-'))
for rel,h in manifest.items():
 p=a/'source'/rel;assert sha(p)==h
 if p.suffix=='.py':ast.parse(p.read_bytes(),filename=rel)
 q=overlay/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);assert sha(q)==h
setup={'overlay':str(overlay),'source_manifest_sha256':sha(a/'source-hashes.json'),'report_sha256':sha(a/'report.md'),'verified_files':len(manifest),'reference_identity_pass':True,'owned':ownership['owned'],'env':{'PYTHONPATH':str(overlay/'src')+':'+str(overlay),'PYTHONDONTWRITEBYTECODE':'1'},'scope':'SOURCE_CONSISTENCY_ONLY','actual_calls':0,'live_overlay_files':[]}
(a/'root-independent-setup.json').write_text(json.dumps(setup,indent=2)+'\n')
print(overlay)
