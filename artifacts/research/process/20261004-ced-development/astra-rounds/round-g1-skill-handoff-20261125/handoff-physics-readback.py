"""Cold-read native handoff / dwell stop files into paired-clearance and support measurements."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    with p.open('x') as f:json.dump(d,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')

def run(root,out,case,*,readback_base=None):
    base=readback_base or root/'experiments/results/g1-skill-handoff-20261125';norm=base/'physical-capture-01'/case;stops=base/'physical-stops-01'/case;out.mkdir(exist_ok=True,parents=True)
    with np.load(norm/'physical-geometries.npz') as g:local=g['local_vertices'];names=g['names'].tolist()
    with np.load(norm/'normal.npz') as r:normal={k:r[k] for k in ('step','q','qvel','tcp','centers','rotation','contacts','force_N','cube_in_tcp')}
    stages={};file_digests={};limits_source={}
    for hs in read(norm/'handoffs.json'):
        phase=hs['incoming'];edge=hs['start_step'];night=stops/phase;limits=read(night/'limits.json');limits_source[phase]=sha(night/'limits.json')
        expected=([str(i) for i in range(241)]+['pre']) if phase in ('GRASP','RELEASE') else [str(i) for i in range(9)]
        assert set(expected)=={str(r['delay']) for r in limits['delays']}; initial=normal['centers'][edge,:,None]+local@normal['rotation'][edge].transpose(0,2,1)
        clearance=None;min_gap=np.full(30,np.inf);max_body_step=np.zeros(18);signed_min=np.full((18,3),np.inf);signed_max=np.full((18,3),-np.inf)
        worst_drift=0.;lowest_bilateral=np.full(2,np.inf);dropped=0;bad=0;displacements=[];critical=[];subset_min=1.
        bool_allowed=phase in ('GRASP','LIFT','MOVE_TO_REGION','PLACE','RELEASE')
        forbidden_indices=[i for i,pair in enumerate(limits['geometry_pairs']) if not (bool_allowed and pair[0] in ('left_finger_geom','right_finger_geom') and pair[1]=='object_geom')]
        for label in expected:
            f=night/('stop-'+label+'.npz');file_digests[str(f.relative_to(base))]=sha(f);rec=read(night/('stop-'+label+'.json'));delta=0 if label=='pre' else int(label);native=delta+edge
            with np.load(f) as saved:
                q=saved['q'];vel=saved['qvel'];gaps=saved['pair_gap'];contacts=saved['contacts'];tor=saved['force_N'];rot=saved['rotation'];centers=saved['centers'];hold=saved['cube_in_tcp'];command=saved['ctrl'];xyz=centers[:,:,None]+local@rot.transpose(0,1,3,2)
            assert q.shape==(241,16) and gaps.shape==(241,30) and xyz.shape==(241,18,8,3) and np.isfinite(gaps).all() and np.isfinite(xyz).all()
            np.testing.assert_allclose(q[0],normal['q'][native],rtol=0,atol=1e-14);np.testing.assert_allclose(vel[0],normal['qvel'][native],rtol=0,atol=1e-14)
            np.testing.assert_allclose(command[:,7:9],np.broadcast_to(command[0,7:9],(241,2)),rtol=0,atol=1e-14)
            if delta==0 and clearance is None:clearance=gaps[0].copy()
            mn=gaps.min(axis=0);min_gap=np.minimum(min_gap,mn);dxyz=xyz-initial;lo=dxyz.min(axis=(0,2));hi=dxyz.max(axis=(0,2));signed_min=np.minimum(signed_min,lo);signed_max=np.maximum(signed_max,hi)
            max_body_step=np.maximum(max_body_step,np.linalg.norm(dxyz,axis=3).max(axis=(0,2)));bad+=int(np.any(contacts[:,3]>0));
            held=phase in ('LIFT','MOVE_TO_REGION','PLACE'); dropped+=int(held and np.any((contacts[:,:2]==0).any(axis=1)));lowest_bilateral=np.minimum(lowest_bilateral,tor.min(axis=0));
            slip=float(np.linalg.norm(hold[:,:,-1]-normal['cube_in_tcp'][edge,:,-1],axis=1).max());worst_drift=max(worst_drift,slip)
            assert abs(rec['window']['240']['minimum_forbidden_pair_gap_m']-mn[forbidden_indices].min())<1e-13
            subset_min=min(subset_min,float(mn[forbidden_indices].min()))
        stages[phase]=dict(edge_step=edge,role=limits['role'],previous_skill=hs['outgoing'],paired_gap_entry_m=clearance.tolist(),paired_gap_minimum_m=min_gap.tolist(),
            max_loss_from_matching_pair_at_phase_entry_m=np.maximum(clearance-min_gap,0).tolist(),
            world_per_body_negative_displacement_m=signed_min.tolist(),world_per_body_positive_displacement_m=signed_max.tolist(),
            per_body_maximum_corner_displacement_m=max_body_step.tolist(),maximum_relative_cube_in_tcp_displacement_m=worst_drift,
            phase_minimum_forbidden_pair_gap_m=subset_min,worst_minimum_bilateral_finger_normal_force_N=lowest_bilateral.tolist(),
            holds_with_structural_contact=bad,held_stops_losing_bilateral_at_any_tick=dropped,
            first_last_halt_offsets=[0,max(int(i) for i in expected if i!='pre')],number_of_stops=len(expected),
            effective_native_entry=hs['actual_active_commands'],entry_tcp=normal['tcp'][edge].tolist(),entry_cube_in_tcp=normal['cube_in_tcp'][edge].tolist())
    summary=read(norm/'summary.json'); write(out/(case+'-raw-sha256.json'),file_digests)
    result=dict(case=case,role=summary['role'],local_obb_named_vertices_sha256=sha(norm/'physical-geometries.npz'),normal_sha256=sha(norm/'normal.npz'),
                raw_file_manifest_sha256=sha(out/(case+'-raw-sha256.json')),stage_manifests_sha256=limits_source,body_names=names,pair_names=limits['geometry_pairs'],
                stage_diagnostics=stages,total_branch_physics_steps=sum(v['number_of_stops']*240 for v in stages.values()),
                notes='Paired losses are the maximum decrease of the same physical pair across the complete nominal prefix and every following native halt. For gripper calls this covers the whole 240 native ticks. XYZ signed displacements are measured on the identical body/corner against the original phase-entry physical pose, preserving correlation at each sample. An unobserved state requires independent coverage.')
    write(out/(case+'-summary.json'),result);print(case,sum(s['number_of_stops'] for s in stages.values()),'checked',flush=True)


def main():
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--case',required=True);args=a.parse_args();run(args.root.resolve(),args.out,args.case)

if __name__=='__main__':main()
