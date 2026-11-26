"""Compare native RK4 force buffers and held behavior on both archived trajectories."""

import copy
import importlib.util
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, read, sha, write
from stop_motion_decomposition import HERE, OUT, PLAN, REPO, WINDOW, require

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand

ENTRY, LAST = 1632, 1848


def import_round(name, file):
    p = HERE.parent / name / file
    spec = importlib.util.spec_from_file_location(p.stem, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clone_context(b, native):
    data = copy.copy(b._data)
    require(not np.shares_memory(b._data.qpos, data.qpos), "native clone aliases original")
    signature = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(b._model, signature))
    mujoco.mj_getState(b._model, data, state, signature)
    require(np.array_equal(state, native.packed(b)), "native clone changed packed state")
    for name in ("qM", "qfrc_bias", "qfrc_passive", "qfrc_actuator", "qfrc_constraint", "qacc"):
        require(
            np.array_equal(getattr(data, name), getattr(b._data, name)),
            f"native clone differs in {name}",
        )
    return (
        data,
        b._target_positions.copy(),
        b.total_physics_steps,
        b._gripper_open,
        list(b._command_records),
        list(b._last_contacts),
    )


def enter_context(b, saved):
    data, target, step, grip, commands, contacts = saved
    b._data = data
    b._target_positions = target
    b._total_physics_steps = step
    b._gripper_open = grip
    b._command_records = commands
    b._last_contacts = contacts
    b._estop_engaged = False
    b._pending_joint_targets = []


def force_snapshot(b, previous_velocity=None, previous_time=None):
    d, m = b._data, b._model
    matrix = np.empty((m.nv, m.nv))
    mujoco.mj_fullM(m, matrix, d.qM)
    require(not np.any(d.xfrc_applied) and not np.any(d.qfrc_applied), "unregistered applied force")
    bias, act, passive, contact = [
        np.asarray(getattr(d, key)).copy()
        for key in ("qfrc_bias", "qfrc_actuator", "qfrc_passive", "qfrc_constraint")
    ]
    inertial = matrix @ d.qacc
    return {
        "step": b.total_physics_steps,
        "arm_velocity_rad_s": d.qvel[:7].tolist(),
        "arm_bias_nm": bias[:7].tolist(),
        "arm_actuator_nm": act[:7].tolist(),
        "arm_passive_nm": passive[:7].tolist(),
        "arm_constraint_nm": contact[:7].tolist(),
        "arm_other_dof_coupling_nm": (matrix[:7, 7:] @ d.qacc[7:]).tolist(),
        "arm_cached_force_balance_error_nm": (inertial + bias - act - passive - contact)[
            :7
        ].tolist(),
        "implemented_estimator_minus_cached_arm_inertia_nm": (
            matrix[:7, :7]
            @ ((d.qvel[:7] - previous_velocity) / (d.time - previous_time) - d.qacc[:7])
        ).tolist()
        if previous_time is not None
        else None,
        "arm_ctrl": d.ctrl[:7].tolist(),
    }


def normal(b, archive, drive, feedback, native):
    entry = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    arm = entry["robot"]
    ref = QualificationLiftReference(
        b,
        tuple(arm["tcp_position_m"]),
        tuple(entry["target"][k] for k in "xyz"),
        np.array(arm["tcp_quaternion_wxyz"]),
        control_steps=5,
        timeout_s=8,
        max_velocity=0.5,
        max_acceleration=5 / 3,
        initialize_load_from_feedback=feedback,
    )
    command, speed = b._data.qpos[:7].copy(), np.zeros(7)
    dt = 5 / 240
    states = []
    saved = None
    initial_velocity = initial_time = None
    for tick in range(ENTRY, LAST + 1):
        original = archive[tick]
        physical = plain(b.current_physics_observation())
        require(
            {k: v for k, v in physical.items() if k != "episode_id"}
            == {k: v for k, v in original.items() if k != "episode_id"},
            f"native candidate state diverged on replay at {tick}",
        )
        row = force_snapshot(b, initial_velocity, initial_time)
        row["filtered_arm_disturbance_nm"] = ref.disturbance.tolist()
        states.append(row)
        if tick == WINDOW["step"]:
            saved = clone_context(b, native)
        if tick == LAST:
            break
        if (tick - ENTRY) % 5 == 0:
            index = (tick - ENTRY) // 5
            goal = ref.joint_target(tick - ENTRY, 5)
            desired = np.clip((goal - command) / dt, -0.5, 0.5)
            speed += np.clip(desired - speed, -(5 / 3) * dt, (5 / 3) * dt)
            command += speed * dt
            require(
                command.tolist() == drive[tick]["command"], f"actual command mismatch at {tick}"
            )
            row.update(
                reference_positions_rad=ref.positions[index].tolist(),
                unclipped_joint_goal_rad=goal.tolist(),
                sent_joint_goal_rad=command.tolist(),
            )
            b.apply_joint_targets(JointCommand(positions=command.tolist(), max_velocity=0.5))
        initial_velocity, initial_time = b._data.qvel[:7].copy(), float(b._data.time)
        b.step(1)
        require(b._data.ctrl.tolist() == drive[tick]["ctrl"], f"actual ctrl mismatch at {tick}")
        ref.observe_step()
    return states, saved


