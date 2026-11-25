"""Registered native A/B replay and independent reduction of RELEASE mechanics."""

import argparse
import gzip
import hashlib
import importlib.util
import inspect
import json
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from importlib.metadata import version
from itertools import product
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import pinned, read, sha, write

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
PLAN_SHA = "b9ae7268cceca2b5cbac2b7f0e78258f343011feb77a5712730eb6d892e2b6db"
PLAN_TEXT_SHA = "0e634cbb3f84fc1033cd19b74ea0eb9bb8b184bc8ccb57e1ab085dfc86216612"
RECOVERY = HERE.parent / "round-g1-release-replay-cleanup-20261126"
RECOVERY_SHA = "bb3d0633ca8a3334b6375af517770af15090af0520093915892b8be10fca28a0"
RECOVERY_TEXT_SHA = "49cdf0f29b77177210cc22c67f02351dba9b55517d5a3c6024fb7e3ead5b39cf"
EMPTY_FRAME = HERE.parent / "round-g1-release-empty-frame-preflight-20261126"
EMPTY_FRAME_SHA = "8bd3caafcb31f352acd83e2cb217ce6913c4d70958ef0d93dc625fb8fe54ef78"
EMPTY_FRAME_TEXT_SHA = "3d8ebaeaac5e0971e79a7655eaece8d13b4d5a180cf59a8d979a379ce7a4015e"
RESULTS = ROOT / "experiments/results/g1-release-terminal-rebound-20261125"
ORIGINAL = RESULTS / "replay-01"
ARCHIVE = RESULTS / "replay-02"
REGISTRATION = RECOVERY / "recovery-registration.json"
INHERITED_REVIEW = RESULTS / "inherited-A01-cold-review.json"
ZERO_STEP_CHECK = RESULTS / "zero-step-cleanup-check.json"
PRECHECK_REGISTRATION = RESULTS / "zero-step-preflight-registration.json"
ORIGINAL_REGISTRATION_SHA = "40f01f071388784a4803cf67569dbb30bef985208b915bc317620f391dcea59f"
PADS = ("left_finger_geom", "right_finger_geom")
OBJECT = "object_geom"
TABLE = "table"
REGION = "target_region_geom"
DATA_GEOMS = (*PADS, OBJECT, TABLE, REGION)
SIGNS = np.array(list(product((-1, 1), repeat=3)))


class ReplayEndpoint(Exception):
    """Terminate the native on-demand context without its normal final image."""


@contextmanager
def render_free(backend, shutdown):
    endpoint = ReplayEndpoint()
    try:
        try:
            with backend.sensor_capture_on_demand():
                yield
                raise endpoint
        except ReplayEndpoint as stopped:
            if stopped is not endpoint:
                raise
        if backend._sensor_capture_on_demand or backend._camera is not None:
            raise ValueError("native on-demand scope did not exit without a camera")
    except BaseException as original_error:
        try:
            shutdown()
        except BaseException as cleanup_error:
            original_error.add_note(f"native shutdown also failed: {cleanup_error}")
        raise
    else:
        shutdown()


def case_dir(branch, case):
    base = ORIGINAL if branch == "A" and case["id"] == "dense-fit-01" else ARCHIVE
    return base / branch / case["id"]


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def covered_file(root, key):
    path = root / key
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"unregistered source input: {path}")
    return path


def tree_digest(root, names):
    data = "".join(f"{sha(covered_file(root, name))}  {name}\n" for name in sorted(names)).encode()
    return hashlib.sha256(data).hexdigest()


def design():
    p = pinned(HERE / "plan.json", PLAN_SHA)
    if sha(HERE / "plan.md") != PLAN_TEXT_SHA:
        raise ValueError("written Astra plan changed")
    roots = {key: ROOT / path for key, path in p["roots"].items()}
    for name, expected in p["round_folder_sha256"].items():
        folder = roots["rounds"] / name
        if (
            tree_digest(folder, [path.name for path in folder.iterdir() if path.is_file()])
            != expected
        ):
            raise ValueError(f"upstream round directory changed: {name}")
    for parent, mapping in (
        (roots["rounds"], p["round_input_sha256"]),
        (ROOT, p["repository_reference_sha256"]),
    ):
        for name, expected in mapping.items():
            if sha(covered_file(parent, name)) != expected:
                raise ValueError(f"registered input changed: {name}")
    native = roots["runtime"]
    for name, expected in p["runtime_inputs_sha256"].items():
        f = native / name
        if f.is_file():
            actual = sha(covered_file(native, name))
        else:
            actual = tree_digest(
                f, [n.relative_to(f).as_posix() for n in f.rglob("*") if n.is_file()]
            )
        if actual != expected:
            raise ValueError(f"model or asset tree changed: {name}")
    manifest = read(native / "runtime-build.json")
    for name, expected in manifest["runtime_files_sha256"].items():
        if sha(covered_file(native, name)) != expected:
            raise ValueError(f"native runtime file changed: {name}")
    for case in p["cases"]:
        d = roots["fits"] / case["id"]
        names = p["fit_file_order"]
        if tree_digest(d, names) != case["folder_sha256"]:
            raise ValueError(f"sealed fitting case changed: {case['id']}")
        for name, expected in zip(names, case["file_sha256"], strict=True):
            if sha(covered_file(d, name)) != expected:
                raise ValueError(f"original raw file changed: {name}")
    recovery = pinned(RECOVERY / "plan.json", RECOVERY_SHA)
    snapshots = {
        "terminal_rebound.py": ORIGINAL / "initial-terminal_rebound.py",
        "experiment-registration.json": HERE / "experiment-registration.json",
    }
    if sha(RECOVERY / "plan.md") != RECOVERY_TEXT_SHA:
        raise ValueError("following Astra recovery plan changed")
    for name, expected in recovery["parent_sha256"].items():
        if sha(snapshots.get(name, HERE / name)) != expected:
            raise ValueError(f"parent round registration changed: {name}")
    for name, expected in recovery["replay_01_sha256"].items():
        if sha(covered_file(ORIGINAL, name)) != expected:
            raise ValueError(f"first attempt original changed: {name}")
    empty_plan = pinned(EMPTY_FRAME / "plan.json", EMPTY_FRAME_SHA)
    if (
        empty_plan["parent_plan_json_sha256"] != RECOVERY_SHA
        or sha(EMPTY_FRAME / "plan.md") != EMPTY_FRAME_TEXT_SHA
        or empty_plan["frozen_backend_py_sha256"] != recovery["frozen_backend_sha256"]
    ):
        raise ValueError("empty-frame evidence is outside the recovery plan")
    for name, expected in empty_plan["preserve_sha256"].items():
        if sha(covered_file(ROOT, name)) != expected:
            raise ValueError(f"original precheck failure changed: {name}")
    return p, roots


