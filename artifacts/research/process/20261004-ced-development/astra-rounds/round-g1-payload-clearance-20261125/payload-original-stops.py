"""Reproduce the two real stops and branch all nine stop instants before/after their last frame."""
import collections
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from cloud_edge_robot_arm.simulation.models import GripperCommand

HERE=Path(__file__).resolve().parent
mod=HERE.parent/'round-g1-skill-handoff-20261125'/'handoff-physics-stops.py'
spec=importlib.util.spec_from_file_location('branch',mod);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
io=base.io

def run(label):
    case='cvfix-'+label;repo=Path.cwd();private=repo/'experiments/results/g1-complete-cv-repair-20261125'
    directory=private/'batches/train-full-04'/case;src=directory/'instance'
    alloc=io.read(directory/'allocation.json');raw=io.read(src/'offline-truth.json')['samples']
    aud=io.read(src/'local-clearance.json')['rows'];commands=collections.defaultdict(list)
    for x in io.read(src/'backend-commands.json'):commands[x['physics_step']].append(x)
    end=aud[-1]['physics_step'];b=io.init(repo/io.read(HERE/'payload-motion-preregistration.json')['registered_runtime']/alloc['case']['asset_path'],raw[0],alloc)
    out=repo/'experiments/results/g1-payload-clearance-20261125/original-stops-01'/label;out.mkdir(parents=True,exist_ok=True)
    ins=base.Instrument(b);pos={};dif={};stats=[]
    try:
        last_frame=next(x for x in reversed(aud) if x['skill']=='LIFT' and x['status']=='CLEAR' and x['physics_step']<=end-8)
        target=last_frame["target_xyz"];goal=None
        for step in range(end+1):
            io.compare(b,raw[step],dif)
            if max(dif.values())>1e-9:raise ValueError((step,dif))
            if step>=end-8:pos[step]=io.pack(b)
            if step==last_frame['physics_step']:
                xyz=[target[k] for k in 'xyz'] if isinstance(target,dict) else target
                goal=io.MuJoCoMotionController(b)._inverse_kinematics(np.array(xyz),np.asarray(io._DOWNWARD),b._model.site('tcp').id)
            if step==end:break
            for cmd in commands[step]:
                if cmd['type']=='gripper' and cmd['accepted']:
                    b.apply_gripper_command(GripperCommand(open=cmd['target_open']))
                else:io.actuate(b,cmd)
            b.step()
        sent=b.get_joint_command_state()
        laststep=max(k for k,xs in commands.items() if k<end and any(x['type']=='joint_target' and x['accepted'] for x in xs))
        conf=dict(max_velocity_rad_s=.15/.3,max_acceleration_rad_s2=.5/.3)
        for mode in ('observed','retained','last_accepted_visual_target'):
            if mode=='observed':anchors={k:pos[k] for k in range(end-8,end+1)}
            else:
                io.restore(b,pos[end]);anchors={}
                command=np.asarray(sent.positions_rad);velocity=np.asarray(sent.velocity_rad_s)
                for k in range(end,end+9):
                    anchors[k]=io.pack(b)
                    if k==end+8:break
                    if mode=='last_accepted_visual_target' and (k-laststep)%5==0:
                        command,velocity=io.native_next(b,goal,command,velocity,conf)
                    b.step()
            active=[]
            for step,packed in anchors.items():
                io.restore(b,packed);b.emergency_stop();rows=[];bad=[]
                for t in range(241):
                    v,contacts=ins.sample(b);rows.append(v)
                    if contacts:bad.append([t,contacts])
                    if t<240:b.step()
                a=io.stack(rows);f=out/f'{mode}-{step}.npz';np.savez_compressed(f,**a)
                active.append(dict(step=step,sha256=io.sha(f),finger_table_min_m=[float(a['pair_gap'][:,ins.pairs.index((n,'table'))].min()) for n in ('left_finger_geom','right_finger_geom')],
                    minimum_carrier_table_m=float(a['pair_gap'][:,24:].min()),unplanned_contact_ticks=len(bad),
                    minimum_finger_force_N=a['force_N'].min(0).tolist()))
            stats.append(dict(mode=mode,stops=active))
        outdir=out/'receipt.json'
        io.write(outdir,dict(case=case,terminal=end,prefix_max_absolute_residuals=dif,stages=stats,
            original_sha256={k:io.sha(src/k) for k in ('offline-truth.json','backend-commands.json','local-clearance.json')},
            note='Observed prefix is exact. Post-terminal extension retained the last applied drive or continued the last actually accepted visual goal at the original five-tick controller rate.'))
    finally:b.shutdown()
if __name__=='__main__':run(sys.argv[1])
