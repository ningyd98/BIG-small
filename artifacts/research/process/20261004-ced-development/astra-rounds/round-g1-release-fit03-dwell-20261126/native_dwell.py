# ruff: noqa: E402
"""Two registered B03 routes ending before RETREAT."""

import argparse
import gzip
import hashlib
import inspect
import json
import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter_ns

import cv2
import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import ROOT, read, sha

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

HERE = Path(__file__).resolve().parent
ROUNDS = HERE.parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
FIT = ROOT / PLAN["fit_root"]
SOURCE_B = ROOT / PLAN["original_B"]
for folder in (
    "round-g1-release-camera-ab-20261126",
    "round-g1-release-optical-separation-20261125",
    "round-g1-continuous-payload-observation-20261125",
):
    sys.path.insert(0, str(ROUNDS / folder))

import release_camera_ab_capture as native
import release_camera_ab_inputs as inputs
import release_camera_ab_optics as optics


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def store_json(path, value):
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, sort_keys=True, allow_nan=False)
        out.write("\n")


def import_terminal():
    path = ROUNDS / "round-g1-release-terminal-rebound-20261125/terminal_rebound.py"
    spec = spec_from_file_location("b03_frozen_terminal", path)
    terminal = module_from_spec(spec)
    spec.loader.exec_module(terminal)
    return terminal


def configured_inputs():
    for file, digest in PLAN["input_sha256"].items():
        require(sha(ROOT / file) == digest, f"source changed: {file}")
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == PLAN["baseline"],
        "planning baseline changed",
    )
    terminal = import_terminal()
    p, roots = terminal.design()
    case = next(c for c in p["cases"] if c["id"] == "dense-fit-03")
    require(case["seed"] == PLAN["physical_seed"], "frozen seed changed")
    for component in (MuJoCoSkillRobot, VisualServoSession, native.MuJoCoPhysicsBackend):
        require(
            Path(inspect.getfile(component)).is_relative_to(ROOT / PLAN["runtime_root"] / "src"),
            "unregistered native import",
        )
    terminal.native_components(roots)
    _, slots, calibration = inputs.verify_inputs()
    control = optics.historical_controls(slots)
    source_spec = read(FIT / "sensor-receipt.json")
    require(source_spec["renderer"] == calibration["renderer"]["renderer"], "source GPU changed")
    require(
        sha(SOURCE_B / "native-trace.jsonl.gz") == read(SOURCE_B / "receipt.json")["trace_sha256"],
        "source B trace did not join",
    )
    return terminal, p, roots, case, calibration, control


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def peeled(commands):
    return [{k: v for k, v in row.items() if k != "episode_id"} for row in commands]


def physical_comparison(actual, archived):
    require(
        (actual["tick"], actual["open_command"]) == (archived["tick"], archived["open_command"]),
        f"original tick or gripper differs at {actual['tick']}",
    )
    error = 0.0

    def compare(a, b):
        nonlocal error
        error = max(error, float(np.max(np.abs(np.asarray(a, dtype=float) - b), initial=0)))

    for k in ("time_s", "q", "dq", "object_qvel", "arm_target", "control", "tcp_xyz_m", "tcp_R"):
        compare(actual[k], archived[k])
    for name, (xyz, axes) in actual["geom"].items():
        source_xyz, source_axes = archived["geom"][name]
        compare(xyz, source_xyz)
        compare(axes, source_axes)
    contact_keys = ("names", "illegal", "expected_workpiece")
    require(
        [tuple(c[k] for k in contact_keys) for c in actual["contacts"]]
        == [tuple(c[k] for k in contact_keys) for c in archived["contacts"]],
        f"native contact topology changed at {actual['tick']}",
    )
    for a, b in zip(actual["contacts"], archived["contacts"], strict=True):
        compare([a["distance_m"], a["normal_n"]], [b["distance_m"], b["normal_n"]])
    require(
        error <= PLAN["acceptance"]["source_replay_atol_native_units"],
        f"original native state differs at {actual['tick']}: {error:g}",
    )
    return error


