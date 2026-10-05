import hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
from cloud_edge_robot_arm.vision.pose_marker_assets import build_colored_pose_marker_xml
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration,detect_pose_marker
from cloud_edge_robot_arm.vision.observations import RGBDObservation
root=Path.cwd()
base=root/'assets/robots/franka_panda/scene.xml'
asset=base.with_name('scene_pose_marker_color_v2.xml')
generated=build_colored_pose_marker_xml(base.read_bytes())
assert generated==asset.read_bytes(),'checked-in asset differs from deterministic builder'
tree=ET.fromstring(generated)
source=ET.fromstring(base.read_bytes())
old={n.get('name'):n for n in source.iter() if n.get('name')}
new={n.get('name'):n for n in tree.iter() if n.get('name')}
assert all(new[n].tag==old[n].tag and new[n].attrib==old[n].attrib for n in old)
assert all(g.get('mass')=='0' and g.get('contype')=='0' and g.get('conaffinity')=='0' for n,g in new.items() if n not in old)
rejected=[]
for variant in (base.read_bytes()+b'\n',base.read_bytes().replace(b'mass="0.08"',b'mass="0.09"'),b'<mujoco/>'):
 try:build_colored_pose_marker_xml(variant)
 except ValueError:rejected.append(True)
 else:raise AssertionError('nonexact base admitted')
observation=RGBDObservation.model_validate_json((root/'artifacts/research/process/20261004-ced-development/t7b-pose-marker-color/actual-capture-640/frame/observation-full.json').read_text())
registered=PoseMarkerRegistration(7,.045,hashlib.sha256(asset.read_bytes()).hexdigest())
estimate=detect_pose_marker(observation,registered)
assert estimate.status=='OBSERVED' and estimate.observed_marker_ids==(7,)
assert estimate.geometric_error_bound_m is None and estimate.angular_velocity_bound_rad_s is None and estimate.stability_status=='UNKNOWN'
foreign=detect_pose_marker(observation,PoseMarkerRegistration(8,.045,registered.marked_asset_sha256))
assert foreign.status=='UNKNOWN'
print(json.dumps({'checked_in_asset_equals_builder':True,'original_named_element_attributes_preserved':len(old),'no_mass_or_contact_additions':True,'nonexact_base_rejections':len(rejected),'native_saved_observation_checksum':estimate.observation_checksum_sha256,'registered_id_status':estimate.status,'foreign_id_status':foreign.status,'geometric_error_bound_m':estimate.geometric_error_bound_m,'angular_velocity_bound_rad_s':estimate.angular_velocity_bound_rad_s,'stability_status':estimate.stability_status,'scope':'SOFTWARE_ONLY + archived static observation replay, no capture/model/action/admission'},indent=2))
