"""Paired live optical APPROACH/GRASP/LIFT on the actual two archived MOVE_ABOVE returns."""
from __future__ import annotations

import argparse
import fcntl
import gzip
import importlib.util
import time
from pathlib import Path
import cv2
import mujoco
import numpy as np
from OpenGL import GL
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_visibility_vision import measure_frame

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('frozen_rule',HERE/'handoff-physics-candidate-rule.py');rule=importlib.util.module_from_spec(s);s.loader.exec_module(rule);candidates=rule.s;native=candidates.native;io=native.io
FREEZE='576570c1812467b4b2a99d8d3a740fb274e632ca65ed0c25d1dd173eff55e958'

def execute(root,out,case,mode):
    parent=out/case/mode;parent.mkdir(parents=True,exist_ok=False);b,inp=native.setup(root,case);source=inp['source'];robot=MuJoCoSkillRobot(b);sensors=native.Sensors(b);m=b._model;data=mujoco.MjData(m);cam=MuJoCoRGBDCamera(mujoco,m,width=320,height=240);geometry=io.read(source/'allocation.json')['geometry'];scene='live-app-root-'+case;episode=scene+'-'+mode
    rng=np.random.default_rng(inp['seed']);frames=[];rows=[];actions=[];checks={};captured_ids=[];phase='PREFIX'
    def optical(label):
        data.qpos[:]=b._data.qpos;data.qvel[:]=b._data.qvel;data.ctrl[:]=b._data.ctrl;data.time=b.get_sim_time();mujoco.mj_forward(m,data)
        t=time.monotonic_ns();f=observation_from_sensor_frame(cam.capture(data,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=episode),source='mujoco_camera',png_compress_level=1);t1=time.monotonic_ns();r=dict(phase=phase,label=label,step=b.total_physics_steps,capture_ns=t,ready_ns=t1,capture_ms=(t1-t)/1e6,checksum=f.checksum_sha256,frame_id=f.frame_id,state_sha=MuJoCoRGBDCamera._physics_state_hash(data));frames.append((f,r));return f,r
    def record(_=None):
        d,_=sensors.snap(b);tcp=b.get_tcp_pose();rows.append(dict(step=b.total_physics_steps,phase=phase,q=d['q'],qvel=d['qvel'],ctrl=d['ctrl'],tcp=d['tcp'],native_tcp=[tcp.x,tcp.y,tcp.z],cube=d['centers'][10],rotation=d['rotation'][10],forces=d['force_N'],contacts=d['contacts'],bottom=d['cube_bottom_m']))
    def go(name,provider,path,target,call):
        def sample(prior):
            f,r=optical('feedback');observed=provider.update(f);r['target_m']=[observed.x,observed.y,observed.z];r['final_ns']=time.monotonic_ns();return MotionTarget(observed,prior.orientation_wxyz)
        session=VisualServoSession(sample,vertical_clearance=path);tick=b.total_physics_steps
        with robot.visual_servo(session),b.observe_physics_steps(record):action=call()
        actions.append(dict(skill=name,start=tick,end=b.total_physics_steps,success=action.success,code=action.error_code,details=action.details,feedback_count=len(session.records),max_native_sample_ik_s=max((r['sample_and_ik_s'] for r in session.records if r.get('sample_and_ik_s') is not None),default=None)));return action
    try:
        with bind_scene(scene):
            at=min(inp['handoffs']);tracker=ev=None
            for step in range(at+1):
                native.statecheck(b,inp['states'][step],checks)
                if step==120:
                    f,_=optical('bootstrap');tracker,ev=bootstrap_collection_tracker(f,geometry)
                if step==at:
                    # The one successful return hold precedes the next original command at that clock.
                    first=inp['cmds'][step][0];assert first['type']=='hold_current_joints';io.actuate(b,first);break
                for command in inp['cmds'][step]:io.actuate(b,command)
                b.step(1)
            phase='APPROACH';record();ref,rf=optical('reference');meas=measure_frame(ref,geometry);assert meas['usable'];center=meas['object_center_world_m'];selected=rule.choose(center)
            entry=np.array(meas['grasp_world_m']) if mode=='original' else candidates.target(center,next(c for c in candidates.DESIGN['candidates'] if c['id']==selected));pose=Pose(x=entry[0],y=entry[1],z=entry[2]);rf['target_m']=entry.tolist()
            provider=OpenCVServoFeedback(ref,tracker,ev,skill='APPROACH',initial_target=pose,marker_family_id=geometry['marker_family'],verify_mujoco_calibration=True)
            approach=go('APPROACH',provider,None,pose,lambda:robot.approach('object',resolved_target=pose,tcp_velocity=.15,acceleration=.5,timeout_ms=10000))
            if approach.success:
                phase='GRASP';j=b.total_physics_steps
                with b.observe_physics_steps(record):gr=robot.grasp('object',timeout_ms=1000)
                actions.append(dict(skill='GRASP',success=gr.success,details=gr.details,start=j,end=b.total_physics_steps,code=gr.error_code))
            if approach.success and gr.success:
                phase='LIFT';cur=robot.get_state().tcp_pose;tar=Pose(x=cur.x,y=cur.y,z=max(.16,cur.z+.10));v=VerticalClearancePath(task_id=scene,step_id='actual-LIFT',skill='LIFT',start_m=(cur.x,cur.y,cur.z),target_m=(tar.x,tar.y,tar.z),minimum_height_m=.08)
                ref,rf=optical('reference');rf['target_m']=[tar.x,tar.y,tar.z];provider=OpenCVServoFeedback(ref,tracker,ev,skill='LIFT',initial_target=tar,marker_family_id=geometry['marker_family'],verify_mujoco_calibration=True);lift=go('LIFT',provider,v,tar,lambda:robot.lift(tar.z-cur.z,resolved_target=tar,tcp_velocity=.15,acceleration=.5,timeout_ms=10000))
            rr=io.stack(rows);np.savez_compressed(parent/'physics.npz',**rr);frameindex=[]
            for f,r in frames:
                fp=parent/f'{len(frameindex):04d}.json.gz';fp.write_bytes(gzip.compress(f.model_dump_json().encode(),3,mtime=0));mr=measure_frame(f,geometry);frameindex.append(r|dict(file=fp.name,file_sha=io.sha(fp),usable_ids=mr['usable_ids'],reason=mr['reason']))
            ls=np.flatnonzero(rr['phase']=='LIFT');held=len(ls)>=120 and (rr['contacts'][ls[-120:],:2]>0).all() and (rr['bottom'][ls[-120:]]-rr['bottom'][0]>=.05).all();lateral=float(np.linalg.norm(rr['native_tcp'][ls,:2]-[cur.x,cur.y],axis=1).max()) if len(ls) else None
            outrow=dict(case=case,mode=mode,prospective_freeze_sha256=FREEZE,source_camera_sha256=io.sha(root/native.REG['frozen_runtime']/native.REG['frozen_asset']),source_code_sha256=io.sha(Path(__file__)),renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                     physical_source_errors=checks,same_physical_return_step=at,observed_reference_center_m=center,selected_height_radial_id=selected if mode=='rule' else None,approach_target=entry.tolist(),immutable_prior_marker_grasp_m=meas['grasp_world_m'],
                     actions=actions,actual_control_lift_lateral_peak_m=lateral,actual_held_over_50mm_for_120=bool(held),forbidden_contact_steps=int((rr['contacts'][:,3]>0).sum()),
                     frames=frameindex,scope='Paired diagnostic single native optical APPROACH/GRASP/LIFT with independent causal role. Original full worker guards, complete eight-skill scores and hardware are separate.');io.write(parent/'results.json',outrow);print(case,mode,[(r['skill'],r['success'],r['code']) for r in actions],lateral,held,flush=True)
    finally:cam.close();b.shutdown()

if __name__=='__main__':
    opts=argparse.ArgumentParser();opts.add_argument('--root',type=Path,required=True);opts.add_argument('--out',type=Path,required=True);opts.add_argument('--case',action='append',required=True);args=opts.parse_args();root=args.root.resolve();cv2.setNumThreads(1)
    if io.sha(HERE/'handoff-physics-candidate-rule-freeze.public.json')!=FREEZE:raise ValueError('unfrozen rule')
    with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for case in args.case:
            for mode in ('original','rule'):execute(root,args.out.resolve(),case,mode)
