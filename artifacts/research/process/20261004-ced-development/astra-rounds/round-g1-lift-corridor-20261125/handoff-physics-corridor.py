"""Measure true inherited drift and frozen optical LIFT targets at identical native states."""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import math
import os
import time
from pathlib import Path

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.g1_formal_runtime import bind_scene

HERE=Path(__file__).resolve().parent
PLAN_SHA='fe5dae8f0d662c7debf4193aa279f56473e1a41799593eb9175d2208aec77d27'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):return json.loads(p.read_bytes())

def write(p,obj):
    with p.open('x') as f:json.dump(obj,f,ensure_ascii=False,allow_nan=False,indent=2,sort_keys=True);f.write('\n')

def capture(root,raw,frames_dir,case):
    reg=read(HERE.parent/'round-g1-skill-handoff-20261125'/'handoff-physics-preregistration.json');runtime=root/reg['frozen_runtime'];asset=runtime/reg['frozen_asset'];p=raw/case;out=frames_dir/case;out.mkdir(exist_ok=False,parents=True)
    case_ref=case if case in ('t01','t02') else 't01';od=root/reg['source_cases'][case_ref]['dir'];alloc=read(od/'allocation.json');geo=alloc['geometry'];actions=read(p/'actions.json');hs=read(p/'handoffs.json');summ=read(p/'summary.json');
    with np.load(p/'normal.npz') as data:h={k:data[k] for k in ('q','qvel','ctrl','tcp','step','stage','cube_bottom_m','centers','cube_in_tcp','rotation')}
    hmap={r['start_step']:r['incoming'] for r in hs};row=next(a for a in actions if a['stage']=='LIFT');start,fin=row['start_step'],row['step'];gstart=next(r['start_step'] for r in hs if r['incoming']=='GRASP');
    selected={120:'bootstrap',**{s:'into-'+v for s,v in hmap.items()}}
    if case in ('t01','t02'):
        for step in range(start,fin+1,8):selected.setdefault(step,'LIFT-feedback-tick')
        selected.setdefault(fin,'LIFT-end')
    else:selected.setdefault(fin,'LIFT-end')
    # Match the model and depth sensor used on the development arm. Each callback reads
    # the original physical q, qvel and command at this tick in a separate camera process.
    model=mujoco.MjModel.from_xml_path(str(asset));model.opt.timestep=1/240;data=mujoco.MjData(model);cam=MuJoCoRGBDCamera(mujoco,model,width=320,height=240)
    rng=np.random.default_rng(summ['seed']);episode='handoff-native-same-state-'+case;scene='g1-handoff-camera-'+case; records=[];bootstrap=None;provider=None;ref_error=None
    try:
        for t,label in sorted(selected.items()):
            data.qpos[:]=h['q'][t];data.qvel[:]=h['qvel'][t];data.ctrl[:]=h['ctrl'][t];data.time=t/240;mujoco.mj_forward(model,data)
            begin=time.monotonic_ns();f=observation_from_sensor_frame(cam.capture(data,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=episode),source='mujoco_camera',png_compress_level=1); end=time.monotonic_ns()
            binding=MuJoCoRGBDCamera._physics_state_hash(data);flow=None;err=None;target=None;core={}
            try:
                if t==120:bootstrap=bootstrap_collection_tracker(f,geo)
                if t==start:
                    tcp=h['tcp'][start];targ=Pose(x=tcp[0],y=tcp[1],z=max(.16,tcp[2]+.10))
                    if bootstrap is None:raise ValueError('bootstrap tracker missing')
                    provider=OpenCVServoFeedback(f,bootstrap[0],bootstrap[1],skill='LIFT',initial_target=targ,marker_family_id=geo['marker_family'],verify_mujoco_calibration=True)
                    ref_error=None;flow='SERVO_REFERENCE';target=targ
                elif t>start and t<=fin and provider is not None and case in ('t01','t02'):
                    target=provider.update(f);flow='NATIVE_UPDATE'
            except ValueError as ex:
                err=str(ex)
                if t==start:ref_error=err
            provider_done=time.monotonic_ns();det=measure_frame(f,geo);path=out/f'{t:05d}.json.gz';
            with path.open('xb') as fd:fd.write(gzip.compress(f.model_dump_json().encode(),3,mtime=0))
            records.append(dict(step=t,label=label,source_file=path.name,source_sha256=sha(path),state_sha256=binding,frame_id=f.frame_id,checksum=f.checksum_sha256,
                 acquisition_begin_ns=begin,acquisition_end_ns=end,capture_ms=(end-begin)/1e6,native_update_complete_ms=(provider_done-begin)/1e6,
                 observed_ids=det.get('observed_ids'),usable_ids=det.get('usable_ids'),registration_id=det.get('registration_id'),marker_usable=det.get('usable'),marker_reason=det.get('reason'),
                 frozen_provider_role=flow,provider_error=err,reference_error=ref_error,provider_target=None if target is None else [target.x,target.y,target.z]))
        graphics={k:GL.glGetString(a).decode() for k,a in [('renderer',GL.GL_RENDERER),('vendor',GL.GL_VENDOR)]}
    finally:cam.close()
    # A solver's TCP xmat/xpos may correspond to its last forward stage; the archived world FK
    # is independently recomputed from the full q in the mechanical record.
    xy=h['tcp'][start:fin+1,:2]-h['tcp'][start,:2];lat=np.linalg.norm(xy,axis=1);z=h['tcp'][start:fin+1,2];back=np.maximum.accumulate(z)-z
    initial=h['tcp'][gstart];after=h['tcp'][start];init_obj=h['centers'][gstart,10];post_obj=h['centers'][start,10];pvec=xy[np.argmax(lat)];
    if case in ('t01','t02'):
        ind=read(od/'instance/pixel-index.json');old=[{k:r[k] for k in ['file','file_sha256','frame_id','physics_step','label']} for r in ind['frames'] if r['physics_step']==gstart]
    else:old=[]
    successes=[r for r in records if r['frozen_provider_role']=='NATIVE_UPDATE'];initial_target=next((r['provider_target'] for r in records if r['frozen_provider_role']=='SERVO_REFERENCE'),None)
    capture_result=dict(case=case,phase='offline optical and physical same-state evidence',graphics=graphics,calibration_version=geo['camera']['calibration_version'],asset_sha256=sha(asset),normal_sha256=sha(p/'normal.npz'),
       grasp_begin=gstart,lift_begin=start,lift_end=fin,native_lift_status=row['success'],start_tcp_m=after.tolist(),pregrasp_tcp_m=initial.tolist(),during_grasp_tcp_drift_m=(after-initial).tolist(),
       pregrasp_wrist_relative_to_cube_m=(h['rotation'][gstart,10].T@(initial-init_obj)).tolist(),postgrasp_wrist_relative_to_cube_m=(h['rotation'][start,10].T@(after-post_obj)).tolist(),
       closure_object_shift_m=(post_obj-init_obj).tolist(),peak_lateral_m=float(lat.max()),peak_lateral_vector_m=pvec.tolist(),peak_lateral_tick=start+int(lat.argmax()),
       first_tick_over_1mm=next((start+j for j,v in enumerate(lat) if v>.001),None),max_vertical_backtrack_m=float(back.max()),
       highest_object_gain_m=float((h['cube_bottom_m'][start:fin+1]-h['cube_bottom_m'][0]).max()),
       measured_provider_updates=len(successes),provider_max_target_change_m=(max(np.linalg.norm(np.array(r['provider_target'])-initial_target) for r in successes) if successes else None),
       provider_ref_target_m=initial_target,provider_errors=sum(r['provider_error'] is not None for r in records),frames=records,original_frame_files=old,
       no_online_admission_or_scoring=True,context='Direct physical same-state capture, archived original records bound separately. Original LIFT provider updates on this exact pixel stream only, no run-loop timing claim.')
    write(out/'index.json',capture_result);print(case,lat.max(),len(successes),capture_result['provider_errors'],graphics,flush=True)


def main():
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--case',action='append',required=True);args=a.parse_args();root=args.root.resolve();out=args.out.resolve();cv2.setNumThreads(1)
    if sha(HERE/'plan.json')!=PLAN_SHA or os.environ.get('MUJOCO_GL')!='egl':raise ValueError('wrong plan or render backend')
    with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        for case in args.case:
            with bind_scene('g1-handoff-camera-'+case):
                capture(root,root/'experiments/results/g1-skill-handoff-20261125/physical-capture-01',out,case)

if __name__=='__main__':main()
