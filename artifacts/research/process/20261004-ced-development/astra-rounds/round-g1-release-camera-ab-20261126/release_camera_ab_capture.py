"""Registered static native RGB-D A/B capture; this driver never advances physics."""

import argparse
import gzip
import inspect
import math
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

import cv2
import mujoco
import numpy as np

from release_camera_ab_inputs import (
    HERE, PLAN, ROOT, canonical, create, expand, ordered_keys, originals, packet, read,
    require, sha, sha_data, verify_inputs, write,
)
from release_camera_ab_optics import historical_controls
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_complete_cv_clearance import camera_encoder_pose
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.g1_visibility_trials import device

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

NATIVE = PLAN["native_protocol"]
ASSET = next(expand(path) for path in PLAN["verified_input_sha256"] if path.endswith(".xml"))
JOINTS = (
    *(f"joint{i}" for i in range(1, 8)),
    "finger_left_joint",
    "finger_right_joint",
)
ASSEMBLY = ("left_finger_geom", "right_finger_geom", "object_geom", "table", "target_region_geom")


def verify_runtime():
    runtime = expand("{M}")
    for cls, rel in (
        (MuJoCoPhysicsBackend, "simulation/mujoco/backend.py"),
        (MuJoCoRGBDCamera, "simulation/mujoco/camera.py"),
        (observation_from_sensor_frame, "vision/observations.py"),
    ):
        expected = runtime / "src/cloud_edge_robot_arm" / rel
        require(Path(inspect.getfile(cls)).resolve() == expected.resolve(), f"non-frozen native import: {cls}")
    require(mujoco.__version__ == NATIVE["mujoco_version"], "wrong MuJoCo version")
    require(Path(PLAN["worktree"]).resolve() == ROOT, "wrong worktree for registered capture")
    git = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(git == PLAN["base_commit"], "registered capture baseline differs")


def verify_camera_model(model, data, calibration):
    cam = model.camera(NATIVE["camera_name"]).id
    height = NATIVE["size_px"][1]
    f = (height * 0.5) / math.tan(math.radians(float(model.cam_fovy[cam])) * 0.5)
    world = np.eye(4)
    world[:3, :3] = data.cam_xmat[cam].reshape(3, 3) @ np.diag([1, -1, -1])
    world[:3, 3] = data.cam_xpos[cam]
    require(
        model.cam_fovy[cam] == NATIVE["fovy_deg"] and model.vis.quality.offsamples == 4
        and [f, f, (NATIVE["size_px"][0]-1) * 0.5, (height-1)*0.5] == NATIVE["intrinsics"]
        and world.ravel().tolist() == calibration["primary_camera"]["camera_to_world"],
        "fixed camera or multisampling differs",
    )


