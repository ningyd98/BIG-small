"""Capture matched RELEASE views of an opaque plate and independently score the frozen observer."""

import argparse
import base64
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from read_pose_coverage import native_marker
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_complete_cv_calibrate import CAMERA_FIELDS, axial, digest
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, camera_encoder_pose
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation, camera_hash
from scripts.graduation.g1_complete_cv_payload_observation import (
    frozen_red_geometry,
    payload_observation,
)
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.perception_io import pinned

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
RAW = ROOT / "experiments/results/g1-continuous-payload-observation-20261125"
SOURCE = RAW / "physical-03/dense-check-01"
OUT = RAW / "physical-03/dense-negative-03"
BUILDS = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
FROZEN = "3f6e2706bfa488c9ca57e156385e70892adab9a44729f78fc34e58361b88d0da"
NATIVE = "9ed09852049be122ae5ff684af8d89e20012dcae7486db44e93421e075d57caf"
TEMPLATE = BUILDS / "batches/train-full-04/cvfix-t02/allocation.json"
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
SEED = 731707
INDEX = 501
SCENE = "g1.continuous-payload/dense-negative-03"
PART = "diagnostic_regular_opaque_board"


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as f:
        json.dump(plain(value), f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def rgb(frame):
    png = np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8)
    return cv2.imdecode(png, cv2.IMREAD_COLOR)[:, :, ::-1]


def image(path):
    return RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))


def freeze():
    registry = pinned(
        HERE / "observer-freeze.public.json",
        "395cb6c5e156cc3985532eb1c7f72e1054e0f4d1ccf9c55624d2dbeb19ffcd01",
    )
    for path, value in registry["sources_sha256"].items():
        assert digest(ROOT / path) == value
    assert registry["runtime"] == FROZEN
    declared = read(HERE / "dense-negative-03-capture-registration.json")
    reg = pinned(
        HERE / "continuous-diagnostic-registration.json", declared["scene_registration_sha256"]
    )
    slot = next(v for v in reg["negative"] if v["id"] == "dense-negative-03")
    assert slot["depth_seed"] == SEED and slot["offset_from_depth_nearer_m"] == 0.09
    return declared, reg


def source_inputs():
    declared, reg = freeze()
    index = pinned(
        SOURCE / "rgbd-index.json",
        "1e9d89f471f2945e3646b175204fbd0092537ac3b8e2602850a715b034817c9f",
    )
    row = index["rows"][INDEX]
    assert (row["skill"], row["phase"], row["dwell_tick"]) == ("RELEASE", "DWELL", 240)
    assert row["robot"]["physics_step"] == 5670
    path = SOURCE / row["file"]
    assert digest(path) == row["file_sha256"] == declared["source_sha256"]
    frame = image(path)
    assert (frame.frame_id, frame.checksum_sha256) == (
        row["robot"]["frame_id"],
        row["robot"]["checksum_sha256"],
    )
    template = read(TEMPLATE)
    assert (
        digest(ROOT / template["geometry"]["asset_path"]) == reg["native_controller_asset_sha256"]
    )
    return frame, row, template


def board_from_source(frame, pose):
    depth = axial(frame)
    px = rgb(frame).astype(float)
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = frame.intrinsics
    y, x = np.indices(depth.shape)
    rays = np.stack(((x - cx) / fx, (y - cy) / fy, np.ones_like(x)), axis=-1) @ tf[:3, :3].T
    xyz = tf[:3, 3] + rays * depth[..., None]
    c = np.asarray(pose["center_m"])
    rot = np.asarray(pose["rotation"])
    local = (xyz - c) @ rot
    r, g, b = px.transpose(2, 0, 1)
    red = (
        (r > 1.25 * g + 7)
        & (r > 1.25 * b + 7)
        & (np.max(abs(local[:, :, :2]), axis=2) <= 0.037)
        & (abs(local[:, :, 2] - 0.035) < 0.004)
    )
    if red.sum() < 12:
        raise ValueError("observed red surface unavailable at prescribed checkpoint")
    v, u = np.nonzero(red)
    uv = np.array([np.median(u), np.median(v)])
    target_depth = float(np.median(depth[red]))
    top_depth = target_depth - 0.090
    top = tf[:3, 3] + tf[:3, :3] @ np.array([(uv[0] - cx) / fx, (uv[1] - cy) / fy, 1]) * top_depth
    assert np.allclose(tf[:3, 2], [0, 0, -1], atol=1e-12)
    return dict(
        observed_red_pixels=int(red.sum()),
        observed_red_center_uv=uv,
        source_red_depth_m=target_depth,
        nearer_top_face_optical_depth_m=top_depth,
        world_center_m=top - [0, 0, 0.001],
        half_extents_m=[0.042, 0.042, 0.001],
    )


