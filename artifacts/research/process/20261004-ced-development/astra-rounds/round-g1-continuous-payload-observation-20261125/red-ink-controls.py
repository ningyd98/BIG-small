"""Pure current-frame source, identity, color-contrast and occlusion refusal controls."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_cv_red_geometry import RedInkGeometry

HERE=Path(__file__).resolve().parent
BASE=Path('experiments/results/g1-continuous-payload-observation-20261125')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
def main():
    a=Path('assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml')
    lib=Path('/tmp/g1-red-ink-parent-reproduction.so');kernel=RedInkGeometry(a,lib,sha(lib))
    folder=BASE/'physical-03/dense-fit-02';q=read(BASE/'dense-fit-02-prediction-01.json')
    i,r=next((i,r) for i,r in enumerate(q['records']) if r['skill']=='LIFT' and (r['result']['pose'] or {}).get('method')=='id8_and_red_top')
    pose=r['result']['pose'];item=read(folder/'rgbd-index.json')['rows'][i];p=folder/item['file']
    assert sha(p)==item['file_sha256']
    f=RGBDObservation.model_validate_json(gzip.decompress(p.read_bytes())); D=axial(f)
    rgb=cv2.imdecode(np.frombuffer(base64.b64decode(f.rgb_png_base64),np.uint8),1)[:,:,::-1]
    assert kernel.refine(f,pose,rgb,D)
    redless=rgb.copy();red,green,blue=rgb.astype(float).transpose(2,0,1)
    redless[(red>1.25*green+7)&(red>1.25*blue+7)]=[127,127,127]
    fail={'wrong_calibration':kernel.refine(f.model_copy(update={'calibration_version':'foreign'}),pose,rgb,D),
          'red_masked':kernel.refine(f,pose,redless,D),'no_print_contrast':kernel.refine(f,pose,np.full_like(rgb,127),D),
          'missing_depth':kernel.refine(f,pose,rgb,np.zeros_like(D)),'wrong_id':kernel.refine(f,dict(pose,ids=[7]),rgb,D),
          'wrong_frame':kernel.refine(f,dict(pose,frame_id='stale'),rgb,D),'wrong_checksum':kernel.refine(f,dict(pose,checksum_sha256='0'*64),rgb,D),
          'wrong_lever':kernel.refine(f,dict(pose,anchor_object_m=[.115,0,.03505]),rgb,D)}
    assert all(v is None for v in fail.values())
    f_out=HERE/'red-ink-controls.public.json';data=json.dumps(dict(fit_frame_sha256=sha(p),fit_frame_id=f.frame_id,test_sha256=sha(Path(__file__)),control_inputs='synthetic modifications of one actual training frame',original_positive=True,refused=list(fail)),indent=2,sort_keys=True)+'\n'
    if f_out.exists():assert f_out.read_text()==data
    else:f_out.open('x').write(data)
    print(sha(f_out))
if __name__=='__main__':main()
