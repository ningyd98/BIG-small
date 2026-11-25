"""Native RGB-D fit exposures at eight preregistered static carrier poses."""

import fcntl
import gzip
import importlib.util
import math
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
PREREG = "0e483c24f479437d83d443d2e350ecc27e8a7af8f7a5b16d2909e362064b7580"
NATIVE = "816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb"
ORIGINAL = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
BENCH = ROOT / "experiments/results/g1-continuous-payload-observation-20261125"
OUT = ROOT / "experiments/results/g1-print-pose-uncertainty-20261125/native-static-fit-01"
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def reference():
    bench = BENCH / "physical-03/dense-fit-01"
    receipt = pinned(
        bench / "sensor-receipt.json",
        "330019bf2c20b7dedde0375ae617ead005a42adbdc57278deb0561b5cda2dd70",
    )
    rows = pinned(bench / "rgbd-index.json", receipt["index_sha256"])["rows"]
    shadow = read(BENCH / "dense-fit-01-prediction-02.json")["records"]
    for row, frame in zip(rows, shadow, strict=True):
        pose = frame["result"]["pose"] or {}
        if (
            frame["skill"] != "MOVE_TO_REGION"
            or pose.get("method") != "id8_print_grid_and_visible_red_top"
        ):
            continue
        assert frame["frame_id"] == row["robot"]["frame_id"]
        assert sha(bench / row["file"]) == row["file_sha256"]
        return row
    raise ValueError("no registered first print-grid view")


def capture():
    cfg = pinned(HERE / "static-fit-capture-registration.json", PREREG)
    design = pinned(HERE / "diagnostic-registration.json", cfg["diagnostic_registration_sha256"])
    for name, token in design["input_sha256"].items():
        assert sha(ROOT / name) == token
    generation = ORIGINAL / "builds" / NATIVE / "runtime-source"
    code = "src/cloud_edge_robot_arm/simulation/mujoco/camera.py"
    kernel = pinned(generation / "runtime-build.json", NATIVE)
    imported = Path(importlib.util.find_spec(MuJoCoRGBDCamera.__module__).origin).resolve()
    assert (
        imported == (generation / code).resolve()
        and sha(imported) == kernel["runtime_files_sha256"][code]
    )
    a = read(ORIGINAL / "batches/train-full-04/cvfix-t01/allocation.json")
    asset = generation / a["geometry"]["asset_path"]
    assert sha(asset) == design["asset_sha256"]
    anchor = reference()
    frame_ref = anchor["robot"]
    registration = design["new_camera_only_sequences"]["fit"]
    assert [r["id"] for r in registration] == cfg["sequence"]
    OUT.mkdir(parents=True, exist_ok=False)
    rows, truth = [], []
    model = mujoco.MjModel.from_xml_path(str(asset))
    data = mujoco.MjData(model)
    data.qpos[:7] = frame_ref["camera_joint_positions_rad"]
    data.qpos[7:9] = frame_ref["camera_finger_positions_m"]
    data.time = frame_ref["sim_time_s"]
    free = model.joint("object_free").qposadr[0]
    with LOCK.open("rb") as hold:
        fcntl.flock(hold, fcntl.LOCK_EX)
        camera = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        try:
            renderer = GL.glGetString(GL.GL_RENDERER).decode()
            assert renderer == design["renderer"]
            for order, group in enumerate(registration):
                for i, yaw in enumerate(group["yaw_deg"]):
                    center = [*group["xy_m"], group["z_m"]]
                    data.qpos[free : free + 3] = center
                    data.qpos[free + 3 : free + 7] = [
                        math.cos(math.radians(yaw) / 2),
                        0,
                        0,
                        math.sin(math.radians(yaw) / 2),
                    ]
                    mujoco.mj_forward(model, data)
                    for j in range(cfg["independent_seeds_per_pose"]):
                        seed = cfg["capture_seed_start"] + 100 * order + 10 * i + j
                        native = camera.capture(
                            data,
                            rng=np.random.default_rng(seed),
                            noise_std_m=0.001,
                            scene_id="g1.ink.static-fit",
                            episode_id=group["id"],
                        )
                        frame = observation_from_sensor_frame(
                            native, source="mujoco_camera", png_compress_level=1
                        )
                        assert (
                            frame.model_dump(mode="json", include=set(design["camera"]))
                            == design["camera"]
                        )
                        name = f"{len(rows):03}.json.gz"
                        with (OUT / name).open("xb") as f:
                            f.write(gzip.compress(frame.model_dump_json().encode(), 2, mtime=0))
                        rows.append(
                            dict(
                                group=group["id"],
                                frame_id=frame.frame_id,
                                checksum_sha256=frame.checksum_sha256,
                                seed=seed,
                                file=name,
                                sha256=sha(OUT / name),
                            )
                        )
                        truth.append(dict(frame_id=frame.frame_id, center_m=center, yaw_deg=yaw))
        finally:
            camera.close()
    write(
        OUT / "acquisition.json",
        dict(
            registration_sha256=PREREG,
            original_camera_source_sha256=sha(imported),
            optical_source_frame_sha256=anchor["file_sha256"],
            camera=a["geometry"]["camera"],
            renderer=renderer,
            generation=NATIVE,
            raw_rows=rows,
            physics_steps_advanced=0,
        ),
    )
    write(OUT / "offline-labels.json", truth)
    print(len(rows), sha(OUT / "acquisition.json"))


if __name__ == "__main__":
    capture()
