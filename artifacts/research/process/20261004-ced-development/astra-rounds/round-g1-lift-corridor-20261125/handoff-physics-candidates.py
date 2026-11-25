"""Compare registered optical APPROACH candidates with frozen controller and full native motions."""
from __future__ import annotations

import argparse
import collections
import fcntl
import gzip
import importlib.util
import json
import math
import time
from pathlib import Path

import mujoco
import numpy as np
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_visibility_vision import measure_frame

HERE=Path(__file__).resolve().parent
H=HERE.parent/'round-g1-skill-handoff-20261125'
spec=importlib.util.spec_from_file_location('handoff_native',H/'handoff-physics-native.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
io=native.io;DESIGN=io.read(HERE/'handoff-physics-candidate-preregistration.json')

def setup(root,case):
    recipe=next(c for c in DESIGN['cases'] if c['name']==case)
    native.REG['fresh_poses'][case]=dict(object_center_m=recipe['physical_object_center_m'],yaw_deg=recipe['yaw_deg'],bench_target_xy_error_mm=[0,0],bench_target_height_above_center_mm=10,seed=recipe['seed'])
    native.REG['roles'][case]=recipe['role'];return native.setup(root,case)[0],recipe


def prepare(root,out,case):
    # Each original MOVE_ABOVE starts with a target measured by the real registered camera.
    from OpenGL import GL
    d=out/'prefix'/case;d.mkdir(parents=True,exist_ok=False);b,item=setup(root,case);robot=MuJoCoSkillRobot(b);rng=np.random.default_rng(item['seed']);scratch=mujoco.MjData(b._model);cam=MuJoCoRGBDCamera(mujoco,b._model,width=320,height=240)
    ars=root/native.REG['source_cases']['t01']['dir']/'allocation.json';geometry=io.read(ars)['geometry'];scene='approach-candidate-'+case
    def take(label):
        scratch.qpos[:]=b._data.qpos;scratch.qvel[:]=b._data.qvel;scratch.ctrl[:]=b._data.ctrl;scratch.time=b.get_sim_time();mujoco.mj_forward(b._model,scratch)
        tic=time.monotonic_ns();f=observation_from_sensor_frame(cam.capture(scratch,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=scene),source='mujoco_camera',png_compress_level=1);toc=time.monotonic_ns();m=measure_frame(f,geometry)
        fname=d/(label+'.json.gz');fname.write_bytes(gzip.compress(f.model_dump_json().encode(),3,mtime=0));
        return dict(label=label,step=b.total_physics_steps,frame_id=f.frame_id,checksum=f.checksum_sha256,file=fname.name,file_sha256=io.sha(fname),capture_ms=(toc-tic)/1e6,ids=m.get('usable_ids'),usable=m['usable'],observed_center_m=m['object_center_world_m'],grasp_world_m=m['grasp_world_m'])
    try:
        with bind_scene(scene):
            b.step(120);bootstrap=take('bootstrap');assert bootstrap['usable'];action,_=native.execute(robot,b,'MOVE_ABOVE',bootstrap['grasp_world_m'],scene);assert action.success,action.error_code;above=take('approach-reference');assert above['usable']
            state,cmd,opened,step=io.pack(b);np.savez_compressed(d/'return.npz',packed=state,command_q=cmd,command_open=opened,step=step,q=b._data.qpos,qvel=b._data.qvel);io.write(d/'commands.json',b.command_records)
            data=dict(case=case,role=item['role'],registration_sha256=io.sha(HERE/'handoff-physics-candidate-preregistration.json'),bootstrap=bootstrap,above=above,return_step=step,renderer=GL.glGetString(GL.GL_RENDERER).decode(),native_state_sha256=io.sha(d/'return.npz'),native_command_sha256=io.sha(d/'commands.json'));io.write(d/'prefix.json',data);print(case,'ready',step,bootstrap['ids'],above['ids'],flush=True)
    finally:cam.close();b.shutdown()


def target(center,cand):
    c=np.asarray(center,float);radial=c[:2]/np.linalg.norm(c[:2]);return np.r_[c[:2]+radial*cand['radial_mm']/1000,c[2]+cand['height_above_estimated_center_mm']/1000]


def simulate(root,out,case,candidates):
    prefix=out/'prefix'/case;orig=io.read(prefix/'prefix.json');start=np.load(prefix/'return.npz');command_hist=io.read(prefix/'commands.json');c=np.asarray(orig['above']['observed_center_m']);
    if orig['native_state_sha256']!=io.sha(prefix/'return.npz') or orig['native_command_sha256']!=io.sha(prefix/'commands.json'):raise ValueError('prefix drift')
    baseaim=orig['bootstrap']['grasp_world_m'];begin0=int(start['step']);speed_aim={};
    for chosen in candidates:
        cand=next(z for z in DESIGN['candidates'] if z['id']==chosen);d=out/'courses'/case/chosen
        if (d/'result.json').is_file():continue
        d.mkdir(exist_ok=False,parents=True);b,recipe=setup(root,case);robot=MuJoCoSkillRobot(b);m=b._model;data=b._data;vtx=np.array(list(__import__('itertools').product((-1,1),repeat=3)))*.035
        pkt=(start['packed'],start['command_q'],bool(start['command_open']),begin0);io.restore(b,pkt);b._command_records=command_hist.copy();
        np.testing.assert_array_equal(data.qpos,start['q']);np.testing.assert_array_equal(data.qvel,start['qvel']);rows=[];packed=[];results=[];edges=[];err=None;aim=target(c,cand);stage='APPROACH';
        fids=[m.geom('left_finger_geom').id,m.geom('right_finger_geom').id];obj=m.geom('object_geom').id;table=m.geom('table').id
        def snap():
            force=np.zeros(2);counts=np.zeros(4,int)
            for idx,co in enumerate(data.contact):
                pair={int(co.geom1),int(co.geom2)};j=3
                if obj in pair:
                    if table in pair:j=2
                    else:
                        for fi,fg in enumerate(fids):
                            if fg in pair:
                                buf=np.zeros(6);mujoco.mj_contactForce(m,data,idx,buf);j=fi;force[fi]+=buf[0]
                counts[j]+=1
            cube=data.geom('object_geom');cr=cube.xmat.reshape(3,3);tcp=data.site('tcp');rr=tcp.xmat.reshape(3,3);xyz=cube.xpos+vtx@cr.T;pos=b.get_tcp_pose();
            rows.append(dict(step=b.total_physics_steps,stage=stage,q=data.qpos.copy(),qvel=data.qvel.copy(),ctrl=data.ctrl.copy(),command_q=b._target_positions.copy(),command_open=b._gripper_open,
                   tcp=[pos.x,pos.y,pos.z],cube=cube.xpos.copy(),rot=cr.copy(),wrist=rr.copy(),forces=force,contact_count=counts,bottom=float(xyz[:,2].min()),cube_corners_world=xyz,
                   cube_in_tcp=rr.T@(cube.xpos-tcp.xpos)))
            packed.append(io.pack(b)[0]);
        try:
            snap()
            for n in native.STAGES[1:]:
                stage=n;begin=b.total_physics_steps;edges.append(dict(stage=n,step=begin,active=native.commands_at(b)))
                with b.observe_physics_steps(lambda s:snap()):act,session=native.execute(robot,b,n,aim if n=='APPROACH' else baseaim,'candidate-'+case)
                results.append(dict(stage=n,success=act.success,end=b.total_physics_steps,reason=act.error_code,details=act.details));
                if not act.success:break
            if results[-1]['stage']=='RETREAT' and results[-1]['success']:
                stage='FINAL_OBSERVATION'
                with b.observe_physics_steps(lambda s:snap()):b.step(240)
            a=io.stack(rows);np.savez_compressed(d/'series.npz',**a,packed=packed);io.write(d/'handoffs.json',edges);io.write(d/'commands.json',b.command_records)
            for edge in edges:
                if edge['stage']=='LIFT':e=edge;break
            else:e=None
            ids=np.flatnonzero(a['stage']=='LIFT');gh=np.flatnonzero(a['stage']=='GRASP');ii=np.arange(max(0,len(rows)-120),len(rows));li=ids[-120:] if len(ids)>=120 else np.array([],dtype=int)
            last_120=bool(len(li)==120 and np.all(a['bottom'][li]-a['bottom'][0]>=.05) and np.all(a['contact_count'][li,:2]>0));closed=bool(len(gh) and (a['contact_count'][gh[-1],:2]>0).all());full=results[-1]['stage']=='RETREAT' and results[-1]['success'];
            settled=bool(full and np.all(abs(a['cube_corners_world'][ii,:,:2]-[.2,.25])<np.array([.08,.08])) and np.all(a['contact_count'][ii,2]>0) and np.max(np.linalg.norm(a['qvel'][ii,9:12],axis=1))<.01 and np.max(np.linalg.norm(a['qvel'][ii,12:15],axis=1))<.1)
            lateral=None if e is None else float(np.linalg.norm(a['tcp'][ids,:2]-a['tcp'][e['step']-begin0,:2],axis=1).max());structs=int((a['contact_count'][:,3]>0).sum());good=bool(full and closed and last_120 and settled and structs==0 and lateral<.001)
            rec=dict(case=case,role=recipe['role'],candidate=cand,registration_sha256=orig['registration_sha256'],source_pixel_file_sha256=orig['above']['file_sha256'],observed_center=c.tolist(),actual_approach_target=aim.tolist(),source_return_step=begin0,entry_unchanged=True,
              grasp_bilateral=closed,terminal_grasp_force_N=a['forces'][gh[-1]].tolist() if len(gh) else None,lift_peak_lateral_m=lateral,last_120_bilateral_over_50mm=last_120,
              lift_120_min_gain_m=float((a['bottom'][li]-a['bottom'][0]).min()) if len(li) else None,original_native_skills_complete=full,stable_inside=settled,actual_structure_contact_steps=structs,eligible=good,
              terminal_stage=results[-1]['stage'],terminal_success=results[-1]['success'],terminal_error=results[-1]['reason'],actions=results,series_sha256=io.sha(d/'series.npz'))
            io.write(d/'result.json',rec);print(case,chosen,good,lateral,results[-1]['reason'],flush=True)
        finally:b.shutdown()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--mode',choices=('prepare','simulate'),required=True);p.add_argument('--case',action='append',required=True);p.add_argument('--candidate',action='append');p.add_argument('--freeze',type=Path);a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    cases=a.case;choices=a.candidate or [c['id'] for c in DESIGN['candidates']]
    if any(n.startswith('new') for n in cases):
        if not a.freeze:raise ValueError('held-out physical course requires previous candidate freeze')
        frozen=io.read(a.freeze);allowed={'rad+0_h10',frozen['selected_id']}
        if not set(choices)<=allowed:raise ValueError('unregistered postfreeze candidate reuse')
    if a.mode=='prepare':
        with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for case in cases:prepare(root,out,case)
    else:
        for case in cases:simulate(root,out,case,choices)

if __name__=='__main__':main()
