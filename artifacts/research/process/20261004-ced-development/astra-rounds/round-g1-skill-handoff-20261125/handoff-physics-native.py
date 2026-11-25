"""Capture original native skill handoffs and branching inputs on a supervised development bench."""
from __future__ import annotations

import argparse
import collections
import gzip
import importlib.util
import json
import math
import sys
from contextlib import nullcontext
from pathlib import Path

import mujoco
import numpy as np
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.mujoco import backend as native
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('g1_native_brake_io',HERE.parent/'round-g1-braking-envelope-20261125/brake-physics-replay.py')
io=importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)
REG=io.read(HERE/'handoff-physics-preregistration.json')
STAGES=REG['stages']


def gz(path,obj):
    with path.open('xb') as f:
        f.write(gzip.compress(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),3,mtime=0))


def asdict_cmd(cmd):
    return {k:v for k,v in cmd.items() if k not in ('episode_id','sim_time_s')}


def commands_at(b):
    arm=None;gripper=None
    for r in reversed(b._command_records):
        if r['accepted'] and r['type'] in ('hold_current_joints','joint_target') and arm is None:
            arm=asdict_cmd(r)
        elif r['accepted'] and r['type']=='gripper' and gripper is None:
            gripper=asdict_cmd(r)
        if arm is not None and gripper is not None:break
    try:
        vel=list(b.get_joint_command_state().velocity_rad_s)
    except ValueError:
        vel=None
    return dict(last_accepted_native_arm_command=arm,last_accepted_gripper_command=gripper,
                command_q=b._target_positions.tolist(),native_sent_arm_velocity_rad_s=vel,
                command_open=b._gripper_open,ctrl=b._data.ctrl.tolist(),q=b._data.qpos.tolist(),
                qvel=b._data.qvel.tolist(),step=b.total_physics_steps)


class Sensors:
    def __init__(self,b):
        self.model=b._model;self.geo=io.Scene(b._model);self.d=mujoco.MjData(b._model)
        self.ids=self.geo.ids;self.named={n:self.model.geom(n).id for n in self.geo.all_names}
        self.names=self.geo.all_names
        self.obj=self.named['object_geom'];self.table=self.named['table'];self.fingers=[self.named[x] for x in ('left_finger_geom','right_finger_geom')]
        self.objectbody=self.model.body('object').id

    def snap(self,b):
        d=self.d;live=b._data
        d.qpos[:]=live.qpos;d.qvel[:]=live.qvel
        mujoco.mj_fwdPosition(self.model,d)
        r=d.geom_xmat[self.ids].reshape(-1,3,3).copy();g=d.geom_xpos[self.ids].copy()
        site=d.site('tcp');wr=site.xmat.reshape(3,3);rel=np.column_stack((wr.T@r[10],wr.T@(g[10]-site.xpos)))
        points=g[:,None,:]+self.geo.local@r.transpose(0,2,1)
        normal=np.zeros(2);counts=np.zeros(4,int);contacts=[]
        for ci,co in enumerate(live.contact):
            aa,bb=int(co.geom1),int(co.geom2);pair={aa,bb}; force=np.zeros(6)
            mujoco.mj_contactForce(self.model,live,ci,force)
            category=3
            if self.obj in pair:
                if self.table in pair:category=2
                else:
                    for jj,fi in enumerate(self.fingers):
                        if fi in pair:
                            category=jj;normal[jj]+=force[0]
            counts[category]+=1
            contacts.append([aa,bb,float(co.dist),co.pos.tolist(),co.frame.reshape(3,3).tolist(),
                             co.friction.tolist(),force.tolist()])
        bottom=float(points[10,:,2].min());tilt=math.degrees(math.acos(float(np.clip(r[10,2,2],-1.,1.))))
        return dict(q=live.qpos.copy(),qvel=live.qvel.copy(),ctrl=live.ctrl.copy(),
                    command_q=b._target_positions.copy(),command_open=b._gripper_open,
                    centers=g,rotation=r,tcp=site.xpos.copy(),tcp_rotation=wr.copy(),
                    cube_in_tcp=rel,force_N=normal,contacts=counts,cube_bottom_m=bottom,
                    world_com=d.xipos[self.objectbody].copy(),cube_tilt_deg=tilt),contacts


