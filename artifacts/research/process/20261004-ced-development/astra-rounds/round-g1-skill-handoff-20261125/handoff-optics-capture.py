"""Capture registered whole-trajectory sampled RGB-D from the original top camera for held-pose work."""
import argparse
import gzip
import json
import os
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_trials import device

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame


def capture(repo,design,output,groups):
    spec=json.loads(design.read_bytes())
    source=repo/"experiments/results/g1-skill-handoff-20261125/physical-capture-01"
    layout=repo/"experiments/results/g1-complete-cv-repair-20261125/mount-optics-02/capture-gpu/compiled.json.gz"
    geometry=json.loads(gzip.decompress(layout.read_bytes()))["geometry"]
    output.mkdir(parents=True,exist_ok=False)
    write(output/"prospective.json",dict(design_sha256=digest(design),groups=groups,geometry_sha256=digest(layout),
        seed=25112595,scene_id=geometry["development_dual"]["scene_id"]))
    backend=mujoco.MjModel.from_xml_path(str(repo/geometry["asset_path"]))
    data=mujoco.MjData(backend)
    rows=[]
    with device(repo/"experiments/results/g1-visibility-pose-repair-20261124"):
        camera=MuJoCoRGBDCamera(mujoco,backend,width=320,height=240)
        try:
            for order,(name,trace) in enumerate(spec["trajectories"].items()):
                if trace["group"] not in groups:continue
                fp=source/name/"normal.npz"
                if digest(fp)!=trace["sha256"]["normal.npz"]:raise ValueError("sealed trajectory changed")
                rng=np.random.default_rng(25112595+order)
                states=np.load(fp)
                for i in trace["sample_indices"]:
                    data.qpos[:]=states["q"][i]
                    data.qvel[:]=states["qvel"][i]
                    data.time=float(states["step"][i])/240
                    mujoco.mj_forward(backend,data)
                    frame=observation_from_sensor_frame(camera.capture(data,rng=rng,noise_std_m=.001,
                       scene_id=geometry["development_dual"]["scene_id"],episode_id="optical-rigidity-"+name),
                       source="mujoco_camera",png_compress_level=1)
                    file=output/f"{name}-{i:05}.rgbd.json.gz"
                    file.write_bytes(gzip.compress(frame.model_dump_json().encode(),mtime=0))
                    rows.append(dict(curve=name,role=trace["group"],step=int(states["step"][i]),
                          stage=str(states["stage"][i]),i=i,file=file.name,sha256=digest(file),
                          frame_id=frame.frame_id,checksum=frame.checksum_sha256))
            renderer=GL.glGetString(GL.GL_RENDERER).decode()
        finally:camera.close()
    write(output/"index.json",dict(records=rows,renderer=renderer,prospective_sha256=digest(output/"prospective.json")))


if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("design",type=Path);a.add_argument("out",type=Path);a.add_argument("groups",nargs="+")
    o=a.parse_args();capture(Path.cwd(),o.design,o.out,o.groups)

