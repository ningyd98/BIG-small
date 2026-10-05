"""Offline geometry audit and model-free exercise of unchanged online asset guard."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import mujoco
import numpy as np
from scripts import evaluate_rgbd_model_scenes as evaluation
from cloud_edge_robot_arm.simulation.mujoco.backend import GRIPPER_OPEN_TARGET_M
from cloud_edge_robot_arm.vision.top_grasp import CALIBRATED_ASSET_SHA256

path=Path('assets/robots/franka_panda/scene.xml'); model=mujoco.MjModel.from_xml_path(str(path)); data=mujoco.MjData(model)
left=model.geom('left_finger_geom'); right=model.geom('right_finger_geom')
def aperture(q):
 for name in ('finger_left_joint','finger_right_joint'):
  data.qpos[model.joint(name).qposadr[0]]=q
 mujoco.mj_forward(model,data)
 return float(data.geom_xpos[left.id,1]-left.size[1]-(data.geom_xpos[right.id,1]+right.size[1]))
current=hashlib.sha256(path.read_bytes()).hexdigest()
report={'asset_sha256':current,'closed_aperture_m':aperture(0),'command_open_aperture_m':aperture(GRIPPER_OPEN_TARGET_M),'full_limit_aperture_m':aperture(.04),'command_open_m':GRIPPER_OPEN_TARGET_M,'physical_slide_limit_m':float(model.joint('finger_left_joint').range[1]),'unchanged_online_calibration_sha256':CALIBRATED_ASSET_SHA256,'online_guard_rejected':False,'model_calls':0}
config=evaluation.nominal_dataset_config()
try:
 evaluation._evaluate_case({'case_id':'frozen-dev-guard-only'},Path('../guard-not-used'),snapshot=SimpleNamespace(grasp_profile='mujoco_upright_box_v1'),dataset_config=config)
except ValueError as exc:
 report['online_guard_rejected']='calibrated asset' in str(exc); report['online_guard_reason']=str(exc)
if not report['online_guard_rejected']: raise RuntimeError('unchanged online asset guard did not reject H3')
Path('../geometry-and-online-guard-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