def fit_sources(case, roots):
    folder = roots["fits"] / case["id"]
    names = ("native-commands", "native-resets", "offline-physics", "rgbd-index", "sensor-receipt")
    return (read(folder / f"{name}.json") for name in names)


def capture_state(backend, mj):
    data, model = backend._data, backend._model
    contact_rows = []
    for i, contact in enumerate(data.contact):
        wrench = np.zeros(6)
        mj.mj_contactForce(model, data, i, wrench)
        native = backend._last_contacts[i]
        contact_rows.append(
            {
                "names": sorted([native.geom1, native.geom2]),
                "normal_n": float(wrench[0]),
                "distance_m": float(contact.dist),
                "expected_workpiece": native.expected,
                "illegal": native.illegal,
            }
        )
    site = data.site("tcp")
    return {
        "tick": backend.total_physics_steps,
        "time_s": float(data.time),
        "q": data.qpos[:9].tolist(),
        "dq": data.qvel[:9].tolist(),
        "object_qvel": data.qvel[9:15].tolist(),
        "arm_target": backend._target_positions.tolist(),
        "control": data.ctrl.tolist(),
        "tcp_xyz_m": site.xpos.tolist(),
        "tcp_R": site.xmat.reshape(3, 3).tolist(),
        "geom": {
            name: [data.geom(name).xpos.tolist(), data.geom(name).xmat.reshape(3, 3).tolist()]
            for name in DATA_GEOMS
        },
        "open_command": backend._gripper_open,
        "contacts": contact_rows,
    }


def integration_digest(backend, mj):
    model, data = backend._model, backend._data
    signature = mj.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mj.mj_stateSize(model, signature), dtype="<f8")
    mj.mj_getState(model, data, state, signature)
    command_prefix = [
        {name: value for name, value in row.items() if name != "episode_id"}
        for row in backend._command_records
    ]
    return {
        "mujoco_integration_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
        "native_state_sha256": digest(
            {
                "tick": backend.total_physics_steps,
                "target": backend._target_positions.tolist(),
                "pending": [
                    [tick, target.tolist()] for tick, target in backend._pending_joint_targets
                ],
                "estop": backend.estop_engaged,
                "gripper_open": backend._gripper_open,
                "brake_state": backend._guard_brake_state,
                "guard_used": backend._execution_guard_used,
                "rng": backend._rng.bit_generator.state,
                "command_seq": backend.next_command_sequence,
                "command_prefix_sha256": digest(command_prefix),
            }
        ),
    }


def archive_match(row, dense, frames, labels, sizes, atol):
    cube, cube_rotation = row["geom"][OBJECT]
    bottom = cube[2] - np.abs(cube_rotation[2]) @ sizes[OBJECT]
    names = [v["names"] for v in row["contacts"]]
    bilateral = all(sorted([OBJECT, pad]) in names for pad in PADS)
    illegal = any(v["illegal"] for v in row["contacts"])
    if (dense[0], dense[2], dense[3]) != (row["tick"], bilateral, illegal):
        raise ValueError(f"dense semantic replay mismatch at {row['tick']}")
    max_error = abs(bottom - dense[1])
    for source in frames:
        packet = source["robot"]
        label = labels[packet["frame_id"]]
        if (
            packet["checksum_sha256"] != label["checksum_sha256"]
            or not packet["physics_step"] == label["physics_step"] == row["tick"]
            or sorted(names) != sorted(label["touching"])
        ):
            raise ValueError(f"eroded label identity near tick {row['tick']}")
        comparisons = (
            (row["q"][:7], packet["joint_positions_rad"]),
            (row["dq"][:7], packet["joint_velocities_rad_s"]),
            (row["q"][7:], packet["finger_positions_m"]),
            (row["dq"][7:], packet["finger_velocities_m_s"]),
            (row["tcp_xyz_m"], packet["tcp_position_m"]),
            (row["time_s"], packet["sim_time_s"]),
            (cube, label["center_m"]),
            (cube_rotation, label["rotation"]),
        )
        for measured, archived in comparisons:
            max_error = max(max_error, float(np.max(abs(np.asarray(measured) - archived))))
    if not 0 <= max_error <= atol:
        raise ValueError(f"frozen physical replay differs at {row['tick']}: {max_error}")
    return max_error


