"""Run the unchanged local RGB-D clearance check at actual lift command boundaries."""

import argparse
import fcntl
import inspect
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.graduation.perception_io import read, sha, write

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "round-g1-lift-natural-native-20261126"
RELATION = HERE.parent / "round-g1-lift-native-original-relation-20261126"
sys.path.insert(0, str(PRIOR))
import collect_lift as prior  # noqa: E402

ROOT = prior.ROOT
OUT = ROOT / "experiments/results/g1-lift-native-full-clearance-20261126/capture-01"
PLAN = read(HERE / "plan.json")
LAST = "registered_80_frame_cutoff"
REJECT = "original_current_clearance_refused"
DEADLINE = "native_shutter_to_control_deadline"
RETURNED = "native_lift_movement_return_before_dwell"


class ScopedStop(ValueError):
    """Stop the fixture at a registered boundary before a new target or integration."""


def prepare():
    inputs = {"prior": PRIOR, "relation": RELATION, "capture": prior.OUT, "repo": ROOT}
    for name, expected in PLAN["sha256"].items():
        key, relative = name.split("/", 1)
        path = inputs[key] / relative
        prior.require(
            path.resolve().is_relative_to(ROOT) and sha(path) == expected,
            f"frozen input differs: {name}",
        )
    with patch.object(prior, "PLAN", dict(prior.PLAN, head=PLAN["head"])):
        model, aim, reset, cal, runtime = prior.preflight()
    registered = read(prior.OUT / "registration.json")
    prior.require(
        registered["aim_offset_m"] == aim and registered["camera"] == cal["primary_camera"],
        "original reference geometry differs",
    )
    slots = [slot for slot in registered["cases"] if slot["id"] in PLAN["slots"]]
    prior.require(
        [slot["id"] for slot in slots] == PLAN["slots"] and len(slots) == PLAN["max_slots"],
        "repeat registration changed",
    )
    return model, aim, reset, cal, runtime, slots


def archive_gap():
    audit = []
    for case in PLAN["slots"]:
        path = prior.OUT / case
        index = read(path / "rgbd-index.json")["rows"]
        commands = read(path / "native-commands.json")
        count = sum(r["skill"] == "LIFT" and r["phase"] == "FEEDBACK" for r in index)
        have = any("handoff" in r["robot"] for r in index)
        pre = any(r["skill"] == "LIFT" and r["phase"] == "PRE" for r in index)
        prior.require(not have and not pre, "archive gap premises changed")
        audit.append(
            {
                "case": case,
                "indexed_lift_feedback": count,
                "lift_pre_recorded": pre,
                "received_handoff": have,
                "command_records": len(commands),
                "required_applied_ctrl_present": False,
                "conclusion": "full_clearance_unverifiable",
            }
        )
    return {
        "cases": audit,
        "source_fields": {
            "recorded": [
                "shutter_encoders",
                "command_goals",
                "accepted_sequences",
                "previous_return",
            ],
            "absent": [
                "lift_PRE_frame",
                "handoff_entry_active_arm_and_finger_ctrl",
                "handoff_entry_native_velocity",
                "current_applied_arm_and_finger_ctrl",
            ],
            "reason": "data.ctrl uses the target, preceding state, and bias feedforward",
        },
    }


