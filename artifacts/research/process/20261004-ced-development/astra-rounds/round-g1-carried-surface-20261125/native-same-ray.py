"""Registered native RGB-D positive/counterfactual at already recorded exposures only."""
import argparse
import base64
import gzip
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from OpenGL import GL
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation.g1_complete_cv_calibrate import axial,digest,write
from scripts.graduation.g1_visibility_trials import device

def capture(out):
    rd=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location("surface_original",rd/"surface-failure.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    fr,pose,row,a,it=mod.load()
    base=mod.BASE;rt=base/"builds"/a["runtime_build_sha256"]/"runtime-source"
    if not Path(importlib.util.find_spec("cloud_edge_robot_arm.simulation.mujoco.camera").origin).resolve().is_relative_to(rt.resolve()):
        raise ValueError("original native camera required")
    native=base/"batches/train-full-04/cvfix-t02/instance";rows=json.loads((native/"local-clearance.json").read_bytes())["rows"];labels=json.loads((native/"offline-truth.json").read_bytes())["samples"]
    perstep={}
    for r in rows:
        if r["physics_step"]<=2112 and r.get("robot",{}).get("camera_joint_positions_rad") is not None:
            perstep[r["physics_step"]]=r
    out.mkdir(parents=True,exist_ok=False)
    asset=Path(a["geometry"]["asset_path"])
    root=ET.parse(base/"carried-surface-same-ray-01/physical-alias.xml")
    material=root.find("./asset/material[@name='diagnostic_reflective_tip']")
    material.set("rgba","1 1 1 1");material.set("emission",".35")
    alias=out/"physically_added_tip.xml";root.write(alias)
    rows=[]
    with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        models=[mujoco.MjModel.from_xml_path(str(p)) for p in (asset,alias)]
        ds=[mujoco.MjData(m) for m in models]
        cameras=[MuJoCoRGBDCamera(mujoco,m,width=320,height=240) for m in models]
        try:
            for step,record in sorted(perstep.items()):
                result=[]
                for mi,(m,d,cam) in enumerate(zip(models,ds,cameras,strict=True)):
                    robot=record["robot"];d.qpos[:7]=robot["camera_joint_positions_rad"]
                    for value,n in zip(robot["camera_finger_positions_m"],("left","right"),strict=True):
                        d.qpos[m.joint("finger_"+n+"_joint").qposadr[0]]=value
                    truth=labels[step]["object_geom_position_m"];rotation=labels[step]["object_geom_rotation_row_major"]
                    addr=m.joint("object_free").qposadr[0];d.qpos[addr:addr+3]=truth
                    mujoco.mju_mat2Quat(d.qpos[addr+3:addr+7],np.asarray(rotation).ravel())
                    d.time=step/240;mujoco.mj_forward(m,d)
                    im=observation_from_sensor_frame(cam.capture(d,rng=np.random.default_rng(649300+step),noise_std_m=.001,scene_id="registered-held-surface-source",episode_id="native-optical-pair-01"),source="mujoco_camera",png_compress_level=1)
                    result.append(im)
                    if step in (0,1504,2104,2112):
                        dest=out/f"{step:04d}-{mi}.json.gz";dest.write_bytes(gzip.compress(im.model_dump_json().encode(),mtime=0))
                clean,pin=result;dz=abs(axial(clean)-axial(pin));c0,_=__import__("cv2").imdecode(np.frombuffer(base64.b64decode(clean.rgb_png_base64),np.uint8),1),None
                c1=__import__("cv2").imdecode(np.frombuffer(base64.b64decode(pin.rgb_png_base64),np.uint8),1)
                rows.append(dict(step=step,physical_tip_unchanged=True,exact_native_rgb=clean.rgb_png_base64==pin.rgb_png_base64,
                    exact_native_depth=clean.depth_float32_base64==pin.depth_float32_base64,different_rgb_pixels=int(np.any(c0!=c1,axis=2).sum()),
                    different_depth_pixels=int((dz>0).sum()),peak_depth_delta_m=float(dz.max()),original_source_checksum=record["frame_id"],
                    original_2112_rgb_byte_equality=fr.rgb_png_base64==clean.rgb_png_base64 if step==2112 else None,
                    original_2112_depth_byte_equality=fr.depth_float32_base64==clean.depth_float32_base64 if step==2112 else None))
            gpu=GL.glGetString(GL.GL_RENDERER).decode()
        finally:
            for cam in cameras:cam.close()
    write(rd/"original-camera-alias.public.json",dict(verified_native_source_sha256=digest(rt/"src/cloud_edge_robot_arm/simulation/mujoco/camera.py"),
        gpu=gpu,physical_tip_xml_sha256=digest(alias),native_asset_sha256=digest(asset),native_noise_std_m=.001,seed="649300+actual_physics_step; identical in both models",
        original_archived_capture_sha256=it["file_sha256"],simulation_advances=0,new_formal_claims=0,actual_recorded_exposures=rows,
        raw_pairs={p.name:digest(p) for p in out.glob("*.gz")}))

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("out",type=Path);capture(a.parse_args().out)
