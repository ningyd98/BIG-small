"""One authorized model process after complete software qualification."""
import ast,hashlib,importlib.util,json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent;ROOT=HERE.parents[5];CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473';R494=HERE.parent/'round494-taichu-readiness-launch-environment-20261108'
def read(p):return json.loads(p.read_text())
def save(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
for roundname in ['round497-taichu-byte-native-json-backend-20261108','round499-taichu-native-token-subset-20261108','round500-taichu-secondary-eos-mask-20261108','round502-taichu-nfc-fixture-oracle-20261108','round503-taichu-raw-bpe-witness-20261108','round504-taichu-cpu-window-continuation-20261108']:
 for row in read(HERE.parent/roundname/'plan.json')['input_sha256']:
  p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p
cpu=read(HERE/'cpu-contract-r504.json');assert cpu['status']=='PASS' and len(cpu['results'])==21 and len(cpu['added_token_ASCII_witnesses'])==27
assert cpu['all_six_original_valid_pass'] and cpu['tokenization_proof']['all21_ID_stream_hashes_match']
assert read(HERE/'environment.json')['status']=='PASS' and read(HERE/'environment.json')['total_distributions']==72
assert read(HERE/'codec-preflight.json')['status']=='PASS' and read(R494/'readiness-gates.json')['status']=='PASS'
assert not any(x in (HERE/'codec-preflight.stderr').read_text() for x in ['fatal error:','roll back to CPU','undefined symbol'])
assert hashlib.sha256((HERE/'implementation/byte_decoder_r500.py').read_bytes()).hexdigest()==cpu['adapter_sha256']
runner=HERE/'implementation/run_constrained_profiles_r504.py';ast.parse(runner.read_text())
spec=importlib.util.spec_from_file_location('readiness_launcher',R494/'launch_preflight.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);env=module.environment();argv=[str(CACHE/'runtime-llguidance-round497/bin/python'),str(runner),'fla']
invocation={'argv':argv,'cwd':str(CACHE),'env_overrides':{k:env[k] for k in ['CPATH','TRITON_CACHE_DIR','TORCHINDUCTOR_CACHE_DIR','TMPDIR','PYTHONNOUSERSITE']},'sources':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [runner,HERE/'implementation/byte_decoder_r500.py',HERE/'cpu-contract-r504.json',HERE/'codec-preflight.json',HERE/'tokenization-proof.json']],'authorized_model_loads':1,'stage_a_generation_cap':8,'total_generation_cap':24,'warm_JIT_reused':True}
save(HERE/'stage-a-invocation.json',invocation)
start=time.monotonic()
with (HERE/'run-stage-a.stdout').open('xb') as out,(HERE/'run-stage-a.stderr').open('xb') as err:
 process=subprocess.Popen(argv,cwd=CACHE,env=env,stdout=out,stderr=err,start_new_session=True)
 try:rc=process.wait(timeout=max(1,1794154140-time.time()))
 except subprocess.TimeoutExpired:
  process.terminate()
  try:rc=process.wait(timeout=10)
  except subprocess.TimeoutExpired:process.kill();rc=process.wait(timeout=5)
save(HERE/'stage-a-launch-result.json',{'rc':rc,'model_process_pid':process.pid,'elapsed_s':time.monotonic()-start})
print('MODEL_PROCESS_FINISHED',rc,round(time.monotonic()-start,3),flush=True)
