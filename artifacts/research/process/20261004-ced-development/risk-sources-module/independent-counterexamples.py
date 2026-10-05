from pathlib import Path
from dataclasses import replace
import json,tempfile
from tests.test_research_risk_sources import fixture_case,registered,hashes,json_file,plain

for kind in ['hold_target','gains','unknown_control_field','numeric_bool','geometry_drift','no_action_commands']:
 root=Path(tempfile.mkdtemp(prefix='risk-source-probe-'));case,d=fixture_case(root)
 commands=[]
 if kind in ['hold_target','no_action_commands']:
  commands=[{'command_seq':1,'physics_step':120,'sim_time_s':120*0.0041666667,'episode_id':case.context['episode_id'],'type':'hold_current_joints' if kind=='hold_target' else 'joint_target','accepted':True,'target_positions_rad':[-.5,0,0,0,0,0,0],'applied_target_positions_rad':[-.5,0,0,0,0,0,0]}]
  json_file(d/'commands.json',commands)
 p=d/'raw-actuators.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
 if commands:
  rows[-1]['applied_joint_targets_rad'][0]=-.5;rows[-1]['control_rad'][0]=-.7
 if kind=='gains':
  row=rows[5];row['actuator_gains'][1]=40.;row['control_rad'][1]=row['pre_joint_positions_rad'][1]+row['pre_gravity_bias_nm'][1]/40.
 if kind=='unknown_control_field':rows[5]['unrecognized_authority']=True
 if kind=='numeric_bool':rows[5]['pre_gravity_bias_nm'][0]=False
 p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
 if kind=='geometry_drift':
  p=d/'raw-physics.jsonl';physics=[json.loads(x) for x in p.read_text().splitlines()];physics[5]['object_half_extent_m'][0]=.0001;p.write_text(''.join(json.dumps(x)+'\n' for x in physics))
 case=replace(case,original_file_hashes=hashes(d),expected_counts={**dict(case.expected_counts),'commands':len(commands)})
 result=registered(root,case).audit('fixture',scope='RAW_EXECUTION')
 print(kind,result.status,result.reasons,'counts',dict(result.counts))