def stop_dynamics(b, path):
    with np.load(path, allow_pickle=False) as f:
        q, dq, ctrl = (f[k] for k in ("q", "qvel", "ctrl"))
        names, counts = f["pair_names"].tolist(), f["contact_counts"]
    phases = []
    b.emergency_stop()
    require(
        [row["type"] for row in b.command_records[-2:]] == ["hold_current_joints", "emergency_stop"]
        and np.array_equal(b._target_positions, b._data.qpos[:7]),
        "native stop did not hold measured joints",
    )
    for tick in range(241):
        d = b._data
        actual = plain(b.current_physics_observation())["contact_pairs"]
        pairs = [sorted(a) for a in actual]
        require(
            np.array_equal(d.qpos, q[tick])
            and np.array_equal(d.qvel, dq[tick])
            and np.array_equal(d.ctrl, ctrl[tick])
            and [pairs.count(a) for a in names] == counts[tick].tolist()
            and all(a in names for a in pairs),
            f"actual stop differs from registered stop at {tick}",
        )
        phases.append(dict(force_snapshot(b), stop_tick=tick, contact_pairs=actual))
        if tick < 240:
            b.step(1)
    return phases


def main():
    script = import_round(
        "round-g1-t01-lift55-force-init-qualification-20261126", "screen_force_initialization.py"
    )
    native = import_round("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    for name, digest in PLAN["sha256"].items():
        require(sha(REPO / name) == digest, f"decomposition source changed: {name}")
    allocation, commands, truth, reset = script.source_inputs()
    cfg = allocation["case"]
    asset = ROOT / cfg["asset_path"]
    cfg_path = OUT / "paired"
    cfg_path.mkdir()
    b = RegisteredAssemblyBackend(cfg_path, cfg)
    previous = {}
    try:
        with patch.multiple(mujoco, Renderer=native.prohibited, mjr_render=native.prohibited):
            b.initialize(
                SimulatorConfig(
                    model_path=str(asset),
                    seed=cfg["visual_seed"],
                    physics_dt_s=1 / 240,
                    render_rgb=True,
                    render_depth=True,
                    domain_randomization=False,
                )
            )
            with native.no_render_context()(b, b.shutdown):
                script.cpu_entry(b, native, commands, truth, reset)
                clone = clone_context(b, native)
                original = read(script.RAW.parent / "lift-qualification-trace.json")
                candidates = read(script.OUT / "candidate-normal.json")["samples"]
                actual = read(script.OUT / "result.json")
                original_drive = {
                    r["physics_step"]: {"ctrl": r["ctrl"], "command": r["arm_target"]}
                    for r in original["before_integrations"]
                }
                candidate_drive = {
                    row["after_step"] - 1: {"ctrl": row["ctrl"]} for row in actual["applied_drive"]
                }
                for row in actual["commands"]:
                    candidate_drive[row["step"]]["command"] = row["command"]
                for label, history, target, feedback in (
                    ("baseline", truth, original_drive, False),
                    (
                        "feedback_init",
                        {int(k): v for k, v in candidates.items()},
                        candidate_drive,
                        True,
                    ),
                ):
                    if feedback:
                        enter_context(b, clone)
                    states, saved = normal(b, history, target, feedback, native)
                    enter_context(b, saved)
                    before = stop_dynamics(b, REPO / PLAN["inputs"][label])
                    previous[label] = {"normal": states, "stop": before}
    except BaseException as error:
        write(
            cfg_path / "failure.json",
            {"reason": str(error), "completed_branches": sorted(previous)},
        )
        raise
    result = {
        "phases": previous,
        "source_sha256": sha(Path(__file__)),
        "plan_sha256": sha(HERE / "plan.json"),
        "cpu_integrations": 2544,
        "new_captures": 0,
        "new_live_claims": 0,
    }
    write(cfg_path / "buffers.json", result)


if __name__ == "__main__":
    main()
