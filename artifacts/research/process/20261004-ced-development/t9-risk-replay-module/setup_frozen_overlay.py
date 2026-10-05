import ast,hashlib,json,shutil,tempfile
from pathlib import Path
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE=ROOT/'artifacts/research/process/20261004-ced-development/risk-supervision-fix-round-1'
OUT=ROOT/'artifacts/research/process/20261004-ced-development/t9-risk-replay-module'
manifest=json.loads((BASE/'source-hashes.json').read_text())
assert hashlib.sha256((BASE/'source-hashes.json').read_bytes()).hexdigest()=='389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8'
assert hashlib.sha256((BASE/'root-independent-review.md').read_bytes()).hexdigest()=='336ff27096693abe4940c6946b62196ff04cd3f2a911a604adc62b5dfd98817c'
root=Path(tempfile.mkdtemp(prefix='risk-replay-frozen-'))
py=0
for name,digest in manifest.items():
    source=BASE/'source'/name
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    if name.endswith('.py'):
        ast.parse(source.read_text());py+=1
(root/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
setup={'overlay':str(root),'base_manifest_sha256':hashlib.sha256((BASE/'source-hashes.json').read_bytes()).hexdigest(),'source_count':len(manifest),'python_ast_count':py,'live_dependency_overlays':[],'owned':['src/cloud_edge_robot_arm/research/risk_replay.py','tests/test_research_risk_replay.py'],'environment':{'PYTHONPATH':'src:.','PYTHONDONTWRITEBYTECODE':'1'}}
(OUT/'overlay-setup.json').write_text(json.dumps(setup,indent=2)+'\n')
(OUT/'baseline-source-hashes.json').write_bytes((BASE/'source-hashes.json').read_bytes())
print(json.dumps(setup,indent=2))
