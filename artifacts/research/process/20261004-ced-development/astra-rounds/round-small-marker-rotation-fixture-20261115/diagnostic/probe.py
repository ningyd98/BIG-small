import sys, runpy, math, json, hashlib
from pathlib import Path
import numpy as np
import cv2
root=Path('/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall')
sys.path.insert(0,str(root/'src'))
t=runpy.run_path(str(root/'tests/test_pose_marker_evidence.py'))
api=t['api']()
base=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
rows=[]
for k in range(4):
    obs,gray=t['_subpix_rejected_scene']((7,),quarter_turns=k)
    result=api.detect_pose_marker(obs,api.PoseMarkerRegistration(7,0.0525,'a'*64),corner_refinement='SUBPIX')
    pts=np.array(result.ordered_corners_px)
    expected=np.roll(base,k,axis=0)
    signs=np.sign(pts-pts.mean(axis=0))
    p=cv2.aruco.DetectorParameters(); p.errorCorrectionRate=0.0; p.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    _,ids,rejected=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),p).detectMarkers(gray)
    delta=math.atan2(math.sin(result.yaw_world_rad-math.radians(5)-k*math.pi/2),math.cos(result.yaw_world_rad-math.radians(5)-k*math.pi/2))
    rows.append(dict(k=k,status=result.status,yaw=result.yaw_world_rad,yaw_error_rad=delta,corners=pts.tolist(),expected_corner_signs=expected.tolist(),actual_corner_signs=signs.tolist(),ordered_correspondence=bool(np.array_equal(signs,expected)),wrong_rolls_rejected=[not np.array_equal(np.roll(signs,r,axis=0),expected) for r in [1,2,3]],reversal_rejected=not np.array_equal(signs[[0,3,2,1]],expected),native_ids=None if ids is None else ids.tolist(),rejected_count=len(rejected)))
print(json.dumps(dict(python=sys.version,opencv=cv2.__version__,numpy=np.__version__,source_module=api.__file__,results=rows),indent=2))