def restored_command(source, backend, replay, branch, terminal_seq):
    if branch == "B" and source["command_seq"] == terminal_seq:
        q = backend._data.qpos[:7].tolist()
        backend.hold_current_joints()
        record = backend._command_records[-1]
        if (
            record["type"] != "hold_current_joints"
            or not record["accepted"]
            or record["command_seq"] != terminal_seq
            or record["physics_step"] != source["physics_step"]
            or record["applied_target_positions_rad"] != q
            or backend._pending_joint_targets
        ):
            raise ValueError("native counterfactual hold failed its frozen source precondition")
    else:
        replay(backend, source)


def prepare_backend(backend, reset, case, roots, plan):
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

    if reset["seed"] != case["seed"]:
        raise ValueError("original fit seed differs")
    scenario = {**reset}
    for key in plan["native"]["reset_pose_fields"]:
        scenario[key] = Pose(**reset[key])
    asset = next(name for name in plan["runtime_inputs_sha256"] if name.endswith(".xml"))
    backend.initialize(
        SimulatorConfig(
            model_path=str(roots["runtime"] / asset),
            seed=case["seed"],
            physics_dt_s=1 / 240,
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
        )
    )
    return PhysicalScenarioConfig(**scenario)


def capture_one(backend, mj, replay, case, roots, plan, branch, folder, baseline):
    events, resets, physics, index, receipt = fit_sources(case, roots)
    opening = case["open_tick"]
    end = case["inclusive_dwell"][1]
    by_tick, frames = defaultdict(list), defaultdict(list)
    for cmd in events:
        by_tick[cmd["physics_step"]].append(cmd)
    for row in index["rows"]:
        frames[row["robot"]["physics_step"]].append(row)
    labels = {r["frame_id"]: r for r in physics["frame_labels"]}
    ordered = by_tick[opening]
    cleanup = by_tick[end][0]
    if (
        [cmd["command_seq"] for cmd in ordered] != case["arm_open_seq"]
        or [cmd["type"] for cmd in ordered] != ["joint_target", "gripper"]
        or not ordered[1]["target_open"]
        or cleanup["command_seq"] != case["archived_cleanup_seq_at_endpoint"]
        or cleanup["type"] != "joint_target"
        or any(by_tick[t] for t in range(opening + 1, end))
        or index["episode_id"] != receipt["episode_id"]
    ):
        raise ValueError("registered boundary commands or reset identity differ")
    reset = resets[0]["parameters"]["requested"]
    scenario = prepare_backend(backend, reset, case, roots, plan)
    witnessed, maximal_error, step, source_commands = 0, 0.0, 0, 0
    complete = False
    trace = folder / "native-trace.jsonl.gz"
    summary = {}
    try:
        with render_free(backend, backend.shutdown), trace.open("xb") as buffer:
            backend.reset(scenario)
            if (
                backend.total_physics_steps
                or backend.get_sim_time()
                or backend._data.qpos[0] != -0.8
            ):
                raise ValueError("original measured reset and native clock differ")
            sizes = {name: backend._model.geom(name).size.tolist() for name in DATA_GEOMS}
            summary["half_extents_m"] = sizes
            # Reset has no saved contact snapshots, so record it after a native read.
            backend._last_contacts = backend._read_contacts()
            with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
                stream.write(json_bytes(capture_state(backend, mj)) + b"\n")
                while step < end:
                    if step == opening:
                        pre = integration_digest(backend, mj)
                        if branch == "B" and baseline["precommand_state"] != pre:
                            raise ValueError("counterfactual changes the pre-open state")
                        summary["precommand_state"] = pre
                        summary["precommand_q"] = backend._data.qpos[:9].tolist()
                        summary["precommand_tcp_xyz_m"] = backend._data.site("tcp").xpos.tolist()
                        summary["original_terminal_commands"] = ordered
                    for cmd in by_tick[step]:
                        restored_command(cmd, backend, replay, branch, case["arm_open_seq"][0])
                        source_commands += 1
                    if step == opening:
                        summary["postcommand_state"] = integration_digest(backend, mj)
                        summary["applied_terminal_commands"] = list(backend._command_records[-2:])
                    advance = backend.step(1)
                    step += 1
                    if advance.physics_steps != 1 or backend.total_physics_steps != step:
                        raise ValueError("native single-step timing changed")
                    state = capture_state(backend, mj)
                    stream.write(json_bytes(state) + b"\n")
                    if branch == "A" or step <= opening:
                        error = archive_match(
                            state,
                            physics["dense"][step - 1],
                            frames[step],
                            labels,
                            sizes,
                            plan["limits"]["archive_numeric_atol_native_units"],
                        )
                        maximal_error = max(maximal_error, error)
                        witnessed += len(frames[step])
                    if (
                        branch == "B"
                        and step > opening
                        and any(c["illegal"] for c in state["contacts"])
                    ):
                        raise ValueError(f"counterfactual illegal contact at {step}")
            if backend._camera is not None:
                raise ValueError("CPU-only physics unexpectedly started a camera")
        complete = True
    finally:
        terminal = {
            **summary,
            "case": case["id"],
            "branch": branch,
            "ticks_through_inclusive": step,
            "archive_sample_checks": witnessed,
            "native_commands_replayed": source_commands,
            "max_software_replay_error": maximal_error,
            "cleanup_command_after_boundary_not_applied": cleanup,
            "original_retreat_only": next(r for r in receipt["actions"] if r["skill"] == "RETREAT"),
            "complete": complete,
            "trace_sha256": sha(trace) if trace.exists() else None,
            "plan_sha256": PLAN_SHA,
            "recovery_sha256": RECOVERY_SHA,
            "shutdown_completed_without_rendering": complete,
            "registration_sha256": sha(REGISTRATION),
        }
        write(folder / "receipt.json", terminal)


