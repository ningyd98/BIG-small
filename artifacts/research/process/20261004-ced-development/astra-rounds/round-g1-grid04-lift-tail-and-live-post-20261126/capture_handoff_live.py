"""One isolated grid-04 RGB-D attempt through the native LIFT return and POST."""

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import qualify_tail as tail
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.mujoco import visual_servo
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "handoff-plan.json"
PLAN = read(PLAN_FILE)
CASE = "g1-lift-grid-04"
ISOLATED_ID = "grid04-isolated-lift-hold-entry-01"
OUT = tail.OUT / "isolated-rgbd-01"
LIMIT = PLAN["limits"]
RETURN = PLAN["handoff_tick"]
END = PLAN["last_hold_candidate"]
SOURCE = HERE.parent / "round-g1-lift-native-full-clearance-20261126/gate_lift.py"
REQUIRE = tail.require


class ScopedStop(ValueError):
    """Retain the first rejected boundary and let the original skill protect it."""


def clearance_is_accepted(status, clocks_match):
    return clocks_match and status == "CLEAR"


def feedback_is_timely(sample_ms, boundary_ms):
    return max(sample_ms, boundary_ms) <= 100


def preflight(*, expected_head=PLAN["execution_base"]):
    tail.checked_inputs()
    for name, expected in PLAN["input_sha256"].items():
        REQUIRE(sha(tail.ROOT / name) == expected, f"changed live input: {name}")
    sealed = [tail.OUT / f"handoff-prefilter-reader-{i}.json" for i in (1, 2)]
    for receipt in sealed:
        report = read(receipt)
        REQUIRE(
            report["plan_sha256"] == sha(PLAN_FILE)
            and report["reader_sha256"] == sha(HERE / "screen_handoff_domain.py")
            and report["egl_gate"] == "NECESSARY_DOMAIN_NOT_REFUTED",
            "frozen-domain screen does not allow the planned attempt",
        )
    REQUIRE(sha(sealed[0]) == sha(sealed[1]), "independent domain preflight disagrees")
    base = tail.earlier.module(SOURCE)
    with patch.object(base, "PLAN", dict(base.PLAN, head=expected_head)):
        model, aim, reset, cal, _, slots = base.prepare()
    (slot,) = [row for row in slots if row["id"] == CASE]
    refs = tail.earlier.module(tail.earlier.source("original/screen_braking.py"))
    refs.verify_inputs()
    history = {row["tick"]: row for row in read(tail.earlier.OUT / "native/normal.json")}
    data = tail.OUT / "native"
    tail_normal = {int(k): v for k, v in read(data / "motion.json").items()}
    REQUIRE(
        history[tail.END]["phase_sha256"] == tail_normal[tail.END]["phase_sha256"],
        "tail boundary changed",
    )
    history.update(tail_normal)
    hold = {int(k): v for k, v in read(data / "retained_hold.json").items()}
    original = read(tail.earlier.OUT / "native/result.json")
    ending = read(data / "result.json")
    entries = {row["delay"] for row in original["entry_checks"]}
    comparisons = {}
    for row in original["ordinary_windows"]:
        if row["trigger"] <= tail.END:
            for mode in row["modes"]:
                if tail.acceptable(mode):
                    comparisons.setdefault(
                        ("motion", row["anchor"], mode["mode"], mode["speed_class"]), set()
                    ).add(row["delay"])
    for row in ending["comparisons"]:
        if tail.acceptable(row):
            phase = "motion" if row["phase"] == "handoff_overlap" else row["phase"]
            comparisons.setdefault(
                (phase, row["anchor"], "generic", row["speed_class"]), set()
            ).add(row["delay"])
    moving = list(range(tail.ENTRY, ending["last_motion_feedback_tick"] + 1, tail.V))
    holding = [RETURN, *ending["hold_feedback_candidate_ticks"]]
    REQUIRE(
        entries == set(range(9)) and holding[-1] == END and len(holding) == 16,
        "closure registration differs",
    )
    REQUIRE(
        len(moving) == 158
        and len(moving) + len(holding) + 11 <= LIMIT["conditional_native_exposures"],
        "exposure plan differs",
    )
    return (
        base,
        model,
        aim,
        reset,
        cal,
        slot,
        sealed,
        refs,
        history,
        hold,
        original,
        comparisons,
        moving,
        holding,
    )


