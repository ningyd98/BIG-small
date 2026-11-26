"""Acquire only newly enrolled source-stop branches from exact CPU replays."""

import argparse
import hashlib
import importlib.util
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from precheck_expansion import HERE, PANDA, PLAN, REPO, ROOTS, deny, require, source
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

REG = read(HERE / "stop-acquisition-registration.json")
OUT = ROOTS["output"]
COUNTS = Counter()
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
ROUNDS = ROOTS["rounds"]
ALLOWED = {
    ("left_finger_geom", "object_geom"),
    ("object_geom", "right_finger_geom"),
    ("object_geom", "table"),
}


def extra(key):
    root, name = key.split("/", 1)
    path = (ROOTS[root] / name).resolve()
    require(path.is_relative_to(REPO), "outside worktree")
    return (
        pinned(path, REG["files_sha256"][key])
        if path.suffix == ".json"
        else verified_path(path, key)
    )


def verified_path(path, key):
    require(sha(path) == REG["files_sha256"][key], f"unregistered file: {key}")
    return path


def open_module(key):
    path = extra(key)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_case(case):
    public = pinned(HERE / "source-expansion-precheck.public.json", REG["public_inventory_sha256"])
    inventory = pinned(OUT / "inventory-1.json", REG["window_inventory_sha256"])
    require(
        sha(OUT / "inventory-2.json") == REG["window_inventory_sha256"]
        and public["profile_changed"] is False
        and all(
            row["known_only_fit_floor_payload_reason"] is None
            for row in public["required_expansions"].values()
        ),
        "frozen precheck is incomplete or rejected",
    )
    if case == "grid02":
        directory = OUT / "fit"
        release = read(directory / "fit-seal.json")
        require(
            release["ready_for_challenge"]
            and release["inventory_sha256"] == REG["window_inventory_sha256"]
            and sha(directory / "candidate-profile.json") == release["profile_sha256"]
            and sha(directory / "reader-1.json")
            == sha(directory / "reader-2.json")
            == release["independent_reader_sha256"],
            "challenge cannot run before profile is sealed by both readers",
        )
    runtime = (REPO / REG["grid_runtime"]) if case.startswith("grid") else ROOTS["runtime"]
    manifest = read(runtime / "runtime-build.json")
    require(sha(runtime / "runtime-build.json") == runtime.parent.name, "foreign native generation")
    for name, expected in manifest["runtime_files_sha256"].items():
        file = (runtime / name).resolve()
        require(
            file.is_relative_to(runtime.resolve()) and sha(file) == expected,
            f"wrong native input {name}",
        )
    import cloud_edge_robot_arm.simulation.mujoco.backend as native

    require(
        Path(native.__file__).resolve().is_relative_to(runtime / "src"),
        "wrong native backend import",
    )
    asset = runtime / PANDA
    require(sha(asset) == PLAN["sha256"]["runtime/" + PANDA], "asset identity mismatch")
    selected = inventory["inventory"][case]
    require(
        len(selected["new_stop_triggers_needed"]) == REG["planned_new_triggers"][case],
        "trigger limits changed",
    )
    return asset, selected


def archives(case):
    if case == "t01":
        receipt = read(source("t01/receipt.json"))
        capture = pinned(source("t01/acquisition-seal.json"), receipt["capture_sha256"])
        truth = extra("t01/offline-truth.json")["samples"]
        require(
            sha(ROOTS["t01"] / "offline-truth.json") == capture["truth_sha256"], "t01 truth binding"
        )
        commands = extra("t01/backend-commands.json")
        require(
            sha(ROOTS["t01"] / "backend-commands.json") == receipt["full_commands_sha256"],
            "t01 native command identity",
        )
        return (
            extra("t01/reset-observed.json"),
            commands,
            truth,
            extra("t01/../lift-qualification-trace.json"),
        )
    r = read(source(f"{case}/sensor-receipt.json"))
    index = pinned(source(f"{case}/rgbd-index.json"), r["index_sha256"])
    truth = {x["frame_id"]: x for x in extra(f"{case}/offline-physics.json")["frame_labels"]}
    seek = defaultdict(list)
    for e in index["rows"]:
        robot = e["robot"]
        label = truth[robot["frame_id"]]
        require(
            robot["checksum_sha256"] == label["checksum_sha256"]
            and robot["physics_step"] == label["physics_step"],
            "foreign grid label",
        )
        seek[robot["physics_step"], robot["native_last_command_seq"]].append((robot, label))
    return extra(f"{case}/native-resets.json"), extra(f"{case}/native-commands.json"), seek, None


