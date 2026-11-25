"""Independently read previously captured physical RK4 samples against the near-support world facets."""
import json
from pathlib import Path
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry,support_axes
from scripts.graduation.g1_complete_cv_payload import SPEED_CLASSES,object_matrix
from scripts.graduation.g1_complete_cv_payload_fit import measurements

data=Path('experiments/results/g1-payload-clearance-20261125')
near=Path('scripts/graduation/g1_complete_cv_source_motion_profile.json')
named=Path('scripts/graduation/g1_complete_cv_source_support_profile.json')
table=json.loads(near.read_bytes())['classes'];cert=json.loads(named.read_bytes())
asset=Path('assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml')
mg=MotionGeometry(Model(asset));out=[]
for file in sorted((data/'solver-substeps-all-01').glob('*/summary.json')):
    src=json.loads(file.read_bytes());case=src['case'];series='01' if int(case[-2:])<=3 else '02'
    index=data/('physical-stops-'+series)/case/'index.json';reg=json.loads(index.read_bytes())
    for x in src['rows']:
        if x['phase']!='LIFT' or not -.001<=x['first_bottom_m']<=cert['max_current_gap_m']:continue
        row=next(z for z in reg['phases']['LIFT'] if z['step']==x['step'])
        path=index.parent/row['file'];assert digest(path)==row['sha256']
        world,_,speed,bad,q0=measurements(mg,path,support_axes())
        keys=[str(k) for k in SPEED_CLASSES if speed<=k and str(k) in table];key=keys[0] if keys else 'all'
        bound=1.25*np.asarray(table[key]['world'])+.0005
        rk=file.parent/x['file'];assert digest(rk)==x['sha256']
        with np.load(rk) as z:q=z['native_rk4'][:,:,1:17].reshape(-1,16)
        world0=mg.vertices(*mg.solids(q0[None,:7],q0[None,7:9],q0[None,9:12],object_matrix(q0[None]))[:2])[0]
        c,r,*_=mg.solids(q[:,:7],q[:,7:9],q[:,9:12],object_matrix(q));delta=mg.vertices(c,r)-world0
        pos=delta.max(axis=(0,2));neg=(-delta).max(axis=(0,2))
        actual=np.stack([pos,neg],axis=-1).reshape(-1,6)
        out.append(dict(case=case,step=x['step'],world_hermite_margin_m=float((bound-world).min()),
            rk4_world_margin_m=float((bound-actual).min()),raw_sha256=x['sha256'],speed_class=key,
            physical_force_N=x['max_table_force_N'],min_bilateral_force_N=x['min_bilateral_force_N'],negative_distance_m=x['min_solver_support_distance_m'],
            tilt_deg=x['max_cube_tilt_degrees'],stop_xy_m=x['max_stop_cube_xy_drift_m'],forbidden_contacts=bad))
dst=data/'source-support-physics-01.json'
with dst.open('x') as f:json.dump(dict(near_sha256=digest(near),source_sha256=digest(named),rows=out),f,indent=2,sort_keys=True);f.write('\n')
print(len(out),min(x['world_hermite_margin_m'] for x in out),min(x['rk4_world_margin_m'] for x in out),digest(dst))