def driver(marker_detect, legacy):
    from scripts.graduation.g1_complete_cv_clearance import LocalClearance
    from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
    from scripts.graduation.g1_complete_worker import ClearanceEpisode

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

    template = read(prior.T02 / "allocation.json")
    calibration_dir = prior.CV / "calibration-gpu-01"
    asset = prior.RUNTIME / template["geometry"]["asset_path"]
    from hashlib import sha256

    def run_case(backend, arm, slot, aim, frames, labels, actions, timeline, _legacy):
        allocation = dict(
            template,
            runtime_build_sha256=source_generation(),
            case=dict(template["case"], scene_id=backend._scenario.scenario_id),
        )
        allocation_bytes = json.dumps(allocation, sort_keys=True).encode()
        optical = bind_allocation(
            allocation_bytes,
            allocation_sha256=sha256(allocation_bytes).hexdigest(),
            generation_sha256=allocation["runtime_build_sha256"],
            calibration_sha256=allocation["calibration_sha256"],
            asset_sha256=sha(asset),
            reset_scene_id=backend._scenario.scenario_id,
            reset_episode_id=backend._episode_id,
        )
        cert = LocalClearance(
            allocation["geometry"],
            asset,
            calibration_dir,
            calibration_sha256=allocation["calibration_sha256"],
            isolated_scene=True,
            optical_identity=optical,
        )
        owner = SimpleNamespace(backend=backend, report={"actions": actions}, entry_command=None)
        folder = OUT / slot["id"]
        write(folder / "optical-allocation.json", allocation)
        rows = []
        stage, previous = "SETTLE", None
        session, pending = None, None
        feedback = 0
        target = Pose(
            **dict(
                zip(
                    ("x", "y", "z"),
                    (x + a for x, a in zip(slot["center_m"], aim, strict=True)),
                    strict=True,
                )
            )
        )
        high = Pose(x=target.x, y=target.y, z=max(0.16, target.z + 0.1))
        motion = dict(
            tcp_velocity=prior.PLAN["tcp_velocity_m_s"],
            acceleration=prior.PLAN["tcp_acceleration_m_s2"],
            timeout_ms=prior.PLAN["motion_timeout_ms"],
        )

        def monitor(observation):
            contacts = [legacy.plain(c) for c in backend.get_contacts() if c.illegal]
            if contacts:
                timeline.append(
                    {"step": observation.physics_step, "stage": stage, "illegal": contacts}
                )
                raise prior.PhysicalLimit("native forbidden contact")
            prior.require(
                observation.physics_step < prior.PLAN["exclusive_physics_step_limit_per_case"],
                "native physics budget exhausted",
            )

        def inspect_now(phase, goal):
            last = next(
                (
                    row
                    for row in reversed(backend.command_records)
                    if row["type"] == "gripper" and row["accepted"]
                ),
                {},
            )
            started = time.perf_counter_ns()
            native = backend.capture_sensor_frame()
            image = legacy.append_frame(
                {
                    "skill": stage,
                    "phase": phase,
                    "dwell_tick": None,
                    "previous_native_successful_skill": previous["skill"] if previous else None,
                    "previous_native_return_step": previous["end_step"] if previous else None,
                    "previous_native_terminal_step": previous["end_step"] if previous else None,
                    "last_accepted_gripper_open": last.get("target_open"),
                    "last_accepted_gripper_command_step": last.get("physics_step"),
                },
                backend,
                native,
                frames,
                labels,
            )
            marker = marker_detect(image, allocation["geometry"])
            robot = frames[-1][1]
            prior.require(
                robot["camera_encoder_sim_time_s"] == robot["sim_time_s"] == backend.get_sim_time(),
                "current source clock differs",
            )
            if phase == "POST":
                summary = cert.observe_payload_frame(image, marker, robot, stage, phase)
            else:
                robot["handoff"] = ClearanceEpisode.command_handoff(
                    owner, stage, phase, robot, image
                )
                summary = cert.check(image, marker, robot, stage, goal, _DOWNWARD, phase=phase)
            record = {
                "frame_id": image.frame_id,
                "checksum_sha256": image.checksum_sha256,
                "phase": phase,
                "skill": stage,
                "step": robot["physics_step"],
                "capture_begin_ns": started,
                "gate_finish_ns": time.perf_counter_ns(),
                "native_last_command_seq": robot["native_last_command_seq"],
                "status": summary.get("status"),
                "reason": summary.get("reason"),
                "current": legacy.plain(summary),
            }
            rows.append(record)
            if phase != "POST" and summary["status"] != "CLEAR":
                prior.require(
                    summary["status"] in {"UNKNOWN", "BLOCKED"},
                    "unknown LocalClearance status enumeration",
                )
                if summary.get("reason") in {
                    "missing_native_stage_handoff",
                    "missing_active_payload_drive",
                    "wrong_prior_native_stage",
                    "stage_entry_source_or_drive_changed",
                    "unbound_stage_clock_or_command",
                }:
                    raise prior.PhysicalLimit("live handoff contract failed")
                raise ScopedStop(REJECT)
            return record

        def sample(t):
            nonlocal pending, feedback
            prior.require(
                pending is None and feedback < PLAN["max_lift_feedback_per_case"],
                "native feedback consumed without registered boundary",
            )
            feedback += 1
            pending = inspect_now("FEEDBACK", t.position)
            return t

        def check_boundary(kind):
            nonlocal pending
            if pending is None:
                return
            ts = time.perf_counter_ns()
            prior.require(
                len(session.records) == feedback
                and session.records[-1]["physics_step"] == pending["step"],
                "sample reached actuator without a completed native IK record",
            )
            pending.update(
                next_boundary=kind,
                next_boundary_ns=ts,
                sample_ik_ms=session.records[-1]["sample_and_ik_s"] * 1000,
                before_next_boundary_ms=(ts - pending["capture_begin_ns"]) / 1e6,
            )
            if (
                max(pending["before_next_boundary_ms"], pending["sample_ik_ms"])
                > PLAN["maximum_feedback_ms"]
            ):
                pending["released_to_boundary"] = False
                raise ScopedStop(DEADLINE)
            if feedback >= PLAN["max_lift_feedback_per_case"]:
                pending["released_to_boundary"] = False
                raise ScopedStop(LAST)
            pending["released_to_boundary"] = True
            pending = None

        def lift_to(goal, start):
            nonlocal session
            path = VerticalClearancePath(
                task_id=slot["id"],
                step_id="LIFT",
                skill="LIFT",
                start_m=(start.x, start.y, start.z),
                target_m=(goal.x, goal.y, goal.z),
                minimum_height_m=0.08,
            )
            session = VisualServoSession(sample, vertical_clearance=path)
            command, step, move = backend.apply_joint_targets, backend.step, arm._move

            def next_command(*args, **kwargs):
                check_boundary("COMMAND")
                return command(*args, **kwargs)

            def next_integration(*args, **kwargs):
                check_boundary("PHYSICS")
                return step(*args, **kwargs)

            def no_dwell(*args, **kwargs):
                result = move(*args, **kwargs)
                if result.success:
                    raise ScopedStop(RETURNED)
                return result

            with (
                patch.object(backend, "apply_joint_targets", next_command),
                patch.object(backend, "step", next_integration),
                patch.object(arm, "_move", no_dwell),
                arm.visual_servo(session),
            ):
                return arm.lift(goal.z - start.z, resolved_target=goal, **motion)

        try:
            with backend.observe_physics_steps(monitor):
                with backend.sensor_capture_on_demand():
                    backend.step(prior.PLAN["settle_steps"])
                for stage in prior.SKILLS:
                    record = {
                        "skill": stage,
                        "start_step": backend.total_physics_steps,
                        "controller_called": False,
                    }
                    actions.append(record)
                    try:
                        if stage == "GRASP":
                            inspect_now("PRE", target)
                            record["controller_called"] = True
                            result = arm.grasp("object", timeout_ms=prior.PLAN["grasp_timeout_ms"])
                        elif stage == "LIFT":
                            start = backend.get_tcp_pose()
                            goal = Pose(x=start.x, y=start.y, z=max(0.16, start.z + 0.1))
                            inspect_now("PRE", goal)
                            record["controller_called"] = True
                            result = lift_to(goal, start)
                        else:
                            record["controller_called"] = True
                            with arm.visual_servo(VisualServoSession(lambda value: value)):
                                result = (
                                    arm.move_above("object", resolved_target=high, **motion)
                                    if stage == "MOVE_ABOVE"
                                    else arm.approach("object", resolved_target=target, **motion)
                                )
                    except ScopedStop as stop:
                        record.update(
                            status="STOPPED", reason=str(stop), end_step=backend.total_physics_steps
                        )
                        return str(stop)
                    record.update(
                        status="PASS" if result.success else "STOPPED",
                        end_step=backend.total_physics_steps,
                        success=result.success,
                        error=result.error_code,
                        details=legacy.plain(result.details),
                    )
                    if not result.success:
                        reason = result.details.get("reason")
                        if reason in (LAST, REJECT, DEADLINE):
                            return reason
                        return "native_controller_stop"
                    previous = record
                    if stage == "GRASP":
                        inspect_now("POST", None)
            raise prior.PhysicalLimit("bounded route has no expected terminal condition")
        finally:
            if pending is not None:
                pending.setdefault("released_to_boundary", False)
            write(folder / "clearance-gate.json", {"checks": rows, "sample_count": feedback})
            cert.close()

    return run_case


