"""One bounded non-model CUDA/JIT probe after stage A exits."""
import fcntl, hashlib, json, os, subprocess, sys, time, traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[5]
R486=HERE.parent/'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0,str(R486/'implementation'))
from experiment_r488 import base_versions
start=time.monotonic(); state={'status':'STARTED','model_loads':0,'model_generations':0,'probe_elements':4096}
lock=(ROOT/'cache/research/.r468-r469-gpu.lock').open('a+')
try:
 state['base68']=base_versions()
 for item in json.loads((HERE/'plan.json').read_text())['input_sha256']:
  p=ROOT/item['path']; assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],p
 prep=json.loads((HERE.parent/'round489-taichu-isolated-jit-headers-20261108'/'header-preparation.json').read_text()); assert prep['status']=='PASS' and os.environ['CPATH']==prep['CPATH']
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
 compute=subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True,check=True)
 assert int(gpu.stdout.strip())>=14000 and not compute.stdout.strip(),'GPU admission gate'
 state['admission']={'free_mib':int(gpu.stdout.strip()),'compute':compute.stdout}
 import torch, triton, triton.language as tl
 @triton.jit
 def transform(X,Y,N:tl.constexpr,B:tl.constexpr):
  index=tl.program_id(0)*B+tl.arange(0,B)
  value=tl.load(X+index,index<N,other=0)
  tl.store(Y+index,value*2+1,index<N)
 driver_start=time.monotonic(); driver=triton.runtime.driver.active
 target=driver.get_current_target(); props=driver.utils.get_device_properties(0)
 state['driver_initialization_s']=time.monotonic()-driver_start
 assert target.backend=='cuda' and str(target.arch)=='89'
 import fla.utils.hardware as hardware
 facts={'available_device':hardware.get_available_device(),'device_platform':hardware.device_platform,
        'device_name':hardware.device_name,'IS_NVIDIA':hardware.IS_NVIDIA,
        'multiprocessor_count':hardware.get_multiprocessor_count(),
        'max_shared_mem':hardware.get_all_max_shared_mem()}
 assert facts['available_device']==facts['device_platform']==facts['device_name']=='cuda'
 assert facts['IS_NVIDIA'] and facts['multiprocessor_count']==props['multiprocessor_count']>1
 assert facts['max_shared_mem'][0]==props['max_shared_mem']>0
 reference=torch.arange(4096,dtype=torch.float32)*0.25
 tensor=reference.to('cuda'); output=torch.empty_like(tensor)
 launch_start=time.monotonic(); transform[(4,)](tensor,output,4096,1024)
 torch.cuda.synchronize(); state['tiny_jit_and_launch_s']=time.monotonic()-launch_start
 torch.testing.assert_close(output.cpu(),reference*2+1,rtol=0,atol=0)
 state.update(status='PASS',CPATH=os.environ['CPATH'],target={'backend':target.backend,'arch':target.arch},
    device_properties=props,fla_hardware=facts,numerical_check='EXACT_PASS',
    driver_preheated_before_B=True,readiness_total_s=time.monotonic()-start,
    compiler=subprocess.run(['gcc','--version'],capture_output=True,text=True,check=True).stdout,
    header_manifest_sha256=hashlib.sha256((HERE.parent/'round489-taichu-isolated-jit-headers-20261108'/'header-manifest.json').read_bytes()).hexdigest())
except Exception as e:
 state.update(status='NEGATIVE_READINESS_GATE',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc(),elapsed_s=time.monotonic()-start)
 print(state['traceback'],file=sys.stderr,flush=True)
finally:
 lock.close()
 with (HERE/'readiness-target-r494.json').open('x') as f: json.dump(state,f,indent=2,ensure_ascii=False); f.write('\n')
 print('READINESS',state['status'],flush=True)
if state['status']!='PASS': raise SystemExit(2)
