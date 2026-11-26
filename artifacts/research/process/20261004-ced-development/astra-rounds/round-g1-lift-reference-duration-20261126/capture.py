"""Run two registered slower native LIFT attempts behind the original optical gate."""

import argparse
import fcntl
import hashlib
import inspect
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from preflight import (
    HERE,
    PLAN,
    PLAN_PATH,
    ROOT,
    SlowerReference,
    check_cpu,
    original_slot,
    require,
)
from scripts.graduation.perception_io import read, sha, write

OUT = ROOT / PLAN["raw_root"] / "capture-01"
CPU = OUT.parent / "preflight.json"
PREVIOUS = HERE.parent / "round-g1-lift-native-full-clearance-20261126"
REJECT = "original_current_clearance_refused"
DEADLINE = "native_shutter_to_control_deadline"
COMPLETE = "native_lift_with_hold_and_post"
READY = {"FEEDBACK", "HOLD_ENTRY", "HOLD"}


class Stop(ValueError):
    """Terminal refusal preceding the next drive command or integration."""


class Boundary:
    def __init__(self, session, max_ms):
        self.session, self.max_ms = session, max_ms
        self.pending = None
        self.last = None

    def arm(self, row):
        require(self.pending is None and row["status"] == "CLEAR", "invalid motion gate")
        self.pending = row

    def check(self, what):
        row = self.pending
        if row is None:
            return
        now = time.perf_counter_ns()
        row.update(
            after_gate_boundary=what,
            boundary_ns=now,
            before_boundary_ms=(now - row["capture_begin_ns"]) / 1e6,
        )
        native = None
        if row["phase"] != "HOLD_ENTRY":
            require(len(self.session.records) > 0, "missing native servo receipt")
            native = self.session.records[-1]
            require(
                native["physics_step"] == row["step"]
                and (native.get("phase") == "HOLD") == (row["phase"] == "HOLD"),
                "wrong servo sample consumed by boundary",
            )
        row["native_sample_ms"] = None if native is None else native["sample_and_ik_s"] * 1000
        if max(row["before_boundary_ms"], row["native_sample_ms"] or 0) > self.max_ms:
            raise Stop(DEADLINE)
        row["released_to_boundary"] = True
        self.pending, self.last = None, row


def motion_contract():
    from cloud_edge_robot_arm.simulation.mujoco import visual_servo
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    hold = inspect.getsource(visual_servo.MuJoCoVisualServoController.monitor_hold)
    lift = inspect.getsource(MuJoCoSkillRobot.lift)
    require(
        hold.index("measured = session.sample(target)")
        < hold.index("latency > session.config.max_sample_latency_s")
        < hold.index("session.records.append(")
        and lift.index("action = self._move(")
        < lift.index("hold_start = self._backend.total_physics_steps")
        < lift.index("self._backend.step(steps=1)")
        < lift.index("monitor_hold(")
        and visual_servo.CartesianMotionReference is SlowerReference.__base__
        and visual_servo.VisualServoConfig().vision_period_s == 1 / 30,
        "native motion to holding contract changed",
    )

    no_sample = Boundary(SimpleNamespace(records=[]), 100)
    rejected = {
        "phase": "FEEDBACK",
        "status": "UNKNOWN",
        "capture_begin_ns": time.perf_counter_ns(),
    }
    try:
        no_sample.arm(rejected)
    except ValueError:
        require(no_sample.pending is None, "refusal leaked into boundary")
    else:
        raise ValueError("unsafe negative control")
    old = dict(rejected, phase="HOLD_ENTRY", status="CLEAR", capture_begin_ns=0)
    no_sample.arm(old)
    try:
        no_sample.check("PHYSICS")
    except Stop as error:
        require(str(error) == DEADLINE and "released_to_boundary" not in old, "late gate leaked")
    else:
        raise ValueError("clock negative control")
    valid = Boundary(
        SimpleNamespace(records=[{"phase": "HOLD", "physics_step": 8, "sample_and_ik_s": 0}]),
        100,
    )
    held = dict(
        rejected, phase="HOLD", status="CLEAR", step=8, capture_begin_ns=time.perf_counter_ns()
    )
    valid.arm(held)
    valid.check("LIFT_RETURN")
    require(
        valid.last is held and valid.pending is None and held["released_to_boundary"],
        "terminal HOLD positive control",
    )


