"""Reproduce original t01, then measure the bounded no-vision counterfactual."""

import argparse
import importlib.util
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.g1_lift55_qualification import QualificationLiftReference
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
ENTRY = PLAN["entry_step"]
OPTICAL_STOP = PLAN["real_optical_refusal_step"]
LIMIT = PLAN["first_unavailable_vision_dependent_control_step"]
DT = 5 / 240
FINGERS = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}
TABLE = ("object_geom", "table")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def module(label, filename):
    path = HERE.parent / label / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def verify_inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen import root")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for file, expected in PLAN["sha256"].items():
        require(sha(REPO / file) == expected, "source changed: " + file)


def path_contract():
    seed = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    start = tuple(seed["robot"]["tcp_position_m"])
    target = tuple(seed["target"][a] for a in "xyz")
    orientation = np.asarray(seed["robot"]["tcp_quaternion_wxyz"])
    path = VerticalClearancePath("t01-no-vision-bound", "LIFT", "LIFT", start, target, 0.08)
    return path, orientation


def same_state(expected, row):
    return {k: v for k, v in expected.items() if k != "episode_id"} == {
        k: v for k, v in row.items() if k != "episode_id"
    }


def mechanical_check(row, contract, peak_z, is_after_refusal, bounds):
    tcp = tuple(row["tcp_position_m"])
    values = [*tcp, *row["joint_positions_rad"], *row["object_geom_position_m"]]
    try:
        require(np.isfinite(values).all(), "nonfinite physical observation")
        contract.check_position(tcp, peak_z=peak_z)
        pairs = {tuple(sorted(pair)) for pair in row["contact_pairs"]}
        require(FINGERS <= pairs, "lost bilateral workpiece contact")
        require(pairs <= FINGERS | {TABLE}, "forbidden contact")
        if is_after_refusal and TABLE in pairs:
            return "source table recontact while new source authorization is unavailable"
        q = np.asarray(row["joint_positions_rad"])
        require(np.all(q >= bounds[:, 0]) and np.all(q <= bounds[:, 1]), "arm joint limit")
    except ValueError as error:
        return str(error)
    return None


def readout(rows, bounds):
    contract, _ = path_contract()
    original = rows[0]
    peak_z = original["tcp_position_m"][2]
    z0 = original["object_geom_position_m"][2]
    t0 = peak_z
    lift_peak = tcp_peak = 0.0
    before = None
    milestones = {}
    reason = None
    for index, row in enumerate(rows):
        step = row["physics_step"]
        require(step == ENTRY + index, "missing mechanical sample")
        reason = mechanical_check(row, contract, peak_z, step > OPTICAL_STOP, bounds)
        lift = row["object_geom_position_m"][2] - z0
        tcp_delta = row["tcp_position_m"][2] - t0
        if reason is not None:
            break
        peak_z = max(peak_z, row["tcp_position_m"][2])
        lift_peak, tcp_peak = max(lift_peak, lift), max(tcp_peak, tcp_delta)
        for level in PLAN["workpiece_thresholds_m"]:
            if lift >= level and str(level) not in milestones:
                milestones[str(level)] = step
        if lift >= PLAN["workpiece_thresholds_m"][-1]:
            reason = "original counterfactual mechanical path reached 50 mm"
            break
        before = row
    require(index == len(rows) - 1, "traces advanced beyond the first allowed terminal state")
    return {
        "reason": reason or "visual-dependent completion decision not evaluated",
        "last_step": rows[-1]["physics_step"],
        "previous_safe_step": before["physics_step"] if before else None,
        "last_workpiece_height_delta_m": lift,
        "last_tcp_height_delta_m": tcp_delta,
        "terminal_tcp_lateral_m": float(
            np.linalg.norm(np.asarray(row["tcp_position_m"][:2]) - contract.start_m[:2])
        ),
        "maximum_mechanically_valid_workpiece_lift_m": lift_peak,
        "maximum_mechanically_valid_tcp_lift_m": tcp_peak,
        "first_workpiece_milestones": milestones,
        "physically_exercised_refusal_phase": "CPU_ONLY_FROM_1848_BEFORE_LIVE_STOP",
    }


