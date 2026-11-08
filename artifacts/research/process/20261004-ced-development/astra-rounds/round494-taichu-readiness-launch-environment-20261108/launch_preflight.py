"""R494 isolated fresh-process readiness/config verification, preserving old evidence."""
import hashlib,json,os,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[5];R491=HERE.parent/'round491-taichu-constrained-json-20261108';R489=HERE.parent/'round489-taichu-isolated-jit-headers-20261108';CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
def environment():
 env=os.environ.copy()
 for key in ['PYTHONPATH','PYTHONHOME']:env.pop(key,None)
 env.update(PYTHONNOUSERSITE='1',CPATH=json.loads((R489/'readiness.json').read_text())['CPATH'],TRITON_CACHE_DIR=str(CACHE/'jit-round489/triton'),TORCHINDUCTOR_CACHE_DIR=str(CACHE/'jit-round489/inductor'),TMPDIR=str(CACHE/'jit-round489/tmp'))
 return env
def manifest():
 return [{'path':str(p.relative_to(CACHE)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((CACHE/'jit-round489').rglob('*')) if p.is_file()]
def main():
 env=environment();before=manifest();python=CACHE/'runtime-json-round491/bin/python';records=[];start=time.monotonic()
 for name,script in [('readiness-target-r494',HERE/'probe_readiness_r494.py'),('codec-preflight-r494',R491/'implementation/codec_preflight_r494.py')]:
  argv=[str(python),str(script)];out=HERE/(name+'.stdout');err=HERE/(name+'.stderr')
  with out.open('xb') as o,err.open('xb') as e:r=subprocess.run(argv,cwd=CACHE,env=env,stdout=o,stderr=e,timeout=120)
  critical=any(x in err.read_text() for x in ['fatal error:','roll back to CPU','undefined symbol','ABI'])
  records.append({'argv':argv,'rc':r.returncode,'critical_stderr':critical,'stdout_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256(err.read_bytes()).hexdigest()})
  if r.returncode or critical:raise RuntimeError(records[-1])
 state={'status':'PASS','commands':records,'env_overrides':{k:env[k] for k in ['CPATH','TRITON_CACHE_DIR','TORCHINDUCTOR_CACHE_DIR','TMPDIR','PYTHONNOUSERSITE']},'elapsed_s':time.monotonic()-start,'cache_before':before,'cache_after':manifest(),'jit_reused':True,'model_loads':0,'model_generations':0}
 with (HERE/'readiness-gates.json').open('x') as f:json.dump(state,f,ensure_ascii=False,indent=2);f.write('\n')
 print('R494_READINESS_PASS',flush=True)
if __name__=='__main__':main()