def native_components(roots):
    import mujoco

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import GripperCommand
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    for item in (MuJoCoPhysicsBackend, Pose, SimulatorConfig, GripperCommand):
        if not Path(inspect.getfile(item)).resolve().is_relative_to(roots["runtime"].resolve()):
            raise ValueError("capture imported from outside the frozen native runtime")
    if mujoco.__version__ != "3.3.7":
        raise ValueError("registered MuJoCo version differs")
    return MuJoCoPhysicsBackend, mujoco


def invoke_capture(plan, roots, branch, baseline_gate=None, baseline_sha=None):
    backend_class, mujoco = native_components(roots)
    gate = pinned(baseline_gate, baseline_sha) if branch == "B" else None
    if gate and (
        gate["registration_sha256"] != sha(REGISTRATION)
        or set(gate["baselines"]) != {case["id"] for case in plan["cases"]}
        or not all(row["physical_clearance_and_support"] for row in gate["baselines"].values())
    ):
        raise ValueError("counterfactual requires all three independently proven baselines")
    peer = next(
        name for name in plan["round_input_sha256"] if name.endswith("pad-physics-replay.py")
    )
    spec = importlib.util.spec_from_file_location("frozen_native_replay", roots["rounds"] / peer)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    storage = ARCHIVE / branch
    if branch == "A":
        ARCHIVE.mkdir()
    storage.mkdir()
    selected = plan["cases"][1:] if branch == "A" else plan["cases"]
    for case in selected:
        original = gate["baselines"][case["id"]] if gate else None
        baseline = (
            pinned(case_dir("A", case) / "receipt.json", original["receipt_sha256"])
            if original
            else None
        )
        if baseline is not None and baseline["precommand_state"] != original["precommand_state"]:
            raise ValueError("scored baseline and sealed precommand anchor disagree")
        folder = storage / case["id"]
        folder.mkdir()
        capture_one(
            backend_class(),
            mujoco,
            replay.command,
            case,
            roots,
            plan,
            branch,
            folder,
            baseline,
        )


def gap_and_table(row, sizes):
    pos, r = row["geom"][OBJECT]
    obj = SIGNS * np.asarray(sizes[OBJECT]) @ np.asarray(r).T + pos
    tcp_axis = np.asarray(row["tcp_R"])[:, 1]
    gaps = []
    for side, axis in zip(PADS, (tcp_axis, -tcp_axis), strict=True):
        pad_pos, pad_r = row["geom"][side]
        if axis @ (np.asarray(pad_pos) - row["tcp_xyz_m"]) <= 0:
            raise ValueError("pad geometry is on the wrong side of the native wrist")
        pad = SIGNS * np.asarray(sizes[side]) @ np.asarray(pad_r).T + pad_pos
        gaps.append(float((pad @ axis).min() - (obj @ axis).max()))
    if not np.isfinite([*gaps, *pos]).all():
        raise ValueError("physical geometry nonfinite")
    region, _ = row["geom"][REGION]
    hi = sizes[REGION]
    inside = bool(np.all(abs(obj[:, :2] - region[:2]) <= np.asarray(hi[:2]) + 1e-9))
    table_surface = row["geom"][TABLE][0][2] + sizes[TABLE][2]
    return gaps, float(obj[:, 2].min() - table_surface), inside


def dwell_issues(row, gaps, inside):
    issues = []
    obj_contacts = [c for c in row["contacts"] if OBJECT in c["names"]]
    if not row["open_command"] or min(row["q"][7:9]) <= 0.035 or min(gaps) <= 0.00025:
        issues.append("opening_or_strict_clearance")
    if any(c["illegal"] for c in row["contacts"]):
        issues.append("illegal")
    if any(pad in c["names"] for pad in PADS for c in obj_contacts):
        issues.append("finger_workpiece")
    if (
        not obj_contacts
        or any(set(c["names"]) != {OBJECT, TABLE} for c in obj_contacts)
        or (max([c["normal_n"] for c in obj_contacts], default=0) <= 0)
    ):
        issues.append("no_exclusive_table_support")
    if not inside:
        issues.append("outside_target_region")
    if (
        np.linalg.norm(row["object_qvel"][:3]) > 0.02
        or np.linalg.norm(row["object_qvel"][3:]) > 0.5
    ):
        issues.append("physical_speed")
    return issues


def topology(rows, case, branch, receipt):
    expected = list(range(case["inclusive_dwell"][1] + 1))
    if [row["tick"] for row in rows] != expected or (
        receipt["case"],
        receipt["branch"],
        receipt["ticks_through_inclusive"],
    ) != (case["id"], branch, expected[-1]):
        raise ValueError("wrong case/branch, missing/duplicate/shifted endpoint or time step")
    timing = np.asarray([row["time_s"] for row in rows])
    if not np.isfinite(timing).all() or np.max(abs(timing - np.asarray(expected) / 240)) >= 1e-9:
        raise ValueError("native continuous time differs")
    issued = receipt["applied_terminal_commands"]
    kinds = ["joint_target" if branch == "A" else "hold_current_joints", "gripper"]
    if (
        [cmd["type"] for cmd in issued] != kinds
        or not issued[1]["target_open"]
        or [cmd["command_seq"] for cmd in issued] != case["arm_open_seq"]
        or any(cmd["physics_step"] != case["open_tick"] or not cmd["accepted"] for cmd in issued)
    ):
        raise ValueError("unregistered terminal command order")


