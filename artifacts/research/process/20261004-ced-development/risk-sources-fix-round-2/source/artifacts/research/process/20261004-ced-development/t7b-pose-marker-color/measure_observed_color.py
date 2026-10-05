"""Offline replay: RGB-only neighborhood diagnostic, never native association."""
import base64
import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

process=Path(__file__).resolve().parent
asset=Path('assets/robots/franka_panda/scene_pose_marker_color_v2.xml')
current=RGBDObservation.model_validate_json((process/'actual-capture-640/frame/observation-full.json').read_text())
estimate=detect_pose_marker(current,PoseMarkerRegistration(7,.045,hashlib.sha256(asset.read_bytes()).hexdigest()))
rgb=np.asarray(Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))).convert('RGB'))
hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
red=((hsv[:,:,0]<12)|(hsv[:,:,0]>168))&(hsv[:,:,1]>70)&(hsv[:,:,2]>40)
_,_,stats,_=cv2.connectedComponentsWithStats(red.astype('uint8'),8)
summary={'scope':'OBSERVED_RGB_DIAGNOSTIC_NOT_NATIVE_WHOLE_OBJECT_ASSOCIATION','requested_color':'red',
    'total_observed_red_pixels':int(red.sum()),'largest_red_component_px':max([int(row[4]) for row in stats[1:]],default=0),
    'native_association':'NOT_ADMITTED','color_hole_filling':False,'instance_or_truth_input':False}
if estimate.ordered_corners_px is not None:
    corners=np.array(estimate.ordered_corners_px,dtype=np.float32)
    template=np.array([[0,0],[1,0],[1,1],[0,1]],dtype=np.float32)
    transform=cv2.getPerspectiveTransform(template,corners)
    def region(extent):
        delta=(extent/.045-1)/2
        coordinates=np.array([[-delta,-delta],[1+delta,-delta],[1+delta,1+delta],[-delta,1+delta]],dtype=np.float32)
        polygon=np.rint(cv2.perspectiveTransform(coordinates.reshape(1,4,2),transform)[0]).astype('int32')
        selection=np.zeros(red.shape,dtype='uint8')
        cv2.fillConvexPoly(selection,polygon,1) # selection only, original color mask unchanged
        return selection>0
    outer,quiet=region(.070),region(.060)
    rim=outer&(~quiet)
    summary.update(nominal_color_rim_region_pixels=int(rim.sum()),observed_red_in_nominal_rim_pixels=int((red&rim).sum()),
        observed_red_in_marker_neighborhood_pixels=int((red&outer).sum()),
        neighborhood_geometry_assumption='registered centered marker on original70mm cube face; observed corner homography, not simulator pose',
        observed_marker_id=list(estimate.observed_marker_ids),marker_native_min_side_px=estimate.measured_min_side_px,
        observation_checksum_sha256=estimate.observation_checksum_sha256)
(process/'actual-color-association-replay.json').write_text(json.dumps(summary,indent=2)+'\n')
assert summary==json.loads((process/'actual-color-association.json').read_text())
print(json.dumps(summary,indent=2))
