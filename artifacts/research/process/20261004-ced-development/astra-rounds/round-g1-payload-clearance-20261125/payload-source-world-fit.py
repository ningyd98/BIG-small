"""Fit the same signed world envelope within the separately observed original support neighbourhood."""
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry,support_axes
from scripts.graduation.g1_complete_cv_payload import SPEED_CLASSES,object_matrix
from scripts.graduation.g1_complete_cv_payload_fit import measurements

root=Path.cwd();reg=Path(__file__).with_name('payload-motion-preregistration.json')
cfg=json.loads(reg.read_bytes());private=root/'experiments/results/g1-payload-clearance-20261125'
src=Path('scripts/graduation/g1_complete_cv_source_support_profile.json')
asset=Path(cfg['old_native_runtime'])/'assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml'
mg=MotionGeometry(Model(asset));axis=support_axes();tables={};sources={}
for case in cfg['input_training_trajectories']:
    index=private/'physical-stops-01'/case/'index.json';ix=json.loads(index.read_bytes())
    sources[case]=digest(index)
    for row in ix['phases']['LIFT']:
        path=index.parent/row['file'];assert digest(path)==row['sha256']
        with np.load(path) as z:q=z['q'][0,0]
        bottom=q[11]-abs(object_matrix(q[None])[0,2])@mg.model.object[0].h
        if not -.001<=bottom<=.025:continue
        w,rel,speed,bad,start=measurements(mg,path,axis);assert not bad
        for key in ['all',*[str(k) for k in SPEED_CLASSES if speed<=k]]:
            group=tables.setdefault(key,dict(world=np.zeros_like(w),windows=0,sources=set()))
            group['world']=np.maximum(group['world'],w)
            group['windows']+=1;group['sources'].add(case)
out=dict(schema='g1.named-source-world.v1',asset_sha256=digest(asset),parts=mg.names,source_support_sha256=digest(src),sources=sources,
    classes={key:dict(world=(np.ceil(group['world']*1e8)/1e8).tolist(),windows=group['windows'],sources=sorted(group['sources']))
        for key,group in tables.items() if len(group['sources'])>=2})
dest=Path('scripts/graduation/g1_complete_cv_source_motion_profile.json')
with dest.open('x') as f:json.dump(out,f,sort_keys=True,indent=2);f.write('\n')
print(digest(dest))
