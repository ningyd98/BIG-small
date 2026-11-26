"""Recover the t01 LIFT entrance by native replay and compare in a separate reader."""

import argparse
import hashlib
import importlib.util
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_clearance import camera_encoder_pose
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
SIG = mujoco.mjtState.mjSTATE_INTEGRATION
ENTRY, STOP = PLAN["entry"]["step"], PLAN["comparison"]["end_step"]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def prohibited(*args, **kwargs):
    raise AssertionError("CPU witness must not capture or render")


def verify_inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen runtime import path")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for name, expected in PLAN["sha256"].items():
        path = (REPO / name).resolve()
        require(path.is_relative_to(REPO) and sha(path) == expected, f"source changed: {name}")


def no_render_context():
    fn = HERE.parent / "round-g1-release-terminal-rebound-20261125/terminal_rebound.py"
    spec = importlib.util.spec_from_file_location("frozen_render_free", fn)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_free


def replay_command(backend, record):
    require(
        record["accepted"] and record["physics_step"] == backend.total_physics_steps,
        "historical command is not accepted at this pre-integration step",
    )
    if record["type"] == "joint_target":
        backend.apply_joint_targets(JointCommand(positions=record["target_positions_rad"]))
    elif record["type"] == "gripper":
        backend.apply_gripper_command(GripperCommand(open=record["target_open"]))
    elif record["type"] == "hold_current_joints":
        backend.hold_current_joints()
    else:
        raise ValueError("unexpected protected or non-motion source command")
    emitted = backend.command_records[-1]
    require(
        {k: v for k, v in emitted.items() if k != "episode_id"}
        == {k: v for k, v in record.items() if k != "episode_id"},
        f"native replay command differs at sequence {record['command_seq']}",
    )


def entry_phase(records):
    require(
        len(records) == 258
        and [c["command_seq"] for c in records] == list(range(1, 259))
        and Counter(c["type"] for c in records)
        == Counter(joint_target=255, hold_current_joints=2, gripper=1)
        and [c["type"] for c in records[-2:]] == ["hold_current_joints", "gripper"]
        and all(c["physics_step"] < ENTRY for c in records)
        and records[-1]["target_open"] is False,
        "wrong original command phase at the LIFT entrance",
    )


def packed(backend):
    model, data = backend._model, backend._data
    state = np.empty(mujoco.mj_stateSize(model, SIG), dtype="<f8")
    mujoco.mj_getState(model, data, state, SIG)
    return state


def derived(backend):
    model, data = backend._model, backend._data
    mass = np.empty((model.nv, model.nv))
    mujoco.mj_fullM(model, mass, data.qM)
    return {
        "physics_step": backend.total_physics_steps,
        "time": float(data.time),
        "qr": data.qpos[:7].tolist(),
        "dq": data.qvel[:7].tolist(),
        "mass_arm": mass[:7, :7].tolist(),
        "qM": data.qM.tolist(),
        "bias": data.qfrc_bias[:7].tolist(),
        "actuator": data.qfrc_actuator[:7].tolist(),
        "passive": data.qfrc_passive[:7].tolist(),
        "finger_ctrl": data.ctrl[7:9].tolist(),
    }


def verify_entry(backend, source, old_pose, original_frames):
    native = derived(backend)
    reproduced = packed(backend)
    exposure = camera_encoder_pose(backend._model, backend._data)
    controls = backend._data.ctrl.tolist()
    require(
        reproduced.tobytes() == np.asarray(source["integration"], dtype="<f8").tobytes()
        and native["bias"] == source["qfrc_bias_arm"]
        and controls == source["ctrl"]
        and backend._target_positions.tolist() == source["arm_target"]
        and backend._actuator_delay_steps == source["actuator_delay_steps"] == 0
        and backend._pending_joint_targets == source["pending"] == []
        and backend._gripper_open == source["gripper_open"] is False
        and not backend.estop_engaged
        and not source["estop"]
        and all(value == old_pose[k] for k, value in exposure.items()),
        "full integration, commands, original RK4 bias or exposure encoder differs at entry",
    )
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, backend._data.site("tcp").xmat)
    require(q.tolist() == old_pose["tcp_quaternion_wxyz"], "exact TCP attitude differs")
    ids = {row["frame_id"]: row for row in original_frames}
    require(
        old_pose["frame_id"] in ids
        and ids[old_pose["frame_id"]]["checksum_sha256"] == old_pose["checksum_sha256"]
        and ids[old_pose["frame_id"]]["physics_step"] == ENTRY,
        "unbound original exposure",
    )
    return reproduced


