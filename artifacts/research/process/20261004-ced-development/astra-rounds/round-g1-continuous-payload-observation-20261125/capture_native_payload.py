"""Capture due RGB-D in one continuous original-controller diagnostic trajectory."""

import argparse
import fcntl
import gzip
import importlib.util
import math
import time
import traceback
from functools import partial
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation.g1_complete_cv_clearance import camera_encoder_pose
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
REG = HERE / "continuous-diagnostic-registration.json"
REG_SHA = "7d0a9f809d958b5c413fd91fc85116c2448b58c1c46067adeaef0ad38293f711"
SOURCE = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
RAW = ROOT / "experiments/results/g1-continuous-payload-observation-20261125"
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
STAGES = (
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
)


def plain(value):
    from scripts.graduation.dynamic_vision import plain as native_plain

    return native_plain(value)


def append_frame(row, native, camera_frame, packets, physics):
    frame = observation_from_sensor_frame(
        camera_frame, source="mujoco_camera", png_compress_level=1
    )
    model, data = native._model, native._data
    step = native.total_physics_steps
    tcp = native.get_tcp_pose()
    qr = np.empty(4)
    mujoco.mju_mat2Quat(qr, data.site("tcp").xmat)
    joint = native.get_joint_state()
    packet = dict(
        row,
        physics_step=step,
        sim_time_s=frame.sim_time_s,
        frame_id=frame.frame_id,
        checksum_sha256=frame.checksum_sha256,
        native_last_command_seq=native.next_command_sequence - 1,
        joint_positions_rad=list(joint.positions),
        joint_velocities_rad_s=list(joint.velocities),
        finger_positions_m=data.qpos[7:9].tolist(),
        finger_velocities_m_s=data.qvel[7:9].tolist(),
        tcp_position_m=[tcp.x, tcp.y, tcp.z],
        tcp_quaternion_wxyz=qr.tolist(),
        **camera_encoder_pose(model, data),
    )
    contacts = [sorted((model.geom(x.geom1).name, model.geom(x.geom2).name)) for x in data.contact]
    p = data.geom("object_geom")
    physics.append(
        dict(
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=step,
            center_m=p.xpos.tolist(),
            rotation=p.xmat.reshape(3, 3).tolist(),
            touching=contacts,
        )
    )
    packets.append((frame, packet))
    return frame


