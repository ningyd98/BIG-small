from pathlib import Path
import json,hashlib
from cloud_edge_robot_arm.research import sol_molmo_offline_regression as r
v=Path('/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3')
p=v/'fixed-042001'
entries=json.loads((p/'evidence-manifest.json').read_bytes())['files']
case=r.FrozenCase(p,{x['path']:x for x in entries},{'case':'fixed-042001'})
obs=r.load_observation(case,'before')
provider=r.FrozenPointProvider(case)
rows=[]
for i in range(1,5):
 phrase=case.json(f'raw/molmo/request-{i:04d}/started.json')['phrase']
 bound=provider.point(obs,phrase)
 rows.append({'i':i,'phrase':phrase,'recorded_phase':bound.evidence['phase'],'observation_id':obs.observation_id,'frame_id':obs.frame_id,'captured_at':obs.captured_at.isoformat(),'checksum':bound.observation_checksum})
print(json.dumps({'scope':'READ_ONLY_FROZEN_PROVIDER_PROBE_NO_INFERENCE_NO_SIMULATION','source':str(Path(r.__file__).resolve()),'source_sha256':hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest(),'replay_calls':provider.replay_calls,'rows':rows,'model_loads':provider.model_loads_started,'generation_calls':provider.generation_calls_started,'failure_evidence':'Third call accepted same before observation as post-cloud'},indent=2))
