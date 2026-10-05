"""Read-only offline joint-limit trajectory probe for the frozen T5 case 8."""
from __future__ import annotations
import argparse,gzip,hashlib,json
from dataclasses import asdict
from pathlib import Path
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder,run_teacher_episode
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
parser=argparse.ArgumentParser(); parser.add_argument('--index',type=int,default=8); parser.add_argument('--model-path',type=Path,default=Path('../original-scene.xml')); parser.add_argument('--output',type=Path,default=Path('../baseline-case8-joint-limit.json')); args=parser.parse_args()
source=json.loads(Path('../baseline-t5/manifest.json').read_text()); a=source['assignments'][args.index]
asset=args.model_path; scene=SceneSpec.from_parameters(a['scene']['scene_parameters'],hashlib.sha256(asset.read_bytes()).hexdigest(),a['seed'])
rows=[]
with MuJoCoCaptureSession(SimulatorConfig(model_path=str(asset),camera_width=64,camera_height=64)) as session:
 session.apply_scene(scene); b=session._backend; original=b._build_physics_observation
 def probe(contacts):
  s=original(contacts)
  if any(not lo-1e-4<=v<=hi+1e-4 for v,(lo,hi) in zip((*s.joint_positions_rad,*s.finger_positions_m),(*s.joint_ranges_rad,*s.finger_ranges_m),strict=True)):
   model,data=b._model,b._data
   rows.append({'physics_step':s.physics_step,'sim_time_s':s.sim_time_s,'positions':s.joint_positions_rad,'velocities':s.joint_velocities_rad_s,'ranges':s.joint_ranges_rad,'command_targets':b._target_positions.tolist(),'ctrl':data.ctrl[:7].tolist(),'bias':data.qfrc_bias[:7].tolist(),'finger_positions_m':s.finger_positions_m,'finger_velocities_m_s':s.finger_velocities_m_s,'finger_ranges_m':s.finger_ranges_m,'finger_ctrl':data.ctrl[7:9].tolist(),'finger_actuator_force':data.actuator_force[7:9].tolist()})
  return s
 b._build_physics_observation=probe
 recorder=EpisodeRecorder(); outcome=run_teacher_episode(scene,MuJoCoSkillRobot(b),recorder)
payload={'index':args.index,'scene':a['scene'],'outcome':asdict(outcome),'violations':rows,'actions':[f.action.model_dump(mode='json') for f in recorder.frames]}
args.output.write_text(canonical_json(payload)+'\n')
print(json.dumps(payload['violations'],indent=2))
