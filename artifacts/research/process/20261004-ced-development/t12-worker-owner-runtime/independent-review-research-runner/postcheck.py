"""Verify original774/807 and exact772 base remain untouched after read-only review."""
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
PACKAGE=ROOT/'artifacts/research/process/20261004-ced-development/t12-worker-owner-runtime'
REVIEW=PACKAGE/'independent-review-research-runner'
BASE=ROOT/'artifacts/research/process/20261004-ced-development/t12-visual-owner-repository/fix-round-1'
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source=json.loads((PACKAGE/'source-hashes.json').read_text())
original_artifacts=json.loads((PACKAGE/'artifact-hashes.json').read_text())
base=json.loads((BASE/'source-hashes.json').read_text())
assert sha(BASE/'source-hashes.json')=='0271d4785ef84c7a4f5fdcf4efd0ded0e9baccec02f7351f04d7b9bde4a917d6'
assert len(base)==772 and len(source)==774 and len(original_artifacts)==807
owned=set(json.loads((PACKAGE/'ownership.json').read_text())['owned'])
assert set(source)-set(base)==owned and set(base)-set(source)==set()
assert all(source[name]==digest for name,digest in base.items())
overlay=Path(json.loads((REVIEW/'setup.json').read_text())['overlay'])
pycount=0
for name,digest in source.items():
    archived=PACKAGE/'source'/name
    assert sha(archived)==digest, name
    assert sha(overlay/name)==digest, name
    if name.endswith('.py'):
        assert ast.dump(ast.parse(archived.read_text()))==ast.dump(ast.parse((overlay/name).read_text())), name
        pycount+=1
for name,digest in base.items():
    assert sha(BASE/'source'/name)==digest, name
    assert sha(PACKAGE/'source'/name)==digest, name
for name,digest in original_artifacts.items():
    assert sha(PACKAGE/name)==digest, name
assert sha(PACKAGE/'report.md')=='37c79cefb6cc47a455bb9110fb34b71a8a5b82bde9b75c1abff7526fe8cf3791'
assert sha(PACKAGE/'source-hashes.json')=='f0c84833daf10c8378b8658155b4995b3e9451037cb85a61aa0a70ac155ccfa4'
assert sha(PACKAGE/'artifact-hashes.json')=='120aba8a1b0c9fda92a2cc4b8c449fd35ce454301a3b2d6f9bd90d826303372c'
live_drift=[name for name,digest in source.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]
assert not live_drift, live_drift
matrix=json.loads((REVIEW/'independent-matrix.log').read_text())
result={'verdict':'PASS_INTEGRITY', 'base_count':len(base), 'source_count':len(source),
 'original_artifact_count':len(original_artifacts),'ast_count':pycount,
 'base_manifest_sha256':sha(BASE/'source-hashes.json'), 'source_manifest_sha256':sha(PACKAGE/'source-hashes.json'),
 'original_artifact_manifest_sha256':sha(PACKAGE/'artifact-hashes.json'),
 'live_source_drift':live_drift,'independent_software_probes':matrix['count'],
 'owned': {name:source[name] for name in sorted(owned)},'production_edits':[],
 'review_uses_live_dependency_overlay':False,'simulator_or_controller_calls':0,'provider_requests':0}
(REVIEW/'postcheck.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
