"""Replay earlier original RGB-D and measured robot in role order through the complete gate."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_clearance import LocalClearance
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_visibility_vision import measure_frame

def read(path):return json.loads(path.read_bytes())
def run(label,out):
    private=Path('experiments/results/g1-complete-cv-repair-20261125')
    p=private/'batches/train-full-04'/('cvfix-'+label);src=p/'instance'
    a=read(p/'allocation.json');g=a['geometry'];asset=Path(g['asset_path']);cal=Path(a['calibration_directory'])
    run=read(src/'run.json');index=read(src/'pixel-index.json');local=read(src/'local-clearance.json')
    reset=next(x for x in read(src/'reset-observed.json') if x['phase']=='END')
    idn=bind_allocation((p/'allocation.json').read_bytes(),allocation_sha256=index['allocation_sha256'],
            generation_sha256=digest(private/'builds'/a['runtime_build_sha256']/'runtime-source/runtime-build.json'),
            calibration_sha256=digest(cal/'manifest.json'),asset_sha256=digest(asset),
            reset_scene_id=reset['parameters']['requested']['scenario_id'],reset_episode_id=reset['episode_id'])
    cert=LocalClearance(g,asset,cal,calibration_sha256=a['calibration_sha256'],isolated_scene=True,optical_identity=idn)
    frames={x['frame_id']:x for x in index['frames']}
    rows={(x['skill'],x['phase'],x['frame_id']):x for x in local['rows']}
    actions={x['skill']:x for x in run['actions']};jaws=[x for x in read(src/'backend-commands.json') if x['type']=='gripper' and x['accepted']]
    result=[]
    try:
        for role in run['frame_roles']:
            skill,_,role_phase=role['label'].partition('/')
            if (skill,role_phase) not in (('GRASP','PRE'),('GRASP','POST'),('LIFT','PRE'),('LIFT','feedback')):continue
            phase=role_phase.upper();fid=role['frame_id']
            x=rows[('LIFT','PRE',fid) if (skill,phase)==('GRASP','POST') else (skill,phase,fid)]
            data=frames[fid];srcframe=src/data['file'];assert digest(srcframe)==data['file_sha256']
            started=time.perf_counter_ns();frame=RGBDObservation.model_validate_json(srcframe.read_bytes())
            after_decode=time.perf_counter_ns();marker=measure_frame(frame,g);after_vision=time.perf_counter_ns()
            m=x['robot'];seq=m['handoff']['last_command_seq'];jaw=next((r for r in reversed(jaws) if r['command_seq']<=seq),{})
            prev=actions['APPROACH' if (skill,phase)==('GRASP','PRE') else 'GRASP']
            packet=dict(m,native_last_command_seq=seq,last_accepted_gripper_open=jaw.get('target_open'),last_accepted_gripper_command_step=jaw.get('physics_step'),
                  previous_native_successful_skill=prev['skill'],previous_native_return_step=prev['controller_return_step'],
                  previous_native_terminal_step=None if (skill,phase)==('GRASP','POST') else prev['end_step'])
            if (skill,phase)==('GRASP','POST'):
                answer=cert.observe_payload_frame(frame,marker,packet,skill,phase)
            else:
                answer=cert.check(frame,marker,packet,skill,x['target_xyz'],_DOWNWARD,phase=phase)
            end=time.perf_counter_ns()
            result.append(dict(step=m['physics_step'],frame=fid,phase=role['label'],native_frame_sha256=data['file_sha256'],
                load_from_disk_ms=(after_decode-started)/1e6,rgbd_cv_ms=(after_vision-after_decode)/1e6,
                gate_ms=(end-after_vision)/1e6,original_status=x['status'],original_reason=x['reason'],current=answer))
    finally:cert.close()
    f=out/(label+'.json');out.mkdir(exist_ok=True,parents=True)
    with f.open('x') as h:json.dump(dict(case=label,rows=result,threads=cv2.getNumThreads(),mode='archived camera B+C readback, capture and native IK excluded'),h,sort_keys=True,indent=2,allow_nan=False);h.write('\n')
    print(label,len(result),digest(f),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();cv2.setNumThreads(1)
    for k in ('t01','t02'):run(k,args.output)
