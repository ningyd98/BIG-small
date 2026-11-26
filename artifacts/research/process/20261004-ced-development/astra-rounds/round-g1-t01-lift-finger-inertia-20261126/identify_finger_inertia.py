"""Observe one measured finger-inertia change through the original LIFT command chain."""

import argparse
import importlib.util
import sys
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

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
ENTRY, END = 1632, 1848
DT = 5 / 240
SOURCE_CHALLENGE = 1840
FINGER_NAMES = ("finger_left_joint", "finger_right_joint")
FINGERS = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}
TABLE = ("object_geom", "table")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def import_round(label, name):
    path = HERE.parent / label / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong import root")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for name, expected in PLAN["sha256"].items():
        require(sha(REPO / name) == expected, f"sealed input changed: {name}")
    receipt = read(RAW / "receipt.json")
    allocation = pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"])
    commands = pinned(RAW / "backend-commands.json", receipt["full_commands_sha256"])
    seal = pinned(RAW / "acquisition-seal.json", receipt["capture_sha256"])
    truth = pinned(RAW / "offline-truth.json", seal["truth_sha256"])["samples"]
    resets = pinned(RAW / "reset-observed.json", receipt["reset_sha256"])
    return allocation, commands, truth, resets[0]["parameters"]["requested"]


def finger_indices(model):
    indices = np.array([int(model.joint(name).dofadr[0]) for name in FINGER_NAMES])
    require(
        indices.tolist() == [7, 8]
        and int(model.joint("object_free").dofadr[0]) == 9
        and model.nv == 15,
        "original finger/free DOF mapping changed",
    )
    return indices


def restrict_command(sent, velocity, goal):
    desired = np.clip((goal - sent) / DT, -0.5, 0.5)
    change = np.clip(desired - velocity, -(5 / 3) * DT, (5 / 3) * DT)
    velocity += change
    sent += velocity * DT


def cold(asset, truth):
    model = mujoco.MjModel.from_xml_path(str(asset))
    witness = pinned(REPO / PLAN["witness"], PLAN["sha256"][PLAN["witness"]])
    positions, speed, accel = map(np.asarray, witness["reference"])
    gain, damping = np.asarray(witness["gains"]), np.asarray(witness["damping"])
    lo, hi = np.asarray(witness["arm_ctrl_range"]).T
    states = witness["states"]
    require(len(states) == 217 and states[0]["physics_step"] == ENTRY, "wrong witness range")
    fb_trace = read(REPO / PLAN["old_force_buffers"])["phases"]
    matrix = np.empty((model.nv, model.nv))
    finger = finger_indices(model)
    zero = np.zeros(7)
    old, new = zero.copy(), zero.copy()
    old_sent = np.array(states[0]["qr"])
    sent = old_sent.copy()
    old_dq = zero.copy()
    dq = zero.copy()
    records = []
    first = None
    correction_peak = (0.0, ENTRY)
    for k, row in enumerate(states[:-1]):
        step = ENTRY + k
        require(step == row["physics_step"] == truth[step]["physics_step"], "wrong source clock")
        mujoco.mj_fullM(model, matrix, np.asarray(row["qM"]))
        require(not np.any(matrix[:7, 9:]), "arm/free-body inertial block no longer zero")
        bias, act, pas, qr, qv = map(
            np.asarray, [row[key] for key in ("bias", "actuator", "passive", "qr", "dq")]
        )
        contribution = zero.copy()
        if k:
            prev = states[k - 1]
            dt = row["time"] - prev["time"]
            require(dt > 0 and row["time"] == truth[step]["sim_time_s"], "mismatched finger clock")
            fv = np.asarray(truth[step]["finger_velocities_m_s"])
            prev_fv = np.asarray(truth[step - 1]["finger_velocities_m_s"])
            block = matrix[:7, finger]
            require(not np.any(block @ ((fv - fv) / dt)), "constant-finger negative failed")
            contribution = block @ ((fv - prev_fv) / dt)
            joint_inertia = matrix[:7, :7] @ ((qv - prev["dq"]) / dt)
            ext = joint_inertia + bias - act - pas
            ext_new = (joint_inertia + contribution) + bias - act - pas
            weight = min(1.0, dt / 0.03)
            old += weight * (ext - old)
            new += weight * (ext_new - new)
        correction_peak = max(correction_peak, (float(abs(contribution).max()), step))
        if k % 5 == 0:
            idx = k // 5
            nominal = damping * speed[idx] + matrix[:7, :7] @ accel[idx]
            g0 = positions[idx] + (nominal - old) / gain
            g1 = positions[idx] + (nominal - new) / gain
            restrict_command(old_sent, old_dq, g0)
            restrict_command(sent, dq, g1)
            delta = sent - old_sent
            records.append(
                {
                    "step": step,
                    "unclipped_baseline_rad": g0.tolist(),
                    "unclipped_candidate_rad": g1.tolist(),
                    "sent_change_rad": delta.tolist(),
                    "filtered_estimate_change_nm": (new - old).tolist(),
                }
            )
            if (
                first is None
                and (abs(delta) > PLAN["cold"]["prospective_comparison_atol_rad"]).any()
            ):
                first = {
                    "step": step,
                    "difference_rad": delta.tolist(),
                    "target_rad": sent.tolist(),
                }
        ctrl = np.clip(qr + np.clip(old_sent - qr, -0.10, 0.10) + bias / gain, lo, hi)
        require(
            np.array_equal(old_sent, row["real_arm_target"])
            and np.array_equal(np.r_[ctrl, row["finger_ctrl"]], row["real_ctrl"]),
            f"original cold command or drive diverged at {step}",
        )
    return {
        "original_commands": len(records),
        "original_applied_drives": len(states) - 1,
        "measured_difference_peak_nm_and_step": correction_peak,
        "first_difference": first,
        "same_phase_original_coupling_anchor_nm": fb_trace["baseline"]["normal"][208][
            "arm_other_dof_coupling_nm"
        ],
        "feedback_initialization_magnitude_reference_nm": fb_trace["feedback_init"]["normal"][208][
            "arm_other_dof_coupling_nm"
        ],
        "prior_feedback_init_lacks_same_phase_finger_fd_matrix": True,
        "commands": records,
    }


