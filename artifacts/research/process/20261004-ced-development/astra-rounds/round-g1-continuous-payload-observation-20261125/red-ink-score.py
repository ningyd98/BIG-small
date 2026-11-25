"""Read frozen per-frame estimates, then independently compare true poses and physical contacts."""
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model,box_gap

HERE=Path(__file__).resolve().parent
BASE=Path('experiments/results/g1-continuous-payload-observation-20261125')
OUT=BASE/'red-ink-fit-01'
ASSET=Path('assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
jread=lambda p:json.loads(p.read_bytes())
def form(c,r,a,old,label,packet,model):
    truth=np.asarray(label['center_m']); actual=np.asarray(label['rotation']); tcp,w,_=model.forward(packet['camera_joint_positions_rad']);jaw=w[:,1];f=np.asarray(packet['camera_finger_positions_m']); width=.035*np.abs(jaw@r).sum()
    offset=float((c-tcp)@jaw);gaps=[f[0]+.001-offset-width,f[1]+.001+offset-width]; hb=model.hand_at(tcp,w,f); bb=model.object[0].placed(c,r); pads=[box_gap(i,bb) for i in hb[1:]]
    anch=(truth+actual@np.array(old['anchor_object_m'])-a)@r
    centerjaw=float((c-truth)@jaw)*1000
    mat=float(np.max(np.abs(r.T@actual-np.eye(3))/np.asarray(old['basis_error_object'])))
    ar=float(np.max(abs(anch)/np.asarray(old['anchor_error_object_m'])))
    yaw=float(np.rad2deg(np.arctan2(actual[:,1]@r[:,0],actual[:,0]@r[:,0])))
    return dict(jaw_mm=centerjaw,yaw_deg=yaw,center_mm=float(1000*np.linalg.norm(c-truth)),gaps_mm=(1000*np.array(gaps)).tolist(),boxgaps_mm=(1000*np.array(pads)).tolist(),
                old_bound_ratio=max(ar,mat),both_nominal_contact=bool(max(gaps)<=0 and max(pads)<=0))
def summarize(rows):
    if not rows:return {}
    out={'n':len(rows),'max_inner_fit_ms':max(v['ms'] for v in rows),'max_nominal_yaw_ambiguity_deg':max(v['angle_span'] for v in rows)}
    for side in ('old','new'):
        vals=[v[side] for v in rows];out[side]={'nominal_double_gap_nonpositive':sum(v['both_nominal_contact'] for v in vals),'outside_prior_bounds':sum(v['old_bound_ratio']>1 for v in vals)}
        for metric in ('yaw_deg','jaw_mm','center_mm'):
            a=np.abs([v[metric] for v in vals]);out[side][metric+'_median_max']=[float(np.median(a)),float(a.max())]
    return out
def main():
    seal=HERE/'red-ink-frozen-before-physics.public.json'
    assert sha(seal)=='5057ce8e432d8003adffb253144b089ee9a275e1085e2129f47d72a85f7bba4d'
    assert all(sha(Path(n))==v for n,v in jread(seal)['input_sha256'].items())
    mdl=Model(ASSET); summary={}; ledger=[]
    for n in ('dense-fit-01','dense-fit-02','dense-fit-03'):
        folder=BASE/'physical-03'/n; oldfile=BASE/(n+'-prediction-01.json')
        source=jread(OUT/(n+'.json')); assert sha(oldfile)==source['native_source_sha256']
        old={v['frame_id']:v for v in jread(oldfile)['records']}
        sensors={r['robot']['frame_id']:r['robot'] for r in jread(folder/'rgbd-index.json')['rows']}
        truth={r['frame_id']:r for r in jread(folder/'offline-physics.json')['frame_labels']}
        rows=[]
        for g in source['rows']:
            pose=old[g['frame_id']]['result']['pose'];new=g['pred']
            if not new:continue
            phy=truth[g['frame_id']]; packet=sensors[g['frame_id']]
            assert g['checksum']==phy['checksum_sha256']==packet['checksum_sha256'] and g['step']==phy['physics_step']
            actual=[sorted((tag+'_finger_geom','object_geom')) in phy['touching'] for tag in ('left','right')]
            e=dict(id=n,step=g['step'],skill=g['skill'],frame_id=g['frame_id'],checksum=g['checksum'],physical_bilateral=all(actual),
                   previously_held=old[g['frame_id']]['result']['relation']=='held',ms=g['elapsed_ms'],angle_span=new['competing_angle_range_deg'])
            for key,ctr,rot,an in [('old',pose['center_m'],pose['rotation'],pose['anchor_world_m']),('new',new['center'],new['rotation'],new['anchor'])]:
                e[key]=form(np.asarray(ctr),np.asarray(rot),np.asarray(an),pose,phy,packet,mdl)
            rows.append(e)
        for subset,group in [('all',rows),('lift',[e for e in rows if e['skill']=='LIFT']),('lift_previously_unknown',[e for e in rows if e['skill']=='LIFT' and not e['previously_held']]),('release_retreat',[e for e in rows if e['skill'] in ('RELEASE','RETREAT')])]:
            summary[n+'/'+subset]=summarize(group)
        ledger+=rows
    raw=OUT/'physical-score.json';text=json.dumps(ledger,sort_keys=True,allow_nan=False)+'\n'
    if raw.exists():assert raw.read_text()==text
    else:raw.open('x').write(text)
    refs={str(BASE/'physical-03'/n/'offline-physics.json'):sha(BASE/'physical-03'/n/'offline-physics.json') for n in ('dense-fit-01','dense-fit-02','dense-fit-03')}
    result=dict(ss=summary,physics_sources=refs,seal_sha256=sha(seal),reader_sha256=sha(Path(__file__)),raw_score_sha256=sha(raw),production_qualification=False)
    print(json.dumps(summary['dense-fit-02/lift'],indent=2))
    out=HERE/'red-ink-fit-scores.public.json';s=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if out.exists():assert out.read_text()==s
    else:out.open('x').write(s)
    print(sha(out))
if __name__=='__main__':main()
