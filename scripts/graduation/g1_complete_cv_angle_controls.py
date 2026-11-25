"""Independent subpixel placements and a removable physical cover for single-print validation."""

import argparse
import gzip
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_visibility_trials import device

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame


def capture(repo, out, validation=False, aligned=False):
    priv = repo / "experiments/results/g1-complete-cv-repair-20261125"
    original = priv / "optical-control-gpu-01/index.json"
    known = json.loads(original.read_bytes())["raw"]
    postures = {
        name: next(r["q"] for r in known if r["pose"] == name) for name in ("home", "open-near")
    }
    geom = priv / "mount-optics-02/capture-gpu/compiled.json.gz"
    geometry = json.loads(gzip.decompress(geom.read_bytes()))["geometry"]
    asset = repo / geometry["asset_path"]
    out.mkdir(parents=True, exist_ok=False)
    centers = ((0.4482, -0.0039), (0.4537, 0.0062))
    angles = (-4.8, -4.0, -3.25, -2.25, -1.25, -0.5, 0.5, 1.25, 1.75, 2.25, 3.25, 4.0, 4.8)
    plan = dict(
        asset_sha256=digest(asset),
        fixture_posture_source_sha256=digest(original),
        geometry_source_sha256=digest(geom),
        centers_m=centers,
        angles_deg=angles,
        modes=["home", "open-near", "left-print-only"],
        seed=11254421,
        right_print_cover_m=[0.052, 0.052, 0.0015],
        commands=0,
    )
    if validation:
        centers = ((0.4513, 0.0041), (0.4467, -0.0068))
        angles = (-4.6, -3.15, -2.75, -2.05, -1.55, -0.75, 0.25, 0.95, 1.55, 2.05, 2.75, 3.15, 4.6)
        plan.update(
            centers_m=centers,
            angles_deg=angles,
            seed=11254502,
            role="independent angle/profile validation",
        )
    if aligned:
        centers = ((0.4476, 0.0033), (0.4542, -0.0056))
        angles = (-4.0, -2.0, -1.5, 0.0, 1.5, 2.0, 4.0)
        plan.update(
            centers_m=centers,
            angles_deg=angles,
            seed=11254503,
            role="independent centered optical closure fixture",
            modes=["near-centered"],
        )
    write(out / "prospective.json", plan)
    rng = np.random.default_rng(plan["seed"])
    rows = []
    with device(repo / "experiments/results/g1-visibility-pose-repair-20261124"):
        for mode in plan["modes"]:
            tree = ET.parse(asset)
            if mode == "left-print-only":
                ET.SubElement(
                    tree.find("./worldbody/body[@name='object']"),
                    "geom",
                    type="box",
                    name="diagnostic_opaque_shutter",
                    pos=".13 0 .039",
                    size=".052 .052 .0015",
                    rgba=".07 .17 .20 1",
                    contype="1",
                    conaffinity="3",
                    mass=".001",
                )
            xml = ET.tostring(tree.getroot(), encoding="unicode")
            (out / (mode + ".xml")).write_text(xml)
            model = mujoco.MjModel.from_xml_string(xml)
            data = mujoco.MjData(model)
            cam = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
            try:
                for x, y in centers:
                    if aligned:
                        from scripts.graduation.g1_clearance_mount_physics import (
                            initialize,
                            set_diagnostic_arm,
                        )

                        from cloud_edge_robot_arm.simulation.mujoco.backend import (
                            MuJoCoPhysicsBackend,
                        )

                        fixture = MuJoCoPhysicsBackend()
                        try:
                            robot = initialize(fixture, (x, y, 0.035), 0.0, 8136, False)
                            set_diagnostic_arm(fixture, robot, (x, y, 0.045), (0.039, 0.039))
                            postures[mode] = fixture.get_joint_state().positions
                        finally:
                            fixture.shutdown()
                    for degrees in angles:
                        angle = np.radians(degrees) / 2
                        adr = model.joint("object_free").qposadr[0]
                        data.qpos[adr : adr + 7] = [x, y, 0.035, np.cos(angle), 0, 0, np.sin(angle)]
                        data.qpos[:7] = postures[mode] if mode in postures else postures["home"]
                        data.qpos[7:9] = [0.039, 0.039]
                        mujoco.mj_forward(model, data)
                        obs = observation_from_sensor_frame(
                            cam.capture(
                                data,
                                rng=rng,
                                noise_std_m=0.001,
                                scene_id="G1_ANGLE_DIAGNOSTIC",
                                episode_id="angle-holdout-" + mode,
                            ),
                            source="mujoco_camera",
                            png_compress_level=1,
                        )
                        file = out / f"{mode}-{len(rows):03d}.rgbd.json.gz"
                        file.write_bytes(gzip.compress(obs.model_dump_json().encode(), mtime=0))
                        rows.append(
                            dict(
                                file=file.name,
                                file_sha256=digest(file),
                                kind="yaw",
                                pose=mode,
                                angle_deg=degrees,
                                center=[x, y, 0.035],
                                q=data.qpos[:7].tolist(),
                                fingers=data.qpos[7:9].tolist(),
                                tcp=data.site("tcp").xpos.tolist(),
                                wrist_rotation=data.site("tcp").xmat.tolist(),
                            )
                        )
            finally:
                cam.close()
    write(out / "index.json", dict(prospective_sha256=digest(out / "prospective.json"), raw=rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--validation", action="store_true")
    p.add_argument("--aligned", action="store_true")
    a = p.parse_args()
    capture(a.repo.resolve(), a.out.resolve(), a.validation, a.aligned)