def scenario_driver(
    base, asset, detector, legacy, refs, history, hold, original, comparisons, moving, holding
):
    from scripts.graduation.g1_complete_cv_clearance import LocalClearance
    from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
    from scripts.graduation.g1_complete_worker import ClearanceEpisode

    template = read(base.prior.T02 / "allocation.json")
    clean_geometry = template["geometry"]
    generation = base.source_generation()

    def run(b, arm, slot, aim, frames, labels, actions, timeline, _legacy):
        if slot["id"] != CASE:
            raise ScopedStop("wrong isolated case")
        asset_sha = sha(asset)
        allocation = {
            "kind": "isolated_g1_skill_optical_registration",
            "geometry": clean_geometry,
            "runtime_build_sha256": generation,
            "calibration_sha256": template["calibration_sha256"],
            "asset_sha256": asset_sha,
            "case": {
                "id": ISOLATED_ID,
                "scene_id": b._scenario.scenario_id,
                "asset_sha256": asset_sha,
                "physics_dt_s": template["case"]["physics_dt_s"],
            },
        }
        blob = json.dumps(allocation, sort_keys=True).encode()
        binding = bind_allocation(
            blob,
            allocation_sha256=hashlib.sha256(blob).hexdigest(),
            generation_sha256=generation,
            calibration_sha256=allocation["calibration_sha256"],
            asset_sha256=asset_sha,
            reset_scene_id=b._scenario.scenario_id,
            reset_episode_id=b._episode_id,
        )
        folder = OUT / CASE
        (folder / "optical-registration.json").write_bytes(blob)
        cert = LocalClearance(
            clean_geometry,
            asset,
            base.prior.CV / "calibration-gpu-01",
            calibration_sha256=allocation["calibration_sha256"],
            isolated_scene=True,
            optical_identity=binding,
        )
        _, selected = tail.earlier.prepare_profiles(cert.motion)
        cert.payload_gate = selected
        owner = SimpleNamespace(backend=b, report={"actions": actions}, entry_command=None)
        rows, native_feedback = [], []
        previous, session, pending = None, None, None
        stage = "SETTLE"
        moving_idx, holding_idx = 0, 0
        held_phase, entry_pending = False, False
        motion_return = None
        native_reference = visual_servo.CartesianMotionReference
        target = Pose(**dict(zip(("x", "y", "z"), np.add(slot["center_m"], aim), strict=True)))
        high = Pose(x=target.x, y=target.y, z=max(0.16, target.z + 0.1))
        settings = dict(
            tcp_velocity=base.prior.PLAN["tcp_velocity_m_s"],
            acceleration=base.prior.PLAN["tcp_acceleration_m_s2"],
            timeout_ms=base.prior.PLAN["motion_timeout_ms"],
        )

        def refuse(ok, reason):
            if not ok:
                raise ScopedStop(reason)

        def observe_physics(row):
            if row.physics_step > END or any(c.illegal for c in b.get_contacts()):
                timeline.append({"step": row.physics_step, "stage": stage, "rejected": True})
                raise ScopedStop("physical cap or illegal contact")

        def check_state():
            at = b.total_physics_steps
            expected = (hold if held_phase else history).get(at)
            refuse(expected is not None, f"uncertified native step {at}")
            refuse(
                tail.earlier.pack_hash(b) == expected["phase_sha256"],
                f"integrator state differs at {at}",
            )
            refuse(
                len(b._pending_joint_targets) == expected["pending_count"], f"queue differs at {at}"
            )
            refuse(
                [list(x) for x in tail.earlier.pairs(b)] == expected["contacts"],
                f"contact differs at {at}",
            )
            if held_phase:
                actual = b.get_joint_command_state()
                refuse(
                    list(actual.positions_rad) == expected["retained_command"],
                    f"hold target differs at {at}",
                )
                refuse(
                    b._command_records[-1]["command_seq"] == expected["command_seq"],
                    f"hold command differs at {at}",
                )

        def inspect_now(phase, goal, role=None, dwell=None):
            began = time.perf_counter_ns()
            last = next(
                (
                    r
                    for r in reversed(b.command_records)
                    if r["type"] == "gripper" and r["accepted"]
                ),
                {},
            )
            native = b.capture_sensor_frame()
            image = legacy.append_frame(
                {
                    "skill": stage,
                    "phase": phase,
                    "research_role": role,
                    "dwell_tick": dwell,
                    "previous_native_successful_skill": previous["skill"] if previous else None,
                    "previous_native_return_step": previous["end_step"] if previous else None,
                    "previous_native_terminal_step": previous["end_step"] if previous else None,
                    "last_accepted_gripper_open": last.get("target_open"),
                    "last_accepted_gripper_command_step": last.get("physics_step"),
                },
                b,
                native,
                frames,
                labels,
            )
            robot = frames[-1][1]
            clocks_match = (
                robot["camera_encoder_sim_time_s"] == robot["sim_time_s"] == b.get_sim_time()
            )
            refuse(clocks_match, "RGB-D encoder clock mismatch")
            marker = detector(image, clean_geometry)
            if phase == "POST":
                verdict = cert.observe_payload_frame(image, marker, robot, stage, phase)
            else:
                robot["handoff"] = ClearanceEpisode.command_handoff(
                    owner, stage, phase, robot, image
                )
                verdict = cert.check(image, marker, robot, stage, goal, _DOWNWARD, phase=phase)
            row = {
                "frame_id": image.frame_id,
                "checksum_sha256": image.checksum_sha256,
                "phase": phase,
                "role": role,
                "skill": stage,
                "step": b.total_physics_steps,
                "native_last_command_seq": robot["native_last_command_seq"],
                "capture_begin_ns": began,
                "gate_finish_ns": time.perf_counter_ns(),
                "current": legacy.plain(verdict),
            }
            rows.append(row)
            if phase == "POST":
                return row
            refuse(
                clearance_is_accepted(verdict["status"], clocks_match),
                f"original {stage}/{phase} {verdict['status']}: {verdict.get('reason')}",
            )
            return row

        def sample(t):
            nonlocal pending, moving_idx, holding_idx
            at = b.total_physics_steps
            refuse(pending is None, "unconsumed native feedback")
            if held_phase:
                refuse(
                    holding_idx < len(holding) and at == holding[holding_idx],
                    "hold cadence differs",
                )
                holding_idx += 1
                role = "hold_entry" if at == RETURN else "retained_hold"
                terminal = END
            else:
                refuse(
                    moving_idx < len(moving) and at == moving[moving_idx], "motion cadence differs"
                )
                moving_idx += 1
                role = "motion"
                terminal = RETURN
            check_state()
            pending = inspect_now("FEEDBACK", t.position, role, at - RETURN if held_phase else None)
            decision = pending["current"]
            short = decision["short_motion"]
            if at == tail.ENTRY:
                refuse(
                    short.get("plan") == "continuous_native_handoff"
                    and short.get("validated_stop_delays") == 9,
                    "original entry certificate differs",
                )
            else:
                source_class = short.get("registered_source_speed_class")
                mode = f"source_{source_class}" if source_class else "generic"
                if held_phase or at >= original["status"]["source_grasp_permanently_retired_at"]:
                    refuse(mode == "generic", "retired source exception returned")
                speed_class = short.get("speed_class")
                key = ("retained_hold" if held_phase else role, at, mode, speed_class)
                need = range(min(tail.V, terminal - at) + 1)
                refuse(
                    set(need) <= comparisons.get(key, set()),
                    f"uncertified online stop mode at {at}: {mode}/{speed_class}",
                )
            return t

        def boundary(kind):
            nonlocal pending
            if pending is None:
                return
            ts = time.perf_counter_ns()
            refuse(
                len(session.records) == moving_idx + holding_idx
                and session.records[-1]["physics_step"] == pending["step"],
                "missing authentic native feedback record",
            )
            native_row = session.records[-1]
            pending.update(
                next_boundary=kind,
                next_boundary_ns=ts,
                sample_ik_ms=native_row["sample_and_ik_s"] * 1000,
                before_next_boundary_ms=(ts - pending["capture_begin_ns"]) / 1e6,
                released_to_boundary=False,
            )
            refuse(
                feedback_is_timely(pending["sample_ik_ms"], pending["before_next_boundary_ms"]),
                "native RGB-D deadline exceeded",
            )
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
            session = visual_servo.VisualServoSession(sample, vertical_clearance=path)
            command, step, move = b.apply_joint_targets, b.step, arm._move

            def reference(*args, **kwargs):
                ref = native_reference(*args, **kwargs)
                pin = refs.candidate_reference(b, ref, path, np.asarray(args[3]))
                refuse(pin == original["reference"], "real isolated reference differs")
                return ref

            def after_move(*args, **kwargs):
                nonlocal entry_pending, held_phase, motion_return
                native = move(*args, **kwargs)
                if native.success:
                    refuse(
                        b.total_physics_steps == RETURN and moving_idx == len(moving),
                        "unqualified actual return",
                    )
                    motion_return = legacy.plain(native)
                    held_phase = True
                    entry_pending = True
                    check_state()
                return native

            def next_command(*args, **kwargs):
                check_state()
                boundary("COMMAND")
                return command(*args, **kwargs)

            def next_step(steps=1):
                nonlocal entry_pending
                refuse(
                    steps == 1 and b.total_physics_steps < END, "unexpected integration boundary"
                )
                check_state()
                if entry_pending:
                    entry_pending = False
                    refuse(
                        b._sensor_capture_on_demand and b.total_physics_steps == RETURN,
                        "unbound retained hold entry",
                    )
                    visual_servo.MuJoCoVisualServoController(b).monitor_hold(
                        visual_servo.MotionTarget(goal, _DOWNWARD),
                        session,
                    )
                    check_state()
                boundary("PHYSICS")
                return step(steps=steps)

            def verify_drive(row):
                future = (hold if held_phase else history).get(row.physics_step)
                refuse(future is not None, "drive would advance beyond sealed clock")
                applied = [*row.control_rad, *row.finger_control_targets_m]
                refuse(
                    applied == future["ctrl"],
                    f"applied actuator vector differs at {row.physics_step}",
                )
                if held_phase:
                    refuse(
                        list(row.applied_joint_targets_rad) == future["retained_command"],
                        "retained native drive target differs",
                    )

            with (
                b.observe_actuator_steps(verify_drive),
                patch.object(b, "apply_joint_targets", next_command),
                patch.object(b, "step", next_step),
                patch.object(arm, "_move", after_move),
                patch.object(visual_servo, "CartesianMotionReference", reference),
                arm.visual_servo(session),
            ):
                return arm.lift(goal.z - start.z, resolved_target=goal, **settings)

        try:
            with b.observe_physics_steps(observe_physics):
                with b.sensor_capture_on_demand():
                    b.step(base.prior.PLAN["settle_steps"])
                for stage in base.prior.SKILLS:
                    record = {
                        "skill": stage,
                        "start_step": b.total_physics_steps,
                        "controller_called": False,
                    }
                    actions.append(record)
                    if stage == "GRASP":
                        inspect_now("PRE", target)
                        record["controller_called"] = True
                        result = arm.grasp("object", timeout_ms=base.prior.PLAN["grasp_timeout_ms"])
                    elif stage == "LIFT":
                        start = b.get_tcp_pose()
                        goal = Pose(x=start.x, y=start.y, z=max(0.16, start.z + 0.1))
                        inspect_now("PRE", goal)
                        record["controller_called"] = True
                        result = lift_to(goal, start)
                    else:
                        record["controller_called"] = True
                        with arm.visual_servo(visual_servo.VisualServoSession(lambda t: t)):
                            result = (
                                arm.move_above("object", resolved_target=high, **settings)
                                if stage == "MOVE_ABOVE"
                                else arm.approach("object", resolved_target=target, **settings)
                            )
                    record.update(
                        status="PASS" if result.success else "STOPPED",
                        end_step=b.total_physics_steps,
                        success=result.success,
                        error=result.error_code,
                        details=legacy.plain(result.details),
                        result=legacy.plain(result),
                    )
                    if not result.success:
                        return "native_skill_rejected"
                    previous = record
                    if stage == "GRASP":
                        inspect_now("POST", None)
                    if stage == "LIFT":
                        refuse(
                            held_phase
                            and not entry_pending
                            and holding_idx == len(holding)
                            and b.total_physics_steps == END,
                            "LIFT returned outside complete 120-step retention",
                        )
                        check_state()
                        boundary("TERMINAL_NO_FURTHER_INTEGRATION")
                        post = inspect_now("POST", None)
                        return (
                            "isolated_lift_with_held_post"
                            if post["current"]["relation"] == "held"
                            else "isolated_lift_post_unqualified"
                        )
        except ScopedStop as error:
            actions[-1].update(status="STOPPED", reason=str(error), end_step=b.total_physics_steps)
            return "isolated_safety_refusal"
        finally:
            if pending is not None:
                pending.setdefault("released_to_boundary", False)
            if session is not None:
                native_feedback = legacy.plain(session.records)
            write(
                folder / "clearance-gate.json",
                {
                    "checks": rows,
                    "native_feedback": native_feedback,
                    "motion_return": motion_return,
                    "sealed_plan_sha256": sha(PLAN_FILE),
                    "owner_post": False,
                },
            )
            cert.close()

    return run


