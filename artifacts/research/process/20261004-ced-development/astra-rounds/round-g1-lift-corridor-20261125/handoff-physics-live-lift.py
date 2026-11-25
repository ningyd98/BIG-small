"""Drive the original single LIFT with each arriving RGB-D packet from the actual moving arm."""
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
H=HERE.parent/'round-g1-skill-handoff-20261125'
spec=importlib.util.spec_from_file_location('handoff_native',H/'handoff-physics-native.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
io=native.io

def execute(root,out,case):
    dest=out/case;dest.mkdir(exist_ok=False,parents=True)
    olddir=root/'experiments/results/g1-skill-handoff-20261125/physical-capture-01'/case
    with np.load(olddir/'normal.npz') as arc:old={k:arc[k] for k in ('step','q','qvel','tcp','centers')}
    b,inp=native.setup(root,case);robot=MuJoCoSkillRobot(b);sensors=native.Sensors(b);d=mujoco.MjData(b._model);cam=MuJoCoRGBDCamera(mujoco,b._model,width=320,height=240)
    geom=io.read(inp['source']/'allocation.json')['geometry'];scene='g1-live-optical-lift-'+case;episode='fresh-physical-calibration-'+case;rng=np.random.default_rng(inp['seed']);frames=[];rows=[];res={};timing=[];provider=None
    warm=True
    def optical(role):
        d.qpos[:]=b._data.qpos;d.qvel[:]=b._data.qvel;d.ctrl[:]=b._data.ctrl;d.time=float(b._data.time);mujoco.mj_forward(b._model,d)
        beg=time.monotonic_ns();f=observation_from_sensor_frame(cam.capture(d,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=episode),source='mujoco_camera',png_compress_level=1);end=time.monotonic_ns()
        rec=dict(label=role,step=b.total_physics_steps,acquisition_begin_ns=beg,acquisition_end_ns=end,capture_ms=(end-beg)/1e6,frame_id=f.frame_id,checksum=f.checksum_sha256,state_sha256=MuJoCoRGBDCamera._physics_state_hash(d),target_m=None)
        frames.append((f,rec));return f,rec
    def record(state):
        value,_=sensors.snap(b);step=b.total_physics_steps
        rows.append(dict(step=step,q=value['q'],qvel=value['qvel'],tcp=value['tcp'],cube_in_tcp=value['cube_in_tcp'],centers=value['centers'],force_N=value['force_N'],contacts=value['contacts'],cube_bottom_m=value['cube_bottom_m'],command_q=b._target_positions.copy()))
    try:
        with bind_scene(scene):
            states=inp['states'];cs=inp['cmds'];tracker=ground=None
            for step,row in enumerate(states):
                native.statecheck(b,row,res)
                if step==120:
                    f,_=optical('bootstrap');tracker,ground=bootstrap_collection_tracker(f,geom)
                if step==len(states)-1:
                    assert [c['type'] for c in cs[step]]==['hold_current_joints','hold_current_joints','emergency_stop'];io.actuate(b,cs[step][0]);break
                for cmd in cs[step]:io.actuate(b,cmd)
                b.step(1)
            with b.observe_physics_steps(record):close=robot.grasp('object',timeout_ms=1000)
            begin=b.total_physics_steps;tcp=robot.get_state().tcp_pose;target=Pose(x=tcp.x,y=tcp.y,z=max(.16,tcp.z+.10));path=VerticalClearancePath(task_id=episode,step_id='native-lift',skill='LIFT',start_m=(tcp.x,tcp.y,tcp.z),target_m=(target.x,target.y,target.z),minimum_height_m=.08)
            ref,reference=optical('SERVO_REFERENCE');provider=OpenCVServoFeedback(ref,tracker,ground,skill='LIFT',initial_target=target,marker_family_id=geom['marker_family'],verify_mujoco_calibration=True)
            def sample(previous):
                f,r=optical('NATIVE_FEEDBACK');measured=provider.update(f);r['target_m']=[measured.x,measured.y,measured.z];r['sample_finish_ns']=time.monotonic_ns();return MotionTarget(measured,previous.orientation_wxyz)
            session=VisualServoSession(sample,vertical_clearance=path)
            with robot.visual_servo(session),b.observe_physics_steps(record):action=robot.lift(target.z-tcp.z,resolved_target=target,timeout_ms=10000,tcp_velocity=.15,acceleration=.5)
            graphics={k:GL.glGetString(i).decode() for k,i in [('renderer',GL.GL_RENDERER),('vendor',GL.GL_VENDOR)]}
            rr=io.stack(rows);np.savez_compressed(dest/'measured.npz',**rr);stop=b.total_physics_steps;pos=rr['step'];mask=pos<len(old['step']);ix=pos[mask];i=pos>=begin
            delta=np.linalg.norm(rr['tcp'][i,:2]-np.array([tcp.x,tcp.y]),axis=1);exact={k:float(abs(rr[k][mask]-old[k][ix]).max()) for k in ('q','qvel','tcp','centers')}
            frameindex=[]
            for f,r in frames:
                fp=dest/f'{len(frameindex):04d}.json.gz'
                with fp.open('xb') as stream:stream.write(gzip.compress(f.model_dump_json().encode(),3,mtime=0))
                marker=measure_frame(f,geom);frameindex.append(r|dict(file=fp.name,sha256=io.sha(fp),usable_ids=marker['usable_ids'],reason=marker['reason']))
            feeds=[r for r in frameindex if r['target_m'] is not None];fresh=[n for n in session.records if n.get('sample_and_ik_s') is not None]
            outrow=dict(case=case,scope='Original actuator and optical single-skill closed loop using real newly captured marked RGB-D, original vertical guard and fixed wrist, after exact successful APPROACH return. No repair to full online G1 worker gates and no formal or hardware episode.',
                original_prefix_maximum_residuals=res,registered_xml_sha256=io.sha(root/native.REG['frozen_runtime']/native.REG['frozen_asset']),graphics=graphics,
                grasp_terminal_success=close.success,lift_success=action.success,lift_error=action.error_code,lift_details=action.details,
                start_step=begin,terminal_step=stop,source_nominal_sha256=io.sha(olddir/'normal.npz'),physical_fixed_target_trajectory_maximum_residual_on_common_steps=exact,
                reference_endpoint_m=[target.x,target.y,target.z],live_provider_max_target_change_m=max((float(np.linalg.norm(np.array(r['target_m'])-[target.x,target.y,target.z])) for r in feeds),default=None),
                achieved_lateral_peak_m=float(delta.max()),last_120_minimum_cube_bottom_gain_m=float((rr['cube_bottom_m'][-120:]-old['centers'][0,10,2]+.035).min()) if stop-begin>=120 else None,
                actual_LIFT_movement_feedback_count=len(fresh),actual_LIFT_all_feedback_count=len(feeds),max_native_feedback_and_IK_ms=max((r['sample_and_ik_s']*1000 for r in fresh),default=None),
                max_capture_and_direct_provider_ms=max(((r['sample_finish_ns']-r['acquisition_begin_ns'])/1e6 for r in feeds),default=None),
                received_unplanned_physical_contact=bool(np.any(rr['contacts'][:,3])),input_frame_index=frameindex,source_file_sha256=io.sha(Path(__file__)))
            io.write(dest/'live.json',outrow);print(case,action.success,action.error_code,stop-begin,delta.max(),exact,outrow['max_native_feedback_and_IK_ms'],flush=True)
    finally:cam.close();b.shutdown()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--case',action='append',required=True);opt=parser.parse_args();root=opt.root.resolve();cv2.setNumThreads(1)
    with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for name in opt.case:execute(root,opt.out.resolve(),name)
