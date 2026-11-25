"""Branch each preregistered loaded/released feedback window on the native emergency stop."""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
path=HERE.parent/'round-g1-skill-handoff-20261125'/'handoff-physics-stops.py'
spec=importlib.util.spec_from_file_location('payload_stops',path)
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
io=helpers.io

def anchors(steps):
    first,last=int(steps[0])-1,int(steps[-1])
    if last<first+8:return []
    candidates=[first,first+8,first+((last-first)//16)*8,last-8,*range(first+8,last-7,64)]
    return sorted(k for k in set(candidates) if first<=k<=last-8)

def run(case,source,output):
    source=source/case
    summary=io.read(source/'summary.json')
    cfg=io.read(HERE/'payload-motion-preregistration.json')
    registration=HERE/'payload-motion-preregistration.json'
    if case not in cfg['input_training_trajectories'] and case not in cfg['prospective_validation']:
        registration=HERE/'payload-motion-preregistration-02.json'
        cfg['prospective_validation']=io.read(registration)['prospective_validation']
        if case not in cfg['prospective_validation']:
            registration=HERE/'payload-motion-preregistration-03.json'
            cfg['prospective_validation']=io.read(registration)['prospective_validation']
    if case in cfg['input_training_trajectories']: expected='train'
    elif case in cfg['prospective_validation']:expected='new_whole_trajectory_validation'
    else:raise ValueError('unregistered source')
    if summary['role']!=expected:raise ValueError('wrong frozen role')
    out=output/case;out.mkdir(parents=True,exist_ok=True)
    xml=Path(cfg['old_native_runtime'])/helpers.acquire.REG['frozen_asset']
    b=io.init(xml,dict(object_position_m=[.45,0,.035],object_geom_rotation_row_major=np.eye(3).ravel().tolist(),
             joint_positions_rad=[-.8,0,0,0,0,0,0],finger_positions_m=[.04,.04]),dict(case=dict(seed=summary['seed'])))
    m=b._model;d=b._data
    cube=m.geom('object_geom').id;table=m.geom('table').id;left=m.geom('left_finger_geom').id;right=m.geom('right_finger_geom').id
    names=[m.geom(i).name for i in range(m.ngeom)]
    with np.load(source/'normal.npz') as raw,np.load(source/'restart.npz') as restart:
        records={k:raw[k] for k in ('q','qvel','command_q','command_open','step','stage')}
        states=restart['packed']
    schema=dict(case=case,role=expected,normal_sha256=io.sha(source/'normal.npz'),packed_sha256=io.sha(source/'restart.npz'),
        xml_sha256=io.sha(xml),prereg_sha256=io.sha(registration),
        collision_indices=names,phases={})
    try:
        for phase in cfg['phases']:
            ts=records['step'][records['stage']==phase]
            indices=anchors(ts) if len(ts) else []
            row=[]
            for start in indices:
                f=out/f'{phase}-{start}.npz'
                if not f.exists():
                    qs=np.empty((9,241,m.nq));vs=np.empty((9,241,m.nv));drive=np.empty((9,241,9))
                    hits=np.zeros((9,241,4),np.int16);first=np.full((9,241,2),-1,np.int16)
                    for j in range(9):
                        step=start+j;cmd=records['command_q'][step];opened=bool(records['command_open'][step])
                        io.restore(b,(states[step],cmd,opened,step))
                        if max(abs(d.qpos-records['q'][step]).max(),abs(d.qvel-records['qvel'][step]).max())>1e-12:raise ValueError('restore mismatch')
                        b.emergency_stop()
                        if [v['type'] for v in b.command_records[-2:]]!=['hold_current_joints','emergency_stop']:raise ValueError('stop missing')
                        for t in range(241):
                            qs[j,t]=d.qpos;vs[j,t]=d.qvel;drive[j,t]=d.ctrl
                            for contact in d.contact:
                                a,bb=int(contact.geom1),int(contact.geom2);pair={a,bb}
                                k=0 if pair=={left,cube} else 1 if pair=={right,cube} else 2 if pair=={table,cube} else 3
                                hits[j,t,k]+=1
                                if k==3:first[j,t]=[a,bb]
                            if t<240:b.step()
                    np.savez_compressed(f,q=qs,qvel=vs,ctrl=drive,contacts=hits,forbidden_ids=first)
                row.append(dict(step=start,file=f.name,sha256=io.sha(f)))
            schema['phases'][phase]=row;print(case,phase,len(row),flush=True)
        io.write(out/'index.json',schema)
    finally:b.shutdown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.case,a.source,a.output)