def stability(centers, rotations, bottoms, limits):
    values = {
        "center_peak_to_peak_xyz_mm": (np.ptp(centers, axis=0) * 1000).tolist(),
        "center_peak_to_peak_norm_m": float(np.linalg.norm(np.ptp(centers, axis=0))),
        "rotation_frobenius_from_first": float(
            np.max(np.linalg.norm(np.asarray(rotations) - rotations[0], axis=(1, 2)))
        ),
        "bottom_peak_to_peak_m": float(np.ptp(bottoms)),
    }
    values["inside_frozen_limits"] = (
        values["center_peak_to_peak_norm_m"] <= limits["norm_of_xyz_peak_to_peak_lte_m"]
        and values["rotation_frobenius_from_first"]
        <= limits["max_rotation_frobenius_distance_from_first_lte"]
        and values["bottom_peak_to_peak_m"] <= limits["bottom_peak_to_peak_lte_m"]
    )
    return values


def load_trace(case, branch):
    directory = case_dir(branch, case)
    receipt_file = directory / "receipt.json"
    receipt = read(receipt_file)
    trace = directory / "native-trace.jsonl.gz"
    inherited = directory.is_relative_to(ORIGINAL)
    reg = ORIGINAL_REGISTRATION_SHA if inherited else sha(REGISTRATION)
    if (
        not receipt["complete"]
        or receipt["plan_sha256"] != PLAN_SHA
        or receipt["registration_sha256"] != reg
        or sha(trace) != receipt["trace_sha256"]
        or (
            not inherited
            and (
                not receipt["shutdown_completed_without_rendering"]
                or receipt["recovery_sha256"] != RECOVERY_SHA
            )
        )
    ):
        raise ValueError("raw release seal is incomplete or corrupted")
    with gzip.open(trace, "rb") as f:
        rows = [json.loads(line) for line in f]
    topology(rows, case, branch, receipt)
    return receipt_file, receipt, trace, rows


def summarize(case, branch, plan):
    receipt_file, receipt, trace, rows = load_trace(case, branch)
    sizes = receipt["half_extents_m"]
    opening = case["open_tick"]
    start, end = case["inclusive_dwell"]
    dwell, centers, rotations, bottoms, failures, transient, full_dwell = [], [], [], [], [], [], []
    for row in rows[opening + 1 :]:
        step = row["tick"]
        gaps, bottom, inside = gap_and_table(row, sizes)
        signed_mm = np.array(gaps) * 1000
        if step < start:
            transient.append(signed_mm)
            continue
        full_dwell.append(signed_mm)
        errors = dwell_issues(row, gaps, inside)
        if errors:
            failures.append({"tick": step, "issues": errors})
        c, r = row["geom"][OBJECT]
        centers.append(c)
        rotations.append(r)
        bottoms.append(bottom)
        if (step - start) % 8 == 0:
            dwell.append(
                {
                    "tick": step,
                    "relative_tick": step - opening,
                    "gap_mm": signed_mm.tolist(),
                    "tighter_gap_mm": float(min(signed_mm)),
                    "symmetric_half_sum_mm": float(signed_mm.mean()),
                    "signed_half_difference_mm": float((signed_mm[0] - signed_mm[1]) / 2),
                    "strict_margin_mm": float(min(signed_mm) - 0.25),
                }
            )
    if len(dwell) != 31 or len(full_dwell) != 241:
        raise ValueError("wrong released dwell count")
    worst = min(dwell, key=lambda row: row["tighter_gap_mm"])
    if branch == "A" and abs(worst["tighter_gap_mm"] - case["baseline_min_mm_rounded"]) > 0.00005:
        raise ValueError(f"baseline release gap differs from published receipt: {worst}")
    applied_terminal = receipt["applied_terminal_commands"][0]["applied_target_positions_rad"]
    move = {}
    for label, index in (("first_dwell", start), ("endpoint", end)):
        pre, post = rows[opening], rows[index]
        obj_delta = np.asarray(post["geom"][OBJECT][0]) - pre["geom"][OBJECT][0]
        tcp_delta = np.asarray(post["tcp_xyz_m"]) - pre["tcp_xyz_m"]
        axis = np.asarray(pre["tcp_R"])[:, 1]
        move[label] = {
            "tcp_xyz_mm": (1000 * tcp_delta).tolist(),
            "object_xyz_mm": (1000 * obj_delta).tolist(),
            "object_relative_to_tcp_projected_mm": float(1000 * ((obj_delta - tcp_delta) @ axis)),
        }
    stationary = stability(
        centers, rotations, bottoms, plan["decision"]["original_31_snapshot_stability"]
    )
    return {
        "receipt_sha256": sha(receipt_file),
        "trace_sha256": sha(trace),
        "precommand_state": receipt["precommand_state"],
        "steps": len(rows) - 1,
        "archived_sample_checks": receipt["archive_sample_checks"],
        "replayed_commands": receipt["native_commands_replayed"],
        "max_replay_error": receipt["max_software_replay_error"],
        "failed_process_raw_reused": case_dir(branch, case).is_relative_to(ORIGINAL),
        "pre_open_joint_target_minus_measured_rad": (
            np.asarray(applied_terminal) - receipt["precommand_q"][:7]
        ).tolist(),
        "dwell": dwell,
        "worst_sample": worst,
        "motion": move,
        "dense_dwell_gap_min_by_pad_mm": np.min(full_dwell, axis=0).tolist(),
        "dense_dwell_gap_max_by_pad_mm": np.max(full_dwell, axis=0).tolist(),
        "during_opening_gap_min_by_pad_mm": np.min(transient, axis=0).tolist(),
        "during_opening_gap_max_by_pad_mm": np.max(transient, axis=0).tolist(),
        "stability": stationary,
        "physical_failures": failures,
        "physical_clearance_and_support": not failures and stationary["inside_frozen_limits"],
    }