def restore(model, data, slot, calibration):
    row, source = slot["row"], slot["source"]
    q = np.asarray(row["q"])
    if source["arm"] == "A":
        a = slot["archive_encoder"]
        q = np.r_[a["camera_joint_positions_rad"], a["camera_finger_positions_m"]]
        require(np.max(abs(q - row["q"])) <= 1e-9, "A archive encoder does not match source trajectory")
    center, rotation = (np.asarray(v) for v in row["geom"]["object_geom"])
    dq = np.asarray(row["dq"])
    require(
        q.shape == dq.shape == (9,) and center.shape == (3,) and rotation.shape == (3, 3)
        and np.isfinite(np.r_[q, dq, center, rotation.ravel(), row["object_qvel"], row["control"], row["time_s"]]).all()
        and np.linalg.norm(rotation.T @ rotation - np.eye(3)) <= 1e-9
        and abs(float(np.linalg.det(rotation)) - 1.0) <= 1e-9,
        "sealed state shape, orientation or finite-value check failed",
    )
    free = model.joint("object_free")
    cube = model.geom("object_geom")
    require(
        int(free.type[0]) == mujoco.mjtJoint.mjJNT_FREE
        and int(cube.bodyid[0]) == int(free.bodyid[0])
        and np.array_equal(cube.pos, [0, 0, 0]) and np.array_equal(cube.quat, [1, 0, 0, 0]),
        "body-to-cube transform differs from frozen assembly",
    )
    for joint, position, velocity in zip(JOINTS, q, dq, strict=True):
        name = model.joint(joint)
        data.qpos[int(name.qposadr[0])] = position
        data.qvel[int(name.dofadr[0])] = velocity
    address, velocity = int(free.qposadr[0]), int(free.dofadr[0])
    quat = np.empty(4)
    mujoco.mju_mat2Quat(quat, rotation.ravel())
    require(abs(np.linalg.norm(quat) - 1.0) <= 1e-12, "invalid wxyz quaternion")
    data.qpos[address:address+7] = np.r_[center, quat]
    data.qvel[velocity:velocity+6] = row["object_qvel"]
    data.ctrl[:] = row["control"]
    data.time = row["time_s"]
    require(abs(data.time - source["source_tick"]/240) <= NATIVE["source_time_to_tick_abs_max_s"],
            "static state source clock differs")
    mujoco.mj_forward(model, data)
    require(data.time == row["time_s"], "kinematic reconstruction advanced the native clock")
    verify_camera_model(model, data, calibration)
    expected = {**row["geom"], "tcp": [row["tcp_xyz_m"], row["tcp_R"]]}
    residuals = {}
    for name in (*ASSEMBLY, "tcp"):
        part = data.site("tcp") if name == "tcp" else data.geom(name)
        ref_pos, ref_rot = expected[name]
        residuals[name] = [
            float(np.linalg.norm(part.xpos - ref_pos)),
            float(np.linalg.norm(part.xmat.reshape(3, 3) - ref_rot)),
        ]
        require(
            residuals[name][0] <= NATIVE["position_l2_max_m"]
            and residuals[name][1] <= NATIVE["rotation_matrix_frobenius_max"],
            f"{source['arm']} {source['case']} {source['source_tick']} {name} transform residual {residuals[name]}",
        )
    encoders = camera_encoder_pose(model, data)
    restored_q = np.r_[encoders["camera_joint_positions_rad"], encoders["camera_finger_positions_m"]]
    require(np.max(abs(restored_q-q)) <= 1e-9, "capture buffer differs from admitted static pose")
    return residuals


def pose_preflight(slots, calibration):
    model = mujoco.MjModel.from_xml_path(str(ASSET))
    model.opt.timestep = 1 / 240
    return {
        key: restore(model, mujoco.MjData(model), slots[key], calibration)
        for arm in ("A", "B") for key in ordered_keys(arm)
    }


class EndCaptureScope(Exception):
    """Close the native on-demand context without its implicit final exposure."""


@contextmanager
def on_demand_with_camera_cleanup(backend):
    finished = EndCaptureScope()
    try:
        try:
            with backend.sensor_capture_on_demand():
                yield
                raise finished
        except EndCaptureScope as e:
            if e is not finished:
                raise
        require(not backend._sensor_capture_on_demand, "on-demand cleanup incomplete")
    except BaseException as original:
        try:
            backend.shutdown()
        except BaseException as cleanup:
            original.add_note(f"native shutdown also failed: {cleanup}")
        raise
    else:
        backend.shutdown()
        require(backend._camera is None, "native camera still open after shutdown")


def gl_identity(calibration):
    from OpenGL import GL

    device_info = {
        name: GL.glGetString(value).decode()
        for name, value in (("renderer", GL.GL_RENDERER), ("vendor", GL.GL_VENDOR), ("version", GL.GL_VERSION))
    }
    require(device_info == calibration["renderer"], "native EGL device differs from registration")
    return device_info


def observe_pass(event):
    row = {name: getattr(event, name) for name in (
        "kind", "phase", "operation_id", "episode_id", "physics_step", "sim_time_s", "error_type", "error",
    )}
    if event.kind == "CAPTURE" and event.phase == "END" and event.error is None:
        row["pass_state_hashes"] = list(event.result["pass_state_hashes"])
        row["frame_id"] = event.result["sensor_frame"]["frame_id"]
        row["instance_count"] = len(event.result["instance_ids"])
    return row


def reset_identity(events):
    subset = []
    for event in events:
        result = None if event["result"] is None else {"physics_dt_s": event["result"]["physics_dt_s"]}
        subset.append(dict(
            event, result=result,
            parameters={"requested": {"scenario_id": event["parameters"]["requested"]["scenario_id"]}},
        ))
    return subset


