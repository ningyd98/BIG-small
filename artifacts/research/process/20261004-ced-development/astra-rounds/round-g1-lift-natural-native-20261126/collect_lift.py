"""Collect six preregistered local MuJoCo lift prefixes on the original controller."""

import argparse
import fcntl
import gzip
import importlib
import inspect
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import patch

from scripts.graduation.perception_io import pinned, read, sha, write

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
CV = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
T02 = CV / "batches/train-full-04/cvfix-t02"
RAW = ROOT / "experiments/results/g1-lift-natural-native-20261126"
OUT = RAW / "capture-01"
PLAN = read(HERE / "plan.json")
RUNTIME = CV / "builds" / PLAN["runtime"] / "runtime-source"
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
LEGACY = HERE.parent / "round-g1-continuous-payload-observation-20261125"
SKILLS = ("MOVE_ABOVE", "APPROACH", "GRASP", "LIFT")


class PhysicalLimit(RuntimeError):
    """End the isolated batch at an unexpected state, acquisition or budget limit."""


def require(valid, reason):
    if not valid:
        raise PhysicalLimit(reason)


def preflight():
    dirs = {"rounds": HERE.parent, "cv": CV}
    for alias, expected in PLAN["pins"].items():
        group, name = alias.split("/", 1)
        path = dirs[group] / name
        require(
            path.resolve().is_relative_to(ROOT) and sha(path) == expected,
            f"frozen source differs: {alias}",
        )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["head"], "Astra baseline differs")
    manifest = pinned(RUNTIME / "runtime-build.json", PLAN["runtime"])
    base = read(T02 / "allocation.json")
    model = RUNTIME / base["geometry"]["asset_path"]
    require(sha(model) == base["asset_sha256"], "frozen asset differs")
    calib = read(CV / "calibration-gpu-01/manifest.json")
    require(base["geometry"]["camera"] == calib["primary_camera"], "camera registry differs")
    asked = read(T02 / "instance/reset-observed.json")[0]["parameters"]["requested"]
    require(
        asked["friction_coefficient"] == PLAN["friction"]
        and asked["object_mass_kg"] == PLAN["mass_kg"]
        and asked["object_yaw_rad"] == math.radians(PLAN["yaw_deg"]),
        "original reset differs",
    )
    (original,) = [
        r
        for r in read(T02 / "instance/local-clearance.json")["rows"]
        if r["skill"] == "APPROACH" and r["phase"] == "PRE"
    ]
    require(original["robot"]["physics_step"] == 856, "registered approach source changed")
    aim = [original["target_xyz"][k] - asked["object_pose"][k] for k in ("x", "y", "z")]
    require(
        len(PLAN["cases"]) == PLAN["max_attempts"] == 6
        and len({c["physics_seed"] for c in PLAN["cases"]}) == 6
        and len({c["depth_seed"] for c in PLAN["cases"]}) == 6
        and len({tuple(c["center_m"]) for c in PLAN["cases"]}) == 6,
        "case count, seed or pose registration differs",
    )
    require(LOCK.is_file(), "shared EGL lock missing")
    return model, aim, asked, calib, manifest


def audit_inputs():
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "EGL was not set before imports",
    )
    import mujoco

    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

    require(mujoco.__version__ == "3.3.7", "frozen MuJoCo version differs")
    manifest = pinned(RUNTIME / "runtime-build.json", PLAN["runtime"])
    for filename, cls in (
        ("backend.py", MuJoCoPhysicsBackend),
        ("camera.py", MuJoCoRGBDCamera),
        ("skill_robot.py", MuJoCoSkillRobot),
        ("visual_servo.py", VisualServoSession),
    ):
        part = f"src/cloud_edge_robot_arm/simulation/mujoco/{filename}"
        actual = Path(inspect.getfile(cls)).resolve()
        require(
            actual == (RUNTIME / part).resolve()
            and sha(actual) == manifest["runtime_files_sha256"][part],
            f"active implementation differs from frozen runtime: {filename}",
        )
    source = inspect.getsource(MuJoCoSkillRobot._move)
    require(
        "except ValueError as exc:" in source and '"VISUAL_SERVO_REJECTED"' in source,
        "original controlled callback abort no longer maps to the native result",
    )
    return MuJoCoRGBDCamera