def run():
    prefix = module("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    helper = module(
        "round-g1-t01-lift55-force-init-qualification-20261126", "screen_force_initialization.py"
    )
    allocation, commands, truth, reset = helper.source_inputs()
    cfg = allocation["case"]
    asset = ROOT / cfg["asset_path"]
    require(sha(asset) == allocation["asset_sha256"], "wrong original asset")
    dest = OUT / "continuation"
    dest.mkdir()
    b = RegisteredAssemblyBackend(dest, cfg)
    rows = []
    actual, reconstructed = 0, 0
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
                helper.cpu_entry(b, prefix, commands, truth, reset)
                expect = read(RAW.parent / "lift-qualification-trace.json")
                operations = {x["physics_step"]: x for x in expect["before_integrations"]}
                snapshots = {x["state"]["physics_step"]: x["state"] for x in expect["frames"]}
                by_step = {
                    x["physics_step"]: x
                    for x in commands
                    if x["type"] == "joint_target" and ENTRY <= x["physics_step"] < OPTICAL_STOP
                }
                contract, rot = path_contract()
                ref = QualificationLiftReference(
                    b,
                    contract.start_m,
                    contract.target_m,
                    rot,
                    control_steps=5,
                    timeout_s=8,
                    max_velocity=0.5,
                    max_acceleration=5 / 3,
                    initialize_load_from_feedback=False,
                )
                sent, velocity = b._data.qpos[:7].copy(), np.zeros(7)
                arm_bounds = b._model.jnt_range[:7].copy()
                peak = contract.start_m[2]
                z0 = truth[ENTRY]["object_geom_position_m"][2]

                def check_drive(event):
                    nonlocal actual
                    k = event.physics_step - 1
                    data = b._data
                    if k < OPTICAL_STOP:
                        old = operations[k]
                        require(
                            data.ctrl.tolist() == old["ctrl"]
                            and prefix.packed(b).tolist() == old["integration"],
                            f"original effective drive differs at {k}",
                        )
                        actual += 1
                    low, high = b._model.actuator_ctrlrange.T
                    require(
                        np.isfinite(data.ctrl).all()
                        and np.all(data.ctrl >= low)
                        and np.all(data.ctrl <= high),
                        f"drive limit at {k}",
                    )

                with b.observe_actuator_steps(check_drive):
                    for k in range(ENTRY, LIMIT + 1):
                        row = plain(b.current_physics_observation())
                        rows.append(row)
                        if k <= OPTICAL_STOP:
                            require(same_state(truth[k], row), f"original physical mismatch at {k}")
                            if k in snapshots:
                                old = snapshots[k]
                                require(
                                    prefix.packed(b).tolist() == old["integration"]
                                    and b._data.qfrc_bias[:7].tolist() == old["qfrc_bias_arm"]
                                    and len(b.command_records) == old["command_count"],
                                    f"original pre-exposure state mismatch at {k}",
                                )
                        if mechanical_check(row, contract, peak, k > OPTICAL_STOP, arm_bounds):
                            break
                        peak = max(peak, row["tcp_position_m"][2])
                        if row["object_geom_position_m"][2] - z0 >= 0.05 or k == LIMIT:
                            break
                        if (k - ENTRY) % 5 == 0:
                            goal = ref.joint_target(k - ENTRY, 5)
                            desired = np.clip((goal - sent) / DT, -0.5, 0.5)
                            velocity += np.clip(desired - velocity, -(5 / 3) * DT, (5 / 3) * DT)
                            sent += velocity * DT
                            require(
                                np.all(sent >= arm_bounds[:, 0] + 0.001)
                                and np.all(sent <= arm_bounds[:, 1] - 0.001),
                                f"relative joint command beyond original range at {k}",
                            )
                            if k < OPTICAL_STOP:
                                require(
                                    sent.tolist() == by_step[k]["target_positions_rad"],
                                    f"original ordinary command mismatch at {k}",
                                )
                                reconstructed += 1
                            b.apply_joint_targets(
                                JointCommand(positions=sent.tolist(), max_velocity=0.5)
                            )
                        require(b.step(1).physics_steps == 1, "unexpected mechanical step count")
                        ref.observe_step()
                require(actual == 216 and reconstructed == 44, "original LIFT prefix incomplete")
                require(b._camera is None and b.total_physics_steps <= LIMIT, "scope breach")
    except BaseException as exc:
        write(
            dest / "failure.json",
            {"reason": str(exc), "last_step": (rows[-1]["physics_step"] if rows else 0)},
        )
        raise
    write(
        dest / "trace.json",
        {
            "rows": rows,
            "joint_bounds": arm_bounds.tolist(),
            "original_commands": reconstructed,
            "original_controls": actual,
            "cpu_steps": rows[-1]["physics_step"],
        },
    )
    write(
        dest / "seal.json",
        {
            "trace_sha256": sha(dest / "trace.json"),
            "source_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
        },
    )


def cold(reader):
    dest = OUT / "continuation"
    seal = read(dest / "seal.json")
    require(
        seal["source_sha256"] == sha(Path(__file__))
        and seal["plan_sha256"] == sha(HERE / "plan.json"),
        "missing continuation provenance",
    )
    trace = pinned(dest / "trace.json", seal["trace_sha256"])
    result = readout(trace["rows"], np.asarray(trace["joint_bounds"]))
    write(
        OUT / f"{reader}.json",
        {
            "result": result,
            "seal_sha256": sha(dest / "seal.json"),
            "source_sha256": seal["source_sha256"],
            "plan_sha256": seal["plan_sha256"],
            "original_commands_exact": trace["original_commands"],
            "original_controls_exact": trace["original_controls"],
            "cpu_steps": trace["cpu_steps"],
            "new_optical_qualifications": 0,
            "new_exposures": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "read"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    verify_inputs()
    OUT.mkdir(exist_ok=True)
    if args.mode == "run":
        run()
    else:
        cold(args.reader)
