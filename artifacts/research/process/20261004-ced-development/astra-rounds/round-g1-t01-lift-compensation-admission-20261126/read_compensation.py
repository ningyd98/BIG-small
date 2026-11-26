"""Reconstruct original t01 commands from locked pre-integration checkpoints."""

import argparse
import hashlib
import math
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
SIG = mujoco.mjtState.mjSTATE_INTEGRATION


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prohibited(*args, **kwargs):
    raise AssertionError("command readback cannot render")


def load():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong original runtime")
    verify_generation(ROOT, PLAN["input_sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for name, expected in PLAN["input_sha256"].items():
        source = (REPO / name).resolve()
        require(source.is_relative_to(REPO) and sha(source) == expected, f"source changed: {name}")
    receipt = read(RAW / "receipt.json")
    allocation = pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"])
    commands = pinned(RAW / "backend-commands.json", receipt["full_commands_sha256"])
    trace = read(RAW.parent / "lift-qualification-trace.json")
    require(
        trace["state_signature"] == SIG and trace["reference"]["seconds"] == 5.5,
        "source checkpoint class or reference differs",
    )
    return allocation, commands, trace


def check_stop(asset):
    frozen = PLAN["fixed"]
    motion = MotionGeometry(Model(asset))
    with np.load(REPO / PLAN["stop_archive"], allow_pickle=False) as raw:
        q, dq = raw["q"], raw["qvel"]
    profiles = ROOT / "scripts/graduation"
    source = read(profiles / "g1_complete_cv_source_motion_profile.json")
    body = motion.names.index("g1_dual_id8_plate")
    v, speed, _, _ = snapshot(motion, q, dq, q[:, 9:12], object_matrix(q))
    measured = positive_support(v, speed, v[0], AXES)[body, 5]
    endpoint = float((v[0, body, :, 2] - v[:, body, :, 2]).max())
    allowance = source["classes"]["0.075"]["world"][body][5] * 1.25 + 0.0005
    require(
        abs(measured - 0.002777251732861987) < 1e-12
        and abs(allowance - frozen["downward_ID8_plate_allowance_m"]) < 1e-12
        and measured > endpoint > allowance,
        "frozen ID8 negative-Z witness did not reproduce",
    )
    return {
        "measured_bound_m": float(measured),
        "measured_endpoint_peak_m": endpoint,
        "allowance_m": allowance,
        "margin_m": float(allowance - measured),
        "direction": [0, 0, -1],
        "additional_stop_integrations": 0,
    }


def reconstruct(backend, trace, commands, goal_xyz):
    model, data = backend._model, backend._data
    pre, first = trace["frames"][0], trace["frames"][1]
    entry = first["state"]
    start = entry["physics_step"]
    require(
        pre["state"] == entry and start == PLAN["fixed"]["LIFT_entry_step"],
        "LIFT PRE and first live feedback differ",
    )
    packed = np.asarray(entry["integration"])
    mujoco.mj_setState(model, data, packed, SIG)
    mujoco.mj_forward(model, data)
    forward_bias_residual = float(
        abs(data.qfrc_bias[:7] - np.asarray(entry["qfrc_bias_arm"])).max()
    )
    # The packed state holds the integration fields, not the derived actuator
    # and passive force buffers left by the last live RK4 step before LIFT.
    entry_feedback_known = all(
        key in entry for key in ("qfrc_bias_arm", "qfrc_actuator_arm", "qfrc_passive_arm")
    )
    require(not entry_feedback_known, "original eligibility protocol needs re-review")
    mujoco.mj_setState(model, data, packed, SIG)
    data.qfrc_bias[:7] = entry["qfrc_bias_arm"]
    backend._total_physics_steps = start
    backend._command_records = commands[: entry["command_count"]]
    held = backend.get_joint_command_state()
    dt = backend._config.physics_dt_s
    speed_limit, acceleration_limit = 0.5, 5 / 3
    control_steps = PLAN["fixed"]["control_ticks"]
    control_dt = control_steps * dt
    q_command = np.array(held.positions_rad if held.retained_target else data.qpos[:7])
    velocity = np.array(held.velocity_rad_s) if held.retained_target else np.zeros(7)
    held_s = data.time - held.sim_time_s
    reaffirm = held.retained_target and held_s > 1e-9
    require(
        held_s >= -1e-9
        and np.max(abs(velocity)) <= speed_limit + 1e-8
        and (not reaffirm or np.max(abs(velocity)) <= acceleration_limit * held_s + 1e-8)
        and (not held.retained_target or reaffirm),
        "original active command does not begin the recorded tick-zero grid",
    )
    if reaffirm:
        velocity[:] = 0
    wrist = np.empty(4)
    mujoco.mju_mat2Quat(wrist, data.site("tcp").xmat)
    # In the converged entrance this and the historical exposure pose agree
    # for the same locked Cartesian reference. Use the original measured pose
    # below and independently check it via the array digest.
    actual_entry = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    start_pose = tuple(actual_entry["robot"]["tcp_position_m"])
    q0_orientation = np.asarray(actual_entry["robot"]["tcp_quaternion_wxyz"])
    require(abs(np.dot(wrist, q0_orientation)) > 1 - 1e-10, "entry camera attitude differs")
    # At the entrance the old RK4 position buffer that supplied qM is
    # independently observable through the exposure arm/finger kinematics.
    exposure = mujoco.MjData(model)
    exposure.qpos[:] = data.qpos
    exposure.qpos[:7] = actual_entry["robot"]["camera_joint_positions_rad"]
    exposure.qpos[7:9] = actual_entry["robot"]["camera_finger_positions_m"]
    mujoco.mj_forward(model, exposure)
    data.qM[:] = exposure.qM
    reference = QualificationLiftReference(
        backend,
        start_pose,
        goal_xyz,
        q0_orientation,
        control_steps=control_steps,
        timeout_s=8,
        max_velocity=speed_limit,
        max_acceleration=acceleration_limit,
        initialize_load_from_feedback=False,
    )
    digest = hashlib.sha256()
    for values in (reference.positions, reference.velocities, reference.accelerations):
        digest.update(np.asarray(values, dtype="<f8").tobytes())
    require(digest.hexdigest() == trace["reference"]["array_sha256"], "different reference arrays")
    issued = [
        row for row in commands if row["type"] == "joint_target" and row["physics_step"] >= start
    ]
    duration = len(trace["before_integrations"])
    require(
        len(issued) == len(range(0, duration, control_steps))
        and [row["physics_step"] for row in issued]
        == list(range(start, start + duration, control_steps))
        and all(row["accepted"] for row in issued)
        and [row["type"] for row in commands if row["physics_step"] >= start + duration]
        == ["hold_current_joints", "hold_current_joints", "emergency_stop"],
        "command grid or protection order differs",
    )
    reported = []
    max_target_residual = 0.0
    max_drive_residual = 0.0
    for elapsed, state in enumerate(trace["before_integrations"]):
        require(
            state["physics_step"] == start + elapsed and float(data.time) == state["sim_time_s"],
            "wrong integration clock",
        )
        if elapsed % control_steps == 0:
            goal = reference.joint_target(elapsed, control_steps)
            if not (elapsed == 0 and reaffirm):
                desired = np.clip((goal - q_command) / control_dt, -speed_limit, speed_limit)
                maximum_change = acceleration_limit * control_dt
                velocity += np.clip(desired - velocity, -maximum_change, maximum_change)
                q_command += velocity * control_dt
        if elapsed % control_steps == 0:
            original = issued[elapsed // control_steps]
            discrepancy = float(abs(q_command - original["target_positions_rad"]).max())
            max_target_residual = max(max_target_residual, discrepancy)
            require(
                discrepancy < 1e-12,
                f"original sent target differs at {start + elapsed}: {discrepancy:.16g} rad",
            )
            index = elapsed // control_steps
            reported.append(
                {
                    "physics_step": start + elapsed,
                    "command_seq": original["command_seq"],
                    "unclipped_minus_nominal_rad": (
                        (goal - reference.positions[index]).tolist() if goal is not None else None
                    ),
                    "sent_minus_nominal_rad": (q_command - reference.positions[index]).tolist(),
                    "sent_joint_target_rad": q_command.tolist(),
                }
            )
        backend._target_positions = q_command.copy()
        backend._apply_control()
        drive_error = float(abs(data.ctrl - state["ctrl"]).max())
        max_drive_residual = max(max_drive_residual, drive_error)
        require(drive_error < 1e-12, f"original applied drive differs at {start + elapsed}")
        # Keep the observed physical trajectory independent of the numerical
        # error tolerance of the command reconstruction.
        mujoco.mj_setState(model, data, np.asarray(state["integration"]), SIG)
        mujoco.mj_step(model, data)
        reference.observe_step()
    origin = next(row for row in trace["frames"] if row["status"] == "BLOCKED")["state"]
    require(
        math.isclose(data.time, origin["sim_time_s"], abs_tol=1e-12, rel_tol=0),
        "stop was not reached at the archived clock",
    )
    return {
        "original_steps_reintegrated": duration,
        "original_commands_reconstructed": len(reported),
        "maximum_sent_target_error_rad": max_target_residual,
        "maximum_applied_drive_error_rad": max_drive_residual,
        "original_entry_reaffirmed": reaffirm,
        "entry_recomputed_arm_bias_max_difference_nm": forward_bias_residual,
        "entry_cached_actuator_and_passive_arm_forces_archived": entry_feedback_known,
        "alternate_initialization_evaluated": False,
        "alternate_initialization_blocker": "original RK4 actuator/passive caches absent at entry",
        "commands": reported,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    allocation, commands, trace = load()
    cfg = allocation["case"]
    asset = ROOT / cfg["asset_path"]
    require(sha(asset) == allocation["asset_sha256"], "wrong original assembly")
    entry = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    goal = tuple(entry["target"][axis] for axis in "xyz")
    backend = MuJoCoPhysicsBackend()
    try:
        with patch.multiple(mujoco, Renderer=prohibited, mjr_render=prohibited):
            backend.initialize(
                SimulatorConfig(
                    model_path=str(asset),
                    physics_dt_s=1 / 240,
                    render_rgb=False,
                    render_depth=False,
                    domain_randomization=False,
                )
            )
            backend.reset(
                PhysicalScenarioConfig(
                    scenario_id=cfg["scene_id"],
                    seed=cfg["visual_seed"],
                    object_mass_kg=trace["native_scenario_mass_kg"],
                    friction_coefficient=trace["native_scenario_friction_coefficient"],
                )
            )
            result = reconstruct(backend, trace, commands, goal)
            result["original_stop_witness"] = check_stop(asset)
    finally:
        backend.shutdown()
    result.update(
        source_sha256=sha(Path(__file__)),
        plan_sha256=sha(HERE / "plan.json"),
        native_exposures=0,
        new_task_claims=0,
    )
    out = REPO / PLAN["output"]
    out.mkdir(exist_ok=True)
    write(out / f"{args.reader}.json", result)


if __name__ == "__main__":
    main()