def motion(plan, backend, arm, skill, xy):
    high, low = plan["high_low_z_m"]
    reg = read(
        ROUNDS
        / "round-g1-continuous-payload-observation-20261125/continuous-diagnostic-registration.json"
    )
    slot = next(row for row in reg["fit"] if row["id"] == "dense-fit-03")
    aim = np.asarray(slot["center_m"]) + np.asarray(slot["aim_offset_m"])
    require(np.allclose(aim, plan["aim_m"], rtol=0, atol=1e-15), "frozen grasp aim changed")
    lift_z = max(high, float(aim[2]) + 0.1)
    place_z = float(aim[2]) + 0.004
    require(abs(place_z - low) < 1e-15, "frozen place z changed")
    target_low = Pose(x=aim[0], y=aim[1], z=aim[2])
    target_high = Pose(x=aim[0], y=aim[1], z=lift_z)
    here = backend.get_tcp_pose()
    vertical = Pose(x=here.x, y=here.y, z=max(0.16, here.z + 0.10))
    kwargs = plan["motion"]
    calls = {
        "MOVE_ABOVE": lambda: arm.move_above("object", resolved_target=target_high, **kwargs),
        "APPROACH": lambda: arm.approach("object", resolved_target=target_low, **kwargs),
        "GRASP": lambda: arm.grasp("object", timeout_ms=1000),
        "LIFT": lambda: arm.lift(vertical.z - here.z, resolved_target=vertical, **kwargs),
        "MOVE_TO_REGION": lambda: arm.move_to_region(
            "target_region", resolved_target=Pose(x=xy[0], y=xy[1], z=lift_z), **kwargs
        ),
        "PLACE": lambda: arm.place(
            "target_region", resolved_target=Pose(x=xy[0], y=xy[1], z=place_z), **kwargs
        ),
    }
    if skill == "GRASP":
        return calls[skill]()
    clearance = None
    if skill == "LIFT":
        clearance = VerticalClearancePath(
            task_id="dense-fit-03",
            step_id=skill,
            skill=skill,
            start_m=(here.x, here.y, here.z),
            target_m=(vertical.x, vertical.y, vertical.z),
            minimum_height_m=0.08,
        )
    with arm.visual_servo(
        VisualServoSession(lambda current: current, vertical_clearance=clearance)
    ):
        return calls[skill]()


