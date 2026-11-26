"""Reconstruct the camera's RK4 encoder buffer by CPU-only native command replay."""

import gzip
import json
from collections import defaultdict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from struct import pack

import mujoco
from native_dwell import (
    HERE,
    OUT,
    ROOT,
    configured_inputs,
    native,
    physical_comparison,
    read,
    require,
    sha,
    store_json,
)

RECOVERY = HERE / "exposure-replay-plan.json"
PROOF = OUT.parent / "exposure-replay.json"


def encoder_bits(packet):
    return pack(
        "<10d",
        *packet["camera_joint_positions_rad"],
        *packet["camera_finger_positions_m"],
        packet["camera_encoder_sim_time_s"],
    ).hex()


def evidence(name, item, event, packet, replayed_pass, replayed_integration):
    robot = item["robot"]
    require(
        encoder_bits(packet) == encoder_bits(robot)
        and event["pass_state_hashes"] == [replayed_pass] * 2
        and item["integration_sha256"] == replayed_integration
        and event["physics_step"] == robot["physics_step"]
        and event["sim_time_s"] == packet["camera_encoder_sim_time_s"]
        and event["frame_id"] == robot["frame_id"]
        and event["explicit_role"] == item["role"],
        "replayed exposure disagrees with sealed native event",
    )
    return {
        "route": name,
        "frame_id": event["frame_id"],
        "tick": event["physics_step"],
        "role": item["role"],
        "operation_id": event["operation_id"],
        "encoder_f64_hex": encoder_bits(packet),
        "camera_state_sha256": replayed_pass,
        "integration_sha256": replayed_integration,
    }


def checked_witness(name, item, event, witness):
    packet = item["robot"]
    expected = evidence(
        name, item, event, packet, event["pass_state_hashes"][0], item["integration_sha256"]
    )
    require(witness == expected, "foreign, altered or missing replayed exposure slot")


def source_command():
    directory = HERE.parent / "round-g1-payload-pad-overlap-20261125"
    spec = spec_from_file_location("b03_replay_commands", directory / "pad-physics-replay.py")
    replay = module_from_spec(spec)
    spec.loader.exec_module(replay)
    return replay.command


def one(name, count, setup, report):
    terminal, plan, roots, case, _, _ = setup
    folder = OUT / name
    receipt = read(folder / "native.json")
    catalog = read(folder / "frames.json")
    require(len(catalog) == 32 and receipt["rows"] == count + 1, "source end or slots changed")
    by_tick = defaultdict(list)
    for cmd in receipt["commands"]:
        require(cmd["accepted"] and 0 <= cmd["physics_step"] < count, "unregistered command")
        by_tick[cmd["physics_step"]].append(cmd)
    require(
        [c for tick in sorted(by_tick) for c in by_tick[tick]] == receipt["commands"],
        "source command order changed",
    )
    slots = {item["robot"]["physics_step"]: item for item in catalog}
    source_events = {event["frame_id"]: event for event in receipt["events"] if "frame_id" in event}
    backend = native.MuJoCoPhysicsBackend()
    source_reset = receipt["resets"][0]["parameters"]["requested"]
    scenario = terminal.prepare_backend(backend, source_reset, case, roots, plan)
    restore = source_command()
    report.update(steps=0, new_rgbd=0, shots=[], max_native_difference=0.0)
    with (
        terminal.render_free(backend, backend.shutdown),
        gzip.open(folder / "physical.jsonl.gz", "rt") as archive,
    ):
        backend.reset(scenario)
        backend._last_contacts = backend._read_contacts()
        for tick, line in enumerate(archive):
            require(backend.total_physics_steps == tick <= count, "replay tick or budget mismatch")
            error = physical_comparison(terminal.capture_state(backend, mujoco), json.loads(line))
            report["max_native_difference"] = max(error, report["max_native_difference"])
            commands = by_tick.pop(tick, [])
            item = slots.pop(tick, None)
            if item is not None:
                if item["role"] == "PRE":
                    require(
                        [cmd["type"] for cmd in commands[-2:]] == ["hold_current_joints", "gripper"]
                        and commands[-1]["target_open"] is True,
                        "wrong placement terminal order",
                    )
                    for cmd in commands[:-2]:
                        restore(backend, cmd)
                    commands = commands[-2:]
                else:
                    require(not commands, "unexpected command within dwell")
                data = backend._data
                event = source_events[item["robot"]["frame_id"]]
                packet = native.camera_encoder_pose(backend._model, data)
                replayed_pass = native.MuJoCoRGBDCamera._physics_state_hash(data)
                witnessed_state = terminal.integration_digest(backend, mujoco)
                report["shots"].append(
                    evidence(
                        name,
                        item,
                        event,
                        packet,
                        replayed_pass,
                        witnessed_state["mujoco_integration_sha256"],
                    )
                )
            for cmd in commands:
                restore(backend, cmd)
            if tick < count:
                require(backend.step(1).physics_steps == 1, "native replay single-step failed")
                report["steps"] += 1
        require(
            not by_tick
            and not slots
            and len(report["shots"]) == 32
            and report["steps"] == backend.total_physics_steps == count
            and backend._camera is None,
            "CPU replay evidence incomplete",
        )
        actual = [
            {k: v for k, v in cmd.items() if k != "episode_id"} for cmd in backend.command_records
        ]
        expected = [
            {k: v for k, v in cmd.items() if k != "episode_id"} for cmd in receipt["commands"]
        ]
        require(actual == expected, "native replay commands differ")


def main():
    plan = read(RECOVERY)
    require(not PROOF.exists(), "registered CPU replay already consumed")
    for file, expected in plan["input_sha256"].items():
        require(sha(ROOT / file) == expected, f"replay source changed: {file}")
    capture = OUT / "capture-seal.json"
    seal = read(capture)
    require(
        seal["complete"] and all(sha(OUT / k) == v for k, v in seal["members"].items()),
        "capture sealed members changed",
    )
    context = configured_inputs()
    run = {
        "plan_sha256": sha(RECOVERY),
        "program_sha256": sha(Path(__file__).resolve()),
        "capture_sha256": sha(capture),
        "complete": False,
        "routes": {},
    }
    try:
        for name, count in plan["routes"].items():
            report = run["routes"][name] = {}
            one(name, count, context, report)
        run["complete"] = True
    except BaseException as error:
        run["error"] = {"type": type(error).__name__, "reason": str(error)}
        raise
    finally:
        store_json(PROOF, run)


if __name__ == "__main__":
    main()
