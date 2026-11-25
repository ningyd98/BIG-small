"""Isolated empty-gripper negative control, native drive and true finger-table collision."""
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_stops',HERE/'payload-motion-stops.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
io=module.io
def main(witness):
    cfg=io.read(HERE/'payload-motion-preregistration.json')
    asset=Path(cfg['old_native_runtime'])/module.helpers.acquire.REG['frozen_asset']
    root=Path('experiments/results/g1-payload-clearance-20261125')
    with np.load(root/'original-stops-01/t01/observed-1640.npz') as original:q0=original['q'][0]
    out=root/('physical-pinned-jaw-negative-01' if witness else 'physical-table-geometry-negative-01');out.mkdir(exist_ok=True)
    mg=MotionGeometry(Model(asset))
    if witness:
        center,_rot,_,_=mg.poses(q0[None,:7],np.array([[.039,.039]]))
        left=center[0,mg.names.index('left_finger_geom')]
        xml=ET.parse(asset);world=xml.getroot().find('worldbody')
        ET.SubElement(world,'geom',dict(name='diagnostic_under_left_finger',type='box',pos=f'{left[0]} {left[1]} .005',size='.003 .003 .005',contype='2',conaffinity='2',rgba='.8 .69 .2 1'))
        asset=out/'actual-insert.xml';xml.write(asset)
    b=io.init(asset,dict(object_position_m=[.60,.27,.035],object_geom_rotation_row_major=np.eye(3).ravel(),
        joint_positions_rad=q0[:7].tolist(),finger_positions_m=[.039,.039]),dict(case=dict(seed=251125988)))
    m,d=b._model,b._data
    vals=[];actual=[];states=[]
    table=m.geom('diagnostic_under_left_finger' if witness else 'table').id;fingers=[m.geom(n+'_finger_geom').id for n in ('left','right')]
    def snap():
        gap=[mujoco.mj_geomDistance(m,d,g,table,1.,None) for g in fingers]
        contacts=[(m.geom(co.geom1).name,m.geom(co.geom2).name,float(co.dist)) for co in d.contact if table in {co.geom1,co.geom2} and {co.geom1,co.geom2}&set(fingers)]
        return gap,contacts
    try:
        b._gripper_open=True
        start=b.get_tcp_pose();xyz=np.array([start.x,start.y,.001])
        ctrl=io.MuJoCoMotionController(b)
        goal=ctrl._inverse_kinematics(xyz,np.asarray(io._DOWNWARD),b._model.site('tcp').id)
        cmd=q0[:7].copy();v=np.zeros(7)
        for t in range(600):
            gap,contact=snap();vals.append(np.r_[d.time,d.qpos,d.qvel,d.ctrl,gap]);actual.append(contact);states.append(io.pack(b))
            if contact or (not witness and min(gap)<-.001):break
            if t%5==0:cmd,v=io.native_next(b,goal,cmd,v,dict(max_velocity_rad_s=.5,max_acceleration_rad_s2=.5/.3))
            b.step()
        first=len(vals)-1
        if not actual[first] and (witness or min(vals[-1][-2:])>=0):
            f=out/'negative-no-touch-01.npz';np.savez_compressed(f,rows=vals)
            print('physical control did not contact table',start,b.get_tcp_pose(),goal,xyz,np.array(vals)[:,-2:].min(0),[m.geom(c.geom1).name+'/'+m.geom(c.geom2).name for c in d.contact])
            raise ValueError('physical control failed to reach table')
        files=[];f=out/'normal.npz';np.savez_compressed(f,rows=vals)
        for j in range(max(0,first-16),first+1):
            io.restore(b,states[j]);b.emergency_stop();a=[];c=[]
            for i in range(241):
                gap,contact=snap();a.append(np.r_[d.time,d.qpos,d.qvel,d.ctrl,gap])
                if contact or (not witness and min(gap)<0):c.append([i,contact,min(gap)])
                if i<240:b.step()
            branch=out/f'stop-{j}.npz';np.savez_compressed(branch,rows=a)
            files.append(dict(stop_step=j,sha256=io.sha(branch),start_gap_m=[float(v) for v in a[0][-2:]],minimum_gap_m=np.asarray(a)[:,-2:].min(0).tolist(),first_physical_contact=c[0] if c else None))
        io.write(out/'summary.json',dict(normal_sha256=io.sha(f),asset_sha256=io.sha(asset),solver_pair_contact_enabled=witness,
          original_collision_masks=dict(table=[1,1],finger=[2,2]),normal_first_contact_tick=first,
          normal_first_contact=actual[-1],normal_previous_gap_m=vals[-2][-2:].tolist(),rows=files,
          note='Physical negative control only. The object was placed clear of the deliberately descending jaws. The current-path command and the measured payload relation both disagree with LIFT. No native benchmark episode or evaluation slot was used.'))
    finally:b.shutdown()
if __name__=='__main__':main('--witness' in sys.argv)