def capture_route(folder, name, context, expected_prefix):
    terminal, p, roots, case, cal, _ = context
    folder.mkdir()
    rows, catalog, events, reset_events, actions = [], [], [], [], []
    stats = {"attempts": 0, "returned": 0, "max_original_numeric_delta": 0.0}
    outcome = {"condition": name, "complete": False}
    backend = native.MuJoCoPhysicsBackend()
    arm = MuJoCoSkillRobot(backend)
    source_reset = read(FIT / "native-resets.json")[0]["parameters"]["requested"]
    scenario = terminal.prepare_backend(backend, source_reset, case, roots, p)
    original_commands = peeled(read(FIT / "native-commands.json"))
    locked_ticks = PLAN["limits"][f"physics_steps_{name}"]
    open_tick = None
    explicit = None
    sizes = {geom: backend._model.geom(geom).size.tolist() for geom in terminal.DATA_GEOMS}

    def native_event(event):
        if event.kind == "RESET":
            reset_events.append(plain(event))
        if event.kind != "CAPTURE":
            return
        entry = native.observe_pass(event) | {"explicit_role": explicit}
        events.append(entry)
        if event.phase == "BEGIN":
            stats["attempts"] += 1
            require(stats["attempts"] <= 42, "route image budget reached")
            if explicit is None:
                require(
                    sum(e["phase"] == "BEGIN" and e["explicit_role"] is None for e in events) <= 10,
                    "route implicit image budget reached",
                )
        if event.phase == "END" and event.error is None:
            stats["returned"] += 1
            require(
                len(entry["pass_state_hashes"]) == 2
                and len(set(entry["pass_state_hashes"])) == 1
                and entry["instance_count"] == 0,
                "camera RGB/depth state diverged",
            )

    def snapshot(_event=None):
        row = terminal.capture_state(backend, mujoco)
        tick = row["tick"]
        require(tick == len(rows) and tick <= locked_ticks, "missing or over-budget integration")
        rows.append(row)
        require(not any(c["illegal"] for c in row["contacts"]), f"illegal contact at step {tick}")
        if open_tick is not None and tick >= open_tick + 240:
            gaps, _, inside = terminal.gap_and_table(row, sizes)
            issues = terminal.dwell_issues(row, gaps, inside)
            require(not issues, f"dwell physical refusal at {tick}: {issues}")

    def expose(role, seed):
        nonlocal explicit
        explicit = role
        q = backend._data.qpos[:9].copy()
        step = backend.total_physics_steps
        before = terminal.integration_digest(backend, mujoco)["mujoco_integration_sha256"]
        preceding_rng = digest(backend._rng.bit_generator.state)
        backend._rng = np.random.default_rng(seed)
        exposure_rng = digest(backend._rng.bit_generator.state)
        start = perf_counter_ns()
        try:
            frame = native.observation_from_sensor_frame(
                backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
            )
            exposure_ms = (perf_counter_ns() - start) / 1e6
        finally:
            explicit = None
        after = terminal.integration_digest(backend, mujoco)["mujoco_integration_sha256"]
        require(
            before == after
            and step == backend.total_physics_steps
            and np.array_equal(q, backend._data.qpos[:9])
            and frame.sim_time_s == backend.get_sim_time(),
            "capture changed the physical state or clock",
        )
        slot = {
            "role": role,
            "seed": seed,
            "pre_seed_state": preceding_rng,
            "exposure_seed_state": exposure_rng,
            "after_capture_seed_state": digest(backend._rng.bit_generator.state),
            "integration_sha256": before,
            "capture_ms": exposure_ms,
        }
        packet = native.camera_encoder_pose(backend._model, backend._data)
        require(
            packet["camera_encoder_sim_time_s"] == frame.sim_time_s,
            "encoder exposure is not synchronous",
        )
        completed = actions[-1]
        latest = next(
            row
            for row in reversed(backend.command_records)
            if row["type"] == "gripper" and row["accepted"]
        )
        robot = dict(
            packet,
            physics_step=step,
            sim_time_s=frame.sim_time_s,
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            previous_native_successful_skill=completed["skill"],
            previous_native_return_step=completed["return_step"],
            last_accepted_gripper_open=latest["target_open"],
            last_accepted_gripper_command_step=latest["physics_step"],
        )
        file = folder / f"{len(catalog):02d}.json.gz"
        with file.open("xb") as output:
            output.write(gzip.compress(frame.model_dump_json().encode(), 2, mtime=0))
        catalog.append(slot | {"path": file.name, "sha256": sha(file), "robot": robot})

    def operate(skill):
        begin = backend.total_physics_steps
        action = motion(PLAN, backend, arm, skill, PLAN["conditions"][name])
        actions.append(
            dict(
                skill=skill,
                start_step=begin,
                return_step=backend.total_physics_steps,
                success=action.success,
                result=plain(action),
            )
        )
        require(action.success, f"{name} {skill} returned {action.error_code}")

    try:
        with backend.observe_operation_boundaries(native_event):
            backend.reset(scenario)
            native.verify_camera_model(backend._model, backend._data, cal)
            outcome["renderer"] = native.gl_identity(cal)
            backend._rng = np.random.default_rng(PLAN["depth_seed_initial"])
            backend._last_contacts = backend._read_contacts()
            snapshot()
            with backend.observe_physics_steps(snapshot):
                with backend.sensor_capture_on_demand():
                    backend.step(120)
                for skill in ("MOVE_ABOVE", "APPROACH", "GRASP", "LIFT"):
                    operate(skill)
                require(
                    [a["return_step"] for a in actions] == PLAN["prefix_returns"],
                    "frozen successful prefix clock changed",
                )
                with backend.sensor_capture_on_demand():
                    backend.step(120)
                step = backend.total_physics_steps
                require(
                    step == PLAN["boundary_ticks_B"][0]
                    and arm.get_state().holding_object_id == "object",
                    "closed, held workpiece/return boundary changed",
                )
                commands = peeled(backend.command_records)
                require(
                    commands
                    == [
                        c
                        for c in original_commands
                        if c["physics_step"] <= step
                        and c["command_seq"] <= commands[-1]["command_seq"]
                    ],
                    "frozen prefix commands differ",
                )
                outcome["prefix"] = {
                    "tick": step,
                    "commands_sha256": digest(commands),
                    "physics_sha256": digest(rows),
                    "returns": [a["return_step"] for a in actions],
                    "integration_sha256": terminal.integration_digest(backend, mujoco)[
                        "mujoco_integration_sha256"
                    ],
                }
                if expected_prefix is not None:
                    require(outcome["prefix"] == expected_prefix, "paired prefix differs")
                for skill in ("MOVE_TO_REGION", "PLACE"):
                    operate(skill)
                open_tick = backend.total_physics_steps
                outcome["open_tick"] = open_tick
                if name == "B":
                    require(
                        [a["return_step"] for a in actions[-2:]] == PLAN["boundary_ticks_B"][1:3],
                        "B MOVE/PLACE clock differs",
                    )
                state = rows[open_tick]
                _, _, inside = terminal.gap_and_table(state, sizes)
                require(
                    not state["open_command"]
                    and arm.get_state().holding_object_id == "object"
                    and inside
                    and any(
                        set(c["names"]) == {terminal.OBJECT, terminal.TABLE} and c["normal_n"] > 0
                        for c in state["contacts"]
                    ),
                    "physical release handoff rejected",
                )
                with native.on_demand_with_camera_cleanup(backend):
                    expose("PRE", PLAN["pre_noise_seed"])
                    q = backend._data.qpos[:7].tolist()
                    require(
                        backend.command_records[-1]["type"] == "joint_target",
                        "true final PLACE arm command missing",
                    )
                    backend.hold_current_joints()
                    hold = backend.command_records[-1]
                    require(
                        hold["type"] == "hold_current_joints"
                        and hold["accepted"]
                        and hold["physics_step"] == open_tick
                        and hold["applied_target_positions_rad"] == q
                        and not backend._pending_joint_targets,
                        "hold did not match pre-open encoders",
                    )
                    command_count = len(backend.command_records)
                    action = arm.release(timeout_ms=PLAN["release_timeout_ms"])
                    tick = backend.total_physics_steps
                    actions.append(
                        dict(
                            skill="RELEASE",
                            start_step=open_tick,
                            return_step=tick,
                            success=action.success,
                            result=plain(action),
                        )
                    )
                    (command,) = backend.command_records[command_count:]
                    require(
                        command["accepted"]
                        and command["type"] == "gripper"
                        and command["target_open"]
                        and command["physics_step"] == open_tick
                        and tick == open_tick + 240
                        and action.success,
                        "true OPEN or RELEASE return rejected",
                    )
                    for number, offset in enumerate(PLAN["dwell_offsets_after_open"]):
                        if number:
                            backend.step(8)
                        require(
                            backend.total_physics_steps == open_tick + offset, "dwell cadence drift"
                        )
                        expose(
                            f"DWELL-{number:02d}",
                            PLAN["dwell_seed_first"] + number * PLAN["dwell_seed_stride"],
                        )
                    require(backend.total_physics_steps == open_tick + 480, "wrong dwell endpoint")
                    outcome["commands"] = plain(backend.command_records)
            outcome["episode"] = reset_events[-1]["episode_id"]
        require(
            len(catalog) == 32 and stats["attempts"] == stats["returned"] == 42,
            "unexpected explicit or implicit exposure count",
        )
        if name == "B":
            with gzip.open(SOURCE_B / "native-trace.jsonl.gz", "rt") as src:
                stats["max_original_numeric_delta"] = max(
                    physical_comparison(a, json.loads(b)) for a, b in zip(rows, src, strict=True)
                )
            require(open_tick + 480 == PLAN["boundary_ticks_B"][-1], "wrong B terminal step")
        outcome["complete"] = True
    finally:
        if "commands" not in outcome:
            outcome["commands"] = plain(backend.command_records)
        if backend._data is not None:
            backend.shutdown()
        with (folder / "physical.jsonl.gz").open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as archive:
                for row in rows:
                    archive.write(encode(row) + b"\n")
        store_json(folder / "frames.json", catalog)
        store_json(
            folder / "observable.json",
            {
                "complete": outcome["complete"],
                "episode": outcome.get("episode"),
                "events": events,
                "resets": reset_events,
                "actions": [
                    {k: v for k, v in action.items() if k != "result"} for action in actions
                ],
                "gripper": [entry for entry in outcome["commands"] if entry["type"] == "gripper"],
            },
        )
        store_json(
            folder / "native.json",
            outcome
            | {
                "statistics": stats,
                "actions": actions,
                "resets": reset_events,
                "events": events,
                "geom_sizes": sizes,
                "rows": len(rows),
            },
        )
    return outcome["prefix"]


