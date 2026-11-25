"""Attempt a real scene-layout change through a single entry point on a static native fixture."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL
from PIL import Image
from cloud_edge_robot_arm.simulation.mujoco import camera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_dual_trials import exclusive_egl

HERE=Path(__file__).resolve().parent
BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
RAW=BASE/"temporal-epoch-01"


class LayoutOwner:
    def __init__(self, model, latched):
        self.model=model
        self.index=model.geom("sealed_static_box").id
        self.target=model.geom_pos[self.index].copy()
        self.model.geom_pos[self.index,0]+=3.
        self.latched=latched
        self.epoch=1 if latched else None
        self.events=[]

    def open(self):
        self.epoch=None
        self.latched=False
        self.events.append("revoked_then_opened")

    def insert(self):
        if self.latched:
            self.events.append("denied_before_layout_write")
            return False
        assert self.epoch is None
        self.model.geom_pos[self.index]=self.target
        self.events.append("inserted_after_no_valid_epoch")
        return True


def main():
    spec=HERE/"epoch-control-registration.json"
    r=json.loads(spec.read_bytes())
    xml=BASE/"temporal-subpixel-01/held-out-small-0.xml"
    source=json.loads((BASE/"temporal-subpixel-01/index.json").read_bytes())
    assert digest(xml)==next(e["xml_sha256"] for e in source["generated_files"] if e["id"]=="held-out-small-0")
    output=[]
    with exclusive_egl(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        RAW.mkdir(exist_ok=False)
        for case in r["cases"]:
            m=mujoco.MjModel.from_xml_path(str(xml))
            d=mujoco.MjData(m)
            m.body_pos[m.body("panda_link0").id,0]-=3.
            d.qpos[m.joint("object_free").qposadr[0]]+=3.
            owner=LayoutOwner(m,case!="always_open_never_issued")
            initial=owner.epoch
            cam=camera.MuJoCoRGBDCamera(mujoco,m,width=320,height=240)
            imgs=[]; files=[]
            try:
                for i in range(2):
                    if i:
                        if case.startswith("opened_"):owner.open()
                        wrote=owner.insert()
                    mujoco.mj_forward(m,d)
                    s=cam.capture(d,rng=np.random.default_rng(r["seed"]),noise_std_m=.001,
                                  episode_id=case,scene_id="STATIC_DIAGNOSTIC_OWNER")
                    fr=observation_from_sensor_frame(s,source="mujoco_camera",png_compress_level=1)
                    assert fr.sim_time_s==0.0
                    fname=RAW/f"{case}-{i}.json.gz"
                    fname.write_bytes(gzip.compress(fr.model_dump_json().encode(),mtime=0))
                    files.append(dict(file=fname.name,sha256=digest(fname),checksum=fr.checksum_sha256))
                    imgs.append((base64.b64decode(fr.depth_float32_base64),
                                 Image.open(io.BytesIO(base64.b64decode(fr.rgb_png_base64))).convert("RGB").tobytes()))
                output.append(dict(case=case,initial_epoch=initial,final_epoch=owner.epoch,writer_accepted=wrote,
                        physical_probe_on_table=bool(np.array_equal(m.geom_pos[owner.index],owner.target)),
                        ordered_events=owner.events,identical_depth=imgs[0][0]==imgs[1][0],identical_rgb=imgs[0][1]==imgs[1][1],
                        full_frames=files,renderer=GL.glGetString(GL.GL_RENDERER).decode(),motion_commands=0,
                        historical_free_volume_authorized=False))
            finally:cam.close()
    assert [e["writer_accepted"] for e in output]==[False,True,True]
    assert [e["physical_probe_on_table"] for e in output]==[False,True,True]
    write(HERE/"fixture-epoch.public.json",dict(registration_sha256=digest(spec),source_sha256=digest(Path(__file__)),
          original_camera_sha256=digest(Path(camera.__file__)),fixed_input_xml_sha256=digest(xml),cases=output,
          limitation="Single instrumented writer on a fresh physical development model, no integration-wide or hardware boundary qualification."))

if __name__=="__main__":
    main()