def compare_live_entry(packet, original, target, registration):
    keys = (
        "physics_step",
        "sim_time_s",
        "joint_positions_rad",
        "joint_velocities_rad_s",
        "finger_positions_m",
        "finger_velocities_m_s",
        "tcp_position_m",
        "tcp_quaternion_wxyz",
        "camera_joint_positions_rad",
        "camera_finger_positions_m",
        "native_last_command_seq",
    )
    h = {"entry_frame_id", "entry_checksum_sha256"}
    require(
        all(packet[k] == original[k] for k in keys)
        and {k: v for k, v in packet["handoff"].items() if k not in h}
        == {k: v for k, v in original["handoff"].items() if k not in h}
        and target == registration,
        "new route prefix differs from the original at LIFT/PRE",
    )


def driver(prior, legacy, marker_detect, originals):
    from scripts.graduation.g1_complete_cv_clearance import LocalClearance
    from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
    from scripts.graduation.g1_complete_worker import ClearanceEpisode

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco import visual_servo
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

    template = read(prior.T02 / "allocation.json")
    calibration_dir = prior.CV / "calibration-gpu-01"
    asset = prior.RUNTIME / template["geometry"]["asset_path"]
    limits = PLAN["maximum"]
    knobs = PLAN["command"]
    motion = dict(
        tcp_velocity=knobs["tcp_velocity_m_s"],
        acceleration=knobs["acceleration_m_s2"],
        timeout_ms=knobs["timeout_ms"],
    )

    def run_case(backend, arm, slot, aim, frames, labels, actions, timeline, _legacy):
        allocation = dict(
            template,
            runtime_build_sha256=prior.PLAN["optical_generation"],
            case=dict(template["case"], scene_id=backend._scenario.scenario_id),
        )
        optical = bind_allocation(
            json.dumps(allocation, sort_keys=True).encode(),
            allocation_sha256=hashlib.sha256(
                json.dumps(allocation, sort_keys=True).encode()
            ).hexdigest(),
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
        rows, references = [], []
        stage, previous = "SETTLE", None
        hold_start = None
        start_gate, original_entry = originals[slot["id"]][0]
        target = Pose(
            **dict(
                zip(
                    "xyz",
                    (x + a for x, a in zip(slot["center_m"], aim, strict=True)),
                    strict=True,
                )
            )
        )
        high = Pose(x=target.x, y=target.y, z=max(0.16, target.z + 0.1))

        def monitor(observation):
            contacts = [legacy.plain(c) for c in backend.get_contacts() if c.illegal]
            if contacts:
                timeline.append(
                    {"step": observation.physics_step, "stage": stage, "illegal": contacts}
                )
                raise prior.PhysicalLimit("native forbidden contact")
            require(
                observation.physics_step < limits["exclusive_total_ticks_per_slot"],
                "native total physics budget exhausted",
            )

        def gate(phase, goal):
            gripper = next(
                (
                    r
                    for r in reversed(backend.command_records)
                    if r["type"] == "gripper" and r["accepted"]
                ),
                {},
            )
            started = time.perf_counter_ns()
            image = legacy.append_frame(
                {
                    "skill": stage,
                    "phase": phase,
                    "dwell_tick": None
                    if hold_start is None
                    else backend.total_physics_steps - hold_start,
                    "previous_native_successful_skill": previous["skill"] if previous else None,
                    "previous_native_return_step": previous["end_step"] if previous else None,
                    "previous_native_terminal_step": previous["end_step"] if previous else None,
                    "last_accepted_gripper_open": gripper.get("target_open"),
                    "last_accepted_gripper_command_step": gripper.get("physics_step"),
                },
                backend,
                backend.capture_sensor_frame(),
                frames,
                labels,
            )
            robot = frames[-1][1]
            require(
                robot["camera_encoder_sim_time_s"] == robot["sim_time_s"] == backend.get_sim_time(),
                "native and original camera clock differ",
            )
            marker = marker_detect(image, allocation["geometry"])
            if phase == "POST":
                result = cert.observe_payload_frame(image, marker, robot, stage, phase)
            else:
                robot["handoff"] = ClearanceEpisode.command_handoff(
                    owner, stage, phase, robot, image
                )
                result = cert.check(image, marker, robot, stage, goal, _DOWNWARD, phase=phase)
            row = {
                "frame_id": image.frame_id,
                "checksum_sha256": image.checksum_sha256,
                "phase": phase,
                "skill": stage,
                "step": robot["physics_step"],
                "capture_begin_ns": started,
                "gate_finish_ns": time.perf_counter_ns(),
                "tcp_position_m": robot["tcp_position_m"],
                "native_last_command_seq": robot["native_last_command_seq"],
                "status": result.get("status"),
                "reason": result.get("reason"),
                "current": legacy.plain(result),
            }
            rows.append(row)
            if phase != "POST" and row["status"] != "CLEAR":
                require(
                    row["status"] in {"UNKNOWN", "BLOCKED"}
                    and row["reason"]
                    not in {
                        "missing_native_stage_handoff",
                        "missing_active_payload_drive",
                        "wrong_prior_native_stage",
                        "stage_entry_source_or_drive_changed",
                        "unbound_stage_clock_or_command",
                    },
                    "live clearance contract failed",
                )
                raise Stop(REJECT)
            return row

        def lift_to(goal, start):
            nonlocal hold_start
            path = VerticalClearancePath(
                task_id=slot["id"],
                step_id="LIFT",
                skill="LIFT",
                minimum_height_m=0.08,
                start_m=tuple(getattr(start, k) for k in "xyz"),
                target_m=tuple(getattr(goal, k) for k in "xyz"),
            )
            entry_step = backend.total_physics_steps
            samples = 0

            def sample(t):
                nonlocal samples
                require(samples < limits["feedback_per_slot"], "registered feedback exhausted")
                samples += 1
                boundary.arm(gate("FEEDBACK" if hold_start is None else "HOLD", t.position))
                return t

            session = visual_servo.VisualServoSession(sample, vertical_clearance=path)
            boundary = Boundary(session, knobs["maximum_feedback_ms"])
            command, step, move = backend.apply_joint_targets, backend.step, arm._move

            class RegisteredReference(SlowerReference):
                def __init__(self, backend, start_m, target_m, orientation, **params):
                    require(not references, "more than one candidate reference")
                    reference = {
                        "duration_s": self.duration_s,
                        "settle_s": self.settle_s,
                        "step": backend.total_physics_steps,
                        "start_m": list(start_m),
                        "target_m": list(target_m),
                        "orientation_wxyz": orientation.tolist(),
                        "parameters": params,
                        "constructed": False,
                    }
                    references.append(reference)
                    require(
                        reference["step"] == entry_step
                        and params["control_steps"] == knobs["control_ticks"]
                        and params["timeout_s"] == knobs["timeout_ms"] / 1000
                        and params["max_velocity"] == motion["tcp_velocity"] / 0.3
                        and params["max_acceleration"] == motion["acceleration"] / 0.3
                        and params["initialize_load_from_feedback"] is False,
                        "actual reference parameter changed",
                    )
                    super().__init__(backend, start_m, target_m, orientation, **params)
                    reference["constructed"] = True
                    reference["peak_joint_velocity_rad_s"] = float(abs(self.velocities).max())

            def next_command(*args, **kwargs):
                require(hold_start is None, "unexpected target during the native hold")
                boundary.check("COMMAND")
                return command(*args, **kwargs)

            def next_tick(*args, **kwargs):
                boundary.check("PHYSICS")
                tick = backend.total_physics_steps
                ceiling = (
                    entry_step + limits["move_ticks_per_slot"]
                    if hold_start is None
                    else hold_start + limits["dwell_ticks_per_slot"]
                )
                require(
                    (args == (1,) and not kwargs or not args and kwargs == {"steps": 1})
                    and tick < ceiling
                    and boundary.last is not None
                    and tick - boundary.last["step"] < knobs["feedback_ticks"],
                    "no recent authorized gate before integration",
                )
                if (
                    tick == hold_start
                    and (time.perf_counter_ns() - boundary.last["capture_begin_ns"]) / 1e6
                    > knobs["maximum_feedback_ms"]
                ):
                    raise Stop(DEADLINE)
                return step(*args, **kwargs)

            def movement_return(*args, **kwargs):
                nonlocal hold_start
                result = move(*args, **kwargs)
                if result.success:
                    hold_start = backend.total_physics_steps
                    boundary.check("MOVEMENT_RETURN")
                    require(
                        boundary.last is not None
                        and hold_start - boundary.last["step"] < knobs["feedback_ticks"],
                        "movement-to-hold gate coverage gap",
                    )
                    if boundary.last["step"] != hold_start:
                        boundary.arm(gate("HOLD_ENTRY", goal))
                return result

            original_class = visual_servo.CartesianMotionReference
            try:
                with (
                    patch.object(backend, "apply_joint_targets", next_command),
                    patch.object(backend, "step", next_tick),
                    patch.object(arm, "_move", movement_return),
                    patch.object(visual_servo, "CartesianMotionReference", RegisteredReference),
                    arm.visual_servo(session),
                ):
                    result = arm.lift(goal.z - start.z, resolved_target=goal, **motion)
                    if result.success:
                        boundary.check("LIFT_RETURN")
                        require(
                            hold_start is not None
                            and backend.total_physics_steps - hold_start
                            == limits["dwell_ticks_per_slot"]
                            and boundary.last["step"] == backend.total_physics_steps
                            and boundary.last["phase"] == "HOLD",
                            "native dwell or terminal HOLD is incomplete",
                        )
                    return result
            finally:
                require(visual_servo.CartesianMotionReference is original_class, "reference leaked")

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
                            gate("PRE", target)
                            record["controller_called"] = True
                            result = arm.grasp("object", timeout_ms=prior.PLAN["grasp_timeout_ms"])
                        elif stage == "LIFT":
                            start = backend.get_tcp_pose()
                            goal = Pose(x=start.x, y=start.y, z=max(0.16, start.z + 0.1))
                            sample = gate("PRE", goal)
                            compare_live_entry(
                                frames[-1][1],
                                original_entry,
                                sample["current"]["commanded_target_xyz_m"],
                                start_gate["current"]["commanded_target_xyz_m"],
                            )
                            record["controller_called"] = True
                            result = lift_to(goal, start)
                        else:
                            record["controller_called"] = True
                            with arm.visual_servo(
                                visual_servo.VisualServoSession(lambda value: value)
                            ):
                                result = (
                                    arm.move_above("object", resolved_target=high, **motion)
                                    if stage == "MOVE_ABOVE"
                                    else arm.approach("object", resolved_target=target, **motion)
                                )
                    except Stop as failure:
                        record.update(
                            status="STOPPED",
                            reason=str(failure),
                            end_step=backend.total_physics_steps,
                        )
                        return str(failure)
                    record.update(
                        status="PASS" if result.success else "STOPPED",
                        end_step=backend.total_physics_steps,
                        success=result.success,
                        error=result.error_code,
                        details=legacy.plain(result.details),
                    )
                    if not result.success:
                        reason = result.details.get("reason")
                        return reason if reason in {REJECT, DEADLINE} else "native_controller_stop"
                    previous = record
                    if stage == "GRASP":
                        gate("POST", None)
                    if stage == "LIFT":
                        evidence = gate("POST", None)
                        record["hold_start_step"] = hold_start
                        return (
                            COMPLETE
                            if evidence["current"].get("relation") == "held"
                            else "post_unqualified"
                        )
            raise prior.PhysicalLimit("route finished without a terminal result")
        finally:
            for row in rows:
                if row["phase"] in READY:
                    row.setdefault("released_to_boundary", False)
            write(folder / "clearance-gate.json", {"checks": rows, "references": references})
            cert.close()

    return run_case


def setup():
    sys.path.insert(0, str(PREVIOUS))
    import gate_lift

    prior = gate_lift.prior
    params = dict(
        gate_lift.PLAN,
        head=PLAN["baseline"],
        slots=[s["id"] for s in PLAN["slots"]],
        max_slots=PLAN["maximum"]["attempts"],
    )
    with patch.object(gate_lift, "PLAN", params):
        model, aim, reset, cal, _, slots = gate_lift.prepare()
        gate_lift.confirm_native_deadline_order()
    camera = prior.audit_inputs()
    motion_contract()
    cpu = check_cpu()
    require(read(CPU) == cpu, "zero-integration preflight differs")
    reg = read(ROOT / PLAN["original_capture"] / "registration.json")
    originals = {s["id"]: original_slot(s, reg) for s in PLAN["slots"]}
    sys.path.insert(0, str(prior.LEGACY))
    import capture_native_payload as legacy
    import cv2
    from read_pose_coverage import native_marker

    marker, marker_sha = native_marker(prior.PLAN["optical_generation"])
    require(
        marker_sha == "9e216e93e17f52c0a20619b789d0e05f1382cd22385be96811084d7d8331f3ed",
        "original optical detector differs",
    )
    cv2.setNumThreads(1)
    return prior, legacy, marker, model, aim, reset, cal, slots, camera, originals


def capture():
    from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
    from scripts.graduation.g1_complete_cv_clearance import RobotDepthReference

    prior, legacy, marker, model, aim, reset, cal, slots, camera, originals = setup()
    limit = PLAN["maximum"]
    budgets = dict(
        prior.PLAN,
        max_lift_feedback_per_case=limit["feedback_per_slot"] - 16,
        unlogged_pixel_caps_per_case=limit["camera_overhead_per_slot"] + 16,
    )
    settings = driver(prior, legacy, marker, originals)
    with prior.LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(exist_ok=False)
        registration = OUT / "registration.json"
        write(
            registration,
            {
                "plan_sha256": sha(PLAN_PATH),
                "driver_sha256": sha(Path(__file__)),
                "preflight_sha256": sha(CPU),
                "camera": cal["primary_camera"],
                "asset_sha256": sha(model),
                "slots": slots,
                "runtime": prior.PLAN["runtime"],
                "aim_offset_m": aim,
                "reference_duration_s": PLAN["reference_seconds"]["variant"],
            },
        )
        calls = []
        old_robot, old_carried = RobotDepthReference.project, CarriedSurface.project

        def robot_ref(obj, *args):
            calls.append("robot")
            return old_robot(obj, *args)

        def carried_ref(obj, *args):
            calls.append("carried")
            return old_carried(obj, *args)

        completed = []
        try:
            with (
                patch.object(prior, "OUT", OUT),
                patch.object(prior, "PLAN", budgets),
                patch.object(prior, "scoped_capture", settings),
                patch.object(RobotDepthReference, "project", robot_ref),
                patch.object(CarriedSurface, "project", carried_ref),
            ):
                for slot in slots:
                    calls.clear()
                    try:
                        receipt = prior.acquire_case(
                            slot, model, aim, reset, cal, sha(registration), camera, legacy
                        )
                    finally:
                        write(OUT / slot["id"] / "reference-projections.json", {"passes": calls})
                    completed.append(slot["id"])
                    print(slot["id"], receipt["termination"], receipt["physics_steps"], flush=True)
        finally:
            files = sorted(p for p in OUT.rglob("*") if p.is_file())
            write(
                OUT / "seal.json",
                {
                    "cases": completed,
                    "registration_sha256": sha(registration),
                    "sealed_sha256": {p.relative_to(OUT).as_posix(): sha(p) for p in files},
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture"))
    args = parser.parse_args()
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "EGL must be chosen before imports",
    )
    if args.mode == "preflight":
        setup()
        print("frozen sources, archive, original controllers and native boundary controls verified")
    else:
        capture()