def dispatch(b, record):
    kind = record["type"]
    if kind == "joint_target":
        b.apply_joint_targets(JointCommand(positions=record["target_positions_rad"]))
    elif kind == "gripper":
        b.apply_gripper_command(GripperCommand(open=record["target_open"]))
    elif kind == "hold_current_joints":
        b.hold_current_joints()
    else:
        raise ValueError("run encountered an original protective dispatch; stop before it")
    actual = b.command_records[-1]
    require(
        {k: v for k, v in actual.items() if k != "episode_id"}
        == {k: v for k, v in record.items() if k != "episode_id"},
        f"archived native command {record['command_seq']} differs",
    )


def phase_vector(b):
    value = np.empty(mujoco.mj_stateSize(b._model, STATE), dtype="<f8")
    mujoco.mj_getState(b._model, b._data, value, STATE)
    return value


def state_hash(b):
    return hashlib.sha256(phase_vector(b).tobytes()).hexdigest()


def contact_pairs(b):
    return sorted(tuple(sorted((v.geom1, v.geom2))) for v in b.get_contacts())


def exact_t01_state(b, truth, frames):
    tick = b.total_physics_steps
    actual = plain(b.current_physics_observation())
    require(
        all(actual[k] == v for k, v in truth[tick].items() if k != "episode_id"),
        f"t01 dense state differs: {tick}",
    )
    if tick in frames:
        frame = frames[tick]
        require(
            phase_vector(b).tolist() == frame["integration"]
            and b._data.qfrc_bias[:7].tolist() == frame["qfrc_bias_arm"]
            and b._target_positions.tolist() == frame["arm_target"]
            and len(b.command_records) == frame["command_count"],
            f"t01 sealed integration cache differs: {tick}",
        )


def collect_stop(backend, cloned, restore, tick, folder):
    before = state_hash(backend)
    incoming, work = cloned(backend)
    restore(backend, work)
    backend._actuator_observer = None
    q, dq, ctrl, contact_rows = [], [], [], []
    try:
        q0 = backend._data.qpos[:7].copy()
        seq = len(backend.command_records)
        backend.emergency_stop()
        require(
            [c["type"] for c in backend.command_records[seq:]]
            == ["hold_current_joints", "emergency_stop"]
            and backend.estop_engaged
            and np.array_equal(q0, backend._target_positions)
            and not backend._pending_joint_targets
            and not backend._gripper_open,
            "original native stop transition failed",
        )
        for k in range(241):
            require(backend.total_physics_steps == tick + k, "bad stop clock")
            d = backend._data
            q.append(d.qpos.copy())
            dq.append(d.qvel.copy())
            ctrl.append(d.ctrl.copy())
            contact_rows.append(contact_pairs(backend))
            if k < 240:
                require(backend.step(1).physics_steps == 1, "off-grid STOP integration")
    finally:
        restore(backend, incoming)
    require(state_hash(backend) == before, "STOP modified the original normal replay state")
    state = folder / f"stop-{tick}.npz"
    contacts = folder / f"stop-{tick}.json"
    with state.open("xb") as f:
        np.savez_compressed(f, q=q, dq=dq, ctrl=ctrl)
    write(contacts, contact_rows)
    return {"state_sha256": sha(state), "contacts_sha256": sha(contacts), "phase_sha256": before}


