"""Lock an optical first-face prediction on the original t02 unknown before reading offline labels."""
import base64
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest,axial,write
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from cloud_edge_robot_arm.vision.observations import RGBDObservation

BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
ROUND=Path(__file__).resolve().parent


def load(step=2112):
    release=BASE/"batches/train-full-04/cvfix-t02"; d=release/"instance";author=json.loads((ROUND/"plan.json").read_bytes())["input_sha256"]
    a=json.loads((release/"allocation.json").read_bytes());gen=a["runtime_build_sha256"];rt=BASE/"builds"/gen/"runtime-source";l=json.loads((d/"local-clearance.json").read_bytes())
    rr=next(r for r in l["rows"] if r["physics_step"]==step and r["skill"]=="LIFT" and r["phase"]=="FEEDBACK")
    idx=json.loads((d/"pixel-index.json").read_bytes())["frames"];it=next(t for t in idx if t["frame_id"]==rr["frame_id"])
    rf=d/it["file"]
    if digest(rf)!=it["file_sha256"] or (step==2112 and digest(rf)!=author[str(rf)]):raise ValueError("sealed original camera frame")
    reset=json.loads((d/"reset-observed.json").read_bytes())
    b=bind_allocation((release/"allocation.json").read_bytes(),allocation_sha256=author[str(release/"allocation.json")],generation_sha256=digest(rt/"runtime-build.json"),
            calibration_sha256=digest(Path(a["calibration_directory"])/"manifest.json"),asset_sha256=digest(rt/a["geometry"]["asset_path"]),reset_scene_id=reset[-1]["parameters"]["requested"]["scenario_id"],reset_episode_id=reset[-1]["episode_id"])
    source=RGBDObservation.model_validate_json(rf.read_bytes());m=json.loads((d/"online-vision.json").read_bytes())["frames"][source.frame_id]["measurement"]
    pose=rigid_pose(source,m,a["geometry"],identity=b,physics_step=step)
    return source,pose,rr,a,it


def candidates(uv,frame,pose,geom):
    tf=np.asarray(frame.camera_to_world).reshape(4,4);f=frame.intrinsics;eye=tf[:3,3]
    ray=np.array([(uv[0]-f[2])/f[0],(uv[1]-f[3])/f[1],1.])@tf[:3,:3].T
    rot=np.asarray(pose["rotation"]);local=(eye-pose["center_m"])@rot;direction=ray@rot
    result=[]
    for node in ET.parse(geom["asset_path"]).findall("./worldbody/body[@name='object']/geom"):
        if node.get("type","box")!="box":continue
        c=np.fromstring(node.get("pos","0 0 0"),sep=" ");h=np.fromstring(node.get("size"),sep=" ")
        ab=(np.array([c-h,c+h])-local)/direction
        low=np.minimum(*ab);hi=np.maximum(*ab);front=float(max(low));far=float(min(hi))
        if far>=max(front,0):result.append((node.get("name"),front,far,int(np.argmax(low)),float(np.sign(-direction[np.argmax(low)]))))
    return sorted(result,key=lambda x:x[1])


if __name__=="__main__":
    fr,model,row,a,item=load()
    if not model:raise ValueError("no optically certified three-dimensional pose")
    d=axial(fr)
    rgb=cv2.imdecode(np.frombuffer(base64.b64decode(fr.rgb_png_base64),np.uint8),cv2.IMREAD_COLOR)[:,:,::-1]
    center=[171,122];table=[]
    for v in range(120,125):
        for u in range(169,174):
            table.append(dict(uv=[u,v],color=rgb[v,u].tolist(),axial_m=float(d[v,u]),
                  independent_optical_obb=candidates((u,v),fr,model,a["geometry"])[:3]))
    write(ROUND/"first-face-before-label.public.json",dict(raw=item,old=row["evidence"]["depth"],optical=model,neighborhood=table,
        prediction="only frozen original RGBD + independent matched marker + registered geometry used; online q and actual ray before all offline scene labels"))

