"""Re-render four registered views under one EGL lock from two saved non-integrated poses."""

import argparse
import base64
import fcntl
import importlib
import io
import os
from pathlib import Path

import mujoco
import numpy as np
from contact_geometry import BASE, BUILDS, TRIALS, canonical, exact_asset, pins, prior, screen, sha
from PIL import Image


def project(points, frame):
    t = np.asarray(frame.camera_to_world).reshape(4, 4)
    camera = (np.asarray(points) - t[:3, 3]) @ t[:3, :3]
    assert (camera[:, 2] > 0).all()
    return camera[:, :2] / camera[:, 2:] * frame.intrinsics[:2] + frame.intrinsics[2:], camera[:, 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geometry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assert os.environ["MUJOCO_GL"] == "egl"
    pins()
    args.output.mkdir(exist_ok=False)
    data_doc = prior.read(args.geometry)
    cases = {off: screen.checked_case(p) for off, p in TRIALS.items()}
    native = cases[30]
    idx = native["index"]
    archive = TRIALS[30] / "instance"
    frame = screen.frame_from_row(
        archive, idx["frames"][-1], idx["episode"], idx["scene"], native["geometry"]
    )
    assert idx["frames"][-1]["physics_step"] == 1228 and not any(
        r["physics_step"] == 1227 for r in idx["frames"]
    )
    raw = np.asarray(Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))))
    depth0 = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
        frame.height, frame.width
    )
    from_sensor = importlib.import_module(
        "cloud_edge_robot_arm.vision.observations"
    ).observation_from_sensor_frame
    sealed = BASE / "builds" / BUILDS[30] / "runtime-source"
    for rel in (
        "scripts/graduation/g1_visibility_grid.py",
        "scripts/graduation/g1_visibility_vision.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    ):
        assert prior.sha(sealed / rel) == prior.sha(prior.ROOT / rel)
    out = {}
    pixels = {}
    with (BASE / "egl.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for off in (15, 30):
            registration = cases[off]["geometry"]
            model = mujoco.MjModel.from_xml_path(str(exact_asset(off)))
            d = mujoco.MjData(model)
            camera = screen.MuJoCoRGBDCamera(mujoco, model, width=frame.width, height=frame.height)
            try:
                for step in (1227, 1228):
                    key = f"mount{off}-step{step}"
                    state = native["states"][step]
                    residual = screen.restore(model, d, state)
                    original_state = camera._physics_state_hash(d)
                    sensor, ids, labels, hashes = camera.capture_with_instances(
                        d,
                        rng=np.random.default_rng(0),
                        noise_std_m=0,
                        scene_id=cases[off]["index"]["scene"],
                        episode_id=idx["episode"],
                    )
                    assert (
                        hashes == (original_state,) * 3
                        and camera._physics_state_hash(d) == original_state
                    )
                    assert sensor.sim_time_s == d.time == state["sim_time_s"]
                    packet = from_sensor(sensor, source="mujoco_camera", png_compress_level=1)
                    assert (
                        packet.calibration_version
                        == frame.calibration_version
                        == "f33940579c533afe"
                    )
                    assert (
                        packet.model_dump(mode="json", include=set(registration["camera"]))
                        == registration["camera"]
                    )
                    m = screen.measure_frame(packet, registration)
                    rgb = np.frombuffer(sensor.rgb, dtype=np.uint8).reshape(
                        frame.height, frame.width, 3
                    )
                    depth = np.reshape(sensor.depth, (frame.height, frame.width)).astype("<f4")
                    mask = np.reshape(ids, (frame.height, frame.width)).astype("<i2")
                    images = {"rgb": rgb, "depth": depth, "instance": mask}
                    hashes_files = {}
                    for name, value in images.items():
                        p = args.output / f"{key}-{name}.npy"
                        with p.open("xb") as fp:
                            np.save(fp, value, allow_pickle=False)
                        hashes_files[p.name] = prior.sha(p)
                    pixels[key] = rgb.copy()
                    closest = []
                    record = next(
                        row
                        for row in data_doc["trajectories"]["trajectory-30"]["poses"][str(off)][
                            "states"
                        ]
                        if row["step"] == step
                    )
                    for contact in record["contacts"]:
                        if contact["geom_names"] != ["left_finger_geom", "g1_dual_id7_crossbar"]:
                            continue
                        uv, z = project([contact["midpoint_world_m"]], frame)
                        u, v = np.rint(uv[0]).astype(int)
                        closest.append(
                            dict(
                                uv=uv[0],
                                optical_contact_depth_m=z[0],
                                nearest_native_pixel=[int(u), int(v)],
                                render_visible_geom=labels.get(int(mask[v, u])),
                                render_surface_depth_m=float(depth[v, u]),
                                native_surface_depth_m=float(depth0[v, u]),
                            )
                        )
                    out[key] = dict(
                        state_sha256=original_state,
                        three_camera_pass_hashes=hashes,
                        source_state_index=step,
                        source_time_s=d.time,
                        restore_residual=residual,
                        camera=registration["camera"],
                        registered_marker_asset_sha256=m["asset_sha256"],
                        files=hashes_files,
                        rgb_sha256=sha(rgb.tobytes()),
                        depth_sha256=sha(depth.tobytes()),
                        instance_sha256=sha(mask.tobytes()),
                        readback={
                            k: m[k]
                            for k in (
                                "reason",
                                "usable_ids",
                                "selected_id",
                                "target_disagreement_m",
                            )
                        },
                        native_rgb_comparison=(
                            dict(
                                exact_pixels=int(np.all(raw == rgb, axis=2).sum()),
                                different_pixels=int(np.any(raw != rgb, axis=2).sum()),
                                mean_channel_abs=float(np.mean(abs(raw.astype(float) - rgb))),
                                total_pixels=frame.width * frame.height,
                            )
                            if step == 1228 and off == 30
                            else None
                        ),
                        contact_projection=closest,
                    )
            finally:
                camera.close()
    diffs = {}
    for off in (15, 30):
        a, b = [pixels[f"mount{off}-step{i}"] for i in (1227, 1228)]
        diffs[str(off)] = int(np.any(a != b, axis=2).sum())
    doc = dict(
        schema="g1.dual-support.restored-rgbd.v1",
        source_sha256=prior.sha(Path(__file__)),
        source_geometry_sha256=prior.sha(args.geometry),
        archived_terminal_file_sha256=idx["frames"][-1]["file_sha256"],
        archived_terminal_rgb_sha256=sha(raw.tobytes()),
        archived_camera_frame_at_1227=False,
        independent_renders=out,
        between_step_rgb_changed_pixels=diffs,
        physics_steps=0,
        commands_sent=0,
    )
    with (args.output / "witness.json").open("xb") as fp:
        fp.write(canonical(doc) + b"\n")


if __name__ == "__main__":
    main()
