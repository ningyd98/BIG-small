"""Prepare exact source guards and disjoint, once-only R413 assignments."""
from collections import defaultdict
from datetime import UTC,datetime
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND=Path(__file__).resolve().parent
BASE=ROUND.parent
PLAN=json.loads((ROUND/'plan.json').read_text())
PY=str(ROOT/'.venv/bin/python')
NODE=str(ROOT/'cache/node-v22.23.3-linux-x64/bin/node')
PLUGIN=BASE/'round235-p6-t2-bootstrap-json-and-startup-prerequisites-20261015/implementation'

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as out:json.dump(value,out,ensure_ascii=False,indent=2);out.write('\n')

def pin(path):
 raw=path.read_bytes()
 return {'path':str(path.relative_to(ROOT)),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

for row in PLAN['inputs']:
 assert pin(ROOT/row['path'])==row,row['path']
head=subprocess.run(['git','rev-parse','HEAD'],text=True,capture_output=True,check=True).stdout.strip()
branch=subprocess.run(['git','branch','--show-current'],text=True,capture_output=True,check=True).stdout.strip()
assert head==PLAN['baseline']['head'] and branch==PLAN['baseline']['branch']
for script in ROUND.glob('*.py'):ast.parse(script.read_text(),filename=str(script))
for script in (ROUND/'adapters').glob('*.py'):ast.parse(script.read_text(),filename=str(script))
for path in [ROOT/'.venv/bin/python',Path(NODE),ROOT/'dashboard/node_modules/@playwright/test/cli.js',ROOT/'dashboard/node_modules/openapi-typescript/bin/cli.js',ROOT/'cache/playwright/chromium-1228/chrome-linux64/chrome']:
 assert path.is_file(),str(path)
(Round_inputs:=ROUND/'inputs').mkdir(exist_ok=True)
legacy=BASE/'round381-t3-commit-close-thread-affinity-20261101/inputs/legacy-goldens.json'
with (ROUND/'inputs/legacy-goldens.json').open('xb') as out:out.write(legacy.read_bytes())
assert pin(legacy)['sha256']==pin(ROUND/'inputs/legacy-goldens.json')['sha256']
common={k:os.environ[k] for k in ['HOME','USER','LOGNAME','LD_LIBRARY_PATH','DISPLAY','XAUTHORITY','__EGL_VENDOR_LIBRARY_FILENAMES'] if k in os.environ}
common.update(PATH=str(ROOT/'cache/node-v22.23.3-linux-x64/bin')+':'+str(ROOT/'.venv/bin')+':/usr/bin:/bin',
 LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
 PYTHONPATH=':'.join(map(str,[ROOT/'src',ROOT,ROOT/'tests',ROUND/'adapters',PLUGIN])),MUJOCO_GL='egl',
 REAL_MOTION_DISPATCH_ENABLED='false',GIT_OPTIONAL_LOCKS='0',GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='diff.ignoreSubmodules',GIT_CONFIG_VALUE_0='all',
 PLAYWRIGHT_BROWSERS_PATH=str(ROOT/'cache/playwright'),PLAYWRIGHT_MUJOCO_RUNTIME='0')
check_code='import json;from cloud_edge_robot_arm.simulation.environment import detect_environment;print(json.dumps(detect_environment().to_jsonable()))'
env_report=subprocess.run([PY,'-c',check_code],env=common,capture_output=True,text=True,timeout=120,check=True)
with (ROUND/'preflight/environment.stdout').open('x') as f:f.write(env_report.stdout)
with (ROUND/'preflight/environment.stderr').open('x') as f:f.write(env_report.stderr)
external=json.loads(env_report.stdout)
phase12_ready=external['level'] not in ['ISAAC_READY','MOVEIT_READY','ROS2_READY'] and not common.get('ISAAC_SIM_ROOT') and not common.get('ROS_DISTRO')
save(ROUND/'preflight/external-runtime-prerequisite.json',{'accepted_software_only':phase12_ready,'report':external,'planner_external_providers':'Source-pinned adapter returns BLOCKED_BY_ENV; no model credentials inherited.'})
stages=[]

def stage(id,argv,cap,cwd=None,**extra):
 d=ROUND/'implementation'/id
 d.mkdir(parents=True,exist_ok=False)
 for name in ['resources','resources-a','r223/resources','r223/cases','tmp','cache','runtime']:(d/name).mkdir(parents=True,exist_ok=True)
 env=dict(common)
 env.update(R413_STAGE_DIR=str(d),R413_PYTEST_EVENTS=str(d/'pytest-events.jsonl'),
  PYTHONPYCACHEPREFIX=str(d/'pycache'),RUFF_CACHE_DIR=str(d/'ruff-cache'),MYPY_CACHE_DIR=str(d/'mypy-cache'),
  MODEL_CONTROL_DB=str(d/'runtime/model_control.db'),SIMULATION_RUNTIME_DB=str(d/'runtime/simulation_runtime.db'),DASHBOARD_ARTIFACT_ROOT=str(d/'runtime'),
  TMPDIR=str(d/'tmp'),XDG_CACHE_HOME=str(d/'cache'),BIGSMALL_R158_COMMAND='final_new23',BIGSMALL_R158_LEGACY_GOLDENS=str(ROUND/'inputs/legacy-goldens.json'),
  BIGSMALL_R158_T2_RESOURCE_DIR=str(d/'resources'),BIGSMALL_R175_RESOURCE_DIR=str(d/'resources-a'),BIGSMALL_R235_PREREQUISITE_RECORD=str(d/'prerequisite.json'),
  BIGSMALL_R223_RESOURCE_ROOT=str(d/'r223/resources'),BIGSMALL_R223_CASE_ROOT=str(d/'r223/cases'),R399_EVIDENCE_DIR=str(d),BIGSMALL_E2E_ARTIFACT_ROOT=str(d/'runtime'))
 spec={'id':id,'directory':str(d),'argv':[s.replace('<stage>',str(d)) for s in argv],'cwd':str(cwd or ROOT),'env':env,'timeout_s':cap,
  'resource_dirs':['resources','resources-a','r223/resources','r223/cases','tmp','cache','runtime'],**extra}
 stages.append(spec)
 return spec

collection=json.loads((ROUND/'preflight/collection.json').read_text())['nodes']
nodes=[r['nodeid'] for r in collection]
assert len(nodes)==len(set(nodes))==4753
excluded=PLAN['collection']['external_dataset_not_run']
modules=defaultdict(list)
closure=[]
for node in nodes:
 if node in excluded:continue
 if node.startswith('tests/test_operational_runtime_closure.py::'):closure.append(node)
 else:modules[node.split('::')[0]].append(node)
assert len(closure)==94 and len(modules)==286
caps=PLAN['python_execution']['node_caps_seconds']

def pytest_stage(id,assigned,cap,tail=False):
 spec=stage(id,[PY,'-m','pytest','-q','-p','no:cacheprovider','-p','r413_events','-p','r235_startup_prerequisite','--tb=short',
               '--junitxml=<stage>/junit.xml',f'--basetemp=/tmp/bigsmall-r413-{id}',*assigned],cap,
               nodes=assigned,continue_unstarted=tail,tail_timeout_s=caps['never_started_tail_node'])
 return spec

# Repaired key modules are still tested exactly once within the full assignment.
priority=['tests/test_eteac_retry_lock_regression.py','tests/test_legacy_reference_mode_compatibility.py']
for i,name in enumerate(priority,1):pytest_stage(f'py-key-{i:02}',modules.pop(name),caps['ordinary_module'],True)
long=PLAN['python_execution']['utc_nodes']+PLAN['python_execution']['other_t3_nodes']
for i,node in enumerate(long,1):pytest_stage(f'py-t3-{i:02}',[node],caps['utc_each'] if i<=2 else caps['other_t3_each'])
for i,node in enumerate(n for n in closure if n not in long):pytest_stage(f'py-closure-{i+1:03}',[node],caps['other_closure_each'])
for i,name in enumerate(sorted(modules),1):pytest_stage(f'py-module-{i:03}',modules[name],caps['ordinary_module'],True)
# Static analysis is restricted to the declared current development scope.
tracked=subprocess.run(['git','ls-files','-z','--cached'],capture_output=True,check=True).stdout
python_paths=sorted(p.decode() for p in tracked.split(b'\0') if p and p.decode().endswith('.py') and (Path(p.decode()).parts[0] in {'src','scripts','tests'} or len(Path(p.decode()).parts)==1))
save(ROUND/'preflight/static-python-scope.json',{'paths':python_paths,'note':'Current tracked src/scripts/tests and root Python files. No artifacts or gitlinks.'})
stage('static-compile',[PY,'-m','compileall','-q','src','scripts','tests'],300)
stage('static-ruff-format',[PY,'-m','ruff','format','--check',*python_paths],600)
stage('static-ruff-check',[PY,'-m','ruff','check','--no-cache','--output-format','json',*python_paths],600)
stage('static-mypy',[PY,'-m','mypy','--cache-dir','<stage>/mypy-cache','-p','cloud_edge_robot_arm'],1800)
for id,argv in [('docs',['scripts/check_docs.py','--json']),('comments',['scripts/check_chinese_comments.py']),('secrets',['scripts/check_model_control_secrets.py']),('pip',['-m','pip','check']),('contracts',['scripts/validate_contract_examples.py'])]:
 stage('static-'+id,[PY,*argv],300)
DASH=ROOT/'dashboard'
for id,argv,cap in [
 ('type-app',['typescript/bin/tsc','-p','tsconfig.app.json','--incremental','--tsBuildInfoFile','<stage>/app.tsbuildinfo'],300),
 ('type-node',['typescript/bin/tsc','-p','tsconfig.node.json','--tsBuildInfoFile','<stage>/node.tsbuildinfo'],300),
 ('eslint',['eslint/bin/eslint.js','.'],300),
 ('prettier',['prettier/bin/prettier.cjs','--check','src/**/*.{ts,tsx,css}','tests/**/*.ts'],300),
 ('vitest',['vitest/vitest.mjs','run','--maxWorkers=1','--reporter=default','--reporter=junit','--outputFile.junit=<stage>/junit.xml'],900),
 ('build',['vite/bin/vite.js','build','--outDir','<stage>/dist','--emptyOutDir'],600)]:
 stage('dashboard-'+id,[NODE,str(DASH/'node_modules'/argv[0]),*argv[1:]],cap,DASH)
stage('dashboard-api',[PY,str(ROUND/'api_compare.py')],1200,DASH)
# Browser overlays: only round paths and per-stage environment labels change.
previous=BASE/'round408-browser-workflow-retest-20261103'
for name in ['playwright.default.config.ts','playwright.research.config.ts']:
 raw=(previous/'adapters'/name).read_text();derived=raw.replace(str(previous),str(ROUND)).replace('R408_STAGE_DIR','R413_STAGE_DIR')
 with (ROUND/'adapters'/name).open('x') as out:out.write(derived)
 assert derived.replace(str(ROUND),str(previous)).replace('R413_STAGE_DIR','R408_STAGE_DIR')==raw
(ROUND/'adapters/research-tests').mkdir()
p=previous/'adapters/research-tests/research-evidence.spec.ts'
raw=p.read_text();derived=raw.replace('R408_STAGE_DIR','R413_STAGE_DIR')
with (ROUND/'adapters/research-tests/research-evidence.spec.ts').open('x') as out:out.write(derived)
assert derived.replace('R413_STAGE_DIR','R408_STAGE_DIR')==raw
for id,config,cap,ports in [('browser-default','playwright.default.config.ts',600,[8000,5173]),('browser-research','playwright.research.config.ts',300,[8123,5199])]:
 stage(id,[NODE,str(DASH/'node_modules/@playwright/test/cli.js'),'test','--config',str(ROUND/'adapters'/config),'--workers=1','--retries=0'],cap,DASH,ports=ports)
copy_rows=[]
audit=json.loads((previous/'input-audit.json').read_text())['research_fixture_exact20']
assert len(audit)==20
source_root=ROOT/Path(audit[0]['path']).parent
for row in audit:
 original=ROOT/row['path'];assert pin(original)==row
 target=ROUND/'implementation/browser-research'/original.relative_to(source_root)
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as out:out.write(original.read_bytes())
 assert pin(target)['sha256']==row['sha256']
 copy_rows.append({'original':row,'copy':pin(target)})
save(ROUND/'preflight/browser-inputs.json',{'path_only_overlays_verified':True,'copies':copy_rows})
p12=ROUND/'implementation/phase12-full/artifacts'
run=stage('phase12-full',[PY,'scripts/run_phase12_experiments.py','--profile','full','--output',str(p12)],14400)
run['precondition_software_only']=phase12_ready
stage('phase12-analysis',[PY,'scripts/analyze_phase12_results.py','--profile','full','--output',str(p12)],1800,requires_success='phase12-full',requires_files=[str(p12/'manifests/run_manifests.jsonl'),str(p12/'runs/raw_runs.jsonl')])
stage('phase12-export',[PY,'scripts/export_phase12_thesis_assets.py','--profile','full','--output',str(p12)],1800,requires_success='phase12-analysis')
stage('phase12-verify',[PY,'scripts/verify_phase12.py','--full','--skip-isaac','--skip-model-runtime','--artifact-root',str(p12),'--output','<stage>/verification'],1800,requires_success='phase12-export')
assigned=[n for s in stages for n in s.get('nodes',[])]
assert len(assigned)==len(set(assigned))==4751 and sorted(assigned+excluded)==sorted(nodes)
save(ROUND/'assignment.json',{'collected_count':4753,'software_count':4751,'external_not_run':excluded,'stages':[{'id':s['id'],'nodes':s['nodes'],'timeout_s':s['timeout_s']} for s in stages if 'nodes' in s]})
for s in stages:save(ROUND/'specs'/f"{s['id']}.json",s)
save(ROUND/'stages.json',stages)
# Freeze sources/configs, key original evidence, driver and derived fixtures; no recursive historical walk.
a=json.loads((ROUND/'preflight/source-before.json').read_text())['files']
pins={x['path']:x for x in a if Path(x['path']).parts[0] not in {'output','analysis_draft.md'} and (ROOT/x['path']).is_file()}
for row in PLAN['inputs']:pins[row['path']]=row
for p in list(ROUND.glob('*.py'))+list((ROUND/'adapters').rglob('*'))+[ROUND/'plan.json',ROUND/'inputs/legacy-goldens.json']:
 if p.is_file():pins[str(p.relative_to(ROOT))]=pin(p)
for row in copy_rows:pins[row['copy']['path']]=row['copy']
save(ROUND/'preflight/runtime-source-pins.json',{'files':list(pins.values()),'count':len(pins),'official_source_tree_hash':PLAN['baseline']['official_source_tree_hash'],'source_commit':head})
save(ROUND/'preflight/prepared.json',{'ready':True,'source_commit':head,'branch':branch,'plan_sha256':hashlib.sha256((ROUND/'plan.json').read_bytes()).hexdigest(),
 'created_utc':datetime.now(UTC).isoformat(),'collection_reused':True,'python_assigned':len(assigned),'python_stages':sum('nodes' in s for s in stages),
 'all_stages':len(stages),'python_initial_caps_sum':sum(s['timeout_s'] for s in stages if 'nodes' in s),'python_contingent_tail_caps_sum':sum(len(s['nodes'])*s['tail_timeout_s'] for s in stages if s.get('continue_unstarted')),
 'non_python_caps_sum':sum(s['timeout_s'] for s in stages if 'nodes' not in s),'phase12_software_prerequisite':phase12_ready,'owned_cleanup_cap_each_s':30,
 'source_status_scope':'Tracked development-source diff empty; entire workspace contains protected dirty gitlinks and historical raw/untracked files. Not a globally clean workspace.'})
print(json.dumps({'ready':True,'stages':len(stages),'assigned':len(assigned),'phase12_ready':phase12_ready}))
