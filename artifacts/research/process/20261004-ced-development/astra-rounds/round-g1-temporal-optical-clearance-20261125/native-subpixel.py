"""Capture prospectively fixed static, tabletop optical fixtures with the original native camera."""
import gzip
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from OpenGL import GL
from cloud_edge_robot_arm.simulation.mujoco import camera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_dual_trials import exclusive_egl

HERE = Path(__file__).resolve().parent
BASE = Path("experiments/results/g1-complete-cv-repair-20261125")
RAW = BASE / "temporal-subpixel-01"
REG = HERE / "optical-diagnostic-registration.json"
ROOT_GEN = "816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb"
ASSET = Path("assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml")
LOCK = Path("experiments/results/g1-visibility-pose-repair-20261124")


def scene(row, calibration):
    root = ET.parse(ASSET).getroot()
    if row["width_mm"]:
        u, v = np.array(row["uv"]) + np.array(row["phase_in_pixel_downwards"]) - 0.5
        height = row["height_mm"] / 1000
        fx, fy, cx, cy = calibration["intrinsics"]
        ray = np.array([(u-cx)/fx, (v-cy)/fy, 1.])
        transform = np.asarray(calibration["camera_to_world"]).reshape(4, 4)
        world = transform[:3, :3] @ ray
        top = transform[:3, 3] + world * ((height-transform[2, 3])/world[2])
        material = row["material"]
        ET.SubElement(root.find("asset") if root.find("asset") is not None else ET.SubElement(root,"asset"), "material", name="sealed_probe", rgba="0.45 0.45 0.45 1" if material == "matte" else ".055 .055 .055 1", specular=".05", shininess=".15")
        half = row["width_mm"] / 2000
        ang = math.radians(row["yaw_deg"]) / 2
        ET.SubElement(root.find("worldbody"), "geom", type="box", name="sealed_static_box",
                      material="sealed_probe", contype="1", conaffinity="1", density="750",
                      size=f"{half} {half} {height/2}", pos=f"{top[0]} {top[1]} {height/2}",
                      quat=f"{math.cos(ang)} 0 0 {math.sin(ang)}")
    return ET.tostring(root, encoding="utf-8")


def main():
    assert digest(REG) == "0bd40e685d67cc36f64e961856c84df732b98adfac885d3d33f5de067b29f57b"
    assert Path(camera.__file__).resolve().is_relative_to((BASE/"builds"/ROOT_GEN/"runtime-source").resolve())
    calibration = json.loads((BASE/"calibration-gpu-01/manifest.json").read_bytes())
    assert digest(ASSET) == calibration["asset_sha256"]
    config = json.loads(REG.read_bytes())
    receipts = []
    with exclusive_egl(LOCK):
        RAW.mkdir(exist_ok=False)
        for row in config["rows"]:
            xml = scene(row, calibration["primary_camera"])
            xml_path = RAW / (row["id"] + ".xml")
            xml_path.write_bytes(xml)
            m = mujoco.MjModel.from_xml_string(xml.decode())
            data = mujoco.MjData(m)
            m.body_pos[m.body("panda_link0").id, 0] -= 3.
            data.qpos[m.joint("object_free").qposadr[0]] += 3.
            mujoco.mj_forward(m, data)
            cam = camera.MuJoCoRGBDCamera(mujoco, m, width=320, height=240)
            try:
                gpu = GL.glGetString(GL.GL_RENDERER).decode()
                assert "NVIDIA" in gpu, gpu
                for seed in config["seeds"]:
                    sensor = cam.capture(data, rng=np.random.default_rng(seed),noise_std_m=.001,
                                         scene_id="G1_TEMPORAL_CLOSED_FIXTURE", episode_id=row["id"])
                    im = observation_from_sensor_frame(sensor,source="mujoco_camera",png_compress_level=1)
                    assert list(im.intrinsics)==calibration["primary_camera"]["intrinsics"]
                    assert list(im.camera_to_world)==calibration["primary_camera"]["camera_to_world"]
                    f=RAW/f"{row['id']}-{seed}.json.gz"
                    f.write_bytes(gzip.compress(im.model_dump_json().encode(),mtime=0))
                    receipts.append(dict(id=row["id"],file=f.name,file_sha256=digest(f),checksum=im.checksum_sha256,
                                      frame_id=im.frame_id,seed=seed,xml_sha256=digest(xml_path),sim_time_s=im.sim_time_s))
            finally:
                cam.close()
    write(RAW/"index.json",dict(registration_sha256=digest(REG),renderer=gpu,generated_files=receipts,
                                offsamples=int(m.vis.quality.offsamples),native_camera_sha256=digest(Path(camera.__file__)),
                                sensor_steps=0,command_count=0,source_sha256=digest(Path(__file__))))

if __name__ == "__main__":
    main()