def setup(root,case):
    runtime=root/REG['frozen_runtime'];xml=runtime/REG['frozen_asset']
    if not Path(native.__file__).resolve().is_relative_to(runtime) or io.sha(xml)!='35f50ef8d18a13828541226552678b8ac3fcff4d597794957332f65eb623e1b6':
        raise ValueError('wrong runtime or marked physical asset')
    if io.sha(HERE/'plan.json')!=REG['plan_sha256'] or io.sha(Path(io.__file__))!=REG['continuation_support_sha256']:
        raise ValueError('plan or state branching helper changed')
    if case in REG['source_cases']:
        desc=REG['source_cases'][case];d=root/desc['dir']
        for n,h in desc['sha256'].items():
            if io.sha(d/n)!=h:raise ValueError('source changed '+n)
        states=io.read(d/'instance/offline-truth.json')['samples'];alloc=io.read(d/'allocation.json');run=io.read(d/'instance/run.json');
        handoffs={r['end_step']:r['skill'] for r in run['actions'][:2]};seed=alloc['case']['seed']
        target=run['bootstrap']['resolved_top_grasp_tcp_m'];aim=[target[k] for k in 'xyz']
        cmds=io.read(d/'instance/backend-commands.json'); cmds_by_step=collections.defaultdict(list)
        for c in cmds:cmds_by_step[c['physics_step']].append(c)
        return io.init(xml,states[0],alloc),dict(states=states,handoffs=handoffs,cmds=cmds_by_step,seed=seed,aim=aim,source=d)
    item=REG['fresh_poses'][case];x,y,z=item['object_center_m'];a=math.radians(item['yaw_deg']);rot=[math.cos(a),-math.sin(a),0,math.sin(a),math.cos(a),0,0,0,1];row=dict(object_position_m=[x,y,z],object_geom_rotation_row_major=rot,joint_positions_rad=[-.8,0,0,0,0,0,0],finger_positions_m=[.04,.04])
    dx,dy=item['bench_target_xy_error_mm'];aim=[x+dx/1000,y+dy/1000,z+item['bench_target_height_above_center_mm']/1000]
    return io.init(xml,row,{'case':{'seed':item['seed']}}),dict(seed=item['seed'],aim=aim)


def execute(robot,b,name,aim,task):
    # Physical calibration uses a fixed registered bench endpoint. The native controller still
    # samples at its normal 30 Hz. Raw image evidence is captured separately at the handoffs.
    variance=dict(tcp_velocity=.15,acceleration=.5,timeout_ms=10000)
    lo=Pose(x=aim[0],y=aim[1],z=aim[2]); high=Pose(x=lo.x,y=lo.y,z=max(.16,lo.z+.10))
    current=robot.get_state().tcp_pose;vert=Pose(x=current.x,y=current.y,z=max(.16,current.z+.10));
    desthigh=Pose(x=.2,y=.25,z=high.z);destlow=Pose(x=.2,y=.25,z=lo.z+.004)
    calls={'MOVE_ABOVE':lambda:robot.move_above('object',resolved_target=high,**variance),
           'APPROACH':lambda:robot.approach('object',resolved_target=lo,**variance),
           'GRASP':lambda:robot.grasp('object',timeout_ms=1000),
           'LIFT':lambda:robot.lift(vert.z-current.z,resolved_target=vert,**variance),
           'MOVE_TO_REGION':lambda:robot.move_to_region('target_region',resolved_target=desthigh,**variance),
           'PLACE':lambda:robot.place('target_region',resolved_target=destlow,**variance),
           'RELEASE':lambda:robot.release(timeout_ms=1000),
           'RETREAT':lambda:robot.retreat(vert.z-current.z,resolved_target=vert,**variance)}
    path=None
    if name in ('LIFT','RETREAT'):
        path=VerticalClearancePath(task_id=task,step_id='bench-'+name,skill=name,
              start_m=(current.x,current.y,current.z),target_m=(vert.x,vert.y,vert.z),minimum_height_m=.08)
    session=None if name in ('GRASP','RELEASE') else VisualServoSession(lambda prev:prev,vertical_clearance=path)
    with robot.visual_servo(session) if session else nullcontext():
        result=calls[name]()
    return result,session


def statecheck(b,record,res):
    io.compare(b,record,res)
    if max(res.values())>1e-6:raise ValueError('original physical trajectory mismatch '+str(res))