def replay():
    receipt = read(RAW / "receipt.json")
    allocation = pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"])
    source_seal = pinned(RAW / "acquisition-seal.json", receipt["capture_sha256"])
    samples = pinned(RAW / "offline-truth.json", source_seal["truth_sha256"])["samples"]
    frames = pinned(RAW / "pixel-index.json", source_seal["index_sha256"])["frames"]
    local_seal = read(RAW / "local-clearance-seal.json")
    require(
        local_seal["acquisition_seal_sha256"] == receipt["capture_sha256"], "foreign archived gate"
    )
    local = pinned(RAW / "local-clearance.json", local_seal["local_clearance_sha256"])
    events = pinned(RAW / "reset-observed.json", receipt["reset_sha256"])
    originals = pinned(RAW / "backend-commands.json", receipt["full_commands_sha256"])
    trace = read(RAW.parent / "lift-qualification-trace.json")
    config = allocation["case"]
    asset = ROOT / config["asset_path"]
    require(
        config["view"] == "nominal" and sha(asset) == allocation["asset_sha256"],
        "registered original model differs",
    )
    requested = events[0]["parameters"]["requested"].copy()
    for k in ("object_pose", "target_region_pose"):
        requested[k] = Pose(**requested[k])
    batch = OUT / "native-prefix-01"
    OUT.mkdir(exist_ok=True)
    batch.mkdir()
    backend = RegisteredAssemblyBackend(batch, config)
    tick_commands = defaultdict(list)
    for command in originals:
        if command["physics_step"] < STOP:
            tick_commands[command["physics_step"]].append(command)
    prefix = [cmd for cmd in originals if cmd["physics_step"] < ENTRY]
    entry_phase(prefix)
    for wrong in (originals[:259], [*prefix[:-2], prefix[-1], prefix[-2]]):
        try:
            entry_phase(wrong)
        except ValueError:
            continue
        raise ValueError("an incorrect entrance command phase passed")
    original_trace = {row["physics_step"]: row for row in trace["before_integrations"]}
    visited = []
    states = []
    entry_proof = None
    reference = None
    try:
        backend.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=config["visual_seed"],
                physics_dt_s=1 / 240,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
            )
        )
        with no_render_context()(backend, backend.shutdown):
            backend.reset(PhysicalScenarioConfig(**requested))
            new_reset = read(batch / "reset-observed.json")
            require(
                read(batch / "assembly-reset.json") == read(RAW / "assembly-reset.json")
                and read(batch / "camera-setup.json") == read(RAW / "camera-setup.json")
                and new_reset[0]["parameters"] == events[0]["parameters"]
                and new_reset[1]["parameters"] == events[1]["parameters"],
                "new native reset differs from the sealed original",
            )

            def match(snapshot):
                step = snapshot.physics_step
                original = samples[step]
                live = plain(snapshot)
                missing = [k for k in original if k != "episode_id" and live.get(k) != original[k]]
                require(not missing, f"original physical divergence at {step}: {missing}")
                visited.append(step)

            match(backend.current_physics_observation())

            def observed_drive(event):
                step = event.physics_step - 1
                if step in original_trace:
                    source = original_trace[step]
                    require(
                        list(event.control_rad) + list(event.finger_control_targets_m)
                        == source["ctrl"]
                        and list(event.applied_joint_targets_rad) == source["arm_target"]
                        and packed(backend).tolist() == source["integration"],
                        f"actual drive or integration state differs at {step}",
                    )
                    states[-1]["real_ctrl"] = source["ctrl"]
                    states[-1]["real_arm_target"] = source["arm_target"]

            with (
                backend.observe_physics_steps(match),
                backend.observe_actuator_steps(observed_drive),
            ):
                for tick in range(STOP):
                    if tick == ENTRY:
                        entry_phase(backend.command_records)
                        pre, feedback = trace["frames"][:2]
                        require(
                            pre["state"] == feedback["state"], "two historical entry phases differ"
                        )
                        source = pre["state"]
                        (observable,) = [
                            row
                            for row in local["rows"]
                            if row["frame_id"] == feedback["frame_id"]
                            and row["phase"] == "FEEDBACK"
                        ]
                        robot = observable["robot"]
                        vector = verify_entry(backend, source, robot, frames)
                        entry_proof = {
                            "integration_sha256": hashlib.sha256(vector.tobytes()).hexdigest(),
                            "last_command_seq": backend.command_records[-1]["command_seq"],
                            "original_episode": receipt["physical_reset"]["episode_id"],
                            "replay_episode": backend._episode_id,
                            "frozen_runtime": PLAN["runtime"],
                        }
                        reference = QualificationLiftReference(
                            backend,
                            tuple(robot["tcp_position_m"]),
                            tuple(observable["target_xyz"][k] for k in "xyz"),
                            np.array(robot["tcp_quaternion_wxyz"]),
                            control_steps=5,
                            timeout_s=8.0,
                            max_velocity=0.5,
                            max_acceleration=5 / 3,
                            initialize_load_from_feedback=False,
                        )
                    if tick >= ENTRY:
                        states.append(derived(backend))
                    for command in tick_commands[tick]:
                        replay_command(backend, command)
                    require(backend.step(1).physics_steps == 1, "extra replay integration")
                states.append(derived(backend))
            require(
                visited == list(range(STOP + 1)) and backend._camera is None,
                "incomplete or camera-active original replay",
            )
            arrays = [reference.positions, reference.velocities, reference.accelerations]
            h = hashlib.sha256()
            for value in arrays:
                h.update(np.asarray(value, dtype="<f8").tobytes())
            require(h.hexdigest() == trace["reference"]["array_sha256"], "changed reference array")
            witness = {
                "source_sha256": sha(Path(__file__)),
                "plan_sha256": sha(HERE / "plan.json"),
                "entry": entry_proof,
                "cpu_steps": STOP,
                "cpu_reset_count": 1,
                "ordinary_historical_commands": len(backend.command_records),
                "reference_sha256": h.hexdigest(),
                "reference": [a.tolist() for a in arrays],
                "damping": reference.damping.tolist(),
                "gains": reference.gains.tolist(),
                "arm_ctrl_range": backend._model.actuator_ctrlrange[:7].tolist(),
                "physically_applied_candidate_commands": 0,
                "states": states,
                "camera_exposures": 0,
            }
    except BaseException as exc:
        write(
            batch / "failure.json",
            {"last_checked_step": visited[-1] if visited else None, "error": str(exc)},
        )
        raise
    write(batch / "witness.json", witness)
    write(batch / "seal.json", {"witness_sha256": sha(batch / "witness.json")})