def setup(xml, state, step, sim_time, *, record_reset):
    backend = MuJoCoPhysicsBackend()
    records = []

    def reset_event(event):
        if event.kind == "RESET":
            records.append(plain(event))

    backend.initialize(
        SimulatorConfig(
            model_path=str(xml),
            physics_dt_s=1 / 240,
            render_rgb=True,
            render_depth=True,
            domain_randomization=False,
            seed=731684,
        )
    )
    with backend.observe_operation_boundaries(reset_event):
        backend.reset(
            PhysicalScenarioConfig(
                scenario_id=SCENE,
                seed=731684,
                object_pose=Pose(x=0.44498, y=0.00306, z=0.035),
                object_mass_kg=float(backend._model.body("object").mass[0]),
                friction_coefficient=0.8,
            )
        )
    if record_reset:
        write(record_reset, records)
    model, data = backend._model, backend._data
    data.qpos[:] = state
    data.time = sim_time
    mujoco.mj_forward(model, data)
    backend._rng = np.random.default_rng(SEED)
    # Only view kinematics are restored. No integration, state transition or issued actuator target.
    assert backend.total_physics_steps == 0 and not backend.command_records
    return backend, records


def capture():
    frame, row, template = source_inputs()
    OUT.mkdir(exist_ok=True, parents=True)
    if (OUT / "acquisition.json").exists() or list(OUT.glob("*.rgbd.json.gz")):
        raise FileExistsError("counterfactual has already been observed")
    pred_path = RAW / "dense-check-01-prediction-02.json"
    pred = read(pred_path)["records"][INDEX]
    assert pred["frame_id"] == frame.frame_id and pred["result"]["pose"]
    board = board_from_source(frame, pred["result"]["pose"])
    opt = ROOT / template["geometry"]["asset_path"]
    base = OUT / "registered-reference.xml"
    if base.exists():
        assert digest(base) == digest(opt)
    else:
        base.write_bytes(opt.read_bytes())
    xml = ET.parse(base)
    ET.SubElement(
        xml.find("worldbody"),
        "geom",
        name=PART,
        type="box",
        pos=" ".join(map(str, board["world_center_m"])),
        size=".042 .042 .001",
        rgba=".46 .46 .46 1",
        contype="1",
        conaffinity="3",
    )
    inserted = OUT / "physical-opaque-board.xml"
    content = ET.tostring(xml.getroot(), encoding="utf-8")
    if inserted.exists():
        assert inserted.read_bytes() == content
    else:
        inserted.write_bytes(content)
    truth = pinned(
        SOURCE / "offline-physics.json",
        "6f0b37c593f08781e6809fc57a2ea3115b311f3670c3731d2c43fb0cb1cfb207",
    )["frame_labels"][INDEX]
    assert truth["frame_id"] == frame.frame_id and truth["checksum_sha256"] == frame.checksum_sha256
    rotation = np.asarray(truth["rotation"])
    quat = np.empty(4)
    mujoco.mju_mat2Quat(quat, rotation.reshape(-1))
    packet = row["robot"]
    state = np.r_[
        packet["camera_joint_positions_rad"],
        packet["camera_finger_positions_m"],
        truth["center_m"],
        quat,
    ]
    state_path = OUT / "isolated-camera-state.npy"
    if state_path.exists():
        assert np.array_equal(np.load(state_path, allow_pickle=False), state)
    else:
        np.save(state_path, state, allow_pickle=False)
    epochs = {}
    for tag, path in (("reference", base), ("occluder", inserted)):
        backend, _ = setup(
            path,
            state,
            packet["physics_step"],
            frame.sim_time_s,
            record_reset=OUT / (tag + "-native-reset.json"),
        )
        try:
            backend._camera = backend._camera or MuJoCoRGBDCamera(
                mujoco, backend._model, width=frame.width, height=frame.height
            )
            fresh = backend._camera.capture(
                backend._data,
                rng=backend._rng,
                noise_std_m=backend._sensor_noise_std_m,
                scene_id=SCENE,
                episode_id=backend._episode_id,
            )
            obs = observation_from_sensor_frame(fresh, source="mujoco_camera", png_compress_level=1)
            same_camera = obs.model_dump(mode="json", include=set(CAMERA_FIELDS))
            assert (
                same_camera == template["geometry"]["camera"] and obs.sim_time_s == frame.sim_time_s
            )
            target = OUT / (tag + ".rgbd.json.gz")
            with target.open("xb") as f:
                f.write(gzip.compress(obs.model_dump_json().encode(), 2, mtime=0))
            current = dict(packet, **camera_encoder_pose(backend._model, backend._data))
            current.update(
                frame_id=obs.frame_id,
                checksum_sha256=obs.checksum_sha256,
                sim_time_s=obs.sim_time_s,
            )
            # No commands were executed in these isolated instances. The real source's
            # closed/open action provenance is catalogued separately, never fabricated here.
            for field in (
                "last_accepted_gripper_open",
                "last_accepted_gripper_command_step",
                "previous_native_return_step",
                "previous_native_terminal_step",
                "previous_native_successful_skill",
            ):
                current[field] = None
            current["native_last_command_seq"] = 0
            write(OUT / (tag + "-sensor.json"), current)
            geom = backend._data.geom("object_geom")
            assert np.allclose(geom.xpos, truth["center_m"], atol=1e-12, rtol=0) and np.allclose(
                geom.xmat.reshape(3, 3), rotation, atol=1e-12, rtol=0
            )
            assert backend.total_physics_steps == 0 and len(backend.command_records) == 0
            epochs[tag] = dict(
                frame_sha256=digest(target),
                checksum=obs.checksum_sha256,
                frame_id=obs.frame_id,
                episode=obs.episode_id,
                camera_sha256=camera_hash(same_camera),
                xml_sha256=digest(path),
                sensor_sha256=digest(OUT / (tag + "-sensor.json")),
                renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                physics_ticks_executed=0,
                actuator_commands_issued=0,
                exposure_time_s=obs.sim_time_s,
                reset_sha256=digest(OUT / (tag + "-native-reset.json")),
            )
        finally:
            backend.shutdown()
    write(
        OUT / "acquisition.json",
        dict(
            id="dense-negative-03",
            rows=epochs,
            board=board,
            source_frame=digest(SOURCE / row["file"]),
            source_fid=frame.frame_id,
            source_pose_prediction_sha256=digest(pred_path),
            source_native_physics_sha256=digest(SOURCE / "offline-physics.json"),
            camera_state_sha256=digest(OUT / "isolated-camera-state.npy"),
            method_sha256=digest(Path(__file__)),
            registration_sha256=digest(HERE / "dense-negative-03-capture-registration.json"),
            rng_seed=SEED,
            physical_setup_used_only_for_rendering=True,
        ),
    )