def capture_case(root, arm, case, sources, calibration):
    cid = case["id"]
    folder = root / arm / cid
    folder.mkdir(parents=True, exist_ok=False)
    events, resets, rows = [], [], {}
    identity_receipt = {}
    backend = MuJoCoPhysicsBackend()

    def observer(event):
        events.append(observe_pass(event))
        if event.kind == "RESET":
            resets.append(plain(event))

    backend.initialize(SimulatorConfig(
        model_path=str(ASSET), seed=case["original_physics_seed"], physics_dt_s=1/240,
        domain_randomization=False, render_rgb=True, render_depth=True,
        camera_width=NATIVE["size_px"][0], camera_height=NATIVE["size_px"][1],
    ))
    try:
        with on_demand_with_camera_cleanup(backend), backend.observe_operation_boundaries(observer):
            requested = dict(sources[case["ticks"][0]]["reset"])
            for name in ("object_pose", "target_region_pose"):
                requested[name] = Pose(**requested[name])
            backend.reset(PhysicalScenarioConfig(**requested))
            episode = backend._episode_id
            native_reset_ids(resets, requested["scenario_id"], episode)
            require(resets[0]["parameters"]["requested"] == sources[case["ticks"][0]]["reset"],
                    "native reset request changed")
            require(backend._camera is None and len(events) == 2 and backend.total_physics_steps == 0,
                    "reset performed an unregistered camera exposure or physics step")
            reset_path = folder / "native-resets.json"
            write(reset_path, reset_identity(resets))
            identity_receipt = {"episode_id": episode, "reset_sha256": sha(reset_path)}
            model, data = backend._model, backend._data
            backend._camera = MuJoCoRGBDCamera(
                mujoco, model, width=NATIVE["size_px"][0], height=NATIVE["size_px"][1]
            )
            device_info = gl_identity(calibration)
            require(backend._sensor_noise_std_m == NATIVE["depth_sigma_m"], "native depth noise differs")
            for tick in case["ticks"]:
                slot = sources[tick]
                source = slot["source"]
                residuals = restore(model, data, slot, calibration)
                encoders = camera_encoder_pose(model, data)
                seed = 649300 + tick
                backend._rng = np.random.default_rng(seed)
                rng_sha = sha_data(canonical(backend._rng.bit_generator.state))
                initial = MuJoCoRGBDCamera._physics_state_hash(data)
                write(folder / f"{tick}-request.json", {
                    "source": source, "new_episode": episode, "seed": seed,
                    "rgbd_request": 1, "initial_rng_sha256": rng_sha,
                })
                started = perf_counter_ns()
                native_frame = backend.capture_sensor_frame()
                elapsed = (perf_counter_ns() - started)/1e6
                frame = observation_from_sensor_frame(
                    native_frame, source=NATIVE["source"], png_compress_level=NATIVE["png_compress_level"],
                )
                filename = folder / f"{tick}.json.gz"
                create(filename, gzip.compress(frame.model_dump_json().encode(), compresslevel=2, mtime=0))
                end = events[-1]
                require(
                    backend.total_physics_steps == 0 and len(backend.command_records) == 0
                    and not backend.operation_observer_failures and end["kind"] == "CAPTURE"
                    and end["phase"] == "END" and end["frame_id"] == frame.frame_id and end["instance_count"] == 0
                    and end["pass_state_hashes"] == [initial, initial]
                    and MuJoCoRGBDCamera._physics_state_hash(data) == initial,
                    "native exposure state or pass audit changed",
                )
                crc = frame.model_dump(mode="json", include=set(calibration["primary_camera"]))
                require(
                    crc == calibration["primary_camera"] and frame.episode_id == episode
                    and frame.scene_id == requested["scenario_id"]
                    and frame.sim_time_s == encoders["camera_encoder_sim_time_s"] == source["source_time_s"]
                    and frame.frame_id != source["historical_A_frame"],
                    "native camera/frame/encoder binding differs",
                )
                robot = dict(
                    encoders, frame_id=frame.frame_id, checksum_sha256=frame.checksum_sha256,
                    sim_time_s=frame.sim_time_s, physics_step=tick,
                    last_accepted_gripper_command_step=source["source_open"]["physics_step"],
                    last_accepted_gripper_open=source["source_open"]["target_open"],
                )
                rows[f"{arm}/{cid}/{tick}"] = {
                    "source": source, "source_tick": tick, "new_episode": episode,
                    "packet": filename.relative_to(root / arm).as_posix(), "frame_id": frame.frame_id,
                    "checksum_sha256": frame.checksum_sha256, "file_sha256": sha(filename), "robot": robot,
                }
                write(folder / f"{tick}-receipt.json", {
                    **rows[f"{arm}/{cid}/{tick}"], "max_restore_residuals": residuals,
                    "source_step_end_encoders": slot["row"]["q"],
                    "native_capture_ms": elapsed, "pre_state_sha256": initial,
                    "post_state_sha256": MuJoCoRGBDCamera._physics_state_hash(data),
                    "rng_initial_sha256": rng_sha, "raw_valid_pixels": sum(native_frame.valid_mask),
                    "native_capture_operation_id": end["operation_id"], "gl": device_info,
                })
            require(
                [(event["kind"], event["phase"]) for event in events]
                == [("RESET", "BEGIN"), ("RESET", "END")] + [("CAPTURE", phase) for _ in rows for phase in ("BEGIN", "END")],
                "native reset/exposure count differs",
            )
    finally:
        write(folder / "native-operation-events.json", events)
        write(folder / "native-reset-full.json", resets)
    write(folder / "shutdown.json", {"closed": True, "new_physics_steps": 0, "new_control_actions": 0})
    return rows, identity_receipt