def inherited_review(plan, roots):
    case = plan["cases"][0]
    receipt_file, receipt, trace, rows = load_trace(case, "A")
    events, _, physics, index, _ = fit_sources(case, roots)
    labels = {item["frame_id"]: item for item in physics["frame_labels"]}
    at_step, frames = defaultdict(list), defaultdict(list)
    for cmd in events:
        at_step[cmd["physics_step"]].append(cmd)
    for item in index["rows"]:
        frames[item["robot"]["physics_step"]].append(item)
    opening = case["open_tick"]
    limit = plan["limits"]["archive_numeric_atol_native_units"]
    checks, cmd_count, max_error = 0, 0, 0.0
    target, opened = rows[0]["arm_target"], True
    for row in rows[1:]:
        tick = row["tick"]
        for cmd in at_step[tick - 1]:
            if not cmd["accepted"]:
                raise ValueError("unexpected rejected command in the original replay")
            cmd_count += 1
            if cmd["type"] == "gripper":
                opened = cmd["target_open"]
            else:
                target = cmd["applied_target_positions_rad"]
        if (
            row["open_command"] != opened
            or max(abs(np.asarray(target) - row["arm_target"])) > limit
        ):
            raise ValueError(f"A01 cold command/state join differs at tick {tick}")
        max_error = max(
            max_error,
            archive_match(
                row,
                physics["dense"][tick - 1],
                frames[tick],
                labels,
                receipt["half_extents_m"],
                limit,
            ),
        )
        checks += len(frames[tick])
    summary = summarize(case, "A", plan)
    failure = (ORIGINAL / "cleanup-failure.txt").read_text()
    if (
        checks != receipt["archive_sample_checks"]
        or cmd_count != receipt["native_commands_replayed"]
        or receipt["precommand_q"] != rows[opening]["q"]
        or receipt["precommand_tcp_xyz_m"] != rows[opening]["tcp_xyz_m"]
        or receipt["original_terminal_commands"] != at_step[opening]
        or receipt["cleanup_command_after_boundary_not_applied"] != at_step[rows[-1]["tick"]][0]
        or not all(len(stamp) == 64 for stamp in receipt["precommand_state"].values())
        or not summary["physical_clearance_and_support"]
        or "after all planned" not in failure
        or "mujoco.FatalError" not in failure
        or any(f.suffix.lower() in {".png", ".jpg", ".jpeg"} for f in ORIGINAL.rglob("*"))
    ):
        raise ValueError("failed-process A01 did not retain a complete pre-cleanup physics record")
    write(
        INHERITED_REVIEW,
        {
            "plan_sha256": PLAN_SHA,
            "recovery_sha256": RECOVERY_SHA,
            "reused_archive_relative": str(trace.parent.relative_to(ROOT)),
            "trace_sha256": sha(trace),
            "receipt_sha256": sha(receipt_file),
            "cleanup_error_sha256": sha(ORIGINAL / "cleanup-failure.txt"),
            "old_process_exit_code": 1,
            "old_completed_cleanup": False,
            "physics_steps": rows[-1]["tick"],
            "aligned_exposures": checks,
            "aligned_commands": cmd_count,
            "max_numeric_error": max_error,
            "verified_dwell_frames": len(summary["dwell"]),
            "min_original_gap_mm": summary["worst_sample"]["tighter_gap_mm"],
        },
    )


