"""Independent post-freeze camera exposure on two new naturally completed trajectories."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_trials import device

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame


def run(rd, out, public, details):
    plan=json.loads((rd/"handoff-optics-new-trajectories.public.json").read_bytes())
    if digest(Path("scripts/graduation/g1_complete_cv_handoff_optics.py"))!=plan["reader_sha256"]:
        raise ValueError("reader drift since fresh validation freeze")
    root=Path(plan["source_root"])
    historic=Path("experiments/results/g1-complete-cv-repair-20261125")
    compiled=json.loads(gzip.decompress((historic/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))
    model=mujoco.MjModel.from_xml_path(compiled["geometry"]["asset_path"])
    data=mujoco.MjData(model)
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        cam=MuJoCoRGBDCamera(mujoco,model,width=320,height=240)
        try:
            for j,(name,job) in enumerate(plan["trajectories"].items()):
                if any(digest(root/name/k)!=v for k,v in job["sha256"].items()):raise ValueError(name)
                states=np.load(root/name/"normal.npz")
                rng=np.random.default_rng(25112596+j)
                for i in job["sample_indices"]:
                    data.qpos[:]=states["q"][i];data.qvel[:]=states["qvel"][i]
                    data.time=float(states["step"][i])/240
                    mujoco.mj_forward(model,data)
                    frame=observation_from_sensor_frame(cam.capture(data,rng=rng,noise_std_m=.001,
                        scene_id=compiled["geometry"]["development_dual"]["scene_id"],episode_id="fresh-rigid-"+name),source="mujoco_camera",png_compress_level=1)
                    fp=out/f"{name}-{i:05}.rgbd.json.gz"
                    with fp.open("xb") as stream:stream.write(gzip.compress(frame.model_dump_json().encode(),mtime=0))
                    rows.append(dict(curve=name,role="fresh",i=i,step=int(states["step"][i]),stage=str(states["stage"][i]),
                        file=fp.name,sha256=digest(fp),frame_id=frame.frame_id))
            renderer=GL.glGetString(GL.GL_RENDERER).decode()
        finally:cam.close()
    write(out/"index.json",dict(renderer=renderer,records=rows,design_sha256=digest(rd/"handoff-optics-new-trajectories.public.json")))
    module=importlib.util.spec_from_file_location("optics_scorer",rd/"handoff-optics-readback.py")
    reader=importlib.util.module_from_spec(module);module.loader.exec_module(reader)
    reader.NORMAL=root
    reader.report(out,public,details,False)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ("rd","out","public","details"):parser.add_argument(n,type=Path)
    a=parser.parse_args();run(a.rd,a.out,a.public,a.details)

