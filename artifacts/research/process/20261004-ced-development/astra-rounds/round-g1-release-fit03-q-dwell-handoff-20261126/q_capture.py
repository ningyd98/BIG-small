"""Single registered B03/Q experiment and its independent native exposure witness."""

# ruff: noqa: E402
import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
PRIVATE = ROOT / PLAN["output"]
ACQUISITION = PRIVATE / "native-01"
SOURCE = ROOT / PLAN["source_dwell"]
BLIND = PRIVATE / "blind-01"
DYNAMIC = HERE.parent / "round-g1-release-fit03-dwell-20261126"
HANDOFF = HERE.parent / "round-g1-fit03-handoff-domain-20261126"
sys.path[:0] = [str(DYNAMIC), str(HANDOFF)]

import check_handoff as handoff
import native_dwell as dwell
import read_dwell as reader
import read_minimal_reset as minimal
import replay_exposure as replay

require = dwell.require
store = dwell.store_json
PROGRAMS = (HERE / "q_capture.py", HERE / "read_q.py")


def verified_tree(folder, entries):
    require(
        all(sha(folder / name) == digest for name, digest in entries.items()),
        f"frozen evidence changed: {folder.name}",
    )


def configure():
    for path, expected in PLAN["pins_sha256"].items():
        require(sha(ROOT / path) == expected, f"change in prior plan or experiment: {path}")
    prior = read(SOURCE / "capture-seal.json")
    require(prior["complete"], "prior capture incomplete")
    verified_tree(SOURCE, prior["members"])
    context = dwell.configured_inputs()
    b, p = [read(SOURCE / name / "native.json") for name in ("b0", "b1")]
    require(
        b["complete"]
        and p["complete"]
        and b["prefix"] == p["prefix"]
        and p["prefix"]["tick"] == 2840,
        "B/P true pre-fork state no longer joins",
    )
    return context, p["prefix"]


def programs():
    return {program.name: sha(program) for program in PROGRAMS}


def capture():
    context, reference = configure()
    native = dwell.native
    require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
        "original exclusive EGL not selected",
    )
    require(
        not ACQUISITION.exists() and ACQUISITION.resolve() == ACQUISITION, "Q already attempted"
    )
    ACQUISITION.mkdir(parents=True)
    hardware_counts = {"camera_requests": 0}
    advance, expose = (
        native.MuJoCoPhysicsBackend._advance_unobserved_physics_step,
        native.MuJoCoRGBDCamera._capture,
    )

    def step_under_budget(backend):
        require(
            backend.total_physics_steps < PLAN["limits"]["physics_steps_Q"],
            "native Q physics ceiling reached",
        )
        return advance(backend)

    def expose_under_budget(camera, *args, **kwargs):
        hardware_counts["camera_requests"] += 1
        require(
            hardware_counts["camera_requests"] <= PLAN["limits"]["native_camera_requests_max"],
            "native Q image ceiling reached",
        )
        return expose(camera, *args, **kwargs)

    originals = dwell.inputs.originals()
    store(
        ACQUISITION / "registration.json",
        {
            "q_plan": sha(HERE / "plan.json"),
            "q_plan_text": sha(HERE / "plan.md"),
            "programs_sha256": programs(),
            "source_B_P_sha256": sha(SOURCE / "capture-seal.json"),
            "prefix": reference,
            "limits": PLAN["limits"],
            "goal_xy_m": PLAN["goal_Q_xy_m"],
            "calibration": context[-2],
            "historical_controls": context[-1],
            "formal_originals": originals,
        },
    )
    finished = False
    try:
        with (
            native.device((ROOT / native.NATIVE["exclusive_lock"]).parent),
            patch.object(
                native.MuJoCoPhysicsBackend, "_advance_unobserved_physics_step", step_under_budget
            ),
            patch.object(native.MuJoCoRGBDCamera, "_capture", expose_under_budget),
        ):
            dwell.capture_route(ACQUISITION / "q", "Q", context, reference)
        require(dwell.inputs.originals() == originals, "prior formal original changed")
        require(
            hardware_counts["camera_requests"] == 42, "unexpected number of native camera requests"
        )
        finished = True
    except BaseException as failure:
        store(
            ACQUISITION / "aborted.json", {"type": type(failure).__name__, "reason": str(failure)}
        )
        raise
    finally:
        store(
            ACQUISITION / "capture-seal.json",
            {"complete": finished, "members": dwell.hashes(ACQUISITION), **hardware_counts},
        )


