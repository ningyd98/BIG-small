"""Frozen-profile check against each prospective unseen physical stop and diagnostic camera frame."""
import argparse
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_cv_payload import PayloadClearance, SPEED_CLASSES, STAGES, object_matrix
from scripts.graduation.g1_complete_cv_payload_fit import measurements
from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT=Path.cwd()
PRIVATE=ROOT/'experiments/results'
DATA=PRIVATE/'g1-payload-clearance-20261125'
ORIGINAL=PRIVATE/'g1-complete-cv-repair-20261125'
PROFILE=ROOT/'scripts/graduation/g1_complete_cv_payload_profile.json'
FREEZE='48d5108e194fed21373f96133d174951afaf78fbe4a6e36766d2ee0ba6b1a10e'
def read(path):return json.loads(path.read_bytes())
def verify(label):
    batch=ORIGINAL/'batches/train-full-04'
    allocation=batch/('cvfix-'+label if label in ('t01','t02') else 'cvfix-t01')/'allocation.json'
    alloc=read(allocation)
    asset=ORIGINAL/'builds'/alloc['runtime_build_sha256']/'runtime-source'/alloc['case']['asset_path']
    profile=read(PROFILE)
    if digest(PROFILE)!=FREEZE or digest(asset)!=profile['asset_sha256']:raise ValueError('unfrozen model')
    mg=MotionGeometry(Model(asset));gate=PayloadClearance(mg,profile)
    if label in ('t01','t02'):
        directory=allocation.parent/'instance';reg=read(directory/'pixel-index.json')
        reset=next(row for row in read(directory/'reset-observed.json') if row['phase']=='END')
        idn=bind_allocation(allocation.read_bytes(),allocation_sha256=reg['allocation_sha256'],
                generation_sha256=alloc['runtime_build_sha256'],asset_sha256=digest(asset),
                calibration_sha256=alloc['calibration_sha256'],reset_scene_id=reset['parameters']['requested']['scenario_id'],reset_episode_id=reset['episode_id'])
        by_frame={r['frame_id']:r for r in reg['frames']}
        vision=read(directory/'online-vision.json')['frames'];rows=[]
        source_open=True
        for x in read(directory/'local-clearance.json')['rows']:
            if x['skill']!='LIFT':continue
            f=by_frame[x['frame_id']];path=directory/f['file']
            assert digest(path)==f['file_sha256']
            frame=RGBDObservation.model_validate_json(path.read_bytes())
            marker=vision[x['frame_id']]['measurement']
            rgb=rigid_pose(frame,marker,alloc['geometry'],identity=idn,physics_step=x['physics_step'])
            m=x['robot'];vals=[np.asarray(m[n]) for n in ('joint_positions_rad','finger_positions_m','joint_velocities_rad_s','finger_velocities_m_s')]
            bottom=None
            if rgb:
                bottom=mg.model.object[0].placed(np.array(rgb['center_m']),np.array(rgb['rotation'])).corners()[:,2].min()
                if bottom>.008:source_open=False
            # This dedicated readback isolates B's geometrical pass/stop at the original
            # failure. The runtime requires C's independently observed held/support relation.
            target=np.array([x['target_xyz'][k] for k in 'xyz'])
            r=gate.check('LIFT',*vals,m['handoff'],dict(pose=rgb,relation='held'),lambda box,xyz:True,allow_grasp_station_contact=source_open,native_target=target)
            rows.append(dict(step=x['physics_step'],phase=x['phase'],frame=x['frame_id'],bottom_m=bottom,source_support_allowed=source_open,original=x['reason'],method=rgb['method'] if rgb else None,geometry_only=r))
        return dict(case=label,rows=rows,note='Geometry readback uses original RGB-D, encoders, commands and identity. Independent relation and panel volumes are excluded from this isolated result.')
    series='01' if int(label.split('-')[-1])<=3 else '02'
    reg=DATA/('physical-stops-'+series)/label/'index.json';normal=DATA/('fresh-normal-'+series)/label/'normal.npz'
    ix=read(reg);assert ix['normal_sha256']==digest(normal) and ix['xml_sha256']==digest(asset)
    actions={x['stage']:x for x in read(normal.parent/'actions.json')};ans=[]
    with np.load(normal,allow_pickle=False) as nz:
        q=nz['q'];v=nz['qvel'];ctrl=nz['ctrl']
        for stage in STAGES:
            for d in ix['phases'].get(stage,[]):
                i=d['step'];branch=reg.parent/d['file'];assert digest(branch)==d['sha256']
                world,rel,speed,forbidden,anchor=measurements(mg,branch,gate.axes)
                assert np.max(abs(q[i]-anchor))<1e-10
                limits=gate.data[stage]['classes'];keys=[str(k) for k in SPEED_CLASSES if speed<=k and str(k) in limits]
                bucket=keys[0] if keys else 'all';bound=limits[bucket]
                w=bound['world']-world;rr=bound['relative']-rel
                pose=dict(center_m=q[i,9:12],rotation=object_matrix(q[i:i+1])[0],anchor_object_m=[0]*3,anchor_error_object_m=[0]*3,basis_error_object=np.zeros((3,3)))
                action=actions[stage];t=action['details'].get('target_pose')
                if t is None and stage in ('LIFT','RETREAT'):
                    start=mg.poses(q[action['start_step']:action['start_step']+1,:7],q[i:i+1,7:9])[2][0]
                    t={'x':start[0],'y':start[1],'z':max(.16,start[2]+.10)}
                target=np.array([t[k] for k in 'xyz']) if t else None
                result=gate.check(stage,q[i,:7],q[i,7:9],v[i,:7],v[i,7:9],dict(effective_joint_target_rad=ctrl[i,:7],effective_finger_target_m=ctrl[i,7:9],entry_joint_positions_rad=q[action['start_step'],:7]),
                    dict(pose=pose,relation=('supported_and_separated' if stage=='RETREAT' else 'held')),lambda box,xyz:True,allow_grasp_station_contact=stage in ('PLACE','RETREAT') or (stage=='LIFT' and q[i,11]-.035<=.008),native_target=target)
                wi=np.unravel_index(w.argmin(),w.shape);ri=np.unravel_index(rr.argmin(),rr.shape)
                ans.append(dict(step=int(i),skill=stage,bucket=bucket,geometry_only=result,forbidden_contact_ticks=forbidden,
                     world_min_m=float(w[wi]),world_part=mg.names[wi[0]],world_direction=int(wi[1]),
                     relative_min_m=float(rr[ri]),used_palm_and_finger_relative_min_m=float(rr[mg.hand_start:].min()),relative_part=mg.names[ri[0]],relative_direction=gate.axes[ri[1]].tolist(),
                     finger_downward_min_margin_m=w[mg.hand_start+1:mg.load_start,5].tolist(),file_sha256=d['sha256']))
    return dict(case=label,rows=ans,normal_sha256=digest(normal),stop_index_sha256=digest(reg),note='Offline independent physical measurement is used as zero-error pose to test mechanical scope. Native contact values are isolated from the runtime API.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--output',default='validation-01');a=p.parse_args();r=verify(a.case)
    r['profile_sha256']=digest(PROFILE)
    out=DATA/a.output;out.mkdir(exist_ok=True);f=out/(a.case+'.json')
    with f.open('x') as h:json.dump(r,h,sort_keys=True,indent=2,allow_nan=False);h.write('\n')
    print(a.case,len(r['rows']),digest(f))