def shadow_route(backend, arm, aim, report, frames, frame_labels):
    previous = None
    stage_actions = report["actions"]
    outcome = dict()
    low = Pose(x=aim[0], y=aim[1], z=aim[2])
    high = max(0.16, low.z + 0.1)
    region_high = Pose(x=0.2, y=0.25, z=high)
    region_low = Pose(x=0.2, y=0.25, z=low.z + 0.004)
    motion = dict(tcp_velocity=0.15, acceleration=0.5, timeout_ms=8000)
    dense = []

    def observe(physics):
        assert physics.physics_step < 16000, "original total physical budget"
        x = backend._data.geom("object_geom")
        object_bottom = float(x.xpos[2] - 0.035 * abs(x.xmat.reshape(3, 3)[2]).sum())
        contacts = backend.get_contacts()
        pair = {frozenset((c.geom1, c.geom2)) for c in contacts}
        bilateral = all(
            frozenset((f, "object_geom")) in pair for f in ("left_finger_geom", "right_finger_geom")
        )
        dense.append(
            [physics.physics_step, object_bottom, bilateral, any(c.illegal for c in contacts)]
        )

    def take(role, n=None):
        end = previous or {}
        last = next(
            (
                x
                for x in reversed(backend._command_records)
                if x["type"] == "gripper" and x["accepted"]
            ),
            {},
        )
        return append_frame(
            dict(
                skill=stage,
                phase=role,
                dwell_tick=n,
                previous_native_successful_skill=end.get("skill"),
                previous_native_return_step=end.get("return_step"),
                previous_native_terminal_step=end.get("end_step"),
                last_accepted_gripper_open=last.get("target_open"),
                last_accepted_gripper_command_step=last.get("physics_step"),
            ),
            backend,
            backend.capture_sensor_frame(),
            frames,
            frame_labels,
        )

    with backend.observe_physics_steps(observe):
        with backend.sensor_capture_on_demand():
            backend.step(120)
        for stage in STAGES:
            start = backend.total_physics_steps
            if stage in STAGES[2:]:
                take("PRE")
            current = backend.get_tcp_pose()
            vertical = Pose(x=current.x, y=current.y, z=max(0.16, current.z + 0.10))
            calls = {
                "MOVE_ABOVE": lambda: arm.move_above(
                    "object", resolved_target=Pose(x=low.x, y=low.y, z=high), **motion
                ),
                "APPROACH": lambda: arm.approach("object", resolved_target=low, **motion),
                "GRASP": lambda: arm.grasp("object", timeout_ms=1000),
                "LIFT": partial(
                    arm.lift, vertical.z - current.z, resolved_target=vertical, **motion
                ),
                "MOVE_TO_REGION": lambda: arm.move_to_region(
                    "target_region", resolved_target=region_high, **motion
                ),
                "PLACE": lambda: arm.place("target_region", resolved_target=region_low, **motion),
                "RELEASE": lambda: arm.release(timeout_ms=1000),
                "RETREAT": partial(
                    arm.retreat, vertical.z - current.z, resolved_target=vertical, **motion
                ),
            }
            path = None
            if stage in {"LIFT", "RETREAT"}:
                path = VerticalClearancePath(
                    task_id=report["id"],
                    step_id=stage,
                    skill=stage,
                    start_m=(current.x, current.y, current.z),
                    target_m=(vertical.x, vertical.y, vertical.z),
                    minimum_height_m=0.08,
                )

            def feedback(target, monitored_stage=stage):
                if monitored_stage in STAGES[3:]:
                    take("FEEDBACK")
                return target

            session = None
            started = time.monotonic()
            if stage in {"GRASP", "RELEASE"}:
                result = calls[stage]()
            else:
                session = VisualServoSession(feedback, vertical_clearance=path)
                with arm.visual_servo(session):
                    result = calls[stage]()
            row = dict(
                skill=stage,
                start_step=start,
                return_step=backend.total_physics_steps,
                success=result.success,
                error=result.error_code,
                details=plain(result.details),
                controller_wall_s=time.monotonic() - started,
                native_capture_and_ik_ms=[
                    1000 * z["sample_and_ik_s"]
                    for z in session.records
                    if z.get("sample_and_ik_s") is not None
                ]
                if session
                else [],
            )
            stage_actions.append(row)
            if not result.success:
                break
            previous = row
            if stage in {"LIFT", "RELEASE"}:
                take("DWELL", 0)
                end = 120 if stage == "LIFT" else 240
                for tick in range(8, end + 1, 8):
                    backend.step(8)
                    take("DWELL", tick)
            if stage in STAGES[2:]:
                take("POST")
            row["end_step"] = backend.total_physics_steps
        outcome["physics"] = dense
        outcome["command_rows"] = backend.command_records
    return outcome