def controls(plan):
    row = {
        "q": [0.0] * 7 + [0.039, 0.039],
        "open_command": True,
        "contacts": [{"names": [OBJECT, TABLE], "normal_n": 1.0, "illegal": False}],
        "object_qvel": [0.0] * 6,
    }
    assert not dwell_issues(row, [0.003, 0.004], True)
    assert "opening_or_strict_clearance" in dwell_issues(row, [0.00025, 0.004], True)
    assert "opening_or_strict_clearance" in dwell_issues(row, [0.003, -0.0001], True)
    near = deepcopy(row)
    near["contacts"].append({"names": [OBJECT, PADS[0]], "normal_n": 1.0, "illegal": False})
    assert "finger_workpiece" in dwell_issues(near, [0.003, 0.004], True)
    near["contacts"][-1]["illegal"] = True
    assert "illegal" in dwell_issues(near, [0.003, 0.004], True)
    assert "no_exclusive_table_support" in dwell_issues(
        {**row, "contacts": []},
        [0.003, 0.004],
        True,
    )
    assert "outside_target_region" in dwell_issues(row, [0.003, 0.004], False)
    stable = plan["decision"]["original_31_snapshot_stability"]
    assert not stability([[0, 0, 0], [0.00401, 0, 0]], [np.eye(3), np.eye(3)], [0, 0], stable)[
        "inside_frozen_limits"
    ]
    assert not stability([[0, 0, 0]] * 2, [np.eye(3), np.eye(3)], [0, 0.00301], stable)[
        "inside_frozen_limits"
    ]
    yaw = [[0.99, -0.14, 0], [0.14, 0.99, 0], [0, 0, 1]]
    assert not stability([[0, 0, 0]] * 2, [np.eye(3), yaw], [0, 0], stable)["inside_frozen_limits"]
    test_case = {
        "id": "synthetic",
        "open_tick": 0,
        "inclusive_dwell": [0, 2],
        "arm_open_seq": [1, 2],
    }
    tail = [{"tick": i, "time_s": i / 240} for i in range(3)]
    ticket = {
        "case": "synthetic",
        "branch": "A",
        "ticks_through_inclusive": 2,
        "applied_terminal_commands": [
            {"type": "joint_target", "command_seq": 1, "physics_step": 0, "accepted": True},
            {
                "type": "gripper",
                "target_open": True,
                "command_seq": 2,
                "physics_step": 0,
                "accepted": True,
            },
        ],
    }

    def reject(call, *args):
        try:
            call(*args)
        except ValueError:
            return
        raise ValueError(f"negative control did not reject: {call.__name__}")

    topology(tail, test_case, "A", ticket)
    reject(topology, tail, test_case, "A", {**ticket, "case": "foreign"})
    reject(
        topology,
        tail,
        test_case,
        "A",
        {
            **ticket,
            "applied_terminal_commands": ticket["applied_terminal_commands"][::-1],
        },
    )
    reject(topology, tail[:-1], test_case, "A", ticket)
    reject(topology, [tail[0], tail[1], tail[1]], test_case, "A", ticket)
    reject(topology, [tail[0], tail[1], dict(tail[2], tick=3)], test_case, "A", ticket)
    reject(pinned, HERE / "plan.json", "0" * 64)
    geo = {
        "tcp_R": np.eye(3).tolist(),
        "tcp_xyz_m": [0, 0, 0.06],
        "geom": {
            PADS[0]: [[0, 0.048, 0.06], np.eye(3).tolist()],
            PADS[1]: [[0, -0.048, 0.06], np.eye(3).tolist()],
            OBJECT: [[0, 0, 0.035], np.eye(3).tolist()],
            TABLE: [[0, 0, -0.025], np.eye(3).tolist()],
            REGION: [[0, 0, 0], np.eye(3).tolist()],
        },
    }
    sizes = {
        PADS[0]: [0.035, 0.008, 0.028],
        PADS[1]: [0.035, 0.008, 0.028],
        OBJECT: [0.035] * 3,
        TABLE: [0.65, 0.45, 0.025],
        REGION: [0.08, 0.08, 0.002],
    }
    gaps, _, inside = gap_and_table(geo, sizes)
    assert inside and min(gaps) > 0.004
    disrupted = deepcopy(geo)
    disrupted["geom"][PADS[0]], disrupted["geom"][PADS[1]] = (
        geo["geom"][PADS[1]],
        geo["geom"][PADS[0]],
    )
    reject(gap_and_table, disrupted, sizes)
    disrupted = deepcopy(geo)
    disrupted["geom"][OBJECT][0][0] = float("nan")
    reject(gap_and_table, disrupted, sizes)
    return [
        "strict gap equality",
        "one-side failure",
        "intermediate finger contact",
        "illegal contact",
        "missing table support",
        "region escape",
        "center, rotation and bottom instability",
        "case/side swap",
        "command reversal",
        "missing/duplicate/shifted endpoint",
        "digest mismatch",
        "nonfinite geometry",
    ]


def run_score(plan, summary_path, baseline_only):
    checks = controls(plan)
    a = {case["id"]: summarize(case, "A", plan) for case in plan["cases"]}
    if not all(row["physical_clearance_and_support"] for row in a.values()):
        raise ValueError("original-condition replays failed physical baseline")
    outcome = {
        "plan_sha256": PLAN_SHA,
        "registration_sha256": sha(REGISTRATION),
        "negative_controls": checks,
        "baselines": a,
    }
    if not baseline_only:
        b = {case["id"]: summarize(case, "B", plan) for case in plan["cases"]}
        pairs = {}
        for name, base in a.items():
            changed = b[name]
            if changed["precommand_state"] != base["precommand_state"]:
                raise ValueError("paired fits do not share the original physical state")
            pairs[name] = [
                (np.asarray(variant["gap_mm"]) - control["gap_mm"]).tolist()
                for control, variant in zip(base["dwell"], changed["dwell"], strict=True)
            ]
        gains = {
            name: b[name]["worst_sample"]["tighter_gap_mm"]
            - a[name]["worst_sample"]["tighter_gap_mm"]
            for name in a
        }
        decision = plan["decision"]
        outcome.update(
            {
                "counterfactuals": b,
                "per_dwell_pad_B_minus_A_mm": pairs,
                "worst_gap_B_minus_A_mm": gains,
                "useful_fit03_without_loss_other_cases": (
                    gains["dense-fit-03"] >= decision["useful_fit03_B_minus_A_min_mm"]
                    and all(
                        gains[name] >= decision["fit01_fit02_B_minus_A_min_mm"]
                        for name in ("dense-fit-01", "dense-fit-02")
                    )
                    and all(row["physical_clearance_and_support"] for row in b.values())
                ),
                "online_qualification": False,
            }
        )
    write(summary_path, outcome)


def empty_frame_matches(observed, original):
    return (
        observed is original
        and observed.frame_id == "camera"
        and observed.sim_time_s == 0.0
        and (observed.width, observed.height) == (0, 0)
        and observed.rgb is None
        and not observed.depth
    )


def precheck_registration():
    return {
        "parent_plan_sha256": PLAN_SHA,
        "cleanup_plan_sha256": RECOVERY_SHA,
        "placeholder_plan_sha256": EMPTY_FRAME_SHA,
        "source_sha256": sha(Path(__file__)),
        "archive": str(ARCHIVE.relative_to(ROOT)),
        "inherited_A01_sha256": sha(INHERITED_REVIEW),
    }