def checked_capture():
    seal = read(ACQUISITION / "capture-seal.json")
    require(seal["complete"] and seal["camera_requests"] == 42, "native Q attempt incomplete")
    verified_tree(ACQUISITION, seal["members"])
    reg = read(ACQUISITION / "registration.json")
    require(
        reg["programs_sha256"] == programs()
        and reg["q_plan"] == sha(HERE / "plan.json")
        and reg["source_B_P_sha256"] == sha(SOURCE / "capture-seal.json"),
        "foreign Q capture registration",
    )
    return sha(ACQUISITION / "capture-seal.json")


def witness():
    context, _ = configure()
    seal_hash = checked_capture()
    output = PRIVATE / "exposure-witness.json"
    require(not output.exists(), "independent exposure replay already consumed")
    q = read(ACQUISITION / "q/native.json")
    count = q["open_tick"] + 480
    require(
        count == q["rows"] - 1 <= PLAN["limits"]["cpu_physics_steps_max"],
        "unexpected native Q source endpoint",
    )
    unlocked = {}
    complete = False
    try:
        with patch.object(replay, "OUT", ACQUISITION):
            replay.one("q", count, context, unlocked)
        complete = True
    finally:
        store(output, {"complete": complete, "source_capture_sha256": seal_hash, "route": unlocked})


def prepare_blind():
    seal = checked_capture()
    raw_witness = read(PRIVATE / "exposure-witness.json")
    require(
        raw_witness["complete"] and raw_witness["source_capture_sha256"] == seal,
        "Q witness does not bind acquisition",
    )
    root = ACQUISITION / "q"
    actual = read(root / "native.json")
    cat = read(root / "frames.json")
    observed = read(root / "observable.json")
    place, release, closed, opened = reader.action_context(observed, cat)
    references = raw_witness["route"]["shots"]
    require(len(references) == 32, "independent exposure witness incomplete")
    reset = minimal.reset_identity_only(
        {"resets": observed["resets"], "episode": observed["episode"]}
    )
    slots = []
    BLIND.mkdir()
    necessary_states = handoff.one_tick_rows(
        root / "physical.jsonl.gz",
        {cat[0]["robot"]["physics_step"], cat[-1]["robot"]["physics_step"]},
    )
    for item, witness in zip(cat, references, strict=True):
        current = item["robot"]
        (event,) = [e for e in observed["events"] if e.get("frame_id") == current["frame_id"]]
        replay.checked_witness("q", item, event, witness)
        file = root / item["path"]
        original = BLIND / item["path"]
        with original.open("xb") as stream:
            stream.write(file.read_bytes())
        require(sha(original) == item["sha256"], "Q packet changed")
        condensed = {
            name: item[name]
            for name in (
                "role",
                "path",
                "sha256",
                "robot",
                "integration_sha256",
                "seed",
                "exposure_seed_state",
            )
        }
        condensed["event"] = event
        condensed["endpoint"] = None
        if item["role"] in {"PRE", "DWELL-30"}:
            step = current["physics_step"]
            sequence, arm, gripper = handoff.command_prefix(
                actual["commands"], actual["actions"], observed, item["role"], step
            )
            endpoint = {
                "role": item["role"],
                "robot": current,
                "physical_robot": necessary_states[step],
                "command_seq": sequence,
                "arm_commands": arm,
                "gripper_command": gripper,
            }
            endpoint["registered_actuation"] = handoff.actuator_values(endpoint)
            condensed["endpoint"] = endpoint
        slots.append(condensed)
    store(
        BLIND / "input.json",
        {
            "capture_seal_sha256": seal,
            "observable_reset": reset,
            "actions": [place, release],
            "gripper": [closed, opened],
            "slots": slots,
        },
    )
    store(
        BLIND / "blind-seal.json",
        {
            "acquisition_sha256": seal,
            "programs_sha256": programs(),
            "witness_sha256": sha(PRIVATE / "exposure-witness.json"),
            "members": {p.name: sha(p) for p in sorted(BLIND.iterdir())},
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "capture", "witness", "prepare_blind"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.mode == "preflight":
        _, reference = configure()
        print(reference)
    else:
        globals()[args.mode]()


if __name__ == "__main__":
    # Only baseline/design inputs are inherited. The candidate key remains Q in native receipts.
    inherited = dwell.PLAN
    with patch.object(
        dwell,
        "PLAN",
        inherited
        | {
            "baseline": PLAN["baseline"],
            "conditions": PLAN["conditions"],
            "limits": inherited["limits"] | {"physics_steps_Q": PLAN["limits"]["physics_steps_Q"]},
        },
    ):
        main()
