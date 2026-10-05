from pathlib import Path
import ast
import base64
import hashlib
import json
import os
import subprocess
import tempfile

root = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
artifact = root / 'artifacts/research/process/20261004-ced-development/t7b-pose-marker-motion-development'
scratch = Path(tempfile.mkdtemp(prefix='bigsmall-marker-motion-review-'))
base = root / 'artifacts/research/process/20261004-ced-development/t8b-module'
for manifest_path, source_path in [(base / 'fix-round-3-release-source-hashes.json', base / 'fix-round-3-release-source'),(artifact / 'source-hashes.json',artifact / 'source')]:
    for name, digest in json.loads(manifest_path.read_text()).items():
        data = (source_path / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest,name
        if name.endswith('.py'):
            ast.parse(data,filename=name)
        destination = scratch / name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(data)
artifact_manifest = json.loads((artifact / 'artifact-hashes.json').read_text())
for name, digest in artifact_manifest.items():
    assert hashlib.sha256((artifact / name).read_bytes()).hexdigest() == digest,name
raw_manifest = json.loads((artifact / 'attempt-1/raw-hashes.json').read_text())
for name, digest in raw_manifest.items():
    assert hashlib.sha256((artifact / 'attempt-1' / name).read_bytes()).hexdigest() == digest,name
environment = dict(os.environ,PYTHONPATH=f'{scratch / "src"}:{scratch}')
code = '''
import ast,base64,hashlib,json,math
from pathlib import Path
from dataclasses import asdict
import numpy as np
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria,sample_physical_observation,evaluate_evidence
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration,detect_pose_marker
artifact=Path(ARTIFACT_PATH)
run=artifact/'attempt-1'
load=lambda n:json.loads((run/n).read_text())
rows=lambda n:[json.loads(line) for line in (run/n).read_text().splitlines()]
summary=load('summary.json')
physics=rows('raw-physics.jsonl')
actuators=rows('raw-actuators.jsonl')
events=rows('raw-actions.jsonl')
commands=load('commands.json')
assert len(physics)==4807 and len(actuators)==4806 and len(events)==9 and len(commands)==743
assert [r['physics_step'] for r in physics]==list(range(4807))
assert [r['physics_step'] for r in actuators]==list(range(1,4807))
assert [r['command_seq'] for r in commands]==list(range(1,744))
for r in [*physics,*actuators,*events,*commands]:
    assert r['episode_id']==summary['episode_id']
criteria=CompletionCriteria('object','target_region')
rebuilt=[sample_physical_observation(PhysicsStepObservation(**r),criteria) for r in physics]
assert json.loads(json.dumps([asdict(r) for r in rebuilt]))==load('physical-samples.json')
score=asdict(evaluate_evidence(rebuilt,criteria,evaluation_start_step=120))
assert json.loads(json.dumps(score))==summary['outcome']
for previous,control in zip(physics,actuators):
    assert control['sim_time_s']==previous['sim_time_s']
    assert control['pre_joint_positions_rad']==previous['joint_positions_rad']
    expected=np.clip(np.array(control['applied_joint_targets_rad'])+np.array(control['pre_gravity_bias_nm'])/np.array(control['actuator_gains']),np.array(control['actuator_ctrl_ranges'])[:,0],np.array(control['actuator_ctrl_ranges'])[:,1])
    assert np.allclose(expected,control['control_rad'],atol=1e-14,rtol=0)
assert events[0]['start_step']==120 and events[-1]['end_step']==4806
for prior,later in zip(events,events[1:]):
    assert prior['end_step']==later['start_step'] and prior['command_seq_end']==later['command_seq_start']
for event,result in zip(events,load('actions.json')):
    assert event['result']==result
    assert result['details']['physics_steps']==event['end_step']-event['start_step']
    used=[r for r in commands if event['command_seq_start']<=r['command_seq']<event['command_seq_end']]
    assert all(event['start_step']<=r['physics_step']<=event['end_step'] for r in used)
assert load('unframed-actions.json')==[]
registration=PoseMarkerRegistration(7,.045,'2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4')
visibility=[]
for folder in sorted((run/'frames').iterdir()):
    observation=RGBDObservation.model_validate_json((folder/'observation-full.json').read_text())
    assert base64.b64decode(observation.rgb_png_base64)==(folder/'rgb.png').read_bytes()
    assert base64.b64decode(observation.depth_float32_base64)==(folder/'depth.f32').read_bytes()
    assert observation.valid_mask_bytes()==(folder/'valid_mask.u8').read_bytes()
    estimate=detect_pose_marker(observation,registration)
    value=asdict(estimate);value['captured_at']=estimate.captured_at.isoformat()
    assert json.loads(json.dumps(value))==json.loads((folder/'marker-estimate.json').read_text())
    visibility.append({'boundary':folder.name,'status':estimate.status,'sim_time_s':observation.sim_time_s})
assert len(visibility)==10 and sum(r['status']=='OBSERVED' for r in visibility)==1
assert next(r for r in visibility if r['boundary']=='INITIAL_SETTLED')['status']=='OBSERVED'
exclusion=json.loads((artifact/'development-exclusion.json').read_text())
print(json.dumps({'scope':'READ_ONLY_SAVED_RAW_RECONSTRUCTION','raw_physics_to_samples':'PASS','raw_actuator_arithmetic_and_step_binding':'PASS','action_command_ranges':'PASS','source_and_raw_byte_hashes':'PASS','raw_recomputed_outcome':json.loads(json.dumps(score)),'visibility':visibility,'actual_reruns':0,'live_model_calls':0,'renderer':'NOT_RUN','controller_commands_during_review':0,'native_admission':False,'formal_source_eligible':False},indent=2))
'''
# Derive actual persisted depth filename from source, without modifying artifacts.
first = next((artifact / 'attempt-1/frames').iterdir())
depth_file = next(p.name for p in first.iterdir() if p.suffix == '.f32')
code=code.replace('ARTIFACT_PATH',repr(str(artifact))).replace("'depth.f32'",repr(depth_file))
script=scratch/'root_review.py'
script.write_text(code)
result=subprocess.run([str(root/'.venv/bin/python'),str(script)],cwd=scratch,env=environment,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(artifact/'root-independent-review.log').write_text(result.stdout)
print(result.stdout,flush=True)
if result.returncode:
    raise SystemExit(result.returncode)
for name,digest in artifact_manifest.items():
    assert hashlib.sha256((artifact/name).read_bytes()).hexdigest()==digest,name
setup={'scope':'READ_ONLY_SAVED_RAW_RECONSTRUCTION','scratch':str(scratch),'frozen_source25_sha256':hashlib.sha256((artifact/'source-hashes.json').read_bytes()).hexdigest(),'frozen_base768_sha256':hashlib.sha256((base/'fix-round-3-release-source-hashes.json').read_bytes()).hexdigest(),'artifact_files':len(artifact_manifest),'raw_files':len(raw_manifest),'post_review_artifact_hashes':'PASS','renderer':'NOT_RUN','actual_reruns':0,'controller_commands_during_review':0}
(artifact/'root-review-setup.json').write_text(json.dumps(setup,indent=2)+'\n')