def scoped_capture(backend, arm, slot, aim, frames, truth, actions, timeline, legacy):
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

    feedback, stage, previous = 0, "SETTLE", None
    cap = PLAN["max_lift_feedback_per_case"]
    motion = {
        "tcp_velocity": PLAN["tcp_velocity_m_s"],
        "acceleration": PLAN["tcp_acceleration_m_s2"],
        "timeout_ms": PLAN["motion_timeout_ms"],
    }
    target = Pose(
        **dict(
            zip(
                ("x", "y", "z"),
                (c + o for c, o in zip(slot["center_m"], aim, strict=True)),
                strict=True,
            )
        )
    )
    high_target = Pose(x=target.x, y=target.y, z=max(0.16, target.z + 0.10))

    def guard(snapshot):
        illegal = [legacy.plain(c) for c in backend.get_contacts() if c.illegal]
        if illegal:
            timeline.append({"step": snapshot.physics_step, "stage": stage, "illegal": illegal})
            raise PhysicalLimit("native step detected forbidden contact")
        require(
            snapshot.physics_step < PLAN["exclusive_physics_step_limit_per_case"],
            "registered physics budget exhausted",
        )

    def take(phase):
        accepted = [
            cmd for cmd in backend.command_records if cmd["type"] == "gripper" and cmd["accepted"]
        ]
        last_jaw = accepted[-1] if accepted else {}
        last_stage = previous or {}
        begin = time.monotonic_ns()
        native_frame = backend.capture_sensor_frame()
        exposure = (time.monotonic_ns() - begin) / 1e6
        legacy.append_frame(
            {
                "skill": stage,
                "phase": phase,
                "dwell_tick": None,
                "capture_ms": exposure,
                "terminal_budget_sample": phase == "FEEDBACK" and feedback == cap,
                "last_accepted_gripper_open": last_jaw.get("target_open"),
                "last_accepted_gripper_command_step": last_jaw.get("physics_step"),
                "previous_native_successful_skill": last_stage.get("skill"),
                "previous_native_return_step": last_stage.get("return_step"),
                "previous_native_terminal_step": last_stage.get("end_step"),
            },
            backend,
            native_frame,
            frames,
            truth,
        )
        robot = frames[-1][1]
        require(
            robot["sim_time_s"] == robot["camera_encoder_sim_time_s"],
            "sampled encoder and shutter clock differ",
        )
        if phase == "FEEDBACK":
            require(exposure <= PLAN["maximum_feedback_ms"], "camera alone exceeded feedback cap")

    with backend.observe_physics_steps(guard):
        with backend.sensor_capture_on_demand():
            backend.step(PLAN["settle_steps"])
        for stage in SKILLS:
            start = backend.total_physics_steps
            record = {"skill": stage, "start_step": start}
            actions.append(record)
            session = None
            if stage == "GRASP":
                take("PRE")
                result = arm.grasp("object", timeout_ms=PLAN["grasp_timeout_ms"])
            elif stage == "LIFT":
                current = backend.get_tcp_pose()
                vertical = Pose(x=current.x, y=current.y, z=max(0.16, current.z + 0.10))
                vertical_guard = VerticalClearancePath(
                    task_id=slot["id"],
                    step_id="LIFT",
                    skill="LIFT",
                    start_m=(current.x, current.y, current.z),
                    target_m=(vertical.x, vertical.y, vertical.z),
                    minimum_height_m=0.08,
                )

                def retain(measured_target):
                    nonlocal feedback
                    require(feedback < cap, "feedback can no longer be sampled after cutoff")
                    feedback += 1
                    take("FEEDBACK")
                    if feedback == cap:
                        raise ValueError(PLAN["halt_marker"])
                    return measured_target

                session = VisualServoSession(retain, vertical_clearance=vertical_guard)
                with arm.visual_servo(session):
                    result = arm.lift(vertical.z - current.z, resolved_target=vertical, **motion)
            else:
                session = VisualServoSession(lambda measured_target: measured_target)
                with arm.visual_servo(session):
                    if stage == "MOVE_ABOVE":
                        result = arm.move_above("object", resolved_target=high_target, **motion)
                    else:
                        result = arm.approach("object", resolved_target=target, **motion)
            now = backend.total_physics_steps
            record.update(
                return_step=now,
                end_step=now,
                success=result.success,
                error=result.error_code,
                details=legacy.plain(result.details),
            )
            if session:
                record.update(
                    feedback_and_ik_ms=[
                        1000 * r["sample_and_ik_s"]
                        for r in session.records
                        if r.get("sample_and_ik_s") is not None
                    ],
                    native_session_terminal=session.terminal_reason,
                )
            if stage == "LIFT":
                controlled = feedback == cap
                if controlled:
                    require(
                        not result.success
                        and result.error_code == "VISUAL_SERVO_REJECTED"
                        and result.details.get("reason") == PLAN["halt_marker"],
                        "native call chain did not close at the registered cutoff",
                    )
                return "registered_feedback_cutoff" if controlled else "native_lift_return"
            if not result.success:
                return "native_prefix_stop"
            previous = record
            if stage == "GRASP":
                take("POST")
    raise PhysicalLimit("native route returned without a recorded terminal condition")