def cleanup_validation(plan, roots):
    if read(PRECHECK_REGISTRATION) != precheck_registration() or ARCHIVE.exists():
        raise ValueError("unsigned lifecycle precheck or nonexclusive recovery destination")
    backend_class, _ = native_components(roots)
    case = plan["cases"][0]
    _, resets, _, _, _ = fit_sources(case, roots)
    backend = backend_class()
    scenario = prepare_backend(backend, resets[0]["parameters"]["requested"], case, roots, plan)
    original = backend.get_sensor_frame()
    if not empty_frame_matches(original, original) or empty_frame_matches(
        replace(original), original
    ):
        raise ValueError("native empty placeholder or same-name replacement control differed")

    def checked_shutdown():
        if not empty_frame_matches(backend.get_sensor_frame(), original):
            raise ValueError("leaving the native scope replaced the empty frame")
        backend.shutdown()

    with render_free(backend, checked_shutdown):
        backend.reset(scenario)
        if (
            backend.total_physics_steps
            or backend.get_sim_time()
            or backend._camera is not None
            or backend._data.qpos[0] != -0.8
            or backend._command_records
            or not empty_frame_matches(backend.get_sensor_frame(), original)
        ):
            raise ValueError("physical zero-step positive is outside the native reset contract")
    if (
        backend._data is not None
        or backend._camera is not None
        or backend._sensor_capture_on_demand
        or not empty_frame_matches(backend.get_sensor_frame(), original)
    ):
        raise ValueError("completed zero-step lifecycle did not release the native backend")

    class LifecycleFixture:
        def __init__(self):
            self._camera = None
            self._sensor_capture_on_demand = False
            self.shutdown_called = False
            self.refreshed = False

        @contextmanager
        def sensor_capture_on_demand(self):
            self._sensor_capture_on_demand = True
            try:
                yield
            except BaseException:
                self._sensor_capture_on_demand = False
                raise
            else:
                self.refreshed = True

        def shutdown(self):
            self.shutdown_called = True

    @contextmanager
    def failing_writer(error):
        yield
        raise error

    observed = {}
    for condition, expected in (
        ("wrong_instance", ReplayEndpoint("not the verified endpoint")),
        ("body", ValueError("body error")),
        ("writer_close", OSError("writer teardown error")),
        ("shutdown", OSError("shutdown error")),
    ):
        test = LifecycleFixture()
        published_complete = False

        def shutdown_fixture(test=test, condition=condition, expected=expected):
            test.shutdown()
            if condition == "shutdown":
                raise expected

        try:
            with render_free(test, shutdown_fixture):
                if condition in ("wrong_instance", "body"):
                    raise expected
                if condition == "writer_close":
                    with failing_writer(expected):
                        pass
            published_complete = True
        except (ReplayEndpoint, ValueError, OSError) as received:
            if received is not expected:
                raise
        if published_complete or not test.shutdown_called or test.refreshed:
            raise ValueError(f"unexpectedly completed the injected {condition} failure")
        observed[condition] = "same_error_propagated_without_complete_record"
    write(
        ZERO_STEP_CHECK,
        {
            "recovery_sha256": RECOVERY_SHA,
            "physics_steps": 0,
            "successful_rgbd_exposures": 0,
            "restarted_camera": False,
            "restored_original_joint1_rad": -0.8,
            "positive_native_scope_released_and_shutdown": True,
            "initial_empty_frame_identity_preserved": True,
            "separate_equal_empty_frame_rejected": True,
            "negative_controls": observed,
        },
    )


def registration(plan):
    locked = {
        "plan_sha256": PLAN_SHA,
        "plan_md_sha256": PLAN_TEXT_SHA,
        "recovery_sha256": RECOVERY_SHA,
        "placeholder_plan_sha256": EMPTY_FRAME_SHA,
        "signed_precheck_registration_sha256": sha(PRECHECK_REGISTRATION),
        "inherited_A01_cold_review_sha256": sha(INHERITED_REVIEW),
        "zero_step_lifecycle_sha256": sha(ZERO_STEP_CHECK),
        "source_sha256": sha(Path(__file__)),
        "archive_relative_path": str(ARCHIVE.relative_to(ROOT)),
        "native_version": version("mujoco"),
        "numpy_version": np.__version__,
        "paired_fits": [case["id"] for case in plan["cases"]],
        "decision": plan["decision"],
        "limits": plan["limits"],
        "negative_controls": controls(plan),
    }
    if locked["native_version"] != "3.3.7":
        raise ValueError("unexpected pinned native version")
    return locked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "verify-A01",
            "sign-precheck",
            "check-cleanup",
            "register",
            "A",
            "score-A",
            "B",
            "score-paired",
        ),
    )
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--baseline-gate", type=Path)
    parser.add_argument("--baseline-sha256")
    args = parser.parse_args()
    plan, roots = design()
    if args.mode == "verify-A01":
        inherited_review(plan, roots)
    elif args.mode == "sign-precheck":
        write(PRECHECK_REGISTRATION, precheck_registration())
    elif args.mode == "check-cleanup":
        cleanup_validation(plan, roots)
    else:
        locked = registration(plan)
        if args.mode == "register":
            if ARCHIVE.exists():
                raise ValueError("registered recovery archive must be exclusive")
            write(REGISTRATION, locked)
        elif locked != read(REGISTRATION):
            raise ValueError("test code, data or archive registration changed")
        elif args.mode in ("A", "B"):
            invoke_capture(plan, roots, args.mode, args.baseline_gate, args.baseline_sha256)
        else:
            run_score(plan, args.output, args.mode == "score-A")
