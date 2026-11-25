"""Independently repeat native branches and record all four internal RK4 evaluations and forces."""
import argparse
import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import AXES,SPEED_CLASSES,PayloadClearance,object_matrix

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_stops',HERE/'payload-motion-stops.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
io=source.io

def run(case,all_windows=False):
    private=Path('experiments/results');data=private/'g1-payload-clearance-20261125'
    series='01' if case.startswith('fit-') or int(case.split('-')[-1])<=3 else '02'
    normal=(private/'g1-skill-handoff-20261125'/'physical-capture-01' if case.startswith('fit-') else data/('fresh-normal-'+series))/case
    old=data/('physical-stops-'+series)/case;ix=io.read(old/'index.json')
    cfg=io.read(HERE/'payload-motion-preregistration.json')
    asset=Path(cfg['old_native_runtime'])/source.helpers.acquire.REG['frozen_asset']
    prof=Path('scripts/graduation/g1_complete_cv_payload_profile.json')
    mg=MotionGeometry(Model(asset));gate=PayloadClearance(mg,io.read(prof))
    b=io.init(asset,dict(object_position_m=[.45,0,.035],object_geom_rotation_row_major=np.eye(3).ravel().tolist(),joint_positions_rad=[-.8,0,0,0,0,0,0],finger_positions_m=[.04,.04]),dict(case=dict(seed=io.read(normal/'summary.json')['seed'])))
    assert b._model.opt.integrator==mujoco.mjtIntegrator.mjINT_RK4
    m,d=b._model,b._data
    cube=m.geom('object_geom').id;table=m.geom('table').id
    jaws={m.geom('left_finger_geom').id:0,m.geom('right_finger_geom').id:1}
    with np.load(normal/'restart.npz') as z:packed=z['packed']
    with np.load(normal/'normal.npz') as z:q=z['q'];cmd=z['command_q'];opened=z['command_open'];dq=z['qvel'];tcp=z['tcp']
    previous=mujoco.get_mjcb_control()
    if previous is not None:raise ValueError('external control callback in the original plant')
    out=data/('solver-substeps-all-01' if all_windows else 'solver-substeps-01')/case;out.mkdir(parents=True,exist_ok=True)
    results=[]
    native_four=[]
    def observe(model,state):
        native_four.append(np.r_[state.time,state.qpos.copy(),state.qvel.copy()])
    try:
        for stage,rows in ix['phases'].items():
            if not rows:continue
            chosen=rows if all_windows or stage=='LIFT' else [rows[k] for k in sorted({0,len(rows)//2,len(rows)-1})]
            allowed=gate.data[stage]['classes']
            for row in chosen:
                start=row['step'];original=old/row['file'];assert io.sha(original)==row['sha256']
                with np.load(original) as z:expected=z['q'];expected_v=z['qvel']
                speed=abs(dq[start,:7]).max();keys=[str(v) for v in SPEED_CLASSES if speed<=v and str(v) in allowed]
                limits=allowed[keys[0] if keys else 'all']
                q0=q[start];r0=object_matrix(q0[None]);w0=mg.vertices(*mg.solids(q0[None,:7],q0[None,7:9],q0[None,9:12],r0)[:2])[0]
                arm0=(w0[:mg.load_start]-q0[9:12])@r0[0]
                raw=[];forces=[];world_gap=np.inf;relative_gap=np.inf;tcp_reverse=0.;tcp_xy=0.;normal_force=0.;residual=0.
                for j in range(9):
                    step=start+j;io.restore(b,(packed[step],cmd[step],bool(opened[step]),step));b.emergency_stop()
                    force=[]
                    mujoco.set_mjcb_control(observe);native_four.clear()
                    try:
                        for t in range(241):
                            residual=max(residual,float(abs(d.qpos-expected[j,t]).max()),float(abs(d.qvel-expected_v[j,t]).max()))
                            counts=np.zeros(4);fn=np.zeros(4);penetration=0.
                            for k,co in enumerate(d.contact):
                                a,bb=int(co.geom1),int(co.geom2);ids={a,bb}
                                which=2 if ids=={cube,table} else next((n for g,n in jaws.items() if ids=={cube,g}),3)
                                counts[which]+=1;ff=np.zeros(6);mujoco.mj_contactForce(m,d,k,ff);fn[which]+=ff[0]
                                if which==2:penetration=min(penetration,float(co.dist))
                            force.append(np.r_[counts,fn,penetration])
                            if t<240:b.step()
                    finally:mujoco.set_mjcb_control(None)
                    if residual>1e-10:raise ValueError(('instrumented terminal changed',case,start,j,residual))
                    internal=np.array(native_four)
                    if len(internal)!=960:raise ValueError(('wrong substep count',len(internal)))
                    dt=np.round((internal[:4,0]-internal[0,0])*240,7)
                    if not np.array_equal(dt,[0,.5,.5,1]):raise ValueError(('unexpected RK4 stages',dt))
                    a=internal[:,1:17];rot=object_matrix(a);c=a[:,9:12]
                    centers,rs,measured,_=mg.solids(a[:,:7],a[:,7:9],c,rot)
                    world=mg.vertices(centers,rs)
                    rel=(world[:,:mg.load_start]-c[:,None,None])@rot[:,None]
                    ww=world-w0;hh=rel-arm0
                    wu=np.stack([np.maximum(np.max(ww[:,:,:,i],axis=(0,2)),0) for i in range(3)]+[np.maximum(np.max(-ww[:,:,:,i],axis=(0,2)),0) for i in range(3)],1)[:,[0,3,1,4,2,5]]
                    world_gap=min(world_gap,(limits['world']-wu).min())
                    for k in range(mg.hand_start,mg.load_start):
                        projected=(hh[:,k].reshape(-1,3)@gate.axes.T).max(0)
                        relative_gap=min(relative_gap,(limits['relative'][k]-projected).min())
                    tcp_reverse=max(tcp_reverse,float(np.max(np.maximum.accumulate(measured[:,2])-measured[:,2])))
                    tcp_xy=max(tcp_xy,float(np.linalg.norm(measured[:,:2]-tcp[start,:2],axis=1).max()))
                    raw.append(internal);forces.append(force)
                raw=np.stack(raw);forces=np.array(forces);f=out/f'{stage}-{start}.npz';np.savez_compressed(f,native_rk4=raw,contact_counts_then_force_N_and_depth_m=forces)
                c=raw[:,:,10:13];rot=object_matrix(raw[:,:,1:17].reshape(-1,16)).reshape(9,960,3,3)
                bottom=c[:,:,2]-.035*abs(rot[:,:,2]).sum(axis=-1)
                initial_lower=q0[11]-.035*abs(r0[0,2]).sum()
                results.append(dict(phase=stage,step=start,file=f.name,sha256=io.sha(f),first_bottom_m=initial_lower,
                    min_bottom_m=float(bottom.min()),max_stop_cube_xy_drift_m=float(np.linalg.norm(c[:,:,:2]-q0[9:11],axis=-1).max()),
                    max_cube_tilt_degrees=float(np.degrees(np.arccos(np.clip(rot[:,:,2,2],-1,1))).max()),
                    min_bilateral_force_N=forces[:,:,4:6].min(axis=(0,1)).tolist(),max_bilateral_force_N=forces[:,:,4:6].max(axis=(0,1)).tolist(),
                    source_table_contact_ticks=int((forces[:,:,2]>0).sum()),max_table_force_N=float(forces[:,:,6].max()),min_solver_support_distance_m=float(forces[:,:,8].min()),
                    unexpected_contact_ticks=int((forces[:,:,3]>0).sum()),tcp_vertical_reversal_m=tcp_reverse,tcp_xy_from_anchor_m=tcp_xy,
                    world_margin_m=float(world_gap),palm_fingers_relative_margin_m=float(relative_gap),native_endpoint_max_residual=residual))
            print(case,stage,len(chosen),flush=True)
        io.write(out/'summary.json',dict(case=case,index_sha256=io.sha(old/'index.json'),fit_profile_sha256=io.sha(prof),rows=results,solver='unchanged four-stage RK4 at fractions 0,1/2,1/2,1; observation callback read-only; each native endpoint compared with the original physical branch'))
    finally:
        mujoco.set_mjcb_control(previous);b.shutdown()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--all',action='store_true');a=p.parse_args();run(a.case,a.all)