def persist(folder, frames, truth, commands, resets, receipt, timeline):
    index = []
    require(len(frames) == len(truth), "frame and independent label lengths differ")
    for number, (frame, robot) in enumerate(frames):
        name = f"{number:04}.json.gz"
        path = folder / name
        with path.open("xb") as file:
            file.write(gzip.compress(frame.model_dump_json().encode(), compresslevel=2, mtime=0))
        stage, phase = robot["skill"], robot["phase"]
        index.append(
            {"file": name, "file_sha256": sha(path), "robot": robot, "skill": stage, "phase": phase}
        )
    write(
        folder / "rgbd-index.json",
        {"scene_id": receipt["scene_id"], "episode_id": receipt.get("episode_id"), "rows": index},
    )
    write(
        folder / "offline-physics.json", {"frame_labels": truth, "unexpected_step_events": timeline}
    )
    write(folder / "native-resets.json", resets)
    write(folder / "native-commands.json", commands)
    receipt["index_sha256"] = sha(folder / "rgbd-index.json")
    write(folder / "sensor-receipt.json", receipt)


def acquire_case(slot, model, aim, reset_defaults, calibration, reg_sha, native_camera, legacy):
    from OpenGL import GL

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    folder = OUT / slot["id"]
    folder.mkdir(exist_ok=False)
    scene = "g1.continuous-payload/" + slot["id"]
    backend = MuJoCoPhysicsBackend()
    resets, events, frames, labels, actions, timeline = [], [], [], [], [], []
    receipt = {
        "id": slot["id"],
        "scene_id": scene,
        "slot": slot,
        "actions": actions,
        "aim_offset_m": aim,
        "registration_sha256": reg_sha,
        "new_exposure_scope": "prefix",
    }
    counted = native_camera._capture

    def capture_call(camera, data, *args, **kwargs):
        require(
            len(events) < PLAN["max_lift_feedback_per_case"] + PLAN["unlogged_pixel_caps_per_case"],
            "hard camera exposure ceiling",
        )
        events.append({"step": backend.total_physics_steps, "time_s": float(data.time)})
        return counted(camera, data, *args, **kwargs)

    def reset_event(event):
        if event.kind == "RESET":
            resets.append(legacy.plain(event))

    reason = None
    try:
        with patch.object(native_camera, "_capture", capture_call):
            backend.initialize(
                SimulatorConfig(
                    model_path=str(model),
                    seed=slot["physics_seed"],
                    physics_dt_s=PLAN["physics_dt_s"],
                    render_rgb=True,
                    render_depth=True,
                    camera_width=320,
                    camera_height=240,
                    domain_randomization=False,
                )
            )
            kwargs = dict(reset_defaults, scenario_id=scene, seed=slot["physics_seed"])
            kwargs["object_pose"] = Pose(
                **dict(zip(("x", "y", "z"), slot["center_m"], strict=True))
            )
            kwargs["target_region_pose"] = Pose(**kwargs["target_region_pose"])
            with backend.observe_operation_boundaries(reset_event):
                backend.reset(PhysicalScenarioConfig(**kwargs))
            receipt["episode_id"] = backend._episode_id
            require(
                len(resets) == 2
                and resets[-1]["phase"] == "END"
                and resets[-1]["episode_id"] == receipt["episode_id"]
                and resets[-1].get("error") is None
                and backend.total_physics_steps == 0,
                "original reset did not bind the independent scenario",
            )
            state = backend.current_physics_observation()
            require(
                list(state.object_geom_position_m) == slot["center_m"],
                "native reset readback does not match registered workpiece center",
            )
            actual = {
                key: GL.glGetString(value).decode()
                for key, value in (
                    ("version", GL.GL_VERSION),
                    ("vendor", GL.GL_VENDOR),
                    ("renderer", GL.GL_RENDERER),
                )
            }
            require(actual == calibration["renderer"], "unregistered EGL renderer")
            receipt["renderer"] = actual
            backend._rng = legacy.np.random.default_rng(slot["depth_seed"])
            receipt["termination"] = scoped_capture(
                backend,
                MuJoCoSkillRobot(backend),
                slot,
                aim,
                frames,
                labels,
                actions,
                timeline,
                legacy,
            )
            require(
                all(
                    frame.model_dump(mode="json", include=set(calibration["primary_camera"]))
                    == calibration["primary_camera"]
                    for frame, _ in frames
                ),
                "original camera calibration differed",
            )
            require(
                len(events) - sum(packet["phase"] == "FEEDBACK" for _, packet in frames)
                <= PLAN["unlogged_pixel_caps_per_case"],
                "implicit camera overhead exceeds cap",
            )
            backend.emergency_stop()
            receipt["native_emergency_stop"] = backend.estop_engaged
            require(receipt["native_emergency_stop"], "native emergency stop did not engage")
    except BaseException as error:
        reason = error
        receipt["termination"] = "batch_interrupted"
        receipt["failure"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        if backend._data is not None and not backend.estop_engaged:
            backend.emergency_stop()
    finally:
        receipt.update(physics_steps=backend.total_physics_steps, camera_calls=events)
        try:
            persist(folder, frames, labels, backend.command_records, resets, receipt, timeline)
        finally:
            backend.shutdown()
    if reason:
        raise reason
    return receipt


def run():
    model, aim, defaults, calibration, manifest = preflight()
    native_camera = audit_inputs()
    require(OUT.resolve() == OUT and not OUT.exists(), "registered attempt is already used")
    sys.path.insert(0, str(LEGACY))
    legacy = importlib.import_module("capture_native_payload")
    import cv2

    cv2.setNumThreads(1)
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(parents=True, exist_ok=False)
        registration = OUT / "registration.json"
        write(
            registration,
            {
                "plan_sha256": sha(HERE / "plan.json"),
                "driver_sha256": sha(Path(__file__)),
                "model_sha256": sha(model),
                "aim_offset_m": aim,
                "runtime": PLAN["runtime"],
                "runtime_files": manifest["runtime_files_sha256"],
                "cases": PLAN["cases"],
                "camera": calibration["primary_camera"],
            },
        )
        token = sha(registration)
        summaries = []
        try:
            for slot in PLAN["cases"]:
                receipt = acquire_case(
                    slot, model, aim, defaults, calibration, token, native_camera, legacy
                )
                summaries.append(slot["id"])
                print(slot["id"], receipt["termination"], receipt["physics_steps"], flush=True)
        finally:
            paths = sorted(p for p in OUT.rglob("*") if p.is_file())
            write(
                OUT / "capture-seal.json",
                {
                    "registration_sha256": token,
                    "complete_slots": summaries,
                    "all_slots_terminated_as_registered": len(summaries) == PLAN["max_attempts"],
                    "sealed_sha256": {p.relative_to(OUT).as_posix(): sha(p) for p in paths},
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture"))
    args = parser.parse_args()
    if args.mode == "preflight":
        model, aim, _, _, _ = preflight()
        print("Original asset, hashes and six distinct planned resets verified:", sha(model), aim)
    else:
        run()
