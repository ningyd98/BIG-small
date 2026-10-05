import ast
import difflib
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE=ROOT/'artifacts/research/process/20261004-ced-development/risk-supervision-fix-round-1'
OUT=ROOT/'artifacts/research/process/20261004-ced-development/t9-risk-replay-module'
OWNED=('src/cloud_edge_robot_arm/research/risk_replay.py','tests/test_research_risk_replay.py')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'source-hashes.json')=='389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8'
assert sha(BASE/'root-independent-review.md')=='336ff27096693abe4940c6946b62196ff04cd3f2a911a604adc62b5dfd98817c'
base=json.loads((BASE/'source-hashes.json').read_text())
assert len(base)==515 and not set(OWNED)&set(base)
assert not (OUT/'source').exists()
manifest=dict(base)
for name,digest in base.items():
    source=BASE/'source'/name
    assert sha(source)==digest,name
    target=OUT/'source'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
for name in OWNED:
    source=ROOT/name
    target=OUT/'source'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    manifest[name]=sha(target)
assert len(manifest)==517
manifest=dict(sorted(manifest.items()))
(OUT/'source-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
owned={'owned':list(OWNED),'source_count':517,'reference_count':515,'reference_release':'risk-supervision-fix-round-1/source','reference_manifest_sha256':sha(BASE/'source-hashes.json'),'reference_review_sha256':sha(BASE/'root-independent-review.md'),'live_dependency_overlays':[],'scope':'SOFTWARE_ONLY / RECORDED_RAW_DIAGNOSTICS','actual_risk':'UNKNOWN','actual_selection':'UNKNOWN','actual_method':'NOT_RUN','moving_source_fallback':False}
(OUT/'ownership.json').write_text(json.dumps(owned,indent=2)+'\n')
diff=''.join(''.join(difflib.unified_diff([], (OUT/'source'/name).read_text().splitlines(keepends=True),fromfile='/dev/null',tofile=name)) for name in OWNED)
(OUT/'review-package.diff').write_text(diff)
overlay=Path(tempfile.mkdtemp(prefix='risk-replay-final-'))
ast_count=0
for name,digest in manifest.items():
    source=OUT/'source'/name
    assert sha(source)==digest,name
    if name.endswith('.py'):
        ast.parse(source.read_text());ast_count+=1
    target=overlay/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
(overlay/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
python=str(ROOT/'.venv/bin/python')
ruff=str(ROOT/'.venv/bin/ruff')
tests=['tests/test_research_risk_replay.py','tests/test_research_risk_supervision.py','tests/test_research_risk_sources.py','tests/test_research_admission.py','tests/test_pose_marker_evidence.py','tests/test_rgbd_risk_calibration.py']
commands={
'frozen-owned':[python,'-m','pytest','-q','-p','no:cacheprovider','--confcutdir=.',OWNED[1]],
'frozen-cpu':[python,'-m','pytest','-q','-p','no:cacheprovider','--confcutdir=.',*tests,'-k','not compiled'],
'frozen-collected-tests':[python,'-m','pytest','--collect-only','-q','-p','no:cacheprovider','--confcutdir=.',*tests,'-k','not compiled'],
'frozen-ruff':[ruff,'check',*OWNED],
'frozen-format':[ruff,'format','--check',*OWNED],
'frozen-cold-mypy':[python,'-m','mypy','--no-incremental','--follow-imports=silent','--cache-dir',str(overlay/'mypy-cold'),OWNED[0]],
}
setup={'cwd':str(overlay),'environment':{'PYTHONPATH':'src:.','PYTHONDONTWRITEBYTECODE':'1'},'commands':commands,'source_count':517,'reference_count':515,'owned_count':2,'python_ast_count':ast_count,'source_manifest_sha256':sha(OUT/'source-hashes.json'),'no_live_production_fallback':True,'compiled_dynamics_test_excluded':True,'interpreter_link':{'path':str(overlay/'.venv'),'target':str(ROOT/'.venv'),'scope':'environment-only'}}
(OUT/'frozen-overlay-setup.json').write_text(json.dumps(setup,indent=2)+'\n')
print(json.dumps(setup,indent=2))
