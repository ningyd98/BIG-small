"""Check the independent reset and cross-allocation controls on sealed original camera records."""
import argparse
import copy
import gzip
import importlib.util
import json
from pathlib import Path

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_calibrate import digest,write
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation


def run(out,public):
    base=Path("experiments/results/g1-complete-cv-repair-20261125")
    reg=json.loads((out/"before-any-capture.json").read_bytes())["registrations"]
    gen="80b08e403840b7441ee09d8859ba6abdf36477b40e7c254df2f2d842f2d00031"
    runtime=base/"builds"/gen/"runtime-source"
    spec=importlib.util.spec_from_file_location("current_registered_marker",runtime/"scripts/graduation/g1_visibility_vision.py")
    decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
    cert=digest(base/"calibration-gpu-01/manifest.json")
    rows=[];cases={}
    for name in ("sealed-left","sealed-right"):
        root=out/name;raw=(root/"allocation.json").read_bytes();a=json.loads(raw);geo=a["geometry"]
        reset=json.loads((root/"reset.json").read_bytes())
        idx=json.loads((root/"index.json").read_bytes())
        if idx["allocation_sha256"]!=reg[name] or idx["reset_sha256"]!=digest(root/"reset.json"):raise ValueError("seal mismatch")
        src=next(r for r in idx["rows"] if r["qualified"] and r["step"]>24)
        file=root/src["file"]
        if digest(file)!=src["file_sha256"]:raise ValueError("raw mismatch")
        frame=RGBDObservation.model_validate_json(gzip.decompress(file.read_bytes()))
        proof=dict(allocation_sha256=reg[name],generation_sha256=digest(runtime/"runtime-build.json"),
                   calibration_sha256=cert,asset_sha256=digest(Path(geo["asset_path"])),reset_scene_id=reset["scene_id"],reset_episode_id=reset["episode_id"])
        context=bind_allocation(raw,**proof)
        mark=decoder.measure_frame(frame,geo);assert rigid_pose(frame,mark,geo,identity=context,physics_step=src["step"])
        cases[name]=(raw,proof,context,frame,mark,geo,src)
    for name,peer in (("sealed-left","sealed-right"),("sealed-right","sealed-left")):
        raw,proof,context,fr,m,g,src=cases[name]
        other=cases[peer]
        def deny(label,frame=fr,marker=m,geometry=g,identity=context,step=src["step"]):
            claimed=rigid_pose(frame,marker,geometry,identity=identity,physics_step=step)
            rows.append(dict(source=name,case=label,rejected=claimed is None))
        deny("swap_full_allocation_and_reset",identity=other[2])
        deny("swap_original_frame_and_original_marker",frame=other[3],marker=other[4])
        deny("swap_marker",marker=other[4])
        deny("missing_binding",identity=None)
        deny("earlier_owned_frame",step=src["step"]+8)
        deny("missing_independent_step",step=None)
        deny("invalid_marker_ownership",marker=dict(m,scene_id=other[2].scene_id))
        deny("invalid_marker_clock",marker=dict(m,sim_time_s=fr.sim_time_s+1/240))
        deny("wrong_observation_or_capture",marker=dict(m,observation_id="replayed"))
        deny("different_runtime_registration",marker=dict(m,registration_id="other"))
        deny("wrong_marker_asset",marker=dict(m,asset_sha256="0"*64))
        deny("wrong_current_frame_checksum",marker=dict(m,checksum="0"*64))
        for key,value in {"source":"rgbd_camera","calibration_version":"alternate","episode_id":other[2].episode_id,
                          "scene_id":other[2].scene_id,"intrinsics":[*fr.intrinsics[:3],fr.intrinsics[3]+1],
                          "camera_to_world":[*fr.camera_to_world[:3],fr.camera_to_world[3]+.001,*fr.camera_to_world[4:]]}.items():
            wrong=RGBDObservation.model_validate(dict(fr.model_dump(),**{key:value},checksum_sha256=""))
            mm=decoder.measure_frame(wrong,g)
            deny("wrong_frame_"+key,frame=wrong,marker=mm)
        for p,key,v in [("design","scene_id","unrelated"),("family","marker_family","wrong"),("asset","marked_asset_sha256","0"*64)]:
            gg=copy.deepcopy(g)
            if p=="design":gg["development_dual"][key]=v
            elif p=="asset":gg["pose_marker"][key]=v
            else:gg[key]=v
            deny("wrong_registered_"+p,geometry=gg)
        for key in ("allocation_sha256","generation_sha256","calibration_sha256","asset_sha256","reset_scene_id","reset_episode_id"):
            for value_tag,value in ([("missing","")] if key=="reset_episode_id" else [("missing",""),("different",other[1]["allocation_sha256"] if key=="allocation_sha256" else "d"*64)]):
                bad=dict(proof);bad[key]=value
                try:bind_allocation(raw,**bad);rejected=False
                except ValueError:rejected=True
                rows.append(dict(source=name,case="binding_"+key+"_"+value_tag,rejected=rejected))
        alternate=bind_allocation(raw,**dict(proof,reset_episode_id=other[2].episode_id))
        deny("other_valid_reset_episode_with_valid_allocation",identity=alternate)
    if not all(r["rejected"] for r in rows):raise ValueError("released control "+str([r for r in rows if not r['rejected']]))
    write(public,dict(positive_pairs=list(cases),positive_pairs_passed=2,negative_controls=rows,
        total=len(rows),all_rejected=all(r["rejected"] for r in rows),
        positive_frame_sha256={k:v[6]["file_sha256"] for k,v in cases.items()}))


if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("out",type=Path);a.add_argument("public",type=Path)
    v=a.parse_args();run(v.out,v.public)

