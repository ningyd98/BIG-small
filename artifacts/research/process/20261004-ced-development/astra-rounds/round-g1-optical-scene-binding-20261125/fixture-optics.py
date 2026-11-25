"""Acquire an independently allocated, reset-bound optical fixture over sealed native states."""
import argparse
import gzip
import importlib.util
import itertools
import json
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation import g1_complete_cv_handoff_optics as reader
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_visibility_trials import device


BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
SIGN=np.asarray(list(itertools.product((-1.,1.),repeat=3)))
GRANTED={"both","id8_opposite_edges","id8_opposite_ink"}


def imported(name,file):
    spec=importlib.util.spec_from_file_location(name,file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def new_context(root,gen,geom,name,spec,cert,plan_sha):
    alloc=dict(schema="g1.optical.development.fixture.allocation.v1",scope="independent optical reprojection; no production allocation",
         plan_sha256=plan_sha,runtime_build_sha256=gen,asset_sha256=geom["pose_marker"]["marked_asset_sha256"],
         calibration_sha256=cert,geometry=geom,case=dict(id=name,scene_id=spec["scene_id"],physics_dt_s="1/240",asset_sha256=geom["pose_marker"]["marked_asset_sha256"]),
         planned_capture=spec)
    write(root/"allocation.json",alloc)
    return digest(root/"allocation.json")


def measure_case(name,case,context,scene_id,episode,compiled,read,old,root):
    source=Path(case["source_path"]);states=np.load(source/"normal.npz");info=np.load(source/"physical-geometries.npz")
    if digest(source/"normal.npz")!=case["source_states_sha256"] or digest(source/"handoffs.json")!=case["handoffs_sha256"]:
        raise ValueError("source physics mismatch")
    geometry=compiled["geometry"];model=mujoco.MjModel.from_xml_path(str(geometry["asset_path"]));data=mujoco.MjData(model)
    camera=MuJoCoRGBDCamera(mujoco,model,width=320,height=240)
    rng=np.random.default_rng(case["seed"]);other=np.random.default_rng(case["seed"]+10000)
    index=json.loads((Path(case["prior_capture"])/"index.json").read_bytes())["records"]
    old_raw={r["step"]:r for r in index if r["curve"]==name};rows=[]
    try:
        for i in case["sample_steps"]:
            step=int(states["step"][i]);data.qpos[:]=states["q"][i];data.qvel[:]=states["qvel"][i]
            data.time=step/240;mujoco.mj_forward(model,data)
            frame=observation_from_sensor_frame(camera.capture(data,rng=rng if i in case["prior_samples"] else other,noise_std_m=.001,
                    scene_id=scene_id,episode_id=episode),source="mujoco_camera",png_compress_level=1)
            rr=old_raw.get(step);same=False
            if rr:
                raw=Path(case["prior_capture"])/rr["file"]
                if digest(raw)!=rr["sha256"]:raise ValueError("old optical archive mismatch")
                original=json.loads(gzip.decompress(raw.read_bytes()))
                same=bool(frame.rgb_png_base64==original["rgb_png_base64"] and frame.depth_float32_base64==original["depth_float32_base64"])
            path=root/f"{step:05}.rgbd.json.gz"
            with path.open("xb") as f:f.write(gzip.compress(frame.model_dump_json().encode(),mtime=0))
            marker=read(frame,geometry)
            observed=reader.rigid_pose(frame,marker,geometry,identity=context,physics_step=step)
            previous=old.measured_pose(frame,marker,geometry)
            was=bool(previous and previous["method"] in GRANTED)
            if was!=bool(observed):raise ValueError("frozen numeric selection changed")
            if observed and any(previous[k]!=observed[k] for k in previous):
                raise ValueError("current geometric formula changed")
            maximum=0.;inside=True
            if observed:
                j=list(info["names"]).index("object_geom")
                rotation=np.asarray(observed["rotation"]);truth_r=states['rotation'][i,j]
                expected=states['centers'][i,j]+truth_r@observed["anchor_object_m"]
                ao=abs((expected-observed["anchor_world_m"])@rotation);be=abs(rotation.T@truth_r-np.eye(3))
                inside=bool(np.all(ao<=observed["anchor_error_object_m"]) and np.all(be<=observed["basis_error_object"]))
                for geom,box in compiled["structure"].items():
                    jj=list(info["names"]).index(geom);p=np.asarray(box["center_object_m"])+SIGN*box["half_extent_m"]
                    true=states["centers"][i,jj]+(SIGN*box["half_extent_m"])@states["rotation"][i,jj].T
                    err=abs((observed["center_m"]+p@rotation.T-true)@rotation)
                    lim=np.asarray(observed["anchor_error_object_m"])+abs(p-observed["anchor_object_m"])@np.asarray(observed["basis_error_object"]).T
                    maximum=max(maximum,float(np.max(err/lim)))
            rows.append(dict(step=step,stage=str(states["stage"][i]),handoff=step in case["required_handoffs"],same_pixels=same,frame_id=frame.frame_id,
                file=path.name,file_sha256=digest(path),marker_checksum=marker["checksum"],qualified=bool(observed),method=observed["method"] if observed else None,
                geometric_formula_unchanged=True,components_inside=inside,worst_corner_ratio=maximum))
        rendering=GL.glGetString(GL.GL_RENDERER).decode()
    finally:camera.close()
    write(root/"index.json",dict(renderer=rendering,allocation_sha256=context.allocation_sha256,reset_sha256=digest(root/"reset.json"),rows=rows))
    return rows


def capture(plan_file,out,public):
    plan=json.loads(plan_file.read_bytes());gen=plan["raw_physics_generation"]
    source=BASE/"builds"/gen/"runtime-source";comp=BASE/"mount-optics-02/capture-gpu/compiled.json.gz";cal=BASE/"calibration-gpu-01/manifest.json"
    if digest(source/"runtime-build.json")!=gen or digest(cal)!=plan["original_camera_calibration_seal"] or digest(comp)!=plan["compiled_geometry_sha256"]:
        raise ValueError("sealed optical dependency changed")
    if not Path(importlib.util.find_spec("cloud_edge_robot_arm.simulation.mujoco.backend").origin).resolve().is_relative_to(source.resolve()):
        raise ValueError("original sensor/physics source required")
    compiled=json.loads(gzip.decompress(comp.read_bytes()));geom=compiled["geometry"];asset=digest(Path(geom["asset_path"]))
    old=imported("pre_instance_handoff_optics",source/"scripts/graduation/g1_complete_cv_handoff_optics.py")
    read=imported("original_marker_detector",source/"scripts/graduation/g1_visibility_vision.py").measure_frame
    out.mkdir(parents=True,exist_ok=False)
    seals={};reports={}
    for name,case in plan["cases"].items():
        root=out/name;root.mkdir()
        seals[name]=new_context(root,gen,geom,name,case,digest(cal),digest(plan_file))
    write(out/"before-any-capture.json",dict(registrations=seals,plan_sha256=digest(plan_file)))
    with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        for name,case in plan["cases"].items():
            root=out/name
            lifecycle=MuJoCoPhysicsBackend()
            try:
                lifecycle.initialize(SimulatorConfig(model_path=str(Path(geom["asset_path"]).resolve()),seed=case["seed"],physics_dt_s=1/240,
                    domain_randomization=False,render_rgb=False,render_depth=False))
                before=lifecycle._episode_id
                lifecycle.reset(PhysicalScenarioConfig(scenario_id=case["scene_id"],seed=case["seed"],object_mass_kg=.10126432))
                actual_scene=lifecycle._scenario.scenario_id;actual_episode=lifecycle._episode_id
                if before is not None or lifecycle.current_physics_observation().episode_id!=actual_episode:raise ValueError("independent reset boundary")
                write(root/"reset.json",dict(scene_id=actual_scene,episode_id=actual_episode,physics_step=lifecycle.total_physics_steps,prior_episode=before,
                    allocation_sha256=seals[name],method="fresh independent original backend.reset; no tested frame exists"))
                context=bind_allocation((root/"allocation.json").read_bytes(),allocation_sha256=seals[name],generation_sha256=gen,asset_sha256=asset,
                    calibration_sha256=digest(cal),reset_scene_id=actual_scene,reset_episode_id=actual_episode)
                rows=measure_case(name,case,context,actual_scene,actual_episode,compiled,read,old,root)
            finally:lifecycle.shutdown()
            reports[name]=dict(allocation_sha256=seals[name],reset_sha256=digest(root/"reset.json"),raw_index_sha256=digest(root/"index.json"),
               total=len(rows),qualified=sum(r["qualified"] for r in rows),same_native_rgb_and_depth=sum(r["same_pixels"] for r in rows),
               source_handoffs=sum(r["handoff"] for r in rows),qualified_handoffs=sum(r["handoff"] and r["qualified"] for r in rows),
               domain_failures=[r["step"] for r in rows if not r["components_inside"] or r["worst_corner_ratio"]>1],
               largest_corner_ratio=max(r["worst_corner_ratio"] for r in rows),measured_formula_equal=sum(r["geometric_formula_unchanged"] for r in rows))
    write(public,dict(registration_before_capture=digest(out/"before-any-capture.json"),cases=reports,formal_runs=0,independent_slots=0))


if __name__=="__main__":
    a=argparse.ArgumentParser()
    for k in ("registration","out","public"):a.add_argument(k,type=Path)
    v=a.parse_args();capture(v.registration,v.out,v.public)