def source_generation():
    return prior.PLAN["optical_generation"]


def confirm_native_deadline_order():
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import (
        MuJoCoVisualServoController,
        VisualServoConfig,
    )

    native = inspect.getsource(MuJoCoVisualServoController._move_tcp)
    sample = native.index("current = session.sample(current)")
    check = native.index("latency > session.config.max_sample_latency_s", sample)
    evidence = native.index("session.records.append(", check)
    submit = native.index("backend.apply_joint_targets(", evidence)
    next_physics = native.index("backend.step(", submit)
    prior.require(
        sample < check < evidence < submit < next_physics
        and VisualServoConfig().max_sample_latency_s * 1000 == PLAN["maximum_feedback_ms"],
        "native feedback deadline/command ordering changed",
    )


def capture():
    from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
    from scripts.graduation.g1_complete_cv_clearance import RobotDepthReference

    model, aim, reset, cal, _, slots = prepare()
    camera = prior.audit_inputs()
    confirm_native_deadline_order()
    sys.path.insert(0, str(prior.LEGACY))
    import capture_native_payload as legacy
    import cv2
    from read_pose_coverage import native_marker

    detector, marker_sha = native_marker(source_generation())
    prior.require(
        marker_sha == "9e216e93e17f52c0a20619b789d0e05f1382cd22385be96811084d7d8331f3ed",
        "original frozen marker differs",
    )
    cv2.setNumThreads(1)
    original_project, carried_project = RobotDepthReference.project, CarriedSurface.project
    projected = []
    prior.require(OUT.resolve() == OUT and not OUT.exists(), "registered attempt already used")
    with prior.LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(parents=True, exist_ok=False)
        write(OUT / "archive-handoff-gap.json", archive_gap())
        reg = OUT / "registration.json"
        write(
            reg,
            {
                "plan_sha256": sha(HERE / "plan.json"),
                "driver_sha256": sha(Path(__file__)),
                "asset_sha256": sha(model),
                "aim_offset_m": aim,
                "slots": slots,
                "camera": cal["primary_camera"],
                "runtime": prior.PLAN["runtime"],
            },
        )

        def project_reference(obj, *args):
            projected.append("robot")
            return original_project(obj, *args)

        def project_carried(obj, *args):
            projected.append("carried")
            return carried_project(obj, *args)

        cases = []
        try:
            with (
                patch.object(prior, "OUT", OUT),
                patch.object(prior, "scoped_capture", driver(detector, legacy)),
                patch.object(RobotDepthReference, "project", project_reference),
                patch.object(CarriedSurface, "project", project_carried),
            ):
                for case in slots:
                    projected.clear()
                    receipt = prior.acquire_case(
                        case, model, aim, reset, cal, sha(reg), camera, legacy
                    )
                    write(OUT / case["id"] / "reference-projections.json", {"passes": projected})
                    cases.append(case["id"])
                    print(case["id"], receipt["termination"], receipt["physics_steps"], flush=True)
        finally:
            files = sorted(p for p in OUT.rglob("*") if p.is_file())
            write(
                OUT / "seal.json",
                {
                    "cases": cases,
                    "registration_sha256": sha(reg),
                    "sealed_sha256": {p.relative_to(OUT).as_posix(): sha(p) for p in files},
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture"))
    cli = parser.parse_args()
    if cli.mode == "preflight":
        prepare()
        print(json.dumps(archive_gap(), ensure_ascii=False, indent=2))
    else:
        prior.require(
            os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
            "EGL must be selected before native imports",
        )
        capture()
