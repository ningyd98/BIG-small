"""Replay the frozen mechanical path and sample only six original-HOLD branches."""

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
    positive_support,
    snapshot,
)
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
SLOTS = PLAN["profile"]
BODY = "g1_dual_id8_plate"
TABLE = ("object_geom", "table")
FINGERS = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def tool(label, name):
    p = HERE.parent / label / name
    spec = importlib.util.spec_from_file_location(p.stem, p)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(p.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def verify():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong original runtime import")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for file, expected in PLAN["sha256"].items():
        require(sha(REPO / file) == expected, "source changed: " + file)


def original_path(b, authority, paired, prefix, truth):
    path, quat = authority.path_contract()
    ref = QualificationLiftReference(
        b,
        path.start_m,
        path.target_m,
        quat,
        control_steps=5,
        timeout_s=8,
        max_velocity=0.5,
        max_acceleration=5 / 3,
        initialize_load_from_feedback=False,
    )
    recovered = {row["physics_step"]: row for row in read(REPO / PLAN["mechanical_route"])["rows"]}
    old = read(RAW.parent / "lift-qualification-trace.json")
    original_packed = {r["physics_step"]: r for r in old["before_integrations"]}
    entry_frames = {r["state"]["physics_step"]: r["state"] for r in old["frames"]}
    cmd = read(RAW / "backend-commands.json")
    target = {
        r["physics_step"]: r["target_positions_rad"]
        for r in cmd
        if 1632 <= r["physics_step"] < 1848 and r["type"] == "joint_target"
    }
    angles, velocity = b._data.qpos[:7].copy(), np.zeros(7)
    bounds = b._model.jnt_range[:7]
    saved = {}
    actual = 0
    emitted = 0
    peak_z = path.start_m[2]

    def observe(event):
        nonlocal actual
        k = event.physics_step - 1
        if k in original_packed:
            original = original_packed[k]
            require(
                prefix.packed(b).tolist() == original["integration"]
                and b._data.ctrl.tolist() == original["ctrl"],
                f"original applied drive or state did not close at {k}",
            )
            actual += 1

    with b.observe_actuator_steps(observe):
        for k in range(1632, 2282):
            row = plain(b.current_physics_observation())
            require(
                authority.same_state(recovered[k], row), f"counterfactual main trace drift at {k}"
            )
            if k <= 1848:
                require(authority.same_state(truth[k], row), f"true original state mismatch at {k}")
                if k in entry_frames:
                    original = entry_frames[k]
                    require(
                        prefix.packed(b).tolist() == original["integration"]
                        and b._data.qfrc_bias[:7].tolist() == original["qfrc_bias_arm"]
                        and b._target_positions.tolist() == original["arm_target"]
                        and len(b.command_records) == original["command_count"],
                        f"original exact cache or phase differs at {k}",
                    )
            reason = authority.mechanical_check(row, path, peak_z, k > 1848, bounds)
            require(reason is None, f"mechanical main trace differs at {k}: {reason}")
            peak_z = max(peak_z, row["tcp_position_m"][2])
            if k in SLOTS:
                require(
                    not b._pending_joint_targets and not b.estop_engaged,
                    f"unexpected command queue or stop flag at {k}",
                )
                saved[k] = paired.clone_context(b, prefix)
            if k == 2281:
                break
            if (k - 1632) % 5 == 0:
                goal = ref.joint_target(k - 1632, 5)
                needed = np.clip((goal - angles) / (5 / 240), -0.5, 0.5)
                velocity += np.clip(needed - velocity, -(5 / 3) * (5 / 240), (5 / 3) * (5 / 240))
                angles += velocity * (5 / 240)
                if k < 1848:
                    require(angles.tolist() == target[k], f"original arm command mismatch at {k}")
                    emitted += 1
                b.apply_joint_targets(JointCommand(positions=angles.tolist(), max_velocity=0.5))
            require(b.step(1).physics_steps == 1, "unexpected path integration")
            ref.observe_step()
    require(
        actual == 216 and emitted == 44 and list(saved) == SLOTS, "incomplete main-path evidence"
    )
    return saved, recovered


def branch(b, tick, dest):
    states, speeds, drives, pairs = [], [], [], []
    positions, rotations, times = [], [], []
    commands_before = len(b.command_records)
    q0 = b._data.qpos[:7].copy()
    b.emergency_stop()
    require(
        [r["type"] for r in b.command_records[commands_before:]]
        == ["hold_current_joints", "emergency_stop"]
        and np.array_equal(b._target_positions, q0)
        and b._pending_joint_targets == []
        and b.estop_engaged
        and not b._gripper_open,
        f"nonoriginal stop contract at {tick}",
    )
    for dt in range(241):
        d = b._data
        states.append(d.qpos.copy())
        speeds.append(d.qvel.copy())
        drives.append(d.ctrl.copy())
        positions.append(d.geom_xpos.copy())
        rotations.append(d.geom_xmat.copy())
        times.append(float(d.time))
        require(b.total_physics_steps == tick + dt, "wrong absolute branch tick")
        pairs.append([sorted(p) for p in plain(b.current_physics_observation())["contact_pairs"]])
        if dt < 240:
            require(b.step(1).physics_steps == 1, "off-grid stop branch")
    states, speeds, drives = map(np.asarray, (states, speeds, drives))
    if tick == 1840:
        with np.load(REPO / PLAN["source_stop_reference"], allow_pickle=False) as f:
            require(
                np.array_equal(states, f["q"])
                and np.array_equal(speeds, f["qvel"])
                and np.array_equal(drives, f["ctrl"]),
                "first stop witness differs from frozen 1840 q/dq/ctrl",
            )
            names, counts = f["pair_names"].tolist(), f["contact_counts"]
            require(
                all(
                    all(pair in names for pair in sample)
                    and [sample.count(n) for n in names] == count.tolist()
                    for sample, count in zip(pairs, counts, strict=True)
                ),
                "first stop witness differs in frozen contact multiplicity",
            )
    raw = dest / f"stop-{tick}.npz"
    with raw.open("xb") as f:
        np.savez_compressed(
            f,
            q=states,
            qvel=speeds,
            ctrl=drives,
            time_s=times,
            geom_positions_m=positions,
            geom_rotations=rotations,
        )
    contacts = dest / f"stop-{tick}-contacts.json"
    write(contacts, pairs)
    return {
        "state_file": raw.name,
        "state_sha256": sha(raw),
        "contact_file": contacts.name,
        "contact_sha256": sha(contacts),
    }


def run():
    authority = tool(
        "round-g1-t01-lift-mechanical-authority-20261126", "original_lift_mechanical_bound.py"
    )
    prefix = tool("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    helper = tool(
        "round-g1-t01-lift55-force-init-qualification-20261126", "screen_force_initialization.py"
    )
    pair = tool("round-g1-t01-lift-stop-motion-decomposition-20261126", "read_stop_dynamics.py")
    allocation, commands, truth, reset = helper.source_inputs()
    dest = OUT / "native"
    dest.mkdir()
    cfg = allocation["case"]
    asset = ROOT / cfg["asset_path"]
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
                geom_names = [b._model.geom(i).name for i in range(b._model.ngeom)]
                helper.cpu_entry(b, prefix, commands, truth, reset)
                anchors, recovered = original_path(b, authority, pair, prefix, truth)
                initial_load = recovered[1632]["object_geom_position_m"][2]
                for h, k in PLAN["height_to_first_tick"].items():
                    hit = next(
                        row["physics_step"]
                        for row in recovered.values()
                        if row["object_geom_position_m"][2] - initial_load >= float(h)
                    )
                    require(hit == k, "height cross lost its predeclared phase")
                index = {}
                for tick, state in anchors.items():
                    pair.enter_context(b, state)
                    row = branch(b, tick, dest)
                    row["starting_load_lift_m"] = (
                        recovered[tick]["object_geom_position_m"][2] - initial_load
                    )
                    index[str(tick)] = row
    except BaseException as error:
        write(dest / "failure.json", {"reason": str(error)})
        raise
    write(
        dest / "seal.json",
        {
            "source_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "cpu_steps": 2281 + 6 * 240,
            "camera": 0,
            "original_commands_exact": 44,
            "original_controls_exact": 216,
            "branches": index,
            "geom_names": geom_names,
        },
    )


def cold(reader):
    d = OUT / "native"
    seal = read(d / "seal.json")
    require(
        seal["source_sha256"] == sha(Path(__file__))
        and seal["plan_sha256"] == sha(HERE / "plan.json"),
        "stale stop profile",
    )
    alloc = read(RAW.parent / "allocation.json")
    model = MotionGeometry(Model(ROOT / alloc["case"]["asset_path"]))
    p = ROOT / "scripts/graduation"
    guard = PayloadClearance(
        model,
        read(p / "g1_complete_cv_payload_profile.json"),
        read(p / "g1_complete_cv_source_motion_profile.json"),
    )
    figure = model.names.index(BODY)
    result = []
    for tick in SLOTS:
        row = seal["branches"][str(tick)]
        path = d / row["state_file"]
        require(sha(path) == row["state_sha256"], "altered stop file")
        contacts = pinned(d / row["contact_file"], row["contact_sha256"])
        with np.load(path, allow_pickle=False) as f:
            q, dq = f["q"], f["qvel"]
            count = len(seal["geom_names"])
            require(
                np.allclose(f["time_s"], (tick + np.arange(241)) / 240, atol=1e-9, rtol=0)
                and f["geom_positions_m"].shape == (241, count, 3)
                and f["geom_rotations"].shape == (241, count, 9)
                and np.isfinite(f["geom_positions_m"]).all()
                and np.isfinite(f["geom_rotations"]).all()
                and len(contacts) == 241,
                f"missing or invalid original geometry or time at {tick}",
            )
        position, rate, relative, rel_rate = snapshot(model, q, dq, q[:, 9:12], object_matrix(q))
        shifts = position[0, figure, :, 2] - position[:, figure, :, 2]
        step, corner = np.unravel_index(shifts.argmax(), shifts.shape)
        origin = float(q[0, 11] - q[step, 11])
        bound = positive_support(position, rate, position[0], AXES)
        rel_bound = positive_support(relative, rel_rate, relative[0], guard.axes)
        measured = float(bound[figure, 5])
        pairs = [set(map(tuple, c)) for c in contacts]
        source_touch = next((i for i, c in enumerate(pairs) if TABLE in c), None)
        prohibited = next((i for i, c in enumerate(pairs) if c - FINGERS - {TABLE}), None)
        lost = next((i for i, c in enumerate(pairs) if not FINGERS <= c), None)
        item = {
            "tick": tick,
            "workpiece_lift_at_anchor_m": row["starting_load_lift_m"],
            "ID8_downward_bound_m": measured,
            "ID8_downward_actual_endpoint_m": float(shifts[step, corner]),
            "worst_endpoint_tick": int(step),
            "corner": int(corner),
            "endpoint_origin_down_m": origin,
            "endpoint_rotation_down_m": float(shifts[step, corner] - origin),
            "between_sample_allowance_m": measured - float(shifts[step, corner]),
            "diagnostic_difference_from_original_ID8_limit_m": measured - 0.00261485,
            "first_table_touch_stop_tick": source_touch,
            "first_unauthorized_contact_stop_tick": prohibited,
            "first_no_bilateral_stop_tick": lost,
            "initial_arm_speed_rad_s": float(abs(dq[0, :7]).max()),
            "initial_workpiece_linear_velocity_m_s": dq[0, 9:12].tolist(),
            "initial_workpiece_angular_velocity_rad_s": dq[0, 12:15].tolist(),
            "max_world_travel_by_part_m": dict(
                zip(model.names, bound.max(axis=1).tolist(), strict=True)
            ),
            "max_arm_in_workpiece_frame_travel_by_part_m": dict(
                zip(model.names[: model.load_start], rel_bound.max(axis=1).tolist(), strict=True)
            ),
            "applied_optical_grade": None,
        }
        if tick == 1840:
            w = guard.source_classes["0.075"][0]
            a = guard.data["LIFT"]["classes"]["0.075"]
            item.update(
                certificate_status="ORIGINAL_ACCEPTED_FRAME_WITH_OFFLINE_UNDERCOVERAGE",
                source_world_reserve_m=float((w - bound).min()),
                generic_world_reserve_m=float((a["world"] - bound).min()),
                relative_reserve_m=float((a["relative"] - rel_bound).min()),
            )
            require(abs(measured - 0.002777251732861987) < 1e-12, "unmatched original stop value")
        else:
            item.update(certificate_status="NOT_ESTABLISHED_NO_LIVE_QUALIFICATION")
        result.append(item)
    write(
        OUT / f"{reader}.json",
        {
            "result": result,
            "cpu_steps": seal["cpu_steps"],
            "seal_sha256": sha(d / "seal.json"),
            "new_exposures": 0,
            "plan_sha256": seal["plan_sha256"],
            "source_sha256": seal["source_sha256"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "read"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    verify()
    OUT.mkdir(exist_ok=True)
    if args.mode == "run":
        run()
    else:
        cold(args.reader)