def compare_a(new, old):
    import base64

    def decode(f):
        rgb = cv2.imdecode(np.frombuffer(base64.b64decode(f.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR)
        z = np.frombuffer(base64.b64decode(f.depth_float32_base64), "<f4").astype(float)
        valid = np.frombuffer(base64.b64decode(f.valid_mask_base64), "u1").astype(bool)
        return rgb, z, valid

    im, z, valid = decode(new)
    archived_im, archived_z, archived_valid = decode(old)
    delta = (z - archived_z).reshape(new.height, new.width) * 1000
    use = (valid & archived_valid).reshape(delta.shape)
    values = delta[use]
    maximum = np.unravel_index(np.argmax(np.where(use, abs(delta), -np.inf)), delta.shape)
    result = {
        "rgb_equal": bool(im is not None and np.array_equal(im, archived_im)),
        "valid_mask_equal": bool(np.array_equal(valid, archived_valid)),
        "signed_mean_mm": float(values.mean()),
        "rmse_mm": float(np.sqrt((values**2).mean())),
        "p99_abs_mm": float(np.percentile(abs(values), 99)),
        "max_abs_mm": float(np.max(abs(values))),
        "max_abs_uv": [int(maximum[1]), int(maximum[0])],
    }
    thresholds = NATIVE["A_replay_checks"]
    result["passed"] = (
        result["rgb_equal"] and result["valid_mask_equal"]
        and abs(result["signed_mean_mm"]) <= thresholds["absolute_mean_depth_difference_max_mm"]
        and result["rmse_mm"] <= thresholds["depth_rmse_max_mm"]
        and result["p99_abs_mm"] <= thresholds["absolute_depth_difference_p99_max_mm"]
    )
    return result


def run_capture(root, thread_id, manifest, slots, calibration, controls, poses, frozen):
    require(os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
            "native EGL must be selected before importing MuJoCo and OpenGL")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "input-manifest.json", manifest)
    write(root / "source-slots.json", {key: slot["source"] for key, slot in slots.items()})
    write(root / "historical-controls.json", controls)
    write(root / "static-pose-preflight.json", poses)
    registered = {
        "baseline": PLAN["base_commit"], "astra_local_thread": thread_id, "astra_model": PLAN["requested_planning_model"],
        "utc_registered": datetime.now(UTC).isoformat(),
        "plan_files_sha256": {name: sha(HERE / name) for name in ("plan.md", "plan.json")},
        "source_files_sha256": {file.name: sha(file) for file in sorted(HERE.glob("release_camera_ab_*.py"))},
        "input_manifest_sha256": sha(root / "input-manifest.json"),
        "source_slots_sha256": sha(root / "source-slots.json"),
        "control_receipt_sha256": sha(root / "historical-controls.json"),
        "restore_preflight_sha256": sha(root / "static-pose-preflight.json"),
        "primary_camera": calibration["primary_camera"], "renderer": calibration["renderer"],
        "mujoco_version": mujoco.__version__, "numpy_version": np.__version__, "opencv_version": cv2.__version__,
        "slots": ordered_keys("A") + ordered_keys("B"), "limits": PLAN["future_execution_limits"],
        "native_protocol": NATIVE, "gate": PLAN["gate"], "frozen_formal_originals": frozen,
    }
    registration = root / "registration.json"
    write(registration, registered)
    reg_sha = sha(registration)
    attempt_stage = "EGL lock"
    try:
        with device((ROOT / NATIVE["exclusive_lock"]).parent):
            for arm in ("A", "B"):
                rows, incoming = {}, {}
                for case in PLAN["cases"]:
                    cid = case["id"]
                    attempt_stage = f"{arm}/{cid}"
                    selected = {tick: slots[f"{arm}/{cid}/{tick}"] for tick in case["ticks"]}
                    captured, incoming[cid] = capture_case(root, arm, case, selected, calibration)
                    rows.update(captured)
                write(root / arm / "index.json", {"registration_sha256": reg_sha, "cases": incoming, "rows": rows})
                attempt_stage = f"{arm}/optical-prediction"
                subprocess.run(
                    [sys.executable, "-B", str(HERE / "release_camera_ab_optics.py"), str(root), arm, reg_sha],
                    check=True, cwd=ROOT,
                )
                if arm == "A":
                    attempt_stage = "A historical baseline gate"
                    observed = read(root / arm / "predictions.json")["predictions"]
                    values = {}
                    for key, entry in rows.items():
                        new = packet(root / arm / entry["packet"])
                        original = packet(slots[key]["archive_A"])
                        values[key] = compare_a(new, original)
                        values[key]["original_pose_rejection_reproduced"] = (
                            observed[key]["pose_method"] is None and observed[key]["gaps_m"] is None
                        )
                    write(root / "A-baseline.json", values)
                    require(
                        all(x["passed"] and x["original_pose_rejection_reproduced"] for x in values.values()),
                        f"A baseline rejected: {[key for key, x in values.items() if not x['passed'] or not x['original_pose_rejection_reproduced']]}",
                    )
        write(root / "capture-seal.json", {
            "registration_sha256": reg_sha, "exposure_requests": 18, "captured": 18,
            "new_physics_steps": 0, "new_control_actions": 0, "formal_simulations": 0,
            "originals_after": originals(),
            "sealed_sha256": {
                name: sha(root / name) for name in ("A/index.json", "B/index.json", "A/predictions.json",
                                                    "B/predictions.json", "A-baseline.json")
            },
        })
    except BaseException as exc:
        write(root / "failure.json", {
            "stage": attempt_stage, "error": str(exc), "type": type(exc).__name__,
            "consumed_exposure_slots": len(list(root.glob("[AB]/*/*-request.json"))),
            "registration_sha256": reg_sha,
        })
        raise


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--capture", action="store_true")
    args.add_argument("--astra-thread")
    options = args.parse_args()
    verify_runtime()
    manifest, slots, calibration = verify_inputs()
    frozen = originals()
    controls = historical_controls(slots)
    poses = pose_preflight(slots, calibration)
    print(f"Verified {len(manifest)} input digests, {len(controls['negative_controls'])} negative controls, {len(poses)} static poses", flush=True)
    print("Maximum restore residuals:",
          max(v[0] for parts in poses.values() for v in parts.values()),
          max(v[1] for parts in poses.values() for v in parts.values()), flush=True)
    if options.capture:
        require(options.astra_thread is not None, "capture requires the original Astra planning identity")
        run_capture(expand(PLAN["outputs"]["new_private_root"]), options.astra_thread, manifest, slots,
                    calibration, controls, poses, frozen)
