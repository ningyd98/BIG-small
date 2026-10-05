"""Offline-only boundary instrumentation; never passed to online controller."""
from __future__ import annotations
import argparse,gzip,hashlib,json
from dataclasses import asdict
from pathlib import Path
import numpy as np
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json
from cloud_edge_robot_arm.datasets.rgbd import teacher
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

parser=argparse.ArgumentParser()
parser.add_argument('--source-manifest',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--indices',default='0,2,4,6,8,12,13')
parser.add_argument('--model-path',type=Path,default=Path('assets/robots/franka_panda/scene.xml'))
args=parser.parse_args()
source=json.loads(args.source_manifest.read_text())
asset=args.model_path; asset_hash=hashlib.sha256(asset.read_bytes()).hexdigest()
args.output.mkdir(parents=True,exist_ok=False)
original_capture=teacher._capture
with MuJoCoCaptureSession(SimulatorConfig(model_path=str(asset),camera_width=64,camera_height=64)) as session:
 for index in map(int,args.indices.split(',')):
  assignment=source['assignments'][index]
  scene=SceneSpec.from_parameters(assignment['scene']['scene_parameters'],asset_hash,assignment['seed'])
  session.apply_scene(scene); backend=session._backend
  boundaries=[]
  def capture(physical):
   model,data,mj=physical._model,physical._data,physical._mujoco
   assert model is not None and data is not None and mj is not None
   forces=[]; normal={'left':0.0,'right':0.0}
   for j in range(data.ncon):
    contact=data.contact[j]; names=(model.geom(contact.geom1).name,model.geom(contact.geom2).name)
    force=np.zeros(6); mj.mj_contactForce(model,data,j,force)
    if 'object_geom' in names:
     forces.append({'pair':names,'distance_m':float(contact.dist),'force_contact_frame':force.tolist()})
     for side in normal:
      if side+'_finger_geom' in names: normal[side]+=float(force[0])
   snapshot=asdict(physical.current_physics_observation())
   boundaries.append({'physics':snapshot,'command_positions':physical._target_positions.tolist(),
                      'finger_actuator_forces_N':data.actuator_force[7:9].tolist(),
                      'contact_forces':forces,'normal_force_N':normal})
   return original_capture(physical)
  teacher._capture=capture
  recorder=teacher.EpisodeRecorder()
  try: outcome=teacher.run_teacher_episode(scene,MuJoCoSkillRobot(backend),recorder,case=assignment['case'])
  finally: teacher._capture=original_capture
  payload={'index':index,'original_scene':assignment['scene'],'scene':scene.model_dump(mode='json'),
           'asset_sha256':asset_hash,'outcome':asdict(outcome),'boundaries':boundaries,
           'actions':[f.action.model_dump(mode='json') for f in recorder.frames]}
  compressed=gzip.compress(canonical_json(payload).encode(),mtime=0)
  (args.output/f'{index:04d}.json.gz').write_bytes(compressed)
  print(json.dumps({'index':index,'status':outcome.status,'action_failures':[(f.action.action_type,f.action.error_code) for f in recorder.frames if not f.action.success],'boundary_count':len(boundaries)},ensure_ascii=False),flush=True)
