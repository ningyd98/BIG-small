import ast,hashlib,json
from pathlib import Path
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
OUT=ROOT/'artifacts/research/process/20261004-ced-development/t9-risk-replay-module'
BASE=ROOT/'artifacts/research/process/20261004-ced-development/risk-supervision-fix-round-1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((OUT/'source-hashes.json').read_text())
base=json.loads((BASE/'source-hashes.json').read_text())
setup=json.loads((OUT/'frozen-overlay-setup.json').read_text())
overlay=Path(setup['cwd']);ast_count=0
for name,digest in manifest.items():
    assert sha(OUT/'source'/name)==sha(overlay/name)==digest,name
    if name.endswith('.py'):ast.parse((OUT/'source'/name).read_text());ast_count+=1
for name,digest in base.items():assert sha(BASE/'source'/name)==digest,name
assert sha(BASE/'source-hashes.json')=='389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8'
assert sha(BASE/'root-independent-review.md')=='336ff27096693abe4940c6946b62196ff04cd3f2a911a604adc62b5dfd98817c'
owned=json.loads((OUT/'ownership.json').read_text())['owned']
for name in owned:assert sha(ROOT/name)==manifest[name],name
loaded=json.loads((OUT/'loaded-production-test-source-hashes.json').read_text())
assert all(manifest[k]==v for k,v in loaded.items())
results=json.loads((OUT/'frozen-check-results.json').read_text())
assert len(results)==6 and all(v['exit_code']==0 for v in results.values())
post={'source_manifest_sha256':sha(OUT/'source-hashes.json'),'source_count':len(manifest),'python_ast_count':ast_count,'overlay_and_archive_posthash_match':True,'base515_posthash_match':True,'base_manifest_and_review_unchanged':True,'owned_live_matches_archive':True,'owned_source_hashes':{name:manifest[name] for name in owned},'loaded_production_test_paths':len(loaded),'loaded_sources_all_in_manifest':True,'live_dependency_fallback':False,'all_six_frozen_commands_exit_zero':True}
(OUT/'post-source-verification.json').write_text(json.dumps(post,indent=2)+'\n')
print(json.dumps(post,indent=2))