def predict():
    original, row, template = source_inputs()
    acq = read(OUT / "acquisition.json")
    g = template["geometry"]
    measure, detector = native_marker(template["runtime_build_sha256"])
    red = frozen_red_geometry(BUILDS / "builds" / FROZEN / "runtime-source", ROOT / g["asset_path"])
    ans = {}
    for tag, a in acq["rows"].items():
        file = OUT / (tag + ".rgbd.json.gz")
        assert digest(file) == a["frame_sha256"]
        fc = image(file)
        m = pinned(OUT / (tag + "-sensor.json"), a["sensor_sha256"])
        scene, episode = native_reset_ids(
            pinned(OUT / (tag + "-native-reset.json"), a["reset_sha256"]), SCENE, fc.episode_id
        )
        allocation = read(TEMPLATE)
        allocation["case"].update(scene_id=scene)
        data = json.dumps(allocation, sort_keys=True).encode()
        identity = bind_allocation(
            data,
            allocation_sha256=hashlib.sha256(data).hexdigest(),
            generation_sha256=template["runtime_build_sha256"],
            calibration_sha256=template["calibration_sha256"],
            asset_sha256=digest(ROOT / g["asset_path"]),
            reset_scene_id=scene,
            reset_episode_id=episode,
        )
        marker = measure(fc, g)
        pose = rigid_pose(fc, marker, g, identity=identity, physics_step=m["physics_step"])
        relation = payload_observation(
            fc,
            marker,
            g,
            m,
            "RELEASE",
            "DWELL",
            identity=identity,
            physics_step=m["physics_step"],
            optical=pose,
            history={},
            red_geometry=red,
        )
        gate = LocalClearance(
            g,
            ROOT / g["asset_path"],
            template["calibration_directory"],
            calibration_sha256=template["calibration_sha256"],
            isolated_scene=True,
            optical_identity=identity,
        )
        try:
            q = np.asarray(m["camera_joint_positions_rad"])
            f = np.asarray(m["camera_finger_positions_m"])
            tcp, r, links = gate.model.forward(q)
            hand = gate.model.hand_at(tcp, r, f)
            bodies = []
            if marker.get("usable"):
                c = np.asarray(marker["object_center_world_m"])
                rot = np.asarray(marker["rotation_object_to_world"]).reshape(3, 3)
                bodies = [v.placed(c, rot) for v in gate.model.object]
            surfaces = gate.changed_surfaces(
                fc, bodies, hand, tcp, links, q, f, payload_pose=relation.get("pose")
            )
            ans[tag] = dict(
                marker_usable=marker.get("usable"),
                ids=marker.get("usable_ids"),
                marker_reason=marker.get("reason"),
                relation=relation,
                depth_surfaces=surfaces,
                can_authorize_motion=False,
            )
        finally:
            gate.close()
    write(
        OUT / "sensor-predictions.json",
        dict(
            rows=ans,
            sealed_acquisition_sha256=digest(OUT / "acquisition.json"),
            native_detector_sha256=detector,
            frozen_observer=FROZEN,
            truth_inputs_read=False,
            segmentation_inputs_read=False,
            history="independent single current exposure; no assumed prior action",
        ),
    )


