from pathlib import Path
from dataclasses import replace,asdict
import json,tempfile,shutil,hashlib
from tests.test_research_risk_sources import MOTION,ROOT,hashes,sources,plain
from cloud_edge_robot_arm.research.risk_sources import RawCaseRegistration,RiskSourceRegistration,RiskSourceAuditor
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria,sample_physical_observation
from cloud_edge_robot_arm.research.protocol_evidence import _observation

work=Path(tempfile.mkdtemp(prefix='risk-source-full-probe-'));shutil.copytree(MOTION/'attempt-1',work/'attempt')
d=work/'attempt';header=json.loads((MOTION/'header.json').read_text());summary=json.loads((d/'summary.json').read_text())
context={'episode_id':summary['episode_id'],'physics_dt_s':header['config']['physics_dt_s'],'evaluation_start_step':120,'initial_controller_targets':{'joints_rad':[-.8,0,0,0,0,0,0],'fingers_m':[.039,.039]},'actuator_delay_steps':0}
counts={'physics_steps':4806,'commands':743,'actions':9,'frames':10}
case=RawCaseRegistration('derived-software-probe','attempt','MARKER_MOTION_DEVELOPMENT_RAW_V1',hashes(d),header['scene'],context,counts,source_kind='SOFTWARE_ONLY',marker_registration=PoseMarkerRegistration(7,.045,'2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4'))
current=sources();asset='assets/robots/franka_panda/scene_pose_marker_color_v2.xml';current[asset]=hashlib.sha256((ROOT/asset).read_bytes()).hexdigest()
originals={p:p.read_bytes() for p in [d/'commands.json',d/'raw-actuators.jsonl',d/'raw-actions.jsonl',d/'actions.json',d/'raw-physics.jsonl',d/'physical-samples.json']}
for kind in ['baseline','hold_target_valid_actions','asset_gain','missing_actions','post_reset_geometry']:
 for p,b in originals.items():p.write_bytes(b)
 if kind=='hold_target_valid_actions':
  p=d/'commands.json';commands=json.loads(p.read_text());index=next(i for i,c in enumerate(commands) if c['type']=='hold_current_joints' and i+1<len(commands) and commands[i+1]['physics_step']==c['physics_step']);c=commands[index];c['target_positions_rad'][0]+=.01;c['applied_target_positions_rad'][0]+=.01;p.write_text(json.dumps(commands)+'\n');print('hold_index',index,'step',c['physics_step'],'delta',.01,flush=True)
 if kind=='asset_gain':
  p=d/'raw-actuators.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()];row=rows[5];row['actuator_gains'][1]=40.;row['control_rad'][1]=row['pre_joint_positions_rad'][1]+row['pre_gravity_bias_nm'][1]/40.;p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
 if kind=='missing_actions':
  (d/'raw-actions.jsonl').write_text('');(d/'actions.json').write_text('[]\n')
 if kind=='post_reset_geometry':
  p=d/'raw-physics.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()];rows[5]['object_half_extent_m'][0]=.0001;p.write_text(''.join(json.dumps(x)+'\n' for x in rows));samples=json.loads((d/'physical-samples.json').read_text());samples[5]=asdict(sample_physical_observation(_observation(rows[5]),CompletionCriteria('object','target_region')));(d/'physical-samples.json').write_text(json.dumps(samples)+'\n')
 changed=replace(case,original_file_hashes=hashes(d),expected_counts={**counts,'actions':0 if kind=='missing_actions' else 9})
 registration=RiskSourceRegistration(work,ROOT,current,(changed,),CompletionCriteria('object','target_region'))
 result=RiskSourceAuditor({'probe':registration}).audit('probe',scope='RAW_EXECUTION')
 print(kind,result.status,result.reasons,dict(result.counts),'actions',result.case_results[0].get('actions'),'formal',result.formal_source_eligible,flush=True)
print('All derived fixtures SOFTWARE_ONLY; original archived evidence untouched; no render, model, motion or risk admission.')
