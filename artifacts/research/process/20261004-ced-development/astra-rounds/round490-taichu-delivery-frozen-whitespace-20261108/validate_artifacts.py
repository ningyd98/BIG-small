"""Fresh bounded audit of the completed experiment; no model/API calls."""
import hashlib,json,re,statistics,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[5]; BASE=HERE.parent
NAMES=['round486-taichu-no-think-best-profile-20261108','round487-taichu-config-evidence-serialization-20261108','round488-taichu-json-native-subclasses-20261108','round489-taichu-isolated-jit-headers-20261108','round490-taichu-delivery-frozen-whitespace-20261108']
MAIN=BASE/NAMES[0]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def selected():return sorted(p for name in NAMES for p in (BASE/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and not p.name.endswith('.local.json'))
inputs=[]
for name in NAMES:
 for item in read(BASE/name/'plan.json')['input_sha256']:
  p=ROOT/item['path']; assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],p
  inputs.append({'path':item['path'],'sha256':item['sha256']})
plan=read(HERE/'plan.json');exceptions=plan['exact_frozen_whitespace_exceptions']
assert len(exceptions)==13
for item in exceptions:
 p=ROOT/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
(HERE/'frozen-evidence-allowlist.json').write_text(json.dumps({'plan_sha256':sha(HERE/'plan.json'),'exact_paths_only':exceptions,'full_check_status':'KNOWN_FROZEN_EVIDENCE_FAILURE','does_not_exempt_other_files':True},ensure_ascii=False,indent=2)+'\n')
partial=BASE/NAMES[1]/'diagnostic/loading-info.partial.json'
valid_json=0;compiled=0
for p in selected():
 if p.suffix=='.json':
  if p==partial:
   try:read(p)
   except json.JSONDecodeError:pass
   else:raise AssertionError('historical partial unexpectedly repaired')
  else:read(p);valid_json+=1
 if p.suffix=='.py':compile(p.read_text(),str(p),'exec');compiled+=1
pattern=re.compile(rb'(?:hf_[A-Za-z0-9]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})')
assert not any(pattern.search(p.read_bytes()) for p in selected()),'credential literal pattern hit'
comparison=read(MAIN/'comparison.json'); assert comparison['actual_model_generations']==16
assert comparison['selection']=='NO_PROFILE_PASSED_QUALITY_GATE' and comparison['selected_profile'] is None
for profile,suffix in [('base','r488'),('fla','r489')]:
 run=read(MAIN/('run-'+profile+'-'+suffix+'.json'));score=read(MAIN/('scores-'+profile+'.json'))
 assert len(run['actual_requests'])==8 and len(score['results'])==8 and not Path('/proc/'+str(run['pid'])).exists()
 for mode in ['ON','OFF']:
  rows=[x for x in run['actual_requests'] if x['mode']==mode];warm=[x for x in rows if x['mode_warm_sample']]
  group=next(x for x in comparison['groups'] if x['profile']==profile and x['thinking']==mode)
  assert len(rows)==4 and len(warm)==3 and group['quality_passes']==group['strict_json']==0
  assert statistics.median(x['end_to_end_s'] for x in warm)==group['warm_median_end_to_end_s']
 for row in run['actual_requests']:
  assert row['fp8_weights_preserved'] and sha(Path(row['raw_directory'])/'raw-response.txt')==row['raw_response_sha256']
for item in read(MAIN/'raw-manifest.local-data.json')['files']:
 p=ROOT/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
for name in ['base','fla']:
 env=read(MAIN/('final-environment-'+name+'.json'));assert env['status']=='PASS' and len(env['base68'])==68
assert read(MAIN/'weight-final-verification.json')['status']=='PASS'
assert read(BASE/NAMES[2]/'cpu-gate.json')['status']=='PASS'
assert read(BASE/NAMES[3]/'readiness-gates.json')['status']=='PASS'
index=Path(subprocess.run(['git','rev-parse','--git-path','index'],capture_output=True,text=True,check=True).stdout.strip()).resolve()
head=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
service=ROOT/'src/cloud_edge_robot_arm/model_control/service.py'
result={'status':'PASS_SOFTWARE_AND_EVIDENCE_AUDIT','fixed_input_references_verified':len(inputs),'complete_json_files_parsed':valid_json,'frozen_invalid_json_retained':[str(partial.relative_to(ROOT))],'python_files_compiled':compiled,'credential_literal_pattern_hits':[],'actual_model_generations':16,'quality_eligible_profiles':0,'original_raw_sha_unchanged':True,'weight_full_SHA_recheck':'PASS','base68_both_environments':'PASS','no_model_process_remains':True,'formal_acceptance':'NOT_PERFORMED','shared_state_before_delivery':{'HEAD':head,'index_path':str(index),'index_sha256':sha(index),'unrelated_service_sha256':sha(service)},'network_calls':0,'model_loads':0,'generation_calls':0}
(HERE/'final-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
