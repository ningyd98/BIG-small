"""Re-evaluate the frozen observation gates with only the sealed current-frame pose changed."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
from read_dense_payload import bind_fixture
from read_pose_coverage import native_marker
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose

BASE=Path('experiments/results/g1-continuous-payload-observation-20261125')
HERE=Path(__file__).resolve().parent
OUT=BASE/'red-ink-fit-01'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main(n):
    assert n in ('dense-fit-01','dense-fit-02','dense-fit-03')
    sealed=HERE/'red-ink-frozen-before-physics.public.json'
    assert sha(sealed)=='5057ce8e432d8003adffb253144b089ee9a275e1085e2129f47d72a85f7bba4d'
    fn=OUT/(n+'.json'); assert sha(fn)==read(sealed)['input_sha256'][str(fn)]
    corrections={r['frame_id']:r for r in read(fn)['rows']}
    folder=BASE/'physical-03'/n; old=read(BASE/(n+'-prediction-01.json'))
    receipt=read(folder/'sensor-receipt.json'); geometry_context,g=bind_fixture(folder,receipt)
    mark,_=native_marker('816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb')
    original=BASE/'frozen-pre-change/g1_complete_cv_payload_observation.py'
    assert sha(original)==old['observer_sha256']
    spec=importlib.util.spec_from_file_location('frozen_pose_observer',original);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert sha(original.with_name('g1_complete_cv_relation_profile.json'))==old['current_profile_sha256']
    native_red=mod.red_face_pose
    def fitted(frame,*args,**kwargs):
        raw,face=native_red(frame,*args,**kwargs)
        rec=corrections.get(frame.frame_id)
        if rec:
            assert raw and raw['method']=='id8_and_red_top' and rec['checksum']==frame.checksum_sha256
            p=rec['pred']
            if not p or p['hit_search_boundary']:return None,face
            raw=dict(raw,center_world_m=p['center'],anchor_world_m=p['anchor'],rotation_object_to_world=p['rotation'])
        return raw,face
    mod.red_face_pose=fitted;history={};result=[]
    for s,o in zip(read(folder/'rgbd-index.json')['rows'],old['records'],strict=True):
        f=folder/s['file'];assert sha(f)==s['file_sha256']
        fr=RGBDObservation.model_validate_json(gzip.decompress(f.read_bytes()));pkt=s['robot']; assert o['frame_id']==fr.frame_id==pkt['frame_id']
        m=mark(fr,g); op=rigid_pose(fr,m,g,identity=geometry_context,physics_step=pkt['physics_step'])
        res=mod.payload_observation(fr,m,g,pkt,s['skill'],s['phase'],identity=geometry_context,physics_step=pkt['physics_step'],optical=op,history=history)
        result.append(dict(frame_id=fr.frame_id,checksum=fr.checksum_sha256,step=pkt['physics_step'],skill=s['skill'],old=o['result']['relation'],new=res['relation'],geometry_replay_method=(res['pose'] or {}).get('method'),gaps=res['evidence'].get('actual_inner_face_gaps_m')))
    f=OUT/(n+'-relation.json');f.open('x').write(json.dumps(dict(id=n,reader_sha256=sha(Path(__file__)),physics_read=False,original_observer_sha256=sha(original),preview_only=True,records=result),sort_keys=True)+'\n')
    print(n,Counter(e['new'] for e in result if e['skill']=='LIFT'))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');main(ap.parse_args().case)