def score():
    original, source_row, _ = source_inputs()
    sealed = read(OUT / "sensor-predictions.json")
    acq = pinned(OUT / "acquisition.json", sealed["sealed_acquisition_sha256"])
    state = np.load(OUT / "isolated-camera-state.npy", allow_pickle=False)
    assert digest(OUT / "isolated-camera-state.npy") == acq["camera_state_sha256"]
    imgs = {}
    masks = {}
    labels = {}
    for tag, filename in (
        ("reference", "registered-reference.xml"),
        ("occluder", "physical-opaque-board.xml"),
    ):
        xml = OUT / filename
        assert digest(xml) == acq["rows"][tag]["xml_sha256"]
        captured = image(OUT / (tag + ".rgbd.json.gz"))
        imgs[tag] = captured
        backend, _ = setup(
            xml, state, source_row["robot"]["physics_step"], original.sim_time_s, record_reset=None
        )
        try:
            cam = backend._camera or MuJoCoRGBDCamera(
                mujoco, backend._model, width=captured.width, height=captured.height
            )
            backend._camera = cam
            sensor, ids, names, hashes = cam.capture_with_instances(
                backend._data,
                rng=backend._rng,
                noise_std_m=backend._sensor_noise_std_m,
                scene_id=SCENE,
                episode_id=backend._episode_id,
            )
            scored = observation_from_sensor_frame(
                sensor, source="mujoco_camera", png_compress_level=1
            )
            assert np.array_equal(rgb(captured), rgb(scored)) and np.array_equal(
                axial(captured), axial(scored)
            )
            assert (
                len(set(hashes)) == 1
                and backend.total_physics_steps == 0
                and not backend.command_records
            )
            masks[tag] = np.array(ids, np.int16).reshape(captured.height, captured.width)
            labels[tag] = names
        finally:
            backend.shutdown()
    ids = masks["occluder"]
    new_id = next(i for i, n in labels["occluder"].items() if n == PART)
    board = ids == new_id
    if not board.any():
        raise ValueError("physical board invisible")
    original_ids, mcounts = np.unique(masks["reference"][board], return_counts=True)
    under = {
        labels["reference"].get(int(i), "background"): int(n)
        for i, n in zip(original_ids, mcounts, strict=True)
    }
    delta = axial(imgs["reference"]) - axial(imgs["occluder"])
    color = np.any(rgb(imgs["reference"]) != rgb(imgs["occluder"]), axis=2)
    samples = sealed["rows"]["occluder"]["depth_surfaces"]["unmatched_pixels_uv"]
    truth_sample = [
        dict(
            uv=[u, v],
            geom=labels["occluder"].get(int(ids[v, u]), "background"),
            behind=labels["reference"].get(int(masks["reference"][v, u]), "background"),
            nearer_m=float(delta[v, u]),
        )
        for u, v in samples
    ]
    score = dict(
        board_pixels=int(board.sum()),
        original_geoms_under_board=under,
        board_pixels_directly_changed_rgb=int((board & color).sum()),
        board_pixels_directly_nearer_8mm=int((board & (delta > 0.008)).sum()),
        board_depth_change_quantiles_m=np.quantile(delta[board], [0, 0.5, 1]),
        rgb_and_depth_changed_in_pair_px=[int(color.sum()), int((delta != 0).sum())],
        reference_reproduced_original_rgb_equal_px=int(
            (rgb(original) == rgb(imgs["reference"])).all(2).sum()
        ),
        image_pixels=original.width * original.height,
        reference_depth_abs_vs_archived_p99_m=float(
            np.quantile(abs(axial(original) - axial(imgs["reference"])), 0.99)
        ),
        directly_scored_unmatched_depth_samples=truth_sample,
        original_sensor_relation=read(RAW / "dense-check-01-prediction-02.json")["records"][INDEX][
            "result"
        ]["relation"],
    )
    np.savez_compressed(
        OUT / "offline-instance-maps.npz", reference=masks["reference"], occluder=ids
    )
    write(
        OUT / "offline-attribution.json",
        dict(
            score=score,
            instance_label_maps=labels,
            instance_masks_sha256=digest(OUT / "offline-instance-maps.npz"),
            prediction_sha256=digest(OUT / "sensor-predictions.json"),
            counterfactual_simulation_only=True,
        ),
    )
    print(json.dumps(plain(score), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "predict", "score"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        {"capture": capture, "predict": predict, "score": score}[args.mode]()
