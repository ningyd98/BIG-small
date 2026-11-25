"""Evaluate measured bilateral contact patches and conservative gravity wrench feasibility."""
import argparse
import gzip
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
from scipy.optimize import OptimizeWarning, linprog


def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def frame(manifolds,com,r,c,geom_names,mass):
    obj=geom_names.index('object_geom');finger=[geom_names.index(x) for x in ('left_finger_geom','right_finger_geom')];patches=[[],[]];vertices=[];capacities=[];world=np.zeros(3);moment=np.zeros(3);per_side=np.zeros(2);friction_lift=0.;arms=[];g=mass*9.81
    for a,b,dist,position,fr,mu,w in manifolds:
        pair={a,b}; f=next((i for i,x in enumerate(finger) if x in pair),None)
        if obj not in pair or f is None or w[0]<=1e-7:continue
        p=np.array(position);contact_frame=np.array(fr);nj=float(w[0]);per_side[f]+=nj
        basis=contact_frame if b==obj else -contact_frame; actual=np.asarray(w[:3])@basis;lever=p-com;world+=actual;moment+=np.cross(lever,actual)
        patches[f].append((p-c)@r);arms.append(lever)
        friction_lift+=nj*np.sqrt((mu[0]*basis[1,2])**2+(mu[1]*basis[2,2])**2)
        # Convex hull of four transverse rays is INSIDE each measured Coulomb cone.
        # Give no credit for solver contact torsion, the table or non-finger contact.
        rays=basis[0]+np.array([mu[0]*basis[1],-mu[0]*basis[1],mu[1]*basis[2],-mu[1]*basis[2]])
        vertices.extend(np.column_stack((rays,np.cross(lever,rays))))
        capacities.append(nj)
    nf=len(capacities);spans=np.zeros((2,2));obj_local_centers=np.full((2,3),np.nan)
    for i,points in enumerate(patches):
        if points:
            pc=np.array(points);spans[i]=np.ptp(pc[:,[0,2]],axis=0);obj_local_centers[i]=pc.mean(axis=0)
    capacity=0.;lateral_lever=0.;gravity_moment=0.
    if arms:
        middle=np.mean(arms,axis=0);lateral_lever=float(np.linalg.norm(middle[:2]));gravity_moment=g*lateral_lever
    if per_side.min()>0:
        wrenches=np.array(vertices).T;wrenches[3:]*=30
        eq=np.column_stack((wrenches,[0.,0.,-g,0.,0.,0.]));ub=np.zeros((nf,4*nf+1))
        for i in range(nf):ub[i,i*4:i*4+4]=1
        objective=np.zeros(4*nf+1);objective[-1]=-1
        res=linprog(objective,A_ub=ub,b_ub=capacities,A_eq=eq,b_eq=np.zeros(6),bounds=(0,None),method='highs',options={'threads':1})
        if not res.success:raise ValueError(res.message)
        capacity=float(res.x[-1]);
        if np.max(abs(eq@res.x))>2e-6 or np.max(ub@res.x-capacities)>2e-6:raise ValueError('wrench support solution did not close')
    return dict(force_N=per_side,patch_point_counts=np.array([len(p) for p in patches]),patch_xz_span_m=spans,
        patch_center_object_m=obj_local_centers,gravity_scale_from_measured_normals=capacity,
        transverse_upward_friction_capacity_N=friction_lift,force_world_N=world,measured_contact_torque_Nm=moment,
        contact_centroid_world_horizontal_lever_m=lateral_lever,gravity_torque_about_measured_patch_centroid_Nm=gravity_moment)


def run(root,out,name):
    d=root/'experiments/results/g1-skill-handoff-20261125/physical-capture-01'/name;orig=read(d/'summary.json');
    with np.load(d/'normal.npz') as a:states={k:a[k] for k in ('step','stage','centers','rotation','world_com','cube_in_tcp','cube_bottom_m','cube_tilt_deg','force_N')}
    rows=json.loads(gzip.decompress((d/'contact-manifolds.json.gz').read_bytes()));results=[]
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',category=OptimizeWarning,message='Unrecognized options detected.*')
        for j,(step,man) in enumerate(rows):
            if step!=states['step'][j]:raise ValueError('contact time ordering changed')
            z=frame(man,states['world_com'][j],states['rotation'][j,10],states['centers'][j,10],orig['model_contact_geom_names'],orig['model_mass_kg']);results.append(z)
    arrays={k:np.stack([r[k] for r in results]) for k in results[0]};np.testing.assert_allclose(arrays['force_N'],states['force_N'],rtol=1e-6,atol=2e-7)
    out.mkdir(exist_ok=True,parents=True);afile=out/(name+'-wrenches.npz');np.savez_compressed(afile,step=states['step'],stage=states['stage'],**arrays)
    phases={}
    for phase in ('GRASP','LIFT','MOVE_TO_REGION','PLACE','RELEASE'):
        ix=np.flatnonzero(states['stage']==phase)
        if not len(ix):continue
        end=ix[-1:];held=ix[-120:] if phase=='LIFT' and len(ix)>=120 else None
        def summarize(v):
            return dict(tick_start=int(v[0]),tick_end=int(v[-1]),gravity_wrench_capacity_in_weights_min=float(arrays['gravity_scale_from_measured_normals'][v].min()),
                        normal_force_N_min=arrays['force_N'][v].min(axis=0).tolist(),friction_lift_N_min=float(arrays['transverse_upward_friction_capacity_N'][v].min()),
                        peak_gravity_torque_about_patch_centroid_Nm=float(arrays['gravity_torque_about_measured_patch_centroid_Nm'][v].max()),
                        peak_com_to_patch_centroid_horizontal_lever_m=float(arrays['contact_centroid_world_horizontal_lever_m'][v].max()),
                        patch_point_counts_min=arrays['patch_point_counts'][v].min(axis=0).tolist(),
                        face_xz_contact_span_min_m=arrays['patch_xz_span_m'][v].min(axis=0).tolist(),
                        max_cube_tilt_from_upright_deg=float(states['cube_tilt_deg'][v].max()),
                        minimum_measured_upward_finger_force_N=float(arrays['force_world_N'][v,2].min()))
        phases[phase]=dict(terminal=summarize(end),last_120=summarize(held) if held is not None else None)
    obj=dict(case=name,role=orig['role'],weight_N=orig['model_mass_kg']*9.81,contact_raw_sha256=sha(d/'contact-manifolds.json.gz'),normal_raw_sha256=sha(d/'normal.npz'),per_tick_wrench_sha256=sha(afile),
             phases=phases,scope='Only the two original finger patches, their native per-contact normal force budgets, two sliding friction coefficients and six-component force/torque balance. Conservative four-generator friction diamond. Numbers characterize this nominal dynamic state and a static gravity direction; actual lift, hold, forbidden touch and slip remain separate checks.')
    path=out/(name+'-wrench-summary.json');path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n');print(name,phases['GRASP']['terminal']['gravity_wrench_capacity_in_weights_min'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--case',required=True);a=p.parse_args();run(a.root.resolve(),a.out,a.case)
