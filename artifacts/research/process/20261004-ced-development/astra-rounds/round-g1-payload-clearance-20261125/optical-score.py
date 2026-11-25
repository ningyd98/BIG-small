"""Score frozen RGB-D relation certificates; keep offline physical labels outside the observer."""
import argparse
import base64
import gzip
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation import g1_complete_cv_payload_observation as relation
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_calibrate import axial,digest,write
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation

BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
HERE=Path(__file__).resolve().parent
PROFILE=Path(relation.__file__).with_name("g1_complete_cv_relation_profile.json")
def load_rows(name):
    src=BASE/"payload-optics-01"/name
    manifest=json.loads((src/"index.json").read_bytes());allocation=src/"allocation.json";a=json.loads(allocation.read_bytes())
    rt=BASE/"builds"/a["runtime_build_sha256"]/"runtime-source";reset=json.loads((src/"reset.json").read_bytes())
    context=bind_allocation(allocation.read_bytes(),allocation_sha256=manifest["allocation_sha256"],generation_sha256=digest(rt/"runtime-build.json"),
        asset_sha256=digest(Path(a["geometry"]["asset_path"])),calibration_sha256=digest(BASE/"calibration-gpu-01/manifest.json"),reset_scene_id=reset["scene_id"],reset_episode_id=reset["episode_id"])
    path=rt/"scripts/graduation/g1_visibility_vision.py";s=importlib.util.spec_from_file_location("native_marker",path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    truth=json.loads((src/"offline-labels.json").read_bytes())["physical"]
    for entry,label in zip(manifest["rows"],truth,strict=True):
        f=src/entry["file"]
        if digest(f)!=entry["file_sha256"] or label["file"]!=entry["file"]:raise ValueError("archive changed")
        fr=RGBDObservation.model_validate_json(gzip.decompress(f.read_bytes()));mark=m.measure_frame(fr,a["geometry"])
        yield fr,mark,a["geometry"],entry,label,context

def errors(meas,truth):
    measured=np.asarray(meas["rotation_object_to_world"]);real=np.asarray(truth["rotation"])
    true_anchor=truth["center_m"]+real@meas["anchor_object_m"]
    e=abs((true_anchor-meas["anchor_world_m"])@measured)
    rad=abs(measured.T@real-np.eye(3))
    return e,rad

def fit():
    ee=[];er=[];count={};side_errors=[];middle_errors=[]
    for name in ("fit-a","fit-b","fit-c"):
        n=0
        for fr,m,g,entry,label,ctx in load_rows(name):
            if not ctx.matches(fr,m,g,entry["robot"]["physics_step"]):raise ValueError("identity")
            rgb=cv2.imdecode(np.frombuffer(base64.b64decode(fr.rgb_png_base64),np.uint8),1)[:,:,::-1]
            obs,face=relation.red_face_pose(fr,m,g,rgb,axial(fr))
            if obs and obs["ids"]==[8]:
                e,r=errors(obs,label);ee.append(e);er.append(r);n+=1
                rig=relation._model(g["asset_path"])
                jaw=rig.forward(entry["robot"]["camera_joint_positions_rad"])[1][:,1]
                side=relation.transverse_edges(face,obs,jaw)
                if side is not None:
                    width=.035*abs(jaw@np.asarray(label["rotation"])).sum();mid=jaw@label["center_m"]
                    side_errors.append(abs(side-np.array([mid-width,mid+width])))
                    projected_width=.035*abs(jaw@np.asarray(obs["rotation_object_to_world"])).sum()
                    middle=np.mean(side)+np.array([-projected_width,projected_width])
                    middle_errors.append((middle-np.array([mid-width,mid+width]))*[1,-1])
        count[name]=n
    # Sensor calibration floors and an explicit factor above fit residuals. The full
    # attributed object and all rotated corner intervals are checked on new trajectories.
    anchor=np.maximum([.00125,.00125,.0008],1.4*np.max(ee,axis=0)+.00020)
    basis=np.maximum(1.4*np.max(er,axis=0)+.0015,.00160)
    write(PROFILE,dict(schema="g1.current_red_block_and_marker.metric_pose.v1",single_id8_red_plane=dict(enabled=True,
        anchor=np.round(anchor,7).tolist(),basis=np.round(basis,7).tolist(),fit_trajectories=count),
        independent_rim=dict(samples=len(side_errors),error_m=np.maximum(.0029,1.4*np.max(side_errors,axis=0)+.0004).tolist(),
                             midpoint_outward_m=np.maximum(.0019,1.4*np.max(middle_errors,axis=0)+.0004).tolist()),
        plan_sha256=digest(HERE/"plan.json"),optical_capture_registration_sha256=digest(HERE/"optical-acquisition-preregistration.public.json")))
    print(count,anchor,basis)

def score(names,out):
    samples={}
    for name in names:
        records=[];history={};pre_dwell=None
        for fr,m,g,row,label,ctx in load_rows(name):
            step=row["robot"]["physics_step"]
            optical=rigid_pose(fr,m,g,identity=ctx,physics_step=step)
            # The fixture branches a real open dwell from the release return. The
            # separately archived original RETREAT comes from its own undwelled history.
            if row["phase"]=="DWELL" and pre_dwell is None:
                from copy import deepcopy
                pre_dwell=deepcopy(history)
            if row["skill"]=="RETREAT" and pre_dwell is not None:
                history=pre_dwell;pre_dwell=None
            result=relation.payload_observation(fr,m,g,row["robot"],row["skill"],row["phase"],identity=ctx,physics_step=step,optical=optical,history=history)
            model=result["pose"];e=result["evidence"];coverage=True;ratio=None
            if model:
                an,bb=errors(model,label)
                ratio=float(max((an/model["anchor_error_object_m"]).max(),(bb/model["basis_error_object"]).max()))
                coverage=ratio<=1.
            touches=label["touching"];bilateral=all(sorted((s+"_finger_geom","object_geom")) in touches for s in ("left","right"))
            table=sorted(("object_geom","table")) in touches
            records.append(dict(file=row["file"],skill=row["skill"],phase=row["phase"],step=step,relation=result["relation"],method=model["method"] if model else None,
                admitted_named_contact=result["allow_registered_block_table_contact"],bounded=coverage,worst_matrix_ratio=ratio,
                real_bilateral=bilateral,real_table=table,red=e.get("red_physical_face"),bottom=e.get("cube_bottom_interval_m"),nominal_bottom=e.get("nominal_cube_bottom_m"),
                actual_gaps=e.get("actual_inner_face_gaps_m"),boxgaps=e.get("finger_box_gap_m"),fing=e.get("encoder_finger_positions_m"),plane=e.get("support_surface_visible"),dest=e.get("registered_destination_visible"),
                rim=e.get("observed_support_and_rim"),separated=e.get("observed_two_finger_separation"),window=e.get("stable_observation_count"),
                closed=e.get("compatible_with_bilateral_holding")))
        samples[name]=records
    write(out,dict(sealed_profile=digest(PROFILE),observer_sha256=digest(Path(relation.__file__)),samples=samples))

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("work",choices=["fit","score"]);a.add_argument("--out",type=Path);a.add_argument("name",nargs="*");args=a.parse_args()
    if args.work=="fit":fit()
    else:score(args.name,args.out)
