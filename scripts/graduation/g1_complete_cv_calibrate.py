"""Acquire an independent empty-table map and a physical obstacle control with the native camera."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model

from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

BAND = 0.004
CAMERA_FIELDS = (
    "source",
    "width",
    "height",
    "intrinsics",
    "camera_to_world",
    "calibration_version",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with path.open("x") as stream:
        json.dump(obj, stream, sort_keys=True, allow_nan=False, indent=2)
        stream.write("\n")


def axial(frame):
    return np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4").reshape(
        frame.height, frame.width
    )


def checked_background(images, expected, band):
    stack = np.array(images)
    z = np.median(stack, axis=0)
    returned = (stack > 0).all(axis=0)
    expected_hit = expected > 0
    close = abs(z - expected) <= band
    return np.where(expected_hit & returned & close, z, 0.0), dict(
        confirmed=int((returned & expected_hit & close).sum()),
        mismatched=int((returned & expected_hit & ~close).sum()),
        missing=int((~returned & expected_hit).sum()),
        outside=int((~expected_hit).sum()),
        unexpected=int((~expected_hit & returned).sum()),
    )


def plane_map(frame, model, panel):
    """Exact central rays against registered horizontal rectangle faces."""
    eye = np.asarray(frame.camera_to_world).reshape(4, 4)[:3, 3]
    rot = np.asarray(frame.camera_to_world).reshape(4, 4)[:3, :3]
    fx, fy, cx, cy = frame.intrinsics
    yy, xx = np.indices((frame.height, frame.width))
    dirs = np.stack(((xx - cx) / fx, (yy - cy) / fy, np.ones_like(xx)), axis=-1) @ rot.T
    depth = np.zeros_like(xx, dtype=float)
    planes = [(model.table.c, model.table.h), (model.region.c, model.region.h)]
    if panel:
        planes.insert(0, (np.array([0.35, 0.0, -0.10]), np.array([1.5, 1.2, 0.005])))
    for center, half in planes:
        z = (center[2] + half[2] - eye[2]) / dirs[:, :, 2]
        xy = eye[:2] + dirs[:, :, :2] * z[:, :, None]
        covered = np.all(abs(xy - center[:2]) <= half[:2], axis=2)
        depth = np.where(covered & ((depth == 0) | (z < depth)), z, depth)
    return depth


def fixture(asset, *, panel=False, obstacle=False):
    # Only the separate calibration fixture is modified. Static layout and camera
    # of the running scene are verified against the unmodified registered file.
    root = ET.parse(asset).getroot()
    world = root.find("worldbody")
    if panel:
        ET.SubElement(
            world,
            "geom",
            name="calibration_return_panel",
            type="box",
            pos=".35 0 -.10",
            size="1.5 1.2 .005",
            rgba=".3 .3 .3 1",
        )
    if obstacle:
        ET.SubElement(
            world,
            "geom",
            name="calibration_foreign_prism",
            type="box",
            pos=".453 -.068 .062",
            size=".012 .009 .062",
            rgba=".4 .4 .4 1",
        )
    return ET.tostring(root, encoding="unicode")


def collect(asset, out, lock_root):
    import mujoco
    from OpenGL import GL
    from scripts.graduation.g1_visibility_trials import device

    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

    out.mkdir(parents=True, exist_ok=False)
    items = []
    maps = {}
    geom = Model(asset)
    rng = np.random.default_rng(85137001)
    with device(lock_root):
        for label, y, panel, control in (
            ("table", 0.0, False, None),
            ("panel-primary", 0.0, True, None),
            ("panel-start", -0.47, True, None),
            ("positive", 0.0, False, "positive"),
            ("foreign", 0.0, False, "obstacle"),
        ):
            xml = fixture(asset, panel=panel, obstacle=control == "obstacle")
            model = mujoco.MjModel.from_xml_string(xml)
            data = mujoco.MjData(model)
            model.cam_pos[model.camera("rgbd").id, 1] = y
            if control is None:
                # Move all mobile bodies away in this zero-step diagnostic scene.
                model.body_pos[model.body("panda_link0").id, 0] -= 3.0
                data.qpos[model.joint("object_free").qposadr[0]] += 3.0
            else:
                data.qpos[model.joint("joint1").qposadr[0]] = -0.8
                for n in ("finger_left_joint", "finger_right_joint"):
                    data.qpos[model.joint(n).qposadr[0]] = 0.039
            mujoco.mj_forward(model, data)
            cam = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
            try:
                driver = dict(
                    vendor=GL.glGetString(GL.GL_VENDOR).decode(),
                    renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                    version=GL.glGetString(GL.GL_VERSION).decode(),
                )
                reads = []
                for i in range(1 if control else 5):
                    sensor = cam.capture(
                        data,
                        rng=rng,
                        noise_std_m=0.001,
                        scene_id="G1_LOCAL_CALIBRATION",
                        episode_id=label,
                    )
                    frame = observation_from_sensor_frame(
                        sensor, source="mujoco_camera", png_compress_level=1
                    )
                    dest = out / f"{label}-{i}.rgbd.json"
                    write(dest, frame.model_dump(mode="json"))
                    reads.append(axial(frame))
                    items.append(
                        dict(
                            file=dest.name,
                            sha256=digest(dest),
                            frame_id=frame.frame_id,
                            checksum=frame.checksum_sha256,
                            role=label,
                        )
                    )
                camera = frame.model_dump(mode="json", include=set(CAMERA_FIELDS))
                if control is None:
                    z, counts = checked_background(reads, plane_map(frame, geom, panel), BAND)
                    np.save(out / f"{label}.npy", z.astype("<f4"), allow_pickle=False)
                    maps[label] = dict(
                        camera=camera,
                        depth_file=f"{label}.npy",
                        depth_sha256=digest(out / f"{label}.npy"),
                        counts=counts,
                    )
                else:
                    write(
                        out / f"{label}.robot.json",
                        dict(
                            frame_id=frame.frame_id,
                            checksum_sha256=frame.checksum_sha256,
                            sim_time_s=frame.sim_time_s,
                            joint_positions_rad=data.qpos[:7].tolist(),
                            finger_positions_m=data.qpos[7:9].tolist(),
                            joint_velocities_rad_s=data.qvel[:7].tolist(),
                            finger_velocities_m_s=data.qvel[7:9].tolist(),
                            tcp_position_m=data.site("tcp").xpos.tolist(),
                        ),
                    )
            finally:
                cam.close()
    manifest = dict(
        schema="g1.controlled-workspace.calibration.v1",
        asset_sha256=digest(asset),
        optical_band_m=BAND,
        controls=["positive", "foreign"],
        maps=maps,
        frames=items,
        depth_sigma_m=0.001,
        primary_camera=maps["table"]["camera"],
        renderer=driver,
        deployment="exclusive fixed native XML workspace; no external object admission",
        limitations="conditional closed scene; physical pixel footprint and depth-band detection",
        physics_steps=0,
        motion_commands=0,
    )
    write(out / "manifest.json", manifest)
    return digest(out / "manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--lock-root",
        type=Path,
        default=Path("experiments/results/g1-visibility-pose-repair-20261124"),
    )
    args = parser.parse_args()
    print(collect(args.asset, args.output, args.lock_root), flush=True)


if __name__ == "__main__":
    main()
