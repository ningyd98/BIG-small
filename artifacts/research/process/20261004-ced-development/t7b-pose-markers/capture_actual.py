"""One excluded marked S01 reset/settle capture; truth stays in offline output."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

asset=Path('assets/robots/franka_panda/scene_pose_marker_v1.xml')
base=Path(__file__).resolve().parent/'actual-capture-1'
base.mkdir(exist_ok=False)
config=SimulatorConfig(domain_randomization=False,model_path=str(asset),camera_width=320,camera_height=240,
                       render_rgb=True,render_depth=True)
registration=PoseMarkerRegistration(7,.0525,hashlib.sha256(asset.read_bytes()).hexdigest())
with MuJoCoCaptureSession(config) as session:
    session._backend.step(120) # only settling under unchanged reset/controller initialization
    frame=session.capture_with_instances()
    observation=frame.observation
    save_captured_frame(frame,base/'frame')
    (base/'frame/observation-full.json').write_text(observation.model_dump_json(indent=2)+'\n')
    result=detect_pose_marker(observation,registration) # no truth, labels or instance input
    output=asdict(result);output['captured_at']=result.captured_at.isoformat()
    # Read simulator truth only AFTER online output, into a separate offline file.
    body=session._backend._model.body('object').id
    truth_pos=session._backend._data.xpos[body].copy()
    truth_rotation=session._backend._data.xmat[body].reshape(3,3).copy()
    truth_marker=truth_pos+truth_rotation@np.array([0.,0.,.03505])
    offline={'scope':'OFFLINE_ONLY_NOT_DETECTOR_INPUT','object_center_world_m':truth_pos.tolist(),
        'object_rotation_to_world':truth_rotation.ravel().tolist(),
        'marker_top_center_world_m':truth_marker.tolist(),'actual_sensor_noise_std_m':session._backend._sensor_noise_std_m}
    if result.marker_center_world_m is not None:
        offline['observed_marker_center_error_m']=float(np.linalg.norm(np.array(result.marker_center_world_m)-truth_marker))
        offline['observed_rotation_error_rad']=float(np.arccos(np.clip((np.trace(truth_rotation.T@np.array(result.rotation_marker_to_world).reshape(3,3))-1)/2,-1,1)))
    (base/'offline-truth-comparison.json').write_text(json.dumps(offline,indent=2)+'\n')
    summary={'kind':'REAL_DEVELOPMENT_CAPTURE','scenario':'S01_NORMAL_STATIC','seed':0,
        'status':result.status,'reason':result.reason,'detector':output,
        'image_dimensions':[observation.width,observation.height],
        'camera':'unchanged rgbd top camera, pos=(.35,0,1.4), fovy=50',
        'marked_asset_sha256':registration.marked_asset_sha256,'registration_hash':registration.digest(),
        'model_requests':0,'controller_commands':len(session._backend._command_records),'robot_actions':0,
        'physics_steps_for_settling':120,'physical_success':'NOT_RUN',
        'native_evidence_status':'NOT_PROMOTED','continuous_motion_bound':'UNAVAILABLE','calibrated_error_bound':'UNAVAILABLE'}
    assert summary['controller_commands']==0
    (base/'assessment.json').write_text(json.dumps(summary,indent=2)+'\n')
    hashes={str(path.relative_to(base)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(base.rglob('*')) if path.is_file()}
    (base/'raw-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps({key:value for key,value in summary.items() if key!='detector'},indent=2))
