"""Independent optical-yaw fixture and physically inserted single-pixel obstacle control."""

import argparse
import gzip
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_trials import device
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame


def collect(asset, compiled, near_source, out):
    out.mkdir(parents=True, exist_ok=False)
    geo = json.loads(gzip.decompress(compiled.read_bytes()))["geometry"]
    source = json.loads(gzip.decompress(near_source.read_bytes()))
    near = next(r for r in reversed(source) if r["phase"] == "OPEN_SETTLE")
    records = []
    lock = Path("experiments/results/g1-visibility-pose-repair-20261124")
    with device(lock):
        for kind in ("yaw", "pin"):
            tree = ET.parse(asset)
            if kind == "pin":
                # A 2.0 mm-wide obstacle above an actual rendered FK silhouette,
                # at the optical ray passing through the historical arm edge.
                h = 0.58
                xyz = np.array(
                    [
                        0.35 + (100 - 159.5) * (1.4 - h) / 257.34083046114705,
                        -(165 - 119.5) * (1.4 - h) / 257.34083046114705,
                        h,
                    ]
                )
                ET.SubElement(
                    tree.find("worldbody"),
                    "geom",
                    name="calibration_intruding_pin",
                    type="box",
                    pos=" ".join(map(str, xyz)),
                    size=".001 .001 .002",
                    rgba=".4 .4 .4 1",
                )
            m = mujoco.MjModel.from_xml_string(ET.tostring(tree.getroot(), encoding="unicode"))
            d = mujoco.MjData(m)
            cam = MuJoCoRGBDCamera(mujoco, m, width=320, height=240)
            rng = np.random.default_rng(25113919)
            try:
                settings = (
                    [(0.0, 0.0, 0.0, "home")]
                    if kind == "pin"
                    else [
                        (x, y, angle, pose)
                        for x, y in ((0.0, 0.0), (-0.005, 0.004), (0.007, -0.008))
                        for angle in (-3.5, -2.5, -2.0, -1.5, -1.0, 0.0, 1.0, 1.5, 2.0, 2.5, 3.5)
                        for pose in ("home", "open-near")
                    ]
                )
                for idx, (dx, dy, angle, pose) in enumerate(settings):
                    adr = m.joint("object_free").qposadr[0]
                    r = np.radians(angle) / 2
                    d.qpos[adr : adr + 7] = [0.45 + dx, dy, 0.035, np.cos(r), 0.0, 0.0, np.sin(r)]
                    d.qpos[:7] = (
                        [-0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        if pose == "home"
                        else near["joints_rad"]
                    )
                    d.qpos[7:9] = [0.039, 0.039]
                    mujoco.mj_forward(m, d)
                    frame = observation_from_sensor_frame(
                        cam.capture(
                            d,
                            rng=rng,
                            noise_std_m=0.001,
                            scene_id="G1_ANGLE_DIAGNOSTIC",
                            episode_id=kind,
                        ),
                        source="mujoco_camera",
                        png_compress_level=1,
                    )
                    path = out / f"{kind}-{idx:03d}.rgbd.json.gz"
                    path.write_bytes(gzip.compress(frame.model_dump_json().encode(), mtime=0))
                    mark = measure_frame(frame, geo)
                    records.append(
                        dict(
                            kind=kind,
                            idx=idx,
                            pose=pose,
                            angle_deg=angle,
                            dx=dx,
                            dy=dy,
                            file=path.name,
                            file_sha256=digest(path),
                            reason=mark["reason"],
                            usable_ids=mark["usable_ids"],
                            q=d.qpos[:7].tolist(),
                            fingers=d.qpos[7:9].tolist(),
                            tcp=d.site("tcp").xpos.tolist(),
                        )
                    )
            finally:
                cam.close()
    write(
        out / "index.json",
        dict(
            raw=records,
            geometry_sha256=digest(compiled),
            source_sha256=digest(near_source),
            calibration_only=True,
            physics_steps=0,
            motion_commands=0,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("asset", "compiled", "near-source", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    collect(a.asset, a.compiled, a.near_source, a.out)
