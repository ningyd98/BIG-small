import json,hashlib
from pathlib import Path
from cloud_edge_robot_arm.research import sol_molmo_offline_regression as r
source=r.ROOT.resolve()
v3=Path('/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3')
outputs=[r.PROCESS/'offline-regression/astra-readonly-path-probe-20261115/current.json',Path('/tmp/astra-readonly-path-probe-20261115/current.json')]
rows=[]
for out in outputs:
 assert not out.exists()
 try: result=str(r.output_path(out,[v3,source]));error=None
 except Exception as exc:result=None;error=str(exc)
 rows.append({'path':str(out),'validated':result,'error':error,'exists_after':out.exists()})
print(json.dumps({'scope':'PURE_PATH_CHECK_NO_MKDIR_NO_WRITE_NO_SIMULATION','source':str(Path(r.__file__).resolve()),'source_sha256':hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest(),'source_root':str(source),'rows':rows},indent=2))