class FingerInertiaReference(QualificationLiftReference):
    """One extension of the frozen encoder-based estimate for this CPU intervention."""

    def __init__(self, backend, *args, **kwargs):
        super().__init__(backend, *args, **kwargs)
        self.fingers = finger_indices(backend._model)
        self.previous_fingers = backend._data.qvel[self.fingers]

    def observe_step(self):
        b = self.backend
        d, m = b._data, b._model
        dt = float(d.time) - self.previous_time
        require(dt > 0, "non-advancing finger estimate clock")
        mujoco.mj_fullM(m, self.mass, d.qM)
        dv = (d.qvel[:7] - self.previous_velocity) / dt
        fingers = d.qvel[self.fingers]
        df = (fingers - self.previous_fingers) / dt
        inertial = (self.mass[:7, :7] @ dv) + (self.mass[:7, self.fingers] @ df)
        external = inertial + d.qfrc_bias[:7] - d.qfrc_actuator[:7] - d.qfrc_passive[:7]
        self.disturbance += min(1.0, dt / 0.03) * (external - self.disturbance)
        self.previous_velocity = d.qvel[:7].copy()
        self.previous_fingers = fingers
        self.previous_time = float(d.time)


def candidate_motion(b, paired, prefix, prospective):
    old = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    src = tuple(old["robot"]["tcp_position_m"])
    dst = tuple(old["target"][a] for a in "xyz")
    path = VerticalClearancePath("finger-identification", "LIFT", "LIFT", src, dst, 0.08)
    orient = np.array(old["robot"]["tcp_quaternion_wxyz"])
    ref = FingerInertiaReference(
        b,
        src,
        dst,
        orient,
        control_steps=5,
        timeout_s=8,
        max_velocity=0.5,
        max_acceleration=5 / 3,
        initialize_load_from_feedback=False,
    )
    lower, upper = b._model.jnt_range[:7].T
    sent, velocity = b._data.qpos[:7].copy(), np.zeros(7)
    actual = None
    saves = []
    snapshots = {}
    z_peak = src[2]
    source_cmd = read(RAW / "backend-commands.json")
    commands = {
        c["physics_step"]: c["target_positions_rad"]
        for c in source_cmd
        if ENTRY <= c["physics_step"] < END and c["type"] == "joint_target"
    }
    for tick in range(ENTRY, END + 1):
        row = plain(b.current_physics_observation())
        p = row["tcp_position_m"]
        path.check_position(tuple(p), peak_z=z_peak)
        z_peak = max(z_peak, p[2])
        pairs = {tuple(sorted(x)) for x in row["contact_pairs"]}
        require(
            FINGERS <= pairs <= FINGERS | {TABLE}, f"candidate normal contact refusal at {tick}"
        )
        snapshots[tick] = row
        if tick == SOURCE_CHALLENGE:
            actual = paired.clone_context(b, prefix)
        if tick == END:
            break
        if (tick - ENTRY) % 5 == 0:
            g = ref.joint_target(tick - ENTRY, 5)
            restrict_command(sent, velocity, g)
            require(
                np.all(sent >= lower + 0.001) and np.all(sent <= upper - 0.001),
                f"candidate limit at {tick}",
            )
            if tick < prospective["step"]:
                require(
                    np.array_equal(sent, commands[tick]), "early divergence from sealed command"
                )
            if tick == prospective["step"]:
                require(
                    np.allclose(sent, prospective["target_rad"], rtol=0, atol=1e-12),
                    "first candidate command contradicts the cold comparison",
                )
            saves.append({"step": tick, "unclipped_rad": g.tolist(), "sent_rad": sent.tolist()})
            b.apply_joint_targets(JointCommand(positions=sent.tolist(), max_velocity=0.5))
        require(b.step(1).physics_steps == 1, "unexpected candidate step")
        ref.observe_step()
    return actual, snapshots, saves


