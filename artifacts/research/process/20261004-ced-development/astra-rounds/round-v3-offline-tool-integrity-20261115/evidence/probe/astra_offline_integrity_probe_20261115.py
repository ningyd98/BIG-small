import sys, threading, json, hashlib
from pathlib import Path
from cloud_edge_robot_arm.research import sol_molmo_offline_regression as r
rows=[]
def probe(label):
 try:
  sys.audit('socket.connect',None,('127.0.0.1',9));rows.append({'thread':label,'synthetic_audit':'NOT_BLOCKED'})
 except RuntimeError as e:rows.append({'thread':label,'synthetic_audit':'BLOCKED','reason':str(e)})
with r.NetworkDenyGuard() as g:
 probe('main');t=threading.Thread(target=probe,args=('new-thread',));t.start();t.join()
network={'probe':'synthetic sys.audit only, no socket created, no network attempted','results':rows,'attempts':g.attempts}
b=Path('/tmp/offline-review-baseline-2pagohmw/snapshot.json')
v=Path('/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3')
m=r.load_v3_manifest(v,b);expected=r._expected_sources(m);receipt=r.validate_source_imports(r.ROOT,expected)
print(json.dumps({'network':network,'trimmed_snapshot':{'path':str(b),'sha256':hashlib.sha256(b.read_bytes()).hexdigest(),'source_mapping_count':len(json.loads(b.read_bytes())['source_mapping']),'verified_v3_files':m.verified_files,'expected_sources':len(expected),'validated_modules':len(receipt['modules']),'result':'ACCEPTED_WITH_MISSING_FROZEN_SOURCE_MEMBERS'}},indent=2))