def read_controls(reader):
    batch = OUT / "native-prefix-01"
    seal = read(batch / "seal.json")
    witness = pinned(batch / "witness.json", seal["witness_sha256"])
    require(
        witness["source_sha256"] == sha(Path(__file__))
        and witness["plan_sha256"] == sha(HERE / "plan.json")
        and witness["physically_applied_candidate_commands"] == 0
        and witness["entry"]["last_command_seq"] == 258,
        "bad original witness",
    )
    baseline, candidate = witness_commands(witness)
    delta = np.asarray(candidate) - np.asarray(baseline)
    changed = np.abs(delta) > 1e-12
    first = np.argwhere(changed)
    i, j = first[0] if first.size else (-1, -1)
    write(
        OUT / f"{reader}.json",
        {
            "witness_sha256": seal["witness_sha256"],
            "baseline_commands": len(baseline),
            "baseline_applied_drives": 216,
            "changed_commands": int(changed.any(axis=1).sum()),
            "first_changed_step": ENTRY + 5 * int(i) if first.size else None,
            "first_changed_joint": int(j + 1) if first.size else None,
            "first_difference_rad": float(delta[i, j]) if first.size else None,
            "peak_difference_rad": float(abs(delta).max()),
            "candidate_command_differences_rad": delta.tolist(),
            "candidate_motion_qualified": False,
        },
    )


def witness_commands(witness):
    dt = 1 / 240
    control_dt = 5 * dt
    damp, gains = np.array(witness["damping"]), np.array(witness["gains"])
    low, high = np.array(witness["arm_ctrl_range"]).T
    xyz, speed, accel = [np.asarray(a) for a in witness["reference"]]
    state = witness["states"][0]

    def force(row):
        return np.array(row["bias"]) - row["actuator"] - row["passive"]

    difference = np.stack((np.zeros(7), force(state)))
    commands = np.tile(state["qr"], (2, 1))
    velocity = np.zeros((2, 7))
    sent = [[], []]
    prior = np.array(state["dq"])
    previous_time = state["time"]
    for elapsed, row in enumerate(witness["states"][:-1]):
        mass = np.asarray(row["mass_arm"])
        if elapsed:
            span = row["time"] - previous_time
            observed = mass @ ((np.array(row["dq"]) - prior) / span) + force(row)
            difference += min(1.0, span / 0.03) * (observed - difference)
            prior = np.array(row["dq"])
            previous_time = row["time"]
        if elapsed % 5 == 0:
            i = elapsed // 5
            targets = xyz[i] + (damp * speed[i] + mass @ accel[i] - difference) / gains
            desired = np.clip((targets - commands) / control_dt, -0.5, 0.5)
            velocity += np.clip(desired - velocity, -(5 / 3) * control_dt, (5 / 3) * control_dt)
            commands += velocity * control_dt
            for group, target in zip(sent, commands, strict=True):
                group.append(target.tolist())
        require(
            np.allclose(commands[0], row["real_arm_target"], rtol=0, atol=1e-12)
            and np.allclose(
                np.r_[
                    np.clip(
                        np.asarray(row["qr"])
                        + np.clip(commands[0] - row["qr"], -0.10, 0.10)
                        + np.array(row["bias"]) / gains,
                        low,
                        high,
                    ),
                    row["finger_ctrl"],
                ],
                row["real_ctrl"],
                rtol=0,
                atol=1e-12,
            ),
            f"zero-initialization derivation differs at {row['physics_step']}",
        )
    return sent


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("replay", "read"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    verify_inputs()
    with patch.multiple(mujoco, Renderer=prohibited, mjr_render=prohibited):
        if args.mode == "replay":
            patch_capture = patch.object(
                RegisteredAssemblyBackend, "capture_sensor_frame", prohibited
            )
            with patch_capture:
                replay()
        else:
            read_controls(args.reader)