def capture_stop(b, helper, asset, file):
    motion = MotionGeometry(Model(asset))
    q, dq, ct, rows = [], [], [], []
    b.emergency_stop()
    require(
        [c["type"] for c in b.command_records[-2:]] == ["hold_current_joints", "emergency_stop"],
        "native HOLD order changed",
    )
    for k in range(241):
        d = b._data
        sample = plain(b.current_physics_observation())
        q.append(d.qpos.copy())
        dq.append(d.qvel.copy())
        ct.append(d.ctrl.copy())
        rows.append(sample["contact_pairs"])
        if k < 240:
            require(b.step(1).physics_steps == 1, "unexpected stop step")
    q, dq, ct = np.array(q), np.array(dq), np.array(ct)
    with file.open("xb") as f:
        np.savez_compressed(f, q=q, qvel=dq, ctrl=ct)
    box, _, rel, _ = snapshot(motion, q[:1], dq[:1], q[:1, 9:12], object_matrix(q[:1]))
    base = ROOT / "scripts/graduation"
    gate = PayloadClearance(
        motion,
        read(base / "g1_complete_cv_payload_profile.json"),
        read(base / "g1_complete_cv_source_motion_profile.json"),
    )
    world, relative = helper.observed_payload_support(motion, q, dq, (box[0], rel[0]), gate.axes)
    body = motion.names.index("g1_dual_id8_plate")
    source = gate.source_classes["0.075"][0]
    generic = gate.data["LIFT"]["classes"]["0.075"]
    contact_refusal = next(
        (i for i, r in enumerate(rows) if not {tuple(sorted(p)) for p in r} <= FINGERS | {TABLE}),
        None,
    )
    lateral_speed = float(abs(dq[0, :7]).max())
    require(source[body, 5] == PLAN["fixed_stop"]["negative_Z_allowance_m"], "changed source bound")
    result = {
        "ID8_downward_m": float(world[body, 5]),
        "source_world_reserve": helper.min_reserve(source, world, motion.names, AXES),
        "generic_world_reserve": helper.min_reserve(generic["world"], world, motion.names, AXES),
        "relative_reserve": helper.min_reserve(
            generic["relative"], relative, motion.names, gate.axes
        ),
        "arm_speed_at_stop_rad_s": lateral_speed,
        "first_forbidden_contact_stop_tick": contact_refusal,
        "stopped_archive_sha256": sha(file),
    }
    return result, rows


def screen(allocation, commands, truth, reset, asset):
    paths = [OUT / f"reader-{i}.json" for i in (1, 2)]
    require(paths[0].read_bytes() == paths[1].read_bytes(), "independent cold forecasts differ")
    forecast = read(paths[0])["result"]["first_difference"]
    require(forecast is not None, "cold read showed no real change to arm commands")
    prefix = import_round("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    parent = import_round(
        "round-g1-t01-lift55-force-init-qualification-20261126", "screen_force_initialization.py"
    )
    paired = import_round(
        "round-g1-t01-lift-stop-motion-decomposition-20261126", "read_stop_dynamics.py"
    )
    helper = import_round("round-g1-t01-lift55-native-qualification-20261126", "stop_readback.py")
    dest = OUT / "mechanics"
    dest.mkdir()
    cfg = allocation["case"]
    b = RegisteredAssemblyBackend(dest, cfg)
    try:
        with patch.multiple(mujoco, Renderer=prefix.prohibited, mjr_render=prefix.prohibited):
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
            with prefix.no_render_context()(b, b.shutdown):
                parent.cpu_entry(b, prefix, commands, truth, reset)
                candidate_entry = paired.clone_context(b, prefix)
                frozen = read(RAW.parent / "lift-qualification-trace.json")
                drive = {
                    r["physics_step"]: {"ctrl": r["ctrl"], "command": r["arm_target"]}
                    for r in frozen["before_integrations"]
                }
                _, base_stop = paired.normal(b, truth, drive, False, prefix)
                paired.enter_context(b, base_stop)
                original = paired.stop_dynamics(b, REPO / PLAN["original_stop"])
                paired.enter_context(b, candidate_entry)
                stop, rows, sent = candidate_motion(b, paired, prefix, forecast)
                paired.enter_context(b, stop)
                result, contacts = capture_stop(b, helper, asset, dest / "candidate-stop.npz")
                write(
                    dest / "raw-candidate.json",
                    {"normal": rows, "sent": sent, "stop_contacts": contacts},
                )
                result["original_stop_states_exactly_reproduced"] = len(original)
        return result
    except BaseException as error:
        write(dest / "failure.json", {"reason": str(error)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("cold", "mechanical"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    allocation, commands, truth, reset = inputs()
    asset = ROOT / allocation["case"]["asset_path"]
    require(sha(asset) == allocation["asset_sha256"], "changed assembly")
    OUT.mkdir(exist_ok=True)
    if args.mode == "cold":
        result, dest = cold(asset, truth), OUT / f"{args.reader}.json"
    else:
        result = screen(allocation, commands, truth, reset, asset)
        dest = OUT / "result.json"
    write(
        dest,
        {
            "result": result,
            "plan_sha256": sha(HERE / "plan.json"),
            "source_sha256": sha(Path(__file__)),
            "new_exposures": 0,
        },
    )


if __name__ == "__main__":
    main()
