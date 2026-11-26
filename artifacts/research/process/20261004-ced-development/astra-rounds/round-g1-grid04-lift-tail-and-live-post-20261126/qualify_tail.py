"""Rebuild the sole candidate and test its conditional return and hold without images."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import AXES, SPEED_CLASSES
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

HOME = Path(__file__).resolve().parent
ROOT = next(p for p in HOME.parents if (p / ".git").exists())
PLAN = read(HOME / "plan.json")
OUT = ROOT / PLAN["private_output"]
ENTRY = PLAN["absolute_entry_tick"]
END = PLAN["last_reference_tick"]
ANCHOR = PLAN["incomplete_anchor"]
C = PLAN["control_steps"]
V = PLAN["feedback_steps"]
STOP = PLAN["stop_steps"]
HOLD = PLAN["hold_steps"]
INPUT = ROOT / PLAN["midcourse_plan"]
sys.path.insert(0, str(INPUT.parent))
import qualify_midcourse as earlier  # noqa: E402

require = earlier.require


def checked_inputs():
    for p, expected in PLAN["inputs_sha256"].items():
        require(sha(ROOT / p) == expected, f"tail input changed: {p}")
    for key in earlier.PLAN["hashes"]:
        earlier.source(key)
    runtime = ROOT / PLAN["frozen_runtime"] / "src"
    modules = (MuJoCoPhysicsBackend, MuJoCoMotionController, CartesianMotionReference)
    for kind in modules:
        p = Path(sys.modules[kind.__module__].__file__).resolve()
        require(p.is_relative_to(runtime.resolve()), f"nonfrozen runtime import: {p.name}")
    for name in ("reader", "geometry-reader"):
        require(
            sha(earlier.OUT / f"{name}-1.json") == sha(earlier.OUT / f"{name}-2.json"),
            "earlier independent readers disagree",
        )


def controller_start(b, a, ref):
    sent = b.get_joint_command_state()
    command = np.array(sent.positions_rad if sent.retained_target else b._data.qpos[:7])
    velocity = np.array(sent.velocity_rad_s if sent.retained_target else np.zeros(7))
    held = b.get_sim_time() - sent.sim_time_s
    require(held >= -1e-9 and abs(velocity).max() <= a.LIMIT_V + 1e-8, "invalid entry command")
    reaffirm = sent.retained_target and held > 1e-9
    if reaffirm:
        require(abs(velocity).max() <= a.LIMIT_A * held + 1e-8, "cannot settle entry command")
        velocity[:] = 0
    require(ref.control_dt == C * b._config.physics_dt_s, "changed control dt")
    return command, velocity, reaffirm, C if sent.retained_target and not reaffirm else 0


def state(b, phase, row, actual_velocity=None):
    m, d = b._model, b._data
    sent = b.get_joint_command_state()
    latest = b.command_records[-1]
    return {
        "tick": b.total_physics_steps,
        "phase": phase,
        "q": d.qpos.tolist(),
        "dq": d.qvel.tolist(),
        "ctrl": d.ctrl.tolist(),
        "t": float(d.time),
        "tcp": list(row.tcp_position_m),
        "cube": list(row.object_geom_position_m),
        "contacts": earlier.pairs(b),
        "phase_sha256": earlier.pack_hash(b),
        "pending_count": len(b._pending_joint_targets),
        "retained_command": list(sent.positions_rad),
        "retained_velocity": list(sent.velocity_rad_s),
        "retained_time": sent.sim_time_s,
        "controller_command_velocity": None
        if actual_velocity is None
        else actual_velocity.tolist(),
        "command_seq": latest["command_seq"],
        "command_kind": latest["type"],
        "site_position": d.site_xpos[m.site("tcp").id].tolist(),
        "site_rotation": d.site_xmat[m.site("tcp").id].tolist(),
    }


def serial(value):
    return json.loads(json.dumps(value, allow_nan=False))


def speed(stage, row):
    v = float(abs(np.array(row["dq"][:7])).max())
    require(v <= float(abs(stage["references"][:, 7:14]).max()) + 0.002, "speed domain exceeded")
    return next((str(k) for k in SPEED_CLASSES if str(k) in stage["classes"] and v <= k), "all")


def compare(gate, normal, anchor, trigger, branch, phase):
    stage = gate.data["LIFT"]
    sample = normal[anchor]
    klass = speed(stage, sample)
    world, relative, contacts = earlier.check_step(
        gate.motion,
        gate.axes,
        np.asarray(sample["q"]),
        np.asarray(sample["dq"]),
        branch,
        [normal[k] for k in range(anchor, trigger)],
    )
    limit = stage["classes"][klass]
    reserve = limit["world"] - world
    i, j = np.unravel_index(reserve.argmin(), reserve.shape)
    return {
        "anchor": anchor,
        "trigger": trigger,
        "phase": phase,
        "delay": trigger - anchor,
        "speed_class": klass,
        "world_min_m": float(reserve[i, j]),
        "relative_min_m": float((limit["relative"] - relative).min()),
        "limiting_part": gate.motion.names[i],
        "world_axis": AXES[j].tolist(),
        "first_invalid_contact": next(
            (k for k, c in enumerate(contacts) if set(map(tuple, c)) != earlier.BILATERAL),
            None,
        ),
    }


def acceptable(row):
    return (
        row["world_min_m"] >= 0
        and row["relative_min_m"] >= 0
        and row["first_invalid_contact"] is None
    )


def move(b, bridge, path, reference, history, observe):
    command, velocity, reaffirm, next_control = controller_start(b, bridge, reference)
    dt, peak = b._config.physics_dt_s, path.start_m[2]
    position = np.array(path.target_m)
    quat = np.array(_DOWNWARD)
    kinematics = MuJoCoMotionController(b)
    site = b._model.site("tcp").id
    settled = 0
    prefix = history[0].keys()
    feedback, motion = [], {}
    for offset in range(int(PLAN["timeout_s"] / dt)):
        at = ENTRY + offset
        row = bridge.check_mechanical(b, path, peak)
        peak = max(peak, row.tcp_position_m[2])
        require(at == b.total_physics_steps, "moving tick differs")
        live = state(b, "motion", row, velocity)
        if at <= END:
            original = history[offset]
            require(
                serial({k: live[k] for k in prefix}) == original,
                f"candidate prior moves differ: {at}",
            )
        else:
            require(set(live["contacts"]) == earlier.BILATERAL, f"source contact returns at {at}")
        if at >= ANCHOR:
            motion[at] = live
        if offset % V == 0:
            error, angle = kinematics._pose_error(position, quat, site)
            settled = (
                settled + 1
                if error <= PLAN["position_max_m"] and angle <= PLAN["orientation_max_deg"]
                else 0
            )
            if at >= ANCHOR:
                feedback.append(
                    {
                        "tick": at,
                        "conditional_consecutive_pose_matches": settled,
                        "position_error_m": error,
                        "orientation_error_deg": angle,
                    }
                )
        if at > END:
            observe(motion, at, "motion")
        if offset == next_control:
            goal = reference.joint_target(offset, C)
            if (
                offset * dt >= reference.duration_s + reference.settle_s
                and settled >= PLAN["stable_samples"]
                and abs(velocity).max() <= bridge.LIMIT_A * reference.control_dt
            ):
                require(at >= PLAN["earliest_condition_tick"], "unexpected early mechanical return")
                require(
                    np.array_equal(command, b.get_joint_command_state().positions_rad),
                    "return would reset target instead of retaining it",
                )
                previous = b.command_records[-1]["command_seq"]
                b.apply_joint_targets(
                    JointCommand(positions=command.tolist(), max_velocity=bridge.LIMIT_V)
                )
                require(
                    b.total_physics_steps == at
                    and b.command_records[-1]["command_seq"] == previous + 1
                    and b.command_records[-1]["type"] == "joint_target"
                    and b.command_records[-1]["accepted"]
                    and b.get_joint_command_state().velocity_rad_s == (0.0,) * 7
                    and not b._pending_joint_targets
                    and not b._gripper_open,
                    "duplicate command did not retain the normal closed-finger endpoint",
                )
                power = {
                    "command_positions_rad": command.tolist(),
                    "controller_velocity_before_rad_s": velocity.tolist(),
                    "controller_velocity_limit_rad_s": bridge.LIMIT_A * reference.control_dt,
                    "reference_duration_s": reference.duration_s,
                    "reference_settle_s": reference.settle_s,
                    "feedback_count_if_all_pass": offset // V + 1,
                    "condition_tick": at,
                }
                return at, peak, motion, feedback, power
            if not reaffirm:
                desired = np.clip(
                    (goal - command) / reference.control_dt, -bridge.LIMIT_V, bridge.LIMIT_V
                )
                velocity += np.clip(
                    desired - velocity,
                    -bridge.LIMIT_A * reference.control_dt,
                    bridge.LIMIT_A * reference.control_dt,
                )
                command += velocity * reference.control_dt
            reaffirm = False
            lo, hi = b._model.jnt_range[:7].T
            require(
                ((command >= lo + 0.001) & (command <= hi - 0.001)).all(), "command joint limit"
            )
            b.apply_joint_targets(
                JointCommand(positions=command.tolist(), max_velocity=bridge.LIMIT_V)
            )
            next_control += C
        require(b.step(1).physics_steps == 1, "movement integration count differs")
        reference.observe_step()
        after = bridge.check_mechanical(b, path, peak)
        peak = max(peak, after.tcp_position_m[2])
    raise ValueError("original movement cap without conditional return")


def hold(b, bridge, path, tick, peak, observe):
    rows = {}
    for offset in range(HOLD + 1):
        at = tick + offset
        row = bridge.check_mechanical(b, path, peak)
        peak = max(peak, row.tcp_position_m[2])
        require(b.total_physics_steps == at, "hold clock mismatch")
        rows[at] = state(b, "retained_hold", row)
        require(
            set(rows[at]["contacts"]) == earlier.BILATERAL and not b._gripper_open,
            f"hold lost closed-finger bilateral contact at {at}",
        )
        require(
            rows[at]["retained_command"] == rows[tick]["retained_command"]
            and rows[at]["command_seq"] == rows[tick]["command_seq"],
            f"hold issued a new command at {at}",
        )
        observe(rows, at, "retained_hold")
        if offset < HOLD:
            require(b.step(1).physics_steps == 1, "hold integration count differs")
    return rows


def run():
    checked_inputs()
    bridge = earlier.module(earlier.source("original/screen_braking.py"))
    bridge.verify_inputs()
    renderer = earlier.module(
        earlier.source("rounds/round-g1-release-terminal-rebound-20261125/terminal_rebound.py")
    )
    prior = read(earlier.OUT / "native/normal.json")
    previous_receipt = read(earlier.OUT / "native/result.json")
    require(
        previous_receipt["status"]["source_grasp_permanently_retired_at"]
        == PLAN["source_exemption_retired_tick"],
        "source exemption scope changed",
    )
    samples, commands, _, scenario = bridge.archived()
    asset = bridge.ASSET
    _, gate = earlier.prepare_profiles(MotionGeometry(Model(asset)))
    b = MuJoCoPhysicsBackend()
    counted_steps = 0
    step_impl = mujoco.mj_step

    def counted(m, d):
        nonlocal counted_steps
        counted_steps += 1
        require(counted_steps <= PLAN["budget"]["total_cpu"], "tail CPU cap")
        return step_impl(m, d)

    phases = ("motion", "retained_hold")
    dest = OUT / "native"
    dest.mkdir(parents=True, exist_ok=False)
    for phase in phases:
        (dest / phase).mkdir()
    windows, archives = [], {}
    moving_early = {}

    def observe(normals, at, phase):
        first = ANCHOR if phase == "motion" else min(normals)
        anchors = [k for k in range(max(first, at - V), at + 1) if (k - first) % V == 0]
        require(anchors, "uncovered continuation")
        branch = earlier.native_stop(b, bridge, at, dest / phase)
        archives[f"{phase}/{at}"] = branch[-1]
        require(len(archives) <= PLAN["budget"]["new_stop_triggers"], "too many stop triggers")
        for anchor in anchors:
            margin = compare(gate, normals, anchor, at, branch, phase)
            windows.append(margin)
            if not acceptable(margin):
                write(dest / "failed-comparison.json", {"comparison": margin, "archives": archives})
                raise ValueError(f"generic hold undershoot or contact {phase}/{anchor}/{at}")
        if phase == "retained_hold":
            last_moving_anchor = max(moving_early)
            last_moving_anchor -= (last_moving_anchor - ANCHOR) % V
            if 0 <= at - last_moving_anchor <= V:
                crossed = {**moving_early, **normals}
                margin = compare(gate, crossed, last_moving_anchor, at, branch, "handoff_overlap")
                windows.append(margin)
                if not acceptable(margin):
                    write(
                        dest / "failed-comparison.json",
                        {"comparison": margin, "archives": archives},
                    )
                    raise ValueError(f"generic handoff undercoverage {last_moving_anchor}/{at}")

    with patch.multiple(mujoco, mj_step=counted, Renderer=earlier.deny, mjr_render=earlier.deny):
        b.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=scenario.seed,
                physics_dt_s=1 / 240,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
                camera_width=320,
                camera_height=240,
            )
        )
        with renderer.render_free(b, b.shutdown):
            b.reset(scenario)
            seen = set()
            bridge.early_replay(b, samples, commands, seen)
            require(
                b.total_physics_steps == ENTRY and len(b.command_records) == 236,
                "wrong LIFT entry phase",
            )
            start = tuple(b.current_physics_observation().tcp_position_m)
            path = VerticalClearancePath(
                task_id=earlier.PLAN["only_case"],
                step_id="LIFT",
                skill="LIFT",
                start_m=start,
                target_m=(*start[:2], earlier.PLAN["original_unchanged_grounded_z_m"]),
                minimum_height_m=0.08,
            )
            quat = np.empty(4)
            mujoco.mju_mat2Quat(quat, b._data.site("tcp").xmat)
            reference = CartesianMotionReference(
                b,
                path.start_m,
                path.target_m,
                quat,
                control_steps=C,
                timeout_s=PLAN["timeout_s"],
                max_velocity=bridge.LIMIT_V,
                max_acceleration=bridge.LIMIT_A,
            )
            pin = bridge.candidate_reference(b, reference, path, quat)
            require(pin == previous_receipt["reference"], "different reference dynamics")
            at, peak, motion, feedback, power = move(b, bridge, path, reference, prior, observe)
            moving_early.update({k: row for k, row in motion.items() if k >= at - V})
            held = hold(b, bridge, path, at, peak, observe)

    normal_count = at + HOLD
    require(normal_count <= PLAN["budget"]["normal_cpu"], "different normal clock")
    require(counted_steps == normal_count + len(archives) * STOP, "hidden physics steps")
    last_movement = feedback[-1]["tick"]
    planned_hold = list(range(at + V, at + HOLD + 1, V))
    write(dest / "motion.json", motion)
    write(dest / "retained_hold.json", held)
    write(
        dest / "result.json",
        {
            "archives": archives,
            "comparisons": windows,
            "reference": pin,
            "conditional_feedback": feedback,
            "return": power,
            "last_motion_feedback_tick": last_movement,
            "hold_feedback_candidate_ticks": planned_hold,
            "last_motion_to_first_hold_gap_ticks": planned_hold[0] - last_movement,
            "hold_end_tick": at + HOLD,
            "normal_cpu": normal_count,
            "total_cpu": counted_steps,
            "live": 0,
            "exposures": 0,
            "formal": 0,
            "independent_formal": 0,
            "hardware": 0,
            "remote": 0,
        },
    )


if __name__ == "__main__":
    try:
        run()
    except BaseException as err:
        OUT.mkdir(parents=True, exist_ok=True)
        write(OUT / "failure.json", {"type": type(err).__name__, "reason": str(err)})
        raise
