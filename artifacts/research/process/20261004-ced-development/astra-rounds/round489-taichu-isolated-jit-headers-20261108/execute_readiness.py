"""Launch isolated child probes only after stage A process has exited."""
import hashlib,json,os,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[5]
R486=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
base=json.loads((R486/'run-base-r488.json').read_text())
assert base['status']=='EIGHT_REQUESTS_COMPLETED' and len(base['actual_requests'])==8
assert not Path('/proc/'+str(base['pid'])).exists(),'A process still alive'
prep=json.loads((HERE/'header-preparation.json').read_text()); assert prep['status']=='PASS'
env=os.environ.copy()
for key in ['PYTHONPATH','PYTHONHOME']: env.pop(key,None)
env.update(PYTHONNOUSERSITE='1',CPATH=prep['CPATH'],TRITON_CACHE_DIR=str(CACHE/'jit-round489/triton'),
 TORCHINDUCTOR_CACHE_DIR=str(CACHE/'jit-round489/inductor'),TMPDIR=str(CACHE/'jit-round489/tmp'))
Path(env['TMPDIR']).mkdir(parents=True,exist_ok=False)
python=CACHE/'runtime-fla-round486/bin/python'
commands=[('driver-readiness',[str(python),str(HERE/'probe_readiness.py')],120),
 ('processor-fla-r489',[str(python),str(R486/'implementation/experiment_r489.py'),'fla'],120)]
records=[]; status='PASS'; start=time.monotonic()
for name,argv,timeout in commands:
 out=HERE/(name+'.stdout'); err=HERE/(name+'.stderr')
 try:
  with out.open('xb') as stdout, err.open('xb') as stderr:
   result=subprocess.run(argv,cwd=CACHE,env=env,stdout=stdout,stderr=stderr,timeout=timeout)
  text=err.read_text(); critical=any(x in text for x in ['fatal error:','roll back to CPU','undefined symbol'])
  records.append({'name':name,'argv':argv,'returncode':result.returncode,'critical_error_in_stderr':critical,
                  'stdout_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
                  'stderr_sha256':hashlib.sha256(err.read_bytes()).hexdigest()})
  if result.returncode!=0 or critical: status='NEGATIVE_GATE'; break
 except subprocess.TimeoutExpired:
  records.append({'name':name,'timeout_seconds':timeout});status='NEGATIVE_GATE_TIMEOUT';break
cache_files=[]
for p in sorted((CACHE/'jit-round489').rglob('*')):
 if p.is_file(): cache_files.append({'path':str(p.relative_to(CACHE)),'bytes':p.stat().st_size,
      'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(HERE/'readiness-cache-manifest.json').write_text(json.dumps({'stage':'pre-model driver/numerical/processor probe','files':cache_files},indent=2)+'\n')
summary={'status':status,'commands':records,'elapsed_s':time.monotonic()-start,'env_overrides':{key:env[key] for key in ['CPATH','TRITON_CACHE_DIR','TORCHINDUCTOR_CACHE_DIR','TMPDIR','PYTHONNOUSERSITE']},'A_pid_exited':True,'model_loads':0,'model_generations':0,'B_driver_readiness_preheated':True}
(HERE/'readiness-gates.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print('ALL_READINESS_GATES',status,round(summary['elapsed_s'],3),flush=True)
if status!='PASS': raise SystemExit(2)