def hashes(folder, *, omit=()):
    return {
        p.relative_to(folder).as_posix(): sha(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name not in omit
    }


def capture():
    context = configured_inputs()
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "exclusive EGL required",
    )
    require(
        not OUT.exists() and OUT.resolve() == OUT, "registration already consumed or path aliases"
    )
    OUT.mkdir(parents=True)
    originals = inputs.originals()
    store_json(
        OUT / "registration.json",
        {
            "plan_sha256": sha(HERE / "plan.json"),
            "plan_md_sha256": sha(HERE / "plan.md"),
            "program_sha256": sha(Path(__file__).resolve()),
            "calibration": context[-2],
            "historical_controls": context[-1],
            "formal_originals": originals,
        },
    )
    try:
        with native.device((ROOT / native.NATIVE["exclusive_lock"]).parent):
            prefix = capture_route(OUT / "b0", "B", context, None)
            capture_route(OUT / "b1", "P", context, prefix)
        require(inputs.originals() == originals, "frozen evidence changed")
    except BaseException as error:
        store_json(OUT / "aborted.json", {"type": type(error).__name__, "reason": str(error)})
        raise
    finally:
        store_json(
            OUT / "capture-seal.json",
            {"members": hashes(OUT), "complete": not (OUT / "aborted.json").exists()},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.mode == "preflight":
        context = configured_inputs()
        print(
            json.dumps(
                {
                    "physical_cases": ["B", "P"],
                    "historical_controls": context[-1],
                    "native_versions": [mujoco.__version__, cv2.__version__, np.__version__],
                }
            )
        )
    else:
        capture()


if __name__ == "__main__":
    main()