def acquire(root,case,out):
    out.mkdir(parents=True,exist_ok=False); b,inp=setup(root,case); robot=MuJoCoSkillRobot(b);sensors=Sensors(b)
    hist=[];states=[];contactlog=[];result=[];handoffs=[];residual={};role=REG['roles'][case]
    stage='SETTLE';normal_centers={};plan=io.read(HERE/'plan.json'); task='mechanical-handoff-'+case
    def collect():
        s,contacts=sensors.snap(b);s['step']=b.total_physics_steps;s['stage']=stage;hist.append(s)
        packed=io.pack(b);states.append(packed[0]);contactlog.append([b.total_physics_steps,contacts]);
    def seal(prev,nxt):
        s,c=sensors.snap(b)
        record=dict(outgoing=prev,incoming=nxt,held_object=robot.get_state().holding_object_id,
                    actual_active_commands=commands_at(b),native_object_pose=s['centers'][10].tolist(),
                    native_object_rotation=s['rotation'][10].tolist(),native_force_N=s['force_N'].tolist(),
                    cube_in_tcp=s['cube_in_tcp'].tolist(),start_step=b.total_physics_steps)
        handoffs.append(record)
    try:
        collect()
        if 'states' in inp:
            rows=inp['states'];events=inp['handoffs']; stage='SETTLE'
            for step,row in enumerate(rows):
                statecheck(b,row,residual)
                if step==120:stage='MOVE_ABOVE'
                if step==len(rows)-1:
                    # The first native hold is the successful APPROACH return; the next hold and
                    # emergency_stop belong to the denied GRASP PRE. The arm velocity is untouched.
                    cs=inp['cmds'][step];assert [c['type'] for c in cs]==['hold_current_joints','hold_current_joints','emergency_stop'];io.actuate(b,cs[0]);seal('APPROACH','GRASP');break
                for c in inp['cmds'][step]:
                    io.actuate(b,c)
                    if step in events and c['type']=='hold_current_joints':
                        seal('MOVE_ABOVE','APPROACH');stage='APPROACH'
                b.step(1);collect()
            result.extend([dict(stage=k,source='exact_archived_native_return',success=True,step=z) for z,k in sorted(events.items())]); first=2
        else:
            with b.observe_physics_steps(lambda _s:collect()):b.step(120)
            first=0
        for i,name in enumerate(STAGES[first:],start=first):
            stage=name;beg=b.total_physics_steps
            with b.observe_physics_steps(lambda _s:collect()):
                action,session=execute(robot,b,name,inp['aim'],task)
            row=dict(stage=name,step=b.total_physics_steps,start_step=beg,success=action.success,
                    error_code=action.error_code,details=action.details,
                    servo_feedback_count=len(session.records) if session else 0)
            result.append(row)
            print(case,name,beg,b.total_physics_steps,action.success,action.error_code,flush=True)
            if not action.success:break
            if i+1<len(STAGES):seal(name,STAGES[i+1])
        if result[-1]['stage']=='RETREAT' and result[-1]['success']:
            # Original final stability observation, outside every skill and with unchanged targets.
            stage='FINAL_OBSERVATION'
            with b.observe_physics_steps(lambda _s:collect()):b.step(240)
        io.write(out/'handoffs.json',handoffs);io.write(out/'actions.json',result)
        io.write(out/'commands.json',[asdict_cmd(c) for c in b._command_records]);gz(out/'contact-manifolds.json.gz',contactlog)
        a=io.stack(hist);np.savez_compressed(out/'normal.npz',**a);np.savez_compressed(out/'restart.npz',
                      packed=np.stack(states),step=a['step'],command_q=a['command_q'],command_open=a['command_open'])
        geom=sensors.geo;np.savez_compressed(out/'physical-geometries.npz',local_vertices=geom.local,names=io.NAMES)
        obj=b._model.body('object');base=a['cube_bottom_m'][0]; lifts=np.flatnonzero(a['stage']=='LIFT');
        grasp=np.flatnonzero(a['stage']=='GRASP');end=np.arange(max(0,len(a['step'])-120),len(a['step']));
        hold=lifts[-120:]; held_ok=bool(len(hold)==120 and np.all(a['cube_bottom_m'][hold]-base>=.05) and np.all(a['contacts'][hold,:2]>0));
        released=bool(result[-1]['stage']=='RETREAT' and result[-1]['success']);
        region_good=bool(released and np.all(np.max(abs((a['centers'][end,10,:2]-[.2,.25])),axis=1)<.08-.035) and np.all(a['contacts'][end,2]>0) and np.max(np.linalg.norm(a['qvel'][end,9:12],axis=1))<.01 and np.max(np.linalg.norm(a['qvel'][end,12:15],axis=1))<.1)
        report=dict(case=case,role=role,scope='offline supervised native physical calibration',registered_build=plan['runtime_build_sha256'],
                    plan_sha256=REG['plan_sha256'],seed=inp['seed'],aim_m=inp['aim'],
                    model_mass_kg=float(obj.mass[0]),model_local_com_m=obj.ipos.tolist(),model_principal_inertia=obj.inertia.tolist(),
                    mu_cube=b._model.geom('object_geom').friction.tolist(),mu_finger=b._model.geom('left_finger_geom').friction.tolist(),
                    model_contact_geom_names=sensors.names,physical_geometry_names=io.NAMES,initial_cube_bottom_m=float(base),
                    original_prefix_errors=residual,closed_real_bilateral=bool(len(grasp) and np.all(a['contacts'][grasp[-1],:2]>0)),
                    grasp_terminal_force_N=a['force_N'][grasp[-1]].tolist() if len(grasp) else None,
                    lift_last_120_minimum_bottom_gain_m=float(np.min(a['cube_bottom_m'][hold]-base)) if len(hold)==120 else None,
                    lift_terminal_120_bilateral_at_50mm=held_ok,final_120_settled_and_contained=region_good,
                    forbidden_structural_contact_steps=int(np.sum(a['contacts'][:,3]>0)),
                    first_illegal_step=next((int(a['step'][k]) for k in range(len(a['step'])) if a['contacts'][k,3]),None),
                    skill_summaries=[{k:v for k,v in rr.items() if k!='details'} for rr in result],complete_skill_transitions=len(handoffs),
                    capture_source='archived original online prefix then native bench' if first else 'prospective independently reset native bench',
                    formal_episodes=0,hardware=0)
        io.write(out/'summary.json',report)
        print('END',case,report['closed_real_bilateral'],held_ok,region_good,report['forbidden_structural_contact_steps'],flush=True)
    finally:b.shutdown()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();acquire(a.root.resolve(),a.case,a.out/a.case)

if __name__=='__main__':main()
