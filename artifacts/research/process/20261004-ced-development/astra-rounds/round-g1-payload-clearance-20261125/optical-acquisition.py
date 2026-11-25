"""Isolated original-camera acquisition from registered physical trajectories and real open dwell."""
import argparse
import gzip
import importlib.util
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
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_trials import device

HERE = Path(__file__).resolve().parent
BASE = Path("experiments/results/g1-complete-cv-repair-20261125")

def imported(name, file):
    spec=importlib.util.spec_from_file_location(name,file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def capture(name, spec, setup, out):
    src=Path(spec["path"])
    for f,h in spec["hashes"].items():
        if digest(src/f)!=h: raise ValueError("changed physical trajectory")
    gen=setup["generation_sha256"];geom=json.loads(gzip.decompress((BASE/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))["geometry"]
    runtime=BASE/"builds"/gen/"runtime-source"
    if not Path(importlib.util.find_spec("cloud_edge_robot_arm.simulation.mujoco.backend").origin).resolve().is_relative_to(runtime.resolve()):
        raise ValueError("original native camera required")
    fixture=imported("allocation_writer",HERE.parent/"round-g1-optical-scene-binding-20261125"/"fixture-optics.py")
    io=imported("original_checkpoint",HERE.parent/"round-g1-braking-envelope-20261125"/"brake-physics-replay.py")
    dest=out/name;dest.mkdir(parents=True,exist_ok=False)
    alloc=fixture.new_context(dest,gen,geom,name,spec,setup["calibration_sha256"],digest(HERE/"optical-acquisition-preregistration.public.json"))
    backend=MuJoCoPhysicsBackend();backend.initialize(SimulatorConfig(model_path=str(Path(geom["asset_path"]).resolve()),seed=spec["seed"],physics_dt_s=1/240,domain_randomization=False,render_rgb=False,render_depth=False))
    backend.reset(PhysicalScenarioConfig(scenario_id=spec["scene_id"],seed=spec["seed"],object_mass_kg=.10126432))
    scene=backend._scenario.scenario_id;episode=backend.current_physics_observation().episode_id
    write(dest/"reset.json",dict(scene_id=scene,episode_id=episode,allocation_sha256=alloc))
    action=json.loads((src/"actions.json").read_bytes())
    restart=np.load(src/"restart.npz");packed=restart["packed"];target=restart["command_q"];opened=restart["command_open"]
    rng=np.random.default_rng(spec["seed"]);model=backend._model;oracle={"physical":[]};rows=[]
    fingers=[model.joint("finger_"+n+"_joint").qposadr[0] for n in ("left","right")]
    source_comments=json.loads((src/"commands.json").read_bytes())
    if isinstance(source_comments,dict):source_comments=source_comments["commands"]
    prev=None
    def save(cam,stage,tag,current,commandstep,goal,completed,endstep):
        idx=backend.total_physics_steps;d=backend._data
        frame=observation_from_sensor_frame(cam.capture(d,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=episode),source="mujoco_camera",png_compress_level=1)
        fn=f"{len(rows):04}.json.gz"
        with (dest/fn).open("xb") as f:f.write(gzip.compress(frame.model_dump_json().encode(),2,mtime=0))
        obj=d.geom("object_geom"); wr=d.site("tcp");r=np.empty(4);mujoco.mju_mat2Quat(r,wr.xmat)
        packet=dict(physics_step=idx,frame_id=frame.frame_id,checksum_sha256=frame.checksum_sha256,sim_time_s=frame.sim_time_s,camera_joint_positions_rad=d.qpos[:7].tolist(),camera_finger_positions_m=d.qpos[fingers].tolist(),tcp_position_m=wr.xpos.tolist(),tcp_quaternion_wxyz=r.tolist(),previous_native_successful_skill=completed,previous_native_return_step=endstep,previous_native_terminal_step=endstep,last_accepted_gripper_open=bool(goal),last_accepted_gripper_command_step=commandstep)
        rows.append(dict(file=fn,file_sha256=digest(dest/fn),skill=stage,phase=tag,robot=packet))
        oracle["physical"].append(dict(file=fn,center_m=obj.xpos.tolist(),rotation=obj.xmat.reshape(3,3).tolist(),touching=[sorted((model.geom(int(c.geom1)).name,model.geom(int(c.geom2)).name)) for c in d.contact]))
    def restore(idx):
        io.restore(backend,(packed[idx],target[idx],bool(opened[idx]),idx))
        mujoco.mj_forward(model,backend._data)
    try:
        with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
            cam=MuJoCoRGBDCamera(mujoco,model,width=320,height=240)
            try:
                for row in action:
                    stage=row["stage"];first=row["start_step"];end=row["step"]
                    if stage not in ("GRASP","LIFT","MOVE_TO_REGION","PLACE","RELEASE","RETREAT"):
                        if row["success"]:prev=row
                        continue
                    stop=end-first
                    steps=set([first,end,*[first+8*round(stop*i/32) for i in (1,2,3)]])
                    if stage=="LIFT":steps.update(range(first,min(first+64,end)+1,8))
                    if stage=="PLACE":steps.update(range(max(first,end-240),end+1,8))
                    for idx in sorted(steps):
                        restore(idx)
                        cmd=[r for r in source_comments if r.get("accepted") and r["type"]=="gripper" and r["physics_step"]<=idx]
                        commandstep=cmd[-1]["physics_step"] if cmd else None
                        done=row if idx==end and row["success"] else prev or {}
                        save(cam,stage,"PRE" if idx==first else "POST" if idx==end else "FEEDBACK",idx,commandstep,opened[idx],done.get("stage"),done.get("step"))
                    if stage=="RELEASE" and row["success"]:
                        restore(end)
                        for n in range(31):
                            if n:backend.step(8)
                            save(cam,stage,"DWELL",backend.total_physics_steps,commandstep,True,stage,end)
                    if row["success"]:prev=row
                renderer=GL.glGetString(GL.GL_RENDERER).decode()
            finally:cam.close()
    finally:backend.shutdown()
    write(dest/"index.json",dict(renderer=renderer,allocation_sha256=alloc,reset_sha256=digest(dest/"reset.json"),rows=rows))
    write(dest/"offline-labels.json",oracle)
    print(name,len(rows),renderer,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("out",type=Path);a.add_argument("name",nargs="+");args=a.parse_args()
    setup=json.loads((HERE/"optical-acquisition-preregistration.public.json").read_bytes())
    for name in args.name:capture(name,setup["cases"][name],setup,args.out)
