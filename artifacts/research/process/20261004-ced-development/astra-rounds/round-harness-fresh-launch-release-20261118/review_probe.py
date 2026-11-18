from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import contextlib
import json
import run_fresh as run

allocation=run.read_allocation(run.ROUND/'preallocation.json')
slot=allocation['episodes'][0]
row=dict(audit_status='VERIFIED', signal=None, physical={'safety_violation':False}, component_success=True,terminal_reason=None)
print('completed with unexpected rc=1 released',run._contained_stops(row|{'returncode':1}))
print('recognized stop with unexpected rc=1 released',run._contained_stops(row|{'component_success':False,'terminal_reason':'CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED','returncode':1}))
with TemporaryDirectory() as tmp:
 base=Path(tmp)
 checkout=base/'checkout'
 checkout.mkdir()
 rootbase=checkout/'experiments/results'
 fixture=base/'local-fixture'
 fixture.write_text('fixture')
 digest=run.sha256_file(fixture)
 resource={'--model-directory':str(base),'--asset-manifest':str(fixture),'--native-python':str(fixture)}
 roots=[rootbase/'A',rootbase/'B']
 freeze={'commit':'test','native_python_sha256':digest,'installed_launcher_sha256':digest,'asset_manifest_sha256':digest,'history_roots':[str(checkout)],'slots':{k['id']:{'config_sha256':digest,'role_binding_sha256':'r'} for k in allocation['episodes']}}
 commands=[]
 def simulated_post_claim(*args,**kwargs):
  commands.append(kwargs['cwd'].name)
  raise OSError('intentional post-claim interruption with zero dispatch')
 with contextlib.ExitStack() as st:
  for name,value in {'verify_frozen_sources':None,'_git':'test','_resources':resource,'_check_free_space':None,'_role_config':'r','load_config':None}.items():
   st.enter_context(patch.object(run,name,return_value=value))
  st.enter_context(patch.object(run.subprocess,'run',side_effect=simulated_post_claim))
  for rt in roots:
   (rt/'configs').mkdir(parents=True)
   (rt/'configs'/f"{slot['id']}.json").write_text('fixture')
   realfreeze=freeze|{'schema':run.FREEZE_SCHEMA,'preallocation_sha256':run.PREALLOCATION_SHA256}
   run.write_new(rt/'freeze-receipt.json',realfreeze)
   args=SimpleNamespace(allow_paid=True,raw_root=rt,checkout=checkout,seed=slot['seed'],resources_from=fixture,cli=fixture,freeze_sha256=run.sha256_file(rt/'freeze-receipt.json'))
   try:run.launch(args)
   except OSError as exc: print(str(exc))
  print('same seed passed real lock, history and start claim in distinct roots',commands)
  print('real provider/worker dispatches',0)
  assert commands==['A','B']