def capture(slot, runtime, registration, attempt_folder):
    label = slot["id"]
    path = RAW / attempt_folder / label
    path.mkdir(parents=True, exist_ok=False)
    source = read(SOURCE / "batches/train-full-04/cvfix-t02/allocation.json")
    model_path = runtime / source["geometry"]["asset_path"]
    assert sha(model_path) == registration["native_controller_asset_sha256"]
    rect = slot.get("physical_slab_height_m")
    model_xml = None
    if rect is not None:
        scene_xml = ET.parse(model_path)
        ET.SubElement(
            scene_xml.find("worldbody"),
            "geom",
            name="diagnostic_foreign_slab",
            type="box",
            pos=f"0.2 0.25 {rect / 2}",
            size=f".065 .065 {rect / 2}",
            rgba=".2 .5 .3 1",
        )
        model_xml = ET.tostring(scene_xml.getroot(), encoding="unicode")
        (path / "diagnostic-scene.xml").write_text(model_xml)

    backend = MuJoCoPhysicsBackend()
    resets, frames, labels = [], [], []

    def read_reset(event):
        if event.kind == "RESET":
            resets.append(plain(event))

    ctx = backend.observe_operation_boundaries(read_reset)
    group = next(key for key in ("fit", "holdout", "negative") if slot in registration[key])
    report = dict(
        id=label,
        role=group,
        registration_sha256=REG_SHA,
        actions=[],
        baseline_camera=source["geometry"]["camera"],
        asset_sha256=sha(model_path),
    )
    scene = f"g1.continuous-payload/{label}"
    try:
        backend.initialize(
            SimulatorConfig(
                model_path=str(model_path),
                seed=slot["physics_seed"],
                physics_dt_s=1 / 240,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
            ),
            model_xml=model_xml,
        )
        x, y, z = slot["center_m"]
        with ctx:
            backend.reset(
                PhysicalScenarioConfig(
                    scenario_id=scene,
                    seed=slot["physics_seed"],
                    object_pose=Pose(x=x, y=y, z=z),
                    object_mass_kg=float(backend._model.body("object").mass[0]),
                    object_yaw_rad=math.radians(slot["yaw_deg"]),
                    friction_coefficient=slot.get("cube_friction", 0.8),
                )
            )
        backend._rng = np.random.default_rng(slot["depth_seed"])
        report["renderer"] = GL.glGetString(GL.GL_RENDERER).decode()
        report["episode_id"] = backend._episode_id
        aim = np.array(slot["center_m"]) + np.array(slot["aim_offset_m"])
        outcome = shadow_route(backend, MuJoCoSkillRobot(backend), aim, report, frames, labels)
        index = []
        for number, (frame, robot) in enumerate(frames):
            name = f"{number:04}.json.gz"
            target = path / name
            with target.open("xb") as out:
                out.write(gzip.compress(frame.model_dump_json().encode(), 2, mtime=0))
            index.append(
                dict(
                    file=name,
                    file_sha256=sha(target),
                    skill=robot.pop("skill"),
                    phase=robot.pop("phase"),
                    dwell_tick=robot.pop("dwell_tick"),
                    robot=robot,
                )
            )
        write(
            path / "rgbd-index.json",
            dict(scene_id=scene, episode_id=report["episode_id"], rows=index),
        )
        write(path / "native-resets.json", resets)
        write(path / "native-commands.json", outcome["command_rows"])
        write(
            path / "sensor-receipt.json", report | dict(index_sha256=sha(path / "rgbd-index.json"))
        )
        write(path / "offline-physics.json", dict(frame_labels=labels, dense=outcome["physics"]))
        last = report["actions"][-1]
        print(label, len(index), last["skill"], last["success"], last["error"], flush=True)
    except Exception:
        write(
            path / "interrupted.json",
            dict(
                registration_sha256=REG_SHA,
                id=label,
                reset=resets,
                actions=report["actions"],
                physics_step=backend.total_physics_steps,
                stack=traceback.format_exc(),
            ),
        )
        raise
    finally:
        backend.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-folder",
        default="physical-03",
        choices=("physical-01", "physical-02", "physical-03"),
    )
    parser.add_argument("ids", nargs="+")
    args = parser.parse_args()
    registry = pinned(REG, REG_SHA)
    runtime = SOURCE / "builds" / registry["original_runtime"] / "runtime-source"
    lock = pinned(runtime / "runtime-build.json", registry["original_runtime"])
    for relative, cls in (
        ("simulation/mujoco/backend.py", MuJoCoPhysicsBackend),
        ("simulation/mujoco/skill_robot.py", MuJoCoSkillRobot),
        ("simulation/mujoco/visual_servo.py", VisualServoSession),
    ):
        part = "src/cloud_edge_robot_arm/" + relative
        imported = Path(importlib.util.find_spec(cls.__module__).origin)
        assert (
            imported.resolve() == (runtime / part).resolve()
            and sha(imported) == lock["runtime_files_sha256"][part]
        )
    slots = {
        q["id"]: q
        for group in ("fit", "holdout", "negative")
        for q in registry[group]
        if "center_m" in q
    }
    if any(n not in {k["id"] for k in registry["fit"]} for n in args.ids):
        freeze = read(HERE / "observer-freeze.public.json")
        for name, token in freeze["sources_sha256"].items():
            assert sha(ROOT / name) == token
    cv2.setNumThreads(1)
    with LOCK.open("rb") as hold:
        fcntl.flock(hold, fcntl.LOCK_EX)
        for key in args.ids:
            capture(slots[key], runtime, registry, args.attempt_folder)


if __name__ == "__main__":
    main()