def run(case, directory, asset, enrollment):
    bridge = open_module("rounds/round-g1-grid04-lift-midcourse-braking-20261126/screen_braking.py")
    renderer = open_module("rounds/round-g1-release-terminal-rebound-20261125/terminal_rebound.py")
    resets, commands, truth, trace = archives(case)
    req, end = resets
    require(
        (req["phase"], end["phase"]) == ("BEGIN", "END") and end["error"] is None,
        "invalid original reset",
    )
    params = dict(req["parameters"]["requested"])
    for k in ("object_pose", "target_region_pose"):
        params[k] = Pose.model_validate(params[k])
    scenario = PhysicalScenarioConfig(**params)
    stop_at = REG["normal_end"][case]
    triggers = set(enrollment["new_stop_triggers_needed"])
    command_groups = defaultdict(list)
    for c in commands:
        require(c["episode_id"] == end["episode_id"], "foreign old command episode")
        if c["physics_step"] < stop_at:
            command_groups[c["physics_step"]].append(c)
    directory.mkdir(exist_ok=False, parents=True)
    raw = directory / "stops"
    raw.mkdir()
    backend = MuJoCoPhysicsBackend()
    if case == "t01":
        from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend

        backend = RegisteredAssemblyBackend(directory, extra("t01/../allocation.json")["case"])
    q, dq, ctrl, clock, contacts, stop_hashes = [], [], [], [], [], {}
    seen = set()
    frames = {z["state"]["physics_step"]: z["state"] for z in trace["frames"]} if trace else {}
    pre = {z["physics_step"]: z for z in trace["before_integrations"]} if trace else {}
    phase_matches = []

    def final_drive(event):
        tick = event.physics_step - 1
        if tick in pre:
            original = pre[tick]
            require(
                phase_vector(backend).tolist() == original["integration"]
                and backend._data.ctrl.tolist() == original["ctrl"]
                and backend._data.qfrc_bias[:7].tolist() == original["qfrc_bias_arm"],
                f"original per-step applied actuator state differs at {tick}",
            )
            phase_matches.append(tick)

    step_impl = mujoco.mj_step

    def counted(model, data):
        COUNTS["integrations"] += 1
        require(
            COUNTS["integrations"] <= stop_at + 240 * len(triggers),
            "this physical allocation exceeded its exact budget",
        )
        return step_impl(model, data)

    with patch.multiple(mujoco, Renderer=deny, mjr_render=deny, mj_step=counted):
        backend.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=scenario.seed,
                physics_dt_s=1 / 240,
                render_rgb=True,
                render_depth=True,
                camera_width=320,
                camera_height=240,
                domain_randomization=False,
            )
        )
        with renderer.render_free(backend, backend.shutdown):
            backend.reset(scenario)
            COUNTS["resets"] += 1
            with backend.observe_actuator_steps(final_drive):
                for tick in range(stop_at + 1):
                    d = backend._data
                    require(
                        tick == backend.total_physics_steps
                        and not backend.estop_engaged
                        and not backend._pending_joint_targets,
                        "wrong precommand phase",
                    )
                    if case == "t01":
                        exact_t01_state(backend, truth, frames)
                    else:
                        bridge.audit_samples(backend, truth, seen)
                    q.append(d.qpos.copy())
                    dq.append(d.qvel.copy())
                    ctrl.append(d.ctrl.copy())
                    clock.append(float(d.time))
                    contacts.append(contact_pairs(backend))
                    if tick in triggers:
                        require(not backend._gripper_open, "SOURCE stop trigger still open")
                        stop_hashes[str(tick)] = collect_stop(
                            backend, bridge.cloned, bridge.restore, tick, raw
                        )
                    if tick == stop_at:
                        break
                    for record in command_groups[tick]:
                        dispatch(backend, record)
                        if case != "t01":
                            bridge.audit_samples(backend, truth, seen)
                    require(backend.step(1).physics_steps == 1, "wrong original replay clock")
            command_count = len(backend.command_records)
    if case == "t01":
        require(phase_matches == sorted(pre), "missed t01 per-step drive closure")
    else:
        require(
            len(seen) == sum(len(v) for (tick, _), v in truth.items() if tick <= stop_at),
            "unmatched grid frame",
        )
    require(
        COUNTS["integrations"] == stop_at + len(triggers) * 240,
        "actual count or STOP coverage differs",
    )
    normal = directory / "normal.npz"
    with normal.open("xb") as f:
        np.savez_compressed(f, q=q, dq=dq, ctrl=ctrl, time_s=clock)
    normal_contacts = directory / "contacts.json"
    write(normal_contacts, contacts)
    write(
        directory / "seal.json",
        {
            "case": case,
            "role": REG["roles"][case],
            "registration_sha256": sha(HERE / "stop-acquisition-registration.json"),
            "source_sha256": sha(Path(__file__)),
            "inventory_sha256": REG["window_inventory_sha256"],
            "normal_sha256": sha(normal),
            "normal_contacts_sha256": sha(normal_contacts),
            "new_stops": stop_hashes,
            "normal_steps": stop_at,
            "stop_steps": len(triggers) * 240,
            "steps": COUNTS["integrations"],
            "resets": COUNTS["resets"],
            "original_accepted_commands": command_count,
            "archived_grid_frames": len(seen),
            "verified_t01_actuator_steps": len(phase_matches),
            "exposures": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("grid04", "t01", "grid02"))
    options = parser.parse_args()
    target = OUT / REG["roles"][options.case] / options.case
    asset, selected = verify_case(options.case)
    try:
        run(options.case, target, asset, selected)
    except BaseException as error:
        target.mkdir(parents=True, exist_ok=True)
        write(
            target / "failure.json",
            {"error": str(error), "type": type(error).__name__, "counts": dict(COUNTS)},
        )
        raise
