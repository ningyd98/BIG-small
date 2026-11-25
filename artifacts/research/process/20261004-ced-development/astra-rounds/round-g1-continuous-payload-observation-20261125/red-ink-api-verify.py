"""Verify reusable API against sealed predictions, including native OpenCV and on-frame costs."""
import base64
import collections
import gzip
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from read_dense_payload import bind_fixture
from read_pose_coverage import native_marker
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_red_geometry import RedInkGeometry

BASE=Path('experiments/results/g1-continuous-payload-observation-20261125')
OUT=BASE/'red-ink-fit-01'
HERE=Path(__file__).resolve().parent
ASSET=Path('assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml')
LIB='/tmp/g1-red-ink-parent-reproduction.so'
LIBSHA='6c230df4d7db12ecb8c868c2a934c1f6cd1d665ea050a972d5a01830baf02eb1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())


def main():
    native=BASE/'frozen-pre-change/g1_complete_cv_payload_observation.py'
    spec=importlib.util.spec_from_file_location('original_payload',native)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    kernel=RedInkGeometry(ASSET,Path(LIB),LIBSHA)
    measure,detector_sha=native_marker('816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb')
    orig_face=mod.red_face_pose
    rows=[]; outcomes=[]; frozen=[]; timings=[]
    pose_checks=collections.Counter()
    for n in ['dense-fit-01','dense-fit-02','dense-fit-03']:
        folder=BASE/'physical-03'/n
        receipt=read(folder/'sensor-receipt.json'); identity,g=bind_fixture(folder,receipt)
        sealed=OUT/(n+'.json'); refs={v['frame_id']:v for v in read(sealed)['rows']};frozen.append(sha(sealed))
        def refiner(frame,marker,geometry,rgb,depth,base=None):
            raw,face=orig_face(frame,marker,geometry,rgb,depth,base)
            # Preserve all stronger dual/remote-edge branches; apply only to the original red fallback.
            if base is not None or raw is None:return raw,face
            pt=refs.get(frame.frame_id)
            if not pt or not pt['pred']:return None,face
            assert pt['checksum']==frame.checksum_sha256
            began=time.perf_counter_ns()
            result=kernel.refine(frame,raw,rgb,depth)
            inner=(time.perf_counter_ns()-began)/1e6
            old=pt['pred']
            if old['competing_angle_range_deg']>1.+1e-9 or old['hit_search_boundary']:
                assert result is None
                pose_checks['ambiguous_refused']+=1
                timings.append(inner)
                return None,face
            assert result is not None,(n,pt['step'],frame.calibration_version,raw)
            for k,prev in [('anchor_world_m','anchor'),('center_world_m','center'),('rotation_object_to_world','rotation')]:
                assert np.max(abs(np.array(result[k])-np.array(old[prev])))<1e-12,(k,pt['step'])
            pose_checks['accepted_equal']+=1
            timings.append(inner)
            return dict(raw,**result),face
        mod.red_face_pose=refiner
        history={}
        for s in read(folder/'rgbd-index.json')['rows']:
            raw=gzip.decompress((folder/s['file']).read_bytes())
            start=time.perf_counter_ns()
            fr=RGBDObservation.model_validate_json(raw); pkt=s['robot']; step=pkt['physics_step']
            m=measure(fr,g); op=rigid_pose(fr,m,g,identity=identity,physics_step=step)
            res=mod.payload_observation(fr,m,g,pkt,s['skill'],s['phase'],identity=identity,physics_step=step,optical=op,history=history)
            ms=(time.perf_counter_ns()-start)/1e6; active=fr.frame_id in refs
            rows.append(dict(id=n,step=step,frame=fr.frame_id,checksum=fr.checksum_sha256,skill=s['skill'],method=active,relation=res['relation'],cv_ms=ms))
    def dist(values):
        return dict(zip(('p50','p99','max'),map(float,np.percentile(values,[50,99,100]))))
    raw=OUT/'api-timed-observations.json';raw.open('x').write(json.dumps(rows,sort_keys=True)+'\n')
    totals={name:dict(collections.Counter(r['relation'] for r in rows if r['id']==name and r['skill']=='LIFT')) for name in ('dense-fit-01','dense-fit-02','dense-fit-03')}
    doc=dict(helper_sha256=sha(Path('scripts/graduation/g1_complete_cv_red_geometry.py')),native_kernel_sha256=LIBSHA,cpp_sha256=sha(Path('scripts/graduation/g1_complete_cv_red_ink.cpp')),profile_sha256=sha(native.with_name('g1_complete_cv_relation_profile.json')),old_observer_sha256=sha(native),optical_detector_sha256=detector_sha,input_seals=frozen,observer_role='frozen original observer and unchanged gating with corrected point on red fallback; no independent interval claim or release authorization',resource='CPU single process, OPENBLAS_NUM_THREADS=1; OpenCV '+cv2.__version__,affinity=sorted(os.sched_getaffinity(0)),kernel_ms=dist(timings),full_cv_red_branch_ms=dist([r['cv_ms'] for r in rows if r['method']]),all_frames_cv_ms=dist([r['cv_ms'] for r in rows]),real_capture_and_IK_included=False,relation_counts_LIFT=totals,equality=dict(pose_checks),frames=len(rows),raw_sha256=sha(raw))
    f=HERE/'red-ink-api-validation.public.json';f.open('x').write(json.dumps(doc,indent=2,sort_keys=True)+'\n');print(sha(f),doc['full_cv_red_branch_ms'],doc['relation_counts_LIFT'])

if __name__=='__main__':main()
