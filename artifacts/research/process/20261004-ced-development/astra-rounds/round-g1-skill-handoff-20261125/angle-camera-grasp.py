"""Replay the sealed G1 camera fixture and the exact two native training PRE frames."""

import argparse
import gzip
import json
from pathlib import Path

import mujoco
import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from scripts.graduation.g1_complete_cv_angle import grasp_readiness
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_vision import measure_frame


def decide(frame, geometry, tcp, hand, fingers):
    m=measure_frame(frame,geometry)
    if not m["usable"]:
        return dict(pass_grasp=False,reason=m["reason"],ids=m["usable_ids"])
    a,p,reason=grasp_readiness(frame,m,geometry,np.asarray(m["object_center_world_m"]),
        np.asarray(m["rotation_object_to_world"]).reshape(3,3),np.asarray(tcp),
        np.asarray(hand).reshape(3,3),fingers,closure=True)
    return dict(pass_grasp=reason is None,reason=reason,angle=a,patch=p,ids=m["usable_ids"])


def historical(base,geometry):
    answers=[]
    for case,step in (("cvfix-t01",1392),("cvfix-t02",1264)):
        inp=base/"batches/train-full-02"/case/"instance"
        clearance=json.loads((inp/"local-clearance.json").read_bytes())
        row=next(r for r in clearance["rows"] if r["skill"]=="GRASP" and r["phase"]=="PRE" and r["physics_step"]==step)
        idx=json.loads((inp/"pixel-index.json").read_bytes())
        frame_row=next(r for r in idx["frames"] if r["frame_id"]==row["frame_id"])
        source=inp/frame_row["file"]
        if digest(source)!=frame_row["file_sha256"]:raise ValueError("source hash")
        frame=RGBDObservation.model_validate_json(source.read_bytes())
        robot=row["robot"];hand=np.empty(9)
        mujoco.mju_quat2Mat(hand,np.asarray(robot["tcp_quaternion_wxyz"]))
        if frame.frame_id!=robot["frame_id"] or frame.checksum_sha256!=robot["checksum"]:raise ValueError("pairing failed")
        ans=decide(frame,geometry,robot["tcp_position_m"],hand,robot["finger_positions_m"])
        answers.append(dict(case=case,step=step,active_generation=clearance["runtime_build_sha256"],
            previous_grasp_patch=row["evidence"]["grasp_patch"],original_status=row["status"],
            original_feedback=row["reason"],file=frame_row,sha256=digest(inp/"local-clearance.json"),new_camera_only=ans))
    return answers


def render(repo,base,out,geometry):
    from OpenGL import GL
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from scripts.graduation.g1_visibility_trials import device
    out.mkdir(parents=True,exist_ok=False)
    groups=("handoff-grasp-unseen-01","handoff-grasp-fit-01")
    write(out/"input.json",dict(indices_sha256={g:digest(base/g/"index.json") for g in groups},
          random_seed=25112592,scope="all unseen whole trajectories plus every designed negative; same frozen unmodified optical/geometry reader"))
    rows=[]
    model=mujoco.MjModel.from_xml_path(str(repo/geometry["asset_path"]))
    data=mujoco.MjData(model)
    rng=np.random.default_rng(25112592)
    with device(repo/"experiments/results/g1-visibility-pose-repair-20261124"):
        cam=MuJoCoRGBDCamera(mujoco,model,width=320,height=240)
        try:
            for group in groups:
                d=base/group
                for v in json.loads((d/"index.json").read_bytes())["rows"]:
                    if v["design"]["group"]=="fit":continue
                    archive=d/(v["id"]+".json.gz")
                    if digest(archive)!=v["clip_sha256"]:raise ValueError("raw integrity")
                    orig=next(r for r in reversed(json.loads(gzip.decompress(archive.read_bytes()))) if r["phase"]=="settle")
                    data.qpos[:7]=orig["joints_rad"];data.qpos[7:9]=orig["finger_joints_m"]
                    adr=model.joint("object_free").qposadr[0]
                    data.qpos[adr:adr+3]=orig["cube_xyz_m"]
                    mujoco.mju_mat2Quat(data.qpos[adr+3:adr+7],np.asarray(orig["cube_rotation"]))
                    mujoco.mj_forward(model,data)
                    frame=observation_from_sensor_frame(cam.capture(data,rng=rng,noise_std_m=.001,
                        scene_id="G1_ANGLE_DIAGNOSTIC",episode_id=v["id"]),source="mujoco_camera",png_compress_level=1)
                    fd=out/(v["id"]+".rgbd.json.gz")
                    fd.write_bytes(gzip.compress(frame.model_dump_json().encode(),mtime=0))
                    result=decide(frame,geometry,orig["tcp_xyz_m"],orig["wrist_rotation"],orig["finger_joints_m"])
                    # Physical outcomes never enter the reader above.
                    rows.append(dict(case=v["id"],group=v["design"]["group"],decision=result,
                        grip_and_hold=v["eligible"],file_sha256=digest(fd),raw_physics_sha256=v["clip_sha256"]))
            renderer=GL.glGetString(GL.GL_RENDERER).decode()
        finally:cam.close()
    write(out/"index.json",dict(renderer=renderer,results=rows))
    def summarize(g):
        return dict(n=len(g),admitted=sum(r["decision"]["pass_grasp"] for r in g),
             unsafe_admission=[r["case"] for r in g if r["decision"]["pass_grasp"] and not r["grip_and_hold"]],
             physical_grip_and_hold=sum(r["grip_and_hold"] for r in g),
             reasons={reason:sum(r["decision"]["reason"]==reason for r in g) for reason in sorted({r["decision"]["reason"] for r in g if r["decision"]["reason"]})})
    return dict(renderer=renderer,index_sha256=digest(out/"index.json"),raw_physics_sources=digest(out/"input.json"),partition={k:summarize([r for r in rows if r["group"]==k]) for k in ("validation","negative")})


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("base",type=Path);parser.add_argument("public_out",type=Path);parser.add_argument("--render",type=Path)
    options=parser.parse_args()
    geo=json.loads(gzip.decompress((options.base/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))["geometry"]
    if options.render:
        write(options.public_out,render(Path.cwd(),options.base,options.render,geo))
    else:write(options.public_out,dict(raw_rgbd_only=historical(options.base,geo),formal_runs=0))

