"""Integrate the actual native stop at every possible arrival and gripper-dwell tick."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np
from cloud_edge_robot_arm.simulation.models import GripperCommand

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('handoff_native', HERE/'handoff-physics-native.py')
acquire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acquire)
io = acquire.io
TIMES = (1,8,240)


class Instrument:
    def __init__(self,b):
        m=b._model;self.m=m;self.s=mujoco.MjData(m);self.scene=io.Scene(m)
        self.ids=self.scene.ids;self.names=self.scene.all_names
        self.pairs=list(io.PAIR_NAMES)+[(n,'table') for n in io.NAMES[11:17]]
        self.pair_ids=[(m.geom(a).id,m.geom(c).id) for a,c in self.pairs]
        self.indices=[(io.NAMES.index(a),io.NAMES.index(c)) for a,c in self.pairs]
        self.obj=m.geom('object_geom').id;self.table=m.geom('table').id
        self.fids=[m.geom('left_finger_geom').id,m.geom('right_finger_geom').id]
        self.forbid_physical=set();self.special=[]

    def sample(self,b):
        d=b._data;s=self.s;s.qpos[:]=d.qpos;mujoco.mj_kinematics(self.m,s)
        r=s.geom_xmat[self.ids].reshape(-1,3,3).copy();c=s.geom_xpos[self.ids].copy()
        tcp=s.site('tcp');rt=tcp.xmat.reshape(3,3);rel=np.column_stack((rt.T@r[10],rt.T@(c[10]-tcp.xpos)))
        raw=np.array([mujoco.mj_geomDistance(self.m,s,a,z,2.,None) for a,z in self.pair_ids]);gap=raw.copy()
        for i in np.flatnonzero(raw==0):
            a,z=self.indices[i];ra,rz=r[a].T,r[z].T
            axes=np.vstack((ra,rz,np.cross(ra[:,None],rz[None,:]).reshape(-1,3)))
            ln=np.linalg.norm(axes,axis=1);axes=axes[ln>1e-10]/ln[ln>1e-10,None]
            signed=abs(axes@(c[z]-c[a]))-abs(axes@r[a])@self.scene.half[a]-abs(axes@r[z])@self.scene.half[z]
            gap[i]=max(0.,float(signed.max()))
        counts=np.zeros(4,int);forces=np.zeros(2);bad=[]
        for i,co in enumerate(d.contact):
            q={int(co.geom1),int(co.geom2)};cell=3
            if self.obj in q:
                if self.table in q:cell=2
                else:
                    for jj,f in enumerate(self.fids):
                        if f in q:
                            force=np.zeros(6);mujoco.mj_contactForce(self.m,d,i,force)
                            cell=jj;forces[jj]+=force[0]
            if cell==3:bad.append((int(co.geom1),int(co.geom2),float(co.dist)))
            counts[cell]+=1
        bottom=float(c[10,2]-abs(r[10,2])@self.scene.half[10]);return dict(q=d.qpos.copy(),qvel=d.qvel.copy(),ctrl=d.ctrl.copy(),
              centers=c,rotation=r,tcp=tcp.xpos.copy(),tcp_rotation=rt.copy(),cube_in_tcp=rel,force_N=forces,contacts=counts,
              cube_bottom_m=bottom,pair_gap=gap,engine_gap=raw),bad


def bounds(s,ins,normal0,start,skill,offset,forbidden):
    xyz=s['centers'][:,:,None]+ins.scene.local@s['rotation'].transpose(0,1,3,2)
    unplanned=[i for i,p in enumerate(ins.pairs) if not (p[0] in ('left_finger_geom','right_finger_geom') and p[1]=='object_geom' and skill in ('GRASP','LIFT','MOVE_TO_REGION','PLACE','RELEASE'))]
    results={};vectors=[]
    for k in TIMES:
        pts=xyz[:k+1];delta=pts-xyz[0];disp=np.linalg.norm(delta,axis=-1);gaps=s['pair_gap'][:k+1];rel=s['cube_in_tcp'][:k+1];mov=np.linalg.norm(rel[:,:,-1]-rel[0,:,-1],axis=1)
        i,j=np.unravel_index(gaps[:,unplanned].argmin(),(k+1,len(unplanned)));idx=unplanned[j];shells={}
        for n,g in [('links',slice(0,7)),('hand',slice(7,8)),('fingers',slice(8,10)),('assembly',slice(10,17))]:shells[n]=float(disp[:,g].max())
        results[str(k)]=dict(minimum_forbidden_pair_gap_m=float(gaps[i,idx]),limiting_pair=ins.pairs[idx],minimum_after_stop_ticks=int(i),
             minimum_grasp_finger_gaps_m=[float(gaps[:,ins.pairs.index((n,'object_geom'))].min()) for n in ('left_finger_geom','right_finger_geom')],
             whole_mount_minimum_table_gap_m=float(gaps[:,24:].min()),max_corner_motion_by_group_m=shells,
             max_cube_in_tcp_translation_change_m=float(mov.max()),minimum_cube_bottom_m=float(s['cube_bottom_m'][:k+1].min()),
             minimum_finger_normal_forces_N=s['force_N'][:k+1].min(axis=0).tolist(),
             ticks_with_bilateral=int((s['contacts'][:k+1,:2]>0).all(axis=1).sum()),
             ticks_with_unplanned_actual_contact=int(np.sum(s['contacts'][:k+1,3]>0)),
             max_cube_world_displacement_m=float(np.linalg.norm(s['centers'][:k+1,10]-s['centers'][0,10],axis=1).max()))
        vectors.append([delta.min(axis=(0,2)),delta.max(axis=(0,2))])
    residual=abs(xyz[0]-normal0).max()
    if residual>1e-12:raise ValueError(f'fork differs from native endpoint {residual}')
    return dict(start_step=start,delay=offset,window=results,geometry_at_start_error_m=float(residual),forbidden_contacts=forbidden),np.array(vectors)


def run(root,case,out,stage_filter,max_offset,*,capture_root=None,input_register=None):
    reg=io.read(input_register or HERE/'handoff-physics-branches-preregistration.json');d=(capture_root or root/'experiments/results/g1-skill-handoff-20261125/physical-capture-01')/case
    for path,digest in reg['raw_bound_inputs'].items():
        if Path(path).parent==d.relative_to(root) and io.sha(root/path)!=digest:raise ValueError(path+' drifted')
    if io.sha(Path(acquire.__file__))!=reg['native_source_sha256']:raise ValueError('native capture source changed')
    with np.load(d/'restart.npz') as f:restart={k:f[k] for k in f.files}
    with np.load(d/'normal.npz') as f:normal={k:f[k] for k in ('step','centers','rotation')}
    commands=io.read(d/'commands.json');handoffs=io.read(d/'handoffs.json');
    case_out=out/case;case_out.mkdir(exist_ok=True,parents=True)
    for h in handoffs:
        skill=h['incoming'];start=h['start_step']
        if stage_filter and skill not in stage_filter:continue
        dest=case_out/skill;dest.mkdir(exist_ok=True)
        close=skill in ('GRASP','RELEASE');maximum=240 if close else 8
        offsets=([('pre',0)] if close else [])+[(str(k),k) for k in range(maximum+1)]
        b,_=acquire.setup(root,case);ins=Instrument(b);metadata=[]
        try:
            for label,k in offsets:
                if max_offset is not None and k>max_offset:continue
                archive=dest/('stop-'+label+'.npz');receipt=dest/('stop-'+label+'.json')
                if archive.is_file() and receipt.is_file():metadata.append(io.read(receipt));continue
                step=start+k;assert step==restart['step'][step];cmd=restart['command_q'][step];opened=bool(restart['command_open'][step]);
                if k==0:cmd=np.array(h['actual_active_commands']['command_q']);opened=bool(h['actual_active_commands']['command_open'])
                io.restore(b,(restart['packed'][step],cmd,opened,step));
                if k==0 and label!='pre':
                    previous=h['actual_active_commands']['last_accepted_native_arm_command'];last=previous['command_seq'] if previous else 0
                    following=[r for r in commands if r['physics_step']==step and r['command_seq']>last and r['accepted'] and r['type'] in ('gripper','joint_target')]
                    for c in following:
                        if c['type']=='gripper':b.apply_gripper_command(GripperCommand(open=c['target_open']))
                        else:io.actuate(b,c)
                b.emergency_stop()
                if [z['type'] for z in b.command_records[-2:]]!=['hold_current_joints','emergency_stop']:raise ValueError('missing native stop')
                samples=[];bad=[]
                for tick in range(241):
                    row,contacts=ins.sample(b);samples.append(row)
                    if contacts:bad.append([tick,contacts]);
                    if tick!=240:b.step(1)
                s=io.stack(samples);normal0=normal['centers'][step,:,None]+ins.scene.local@normal['rotation'][step].transpose(0,2,1)
                rec,extrema=bounds(s,ins,normal0,step,skill,label,bad)
                # The full-precision per-step poses and the bound local vertices recover every original corner.
                np.savez_compressed(archive,**s,world_corner_xyz_signed_extrema=extrema)
                io.write(receipt,rec);metadata.append(rec)
            if len(metadata)==len(offsets):
                manifest=dict(trajectory=case,role=acquire.REG['roles'][case],incoming=skill,outgoing=h['outgoing'],start_step=start,
                    time=TIMES,body_names=io.NAMES,geometry_pairs=ins.pairs,unplanned_actual_contact_name_index=ins.names,
                    inside_gripper_has_vision_callback=False if close else None,distinct_halt_branches=len(metadata),delays=metadata)
                limits=dest/'limits.json'
                if not limits.exists():io.write(limits,manifest)
                print(case,skill,len(metadata),'complete',flush=True)
        finally:b.shutdown()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--stage',action='append');p.add_argument('--max-offset',type=int);a=p.parse_args();run(a.root.resolve(),a.case,a.out,a.stage,a.max_offset)

if __name__=='__main__':main()
