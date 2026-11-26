"""Run the isolated mechanical elimination screen without granting visual permission."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    PayloadClearance,
    object_matrix,
    snapshot,
)
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
ENTRY, REFUSAL = PLAN["source_entry"], PLAN["source_first_refusal"]


def require(test, reason):
    if not test:
        raise ValueError(reason)


def local_import(round_name, filename):
    path = HERE.parent / round_name / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen runtime")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for rel, expected in PLAN["sha256"].items():
        require(sha(REPO / rel) == expected, f"source changed: {rel}")
    receipt = read(RAW / "receipt.json")
    seal = pinned(RAW / "acquisition-seal.json", receipt["capture_sha256"])
    return (
        pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"]),
        pinned(RAW / "backend-commands.json", receipt["full_commands_sha256"]),
        pinned(RAW / "offline-truth.json", seal["truth_sha256"])["samples"],
        pinned(RAW / "reset-observed.json", receipt["reset_sha256"])[0]["parameters"]["requested"],
    )


def cpu_entry(backend, prefix, commands, truth, reset):
    requested = dict(reset)
    for k in ("object_pose", "target_region_pose"):
        requested[k] = Pose(**requested[k])
    backend.reset(PhysicalScenarioConfig(**requested))
    frozen = [row for row in commands if row["physics_step"] < ENTRY]
    prefix.entry_phase(frozen)
    grouped = {step: [] for step in range(ENTRY)}
    for row in frozen:
        grouped[row["physics_step"]].append(row)

    def check(snapshot):
        row = truth[snapshot.physics_step]
        current = plain(snapshot)
        require(
            all(current[k] == row[k] for k in row if k != "episode_id"),
            f"original history diverged at {snapshot.physics_step}",
        )

    check(backend.current_physics_observation())
    with backend.observe_physics_steps(check):
        for tick in range(ENTRY):
            for command in grouped[tick]:
                prefix.replay_command(backend, command)
            require(backend.step(1).physics_steps == 1, "unexpected prefix step count")
    prefix.entry_phase(backend.command_records)
    stage = read(RAW.parent / "lift-qualification-trace.json")["frames"][0]["state"]
    observed = prefix.derived(backend)
    source_path = prefix.OUT / "native-prefix-01"
    witness = pinned(
        source_path / "witness.json", read(source_path / "seal.json")["witness_sha256"]
    )
    require(
        observed == {k: witness["states"][0][k] for k in observed}
        and prefix.packed(backend).tolist() == stage["integration"],
        "entry differs from the verified original force cache and full packed state",
    )
    return witness["reference_sha256"]


def state_at(backend, prefix):
    return {
        "physics_step": backend.total_physics_steps,
        "integration": prefix.packed(backend).tolist(),
        "qfrc_bias_arm": backend._data.qfrc_bias[:7].tolist(),
        "arm_target": backend._target_positions.tolist(),
        "gripper_open": backend._gripper_open,
    }


def candidate_motion(backend, prefix, reference_sha, result):
    model, data = backend._model, backend._data
    old = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    start = tuple(old["robot"]["tcp_position_m"])
    target = tuple(old["target"][axis] for axis in "xyz")
    path = VerticalClearancePath("mechanics-only", "LIFT", "LIFT", start, target, 0.08)
    reference = QualificationLiftReference(
        backend,
        start,
        target,
        np.array(old["robot"]["tcp_quaternion_wxyz"]),
        control_steps=5,
        timeout_s=8,
        max_velocity=0.5,
        max_acceleration=5 / 3,
        initialize_load_from_feedback=True,
    )
    import hashlib

    h = hashlib.sha256()
    for array in (reference.positions, reference.velocities, reference.accelerations):
        h.update(np.asarray(array, dtype="<f8").tobytes())
    require(h.hexdigest() == reference_sha, "changed nominal candidate reference")
    control_dt = 5 / 240
    command = data.qpos[:7].copy()
    velocity = np.zeros(7)
    range_ids = [model.joint(name).id for name in backend._joint_names]
    lower, upper = model.jnt_range[range_ids].T
    states, snapshots = {}, {}
    peak = start[2]
    old_init = read(prefix.OUT / "reader-1.json")
    original_cmd = read(RAW / "backend-commands.json")[258]
    expected = (
        np.array(original_cmd["target_positions_rad"])
        + old_init["candidate_command_differences_rad"][0]
    )
    for tick in range(ENTRY, REFUSAL + 1):
        snapshot_now = plain(backend.current_physics_observation())
        states[tick], snapshots[tick] = state_at(backend, prefix), snapshot_now
        pairs = {tuple(sorted(x)) for x in snapshot_now["contact_pairs"]}
        result["last_normal_step"] = tick
        tcp = snapshot_now["tcp_position_m"]
        result["maximum_lateral_m"] = max(
            result["maximum_lateral_m"], float(np.linalg.norm(np.array(tcp[:2]) - start[:2]))
        )
        result["maximum_lift_m"] = max(
            result["maximum_lift_m"],
            snapshot_now["object_geom_position_m"][2]
            - snapshots[ENTRY]["object_geom_position_m"][2],
        )
        if ("object_geom", "table") in pairs:
            result["last_table_contact"] = tick
        elif result["first_no_table_contact"] is None:
            result["first_no_table_contact"] = tick
        try:
            path.check_position(tuple(tcp), peak_z=peak)
            peak = max(peak, tcp[2])
            require(
                {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}
                <= pairs
                <= {
                    ("left_finger_geom", "object_geom"),
                    ("object_geom", "right_finger_geom"),
                    ("object_geom", "table"),
                },
                "mechanical bilateral/contact witness failed",
            )
        except ValueError as exc:
            result["normal_rejection"] = {"step": tick, "reason": str(exc)}
            break
        if tick == REFUSAL:
            break
        if (tick - ENTRY) % 5 == 0:
            goal = reference.joint_target(tick - ENTRY, 5)
            desired = np.clip((goal - command) / control_dt, -0.5, 0.5)
            change = np.clip(desired - velocity, -(5 / 3) * control_dt, (5 / 3) * control_dt)
            velocity += change
            command += velocity * control_dt
            require(
                np.isfinite(command).all()
                and np.all(command >= lower + 0.001)
                and np.all(command <= upper - 0.001),
                "candidate target outside original joint bounds",
            )
            if tick == ENTRY:
                require(np.array_equal(command, expected), "candidate first target mismatch")
            backend.apply_joint_targets(JointCommand(positions=command.tolist(), max_velocity=0.5))
            result["commands"].append(
                {"step": tick, "unclipped": goal.tolist(), "command": command.tolist()}
            )
        require(backend.step(1).physics_steps == 1, "candidate integrated off schedule")
        result["applied_drive"].append({"after_step": tick + 1, "ctrl": data.ctrl.tolist()})
        reference.observe_step()
    return states, snapshots


def screen_stops(backend, prefix, helper, asset, snapshots, states, result):
    original_helper = helper.checked_original_helpers()
    motion = MotionGeometry(Model(asset))
    p = ROOT / "scripts/graduation"
    gate = PayloadClearance(
        motion,
        read(p / "g1_complete_cv_payload_profile.json"),
        read(p / "g1_complete_cv_source_motion_profile.json"),
    )
    allowance = gate.source_classes["0.075"][0]
    fixed = PLAN["fixed_source_075_ID8_neg_Z_m"]
    body = motion.names.index("g1_dual_id8_plate")
    require(abs(allowance[body, 5] - fixed) < 1e-12, "frozen fixed challenge changed")
    order = [*PLAN["source_stop_challenge_steps"], *range(ENTRY, 1840)]
    for tick in order:
        anchor_tick = 1840 if tick >= 1840 else tick
        mujoco.mj_setState(
            backend._model,
            backend._data,
            np.asarray(states[anchor_tick]["integration"]),
            prefix.SIG,
        )
        q0, dq0 = backend._data.qpos[None].copy(), backend._data.qvel[None].copy()
        v, _, rel, _ = snapshot(motion, q0, dq0, q0[:, 9:12], object_matrix(q0))
        file = OUT / f"stop-{tick}.npz"
        q, dq, contacts, _ = helper.run_branch(
            backend, original_helper, states[tick], snapshots, file
        )
        world, relative = helper.observed_payload_support(motion, q, dq, (v[0], rel[0]), gate.axes)
        native_speed = float(abs(dq0[0, :7]).max())
        generic = gate.data["LIFT"]["classes"]
        speed_class = next(
            (
                k
                for k in sorted((k for k in generic if k != "all"), key=float)
                if native_speed <= float(k)
            ),
            "all",
        )
        bounds = generic[speed_class]
        allowed_pairs = helper.ALLOWED_FINGERS | {helper.TABLE_PAIR}
        unallowed = next(
            (
                (j, sorted(r.keys() - allowed_pairs))
                for j, r in enumerate(contacts)
                if r.keys() - allowed_pairs
            ),
            None,
        )
        stop = {
            "step": tick,
            "window_anchor_step": anchor_tick,
            "candidate_initial_arm_speed_rad_s": native_speed,
            "nominal_generic_speed_class": speed_class,
            "source_0_075_world_margin": helper.min_reserve(allowance, world, motion.names, AXES),
            "generic_world_margin": helper.min_reserve(bounds["world"], world, motion.names, AXES),
            "relative_margin": helper.min_reserve(
                bounds["relative"], relative, motion.names, gate.axes
            ),
            "fixed_ID8_negative_Z_margin_m": float(fixed - world[body, 5]),
            "ID8_negative_Z_measured_m": float(world[body, 5]),
            "archive_sha256": sha(file),
            "non_permitted_contact": unallowed,
        }
        result["stops"].append(stop)
        if unallowed or any(
            stop[k]["margin_m"] < 0
            for k in ("source_0_075_world_margin", "generic_world_margin", "relative_margin")
        ):
            result["stop_rejection"] = stop
            break


def main():
    allocation, commands, truth, reset = source_inputs()
    prefix = local_import("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    helper = local_import("round-g1-t01-lift55-native-qualification-20261126", "stop_readback.py")
    previous = local_import(
        "round-g1-t01-lift-compensation-admission-20261126", "read_compensation.py"
    )
    OUT.mkdir()
    native = OUT / "native"
    native.mkdir()
    cfg = allocation["case"]
    asset = ROOT / cfg["asset_path"]
    require(
        cfg["view"] == "nominal" and sha(asset) == allocation["asset_sha256"],
        "wrong physical assembly",
    )
    result = {
        "source_sha256": sha(Path(__file__)),
        "plan_sha256": sha(HERE / "plan.json"),
        "old_stop_witness": previous.check_stop(asset),
        "maximum_lateral_m": 0.0,
        "maximum_lift_m": 0.0,
        "first_no_table_contact": None,
        "last_table_contact": None,
        "normal_rejection": None,
        "stop_rejection": None,
        "stops": [],
        "commands": [],
        "applied_drive": [],
        "capture_requests": 0,
        "owner_claims": 0,
        "live_qualification_authorized_by_cpu": False,
        "cpu_mechanics_screen_passed": False,
    }
    backend = RegisteredAssemblyBackend(native, cfg)
    try:
        with patch.multiple(mujoco, Renderer=prefix.prohibited, mjr_render=prefix.prohibited):
            backend.initialize(
                SimulatorConfig(
                    model_path=str(asset),
                    seed=cfg["visual_seed"],
                    physics_dt_s=1 / 240,
                    render_rgb=True,
                    render_depth=True,
                    domain_randomization=False,
                )
            )
            with prefix.no_render_context()(backend, backend.shutdown):
                digest = cpu_entry(backend, prefix, commands, truth, reset)
                states, snap = candidate_motion(backend, prefix, digest, result)
                write(OUT / "candidate-normal.json", {"states": states, "samples": snap})
                if result["normal_rejection"] is None:
                    screen_stops(backend, prefix, helper, asset, snap, states, result)
                    result["cpu_mechanics_screen_passed"] = result["stop_rejection"] is None
    except BaseException as exc:
        result["execution_failure"] = str(exc)
        raise
    finally:
        write(OUT / "result.json", result)


if __name__ == "__main__":
    main()
