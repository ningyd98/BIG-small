"""Open two pre-sealed physical trajectories only after the independently registered gate freeze."""
import argparse
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent

def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def run(root,name):
    stops=module('handoff-physics-stops');native=stops.acquire;io=native.io
    base=root/'experiments/results/g1-skill-handoff-20261125';out=base/'heldout-post-freeze-01';normal=out/'physical-capture-01';halt=out/'physical-stops-01'
    freeze=HERE/'handoff-motion-validation-freeze.public.json'; seal=base/'heldout-sealed-01/design.json'
    if io.sha(freeze)!='04811664819dae923571d546d55482fb4c9999c84a69716adc74bf75911f67ef' or io.sha(seal)!='76e3e877ac3ed1aeaad94a54a9a474929f50b6b18462703b64280c239e2f720b':raise ValueError('freeze or sealed design changed')
    case=io.read(seal)['cases'][name];native.REG['fresh_poses'][name]=case;native.REG['roles'][name]='new_whole_trajectory_post_freeze_holdout'
    d=normal/name
    if not(d/'summary.json').is_file():native.acquire(root,name,d)
    digests={str((d/n).relative_to(root)):io.sha(d/n) for n in ('normal.npz','restart.npz','commands.json','handoffs.json','actions.json','summary.json','physical-geometries.npz','contact-manifolds.json.gz')}
    br=out/(name+'-branch-inputs.json')
    if not br.exists():io.write(br,dict(freeze_sha256=io.sha(freeze),sealed_design_sha256=io.sha(seal),raw_bound_inputs=digests,native_source_sha256=io.sha(Path(native.__file__))))
    elif io.read(br)['raw_bound_inputs']!=digests:raise ValueError('native holdout files changed since its creation')
    stops.run(root,name,halt,None,8,capture_root=normal,input_register=br)
    stops.run(root,name,halt,None,None,capture_root=normal,input_register=br)
    module('handoff-physics-readback').run(root,out/'physical-readback-01',name,readback_base=out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--case',choices=['sealed-left','sealed-right'],required=True);a=p.parse_args();run(a.root.resolve(),a.case)