def run(frozen, *, second_registration=None):
    from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
    from scripts.graduation.g1_complete_cv_clearance import RobotDepthReference

    (
        base,
        asset,
        aim,
        reset,
        cal,
        slot,
        receipts,
        refs,
        history,
        hold,
        original,
        comparisons,
        moving,
        holding,
    ) = frozen
    old = base.prior
    camera = old.audit_inputs()
    base.confirm_native_deadline_order()
    sys.path.insert(0, str(old.LEGACY))
    import capture_native_payload as legacy
    import cv2
    from read_pose_coverage import native_marker

    detector, marker_sha = native_marker(base.source_generation())
    REQUIRE(
        marker_sha == "9e216e93e17f52c0a20619b789d0e05f1382cd22385be96811084d7d8331f3ed",
        "frozen marker differs",
    )
    cv2.setNumThreads(1)
    max_projections = len(moving) + len(holding) + 2
    counts = {"robot": 0, "carried": 0}

    def counted(name, project):
        def call(*args, **kwargs):
            if counts[name] >= max_projections:
                raise ScopedStop(f"{name} reference projection cap")
            counts[name] += 1
            return project(*args, **kwargs)

        return call

    with old.LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(parents=True, exist_ok=False)
        reg = OUT / "registration.json"
        write(
            reg,
            {
                "plan_sha256": sha(PLAN_FILE),
                "code_sha256": sha(Path(__file__)),
                "reader_sha256": sha(receipts[0]),
                "case": ISOLATED_ID,
                "original_slot": slot,
                "planned_motion_feedback": moving,
                "planned_hold_feedback": holding,
                "explicit_pre_post_count": 4,
                "implicit_native_capture_budget": 7,
                "native_capture_hard_cap": LIMIT["conditional_native_exposures"],
                "reference_projection_hard_caps": {k: max_projections for k in counts},
                "complete_owner": False,
                "second_registration": second_registration,
            },
        )
        prior_plan = dict(
            old.PLAN,
            max_lift_feedback_per_case=len(moving) + len(holding),
            unlogged_pixel_caps_per_case=11,
            exclusive_physics_step_limit_per_case=END + 1,
        )
        attempt = scenario_driver(
            base,
            asset,
            detector,
            legacy,
            refs,
            history,
            hold,
            original,
            comparisons,
            moving,
            holding,
        )
        status = "attempt_interrupted"
        try:
            with (
                patch.object(old, "PLAN", prior_plan),
                patch.object(old, "OUT", OUT),
                patch.object(old, "scoped_capture", attempt),
                patch.object(
                    RobotDepthReference, "project", counted("robot", RobotDepthReference.project)
                ),
                patch.object(CarriedSurface, "project", counted("carried", CarriedSurface.project)),
            ):
                report = old.acquire_case(slot, asset, aim, reset, cal, sha(reg), camera, legacy)
                status = report["termination"]
        finally:
            files = sorted(p for p in OUT.rglob("*") if p.is_file())
            write(
                OUT / "seal.json",
                {
                    "sealed_sha256": {str(p.relative_to(OUT)): sha(p) for p in files},
                    "termination": status,
                    "reference_projection_calls": counts,
                    "formal": 0,
                    "independent_formal": 0,
                    "hardware": 0,
                    "remote": 0,
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "run"))
    args = parser.parse_args()
    frozen = preflight()
    if args.phase == "preflight":
        print(f"Bound sources and {len(frozen[-2])} moving plus {len(frozen[-1])} hold samples.")
    else:
        REQUIRE(
            os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
            "EGL is not exclusive configured mode",
        )
        run(frozen)
