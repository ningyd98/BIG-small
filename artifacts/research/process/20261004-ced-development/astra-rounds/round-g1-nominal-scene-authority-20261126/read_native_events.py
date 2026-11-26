"""Read original scene-authority evidence with native nested guard events."""

import argparse
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import scene_authority as original

HERE = Path(__file__).resolve().parent
SPEC = HERE / "readback-addendum.json"
EXPECTED = [
    ("RETURN", "BEFORE", 0, 1),
    ("CONTROL", "BEFORE", 0, 2),
    ("CONTROL", "AFTER", 0, 2),
    ("RETURN", "AFTER", 0, 2),
    ("PHYSICS", "BEFORE", 0, 3),
    ("PHYSICS", "BEFORE", 0, 3),
    ("PHYSICS", "AFTER", 1, 3),
    ("PHYSICS", "AFTER", 1, 3),
    ("RETURN", "AFTER", 1, 3),
    ("RETURN", "AFTER", 1, 3),
]
INSPECT_SOURCE = original.inspect_probe


def verify_positive(row):
    require = original.require
    require(
        row["name"] == "native_one_step"
        and row["shutdown_complete"]
        and row["guard_settled"]
        and row["estop"]
        and row["camera_instances"] == 0
        and row["request"]["accepted"]
        and row["physical_steps"] == 1
        and row["initial_model_sha256"] == row["final_model_sha256"]
        and [command["type"] for command in row["commands"]]
        == ["hold_current_joints", "emergency_stop"],
        "positive request, native single step, or safe cleanup changed",
    )
    operations = row["operations"]
    require(not any(event["kind"] == "CAPTURE" for event in operations), "unexpected native camera")
    active = [
        (event["kind"], event["phase"], event["step"], event["operation_id"])
        for event in operations
        if event["kind"] == "PHYSICS" or event["operation_id"] in {2, 3}
    ]
    require(
        active
        == [
            ("CONTROL", "BEGIN", 0, 2),
            ("CONTROL", "END", 0, 2),
            ("PHYSICS", "BEGIN", 0, 3),
            ("PHYSICS", "END", 1, 3),
        ],
        "operation ledger does not prove exactly one native physics step",
    )
    require(
        all(
            event["episode"] == row["episode"] and event["error"] is None
            for event in operations
            if event["operation_id"] in {2, 3}
        ),
        "original operation episode or error status differs",
    )
    guards, close = row["guard_events"][:-1], row["guard_events"][-1]
    require(close == {"kind": "CLOSED", "physics_step": 1}, "wrong native closure")
    for n, (guard, effect, expected) in enumerate(
        zip(guards, row["scope_witnesses"], EXPECTED, strict=True), 1
    ):
        kind, phase, step, identity = expected
        require(
            guard["outcome"] == "ALLOWED"
            and guard["sequence"] == n
            and (guard["kind"], guard["phase"], guard["physics_step"], guard["operation_id"])
            == (kind, phase, step, identity)
            and (effect["kind"], effect["phase"], effect["step"]) == (kind, phase, step)
            and guard["episode_id"] == effect["episode"] == row["episode"]
            and effect["model_sha256"] == row["initial_model_sha256"],
            "ordered native guard provenance differs",
        )


def controls(row):
    dropped, extra, swapped, tick, repeated, crossed = (deepcopy(row) for _ in range(6))
    dropped["scope_witnesses"].pop(4)
    extra["guard_events"].insert(5, deepcopy(extra["guard_events"][4]))
    swapped["scope_witnesses"][2], swapped["scope_witnesses"][3] = (
        swapped["scope_witnesses"][3],
        swapped["scope_witnesses"][2],
    )
    tick["scope_witnesses"][6]["step"] = 2
    repeated["operations"].append(
        next(e for e in repeated["operations"] if e["kind"] == "PHYSICS") | {"operation_id": 8}
    )
    crossed["guard_events"][3]["episode_id"] = "different_native_reset"
    for probe in (dropped, extra, swapped, tick, repeated, crossed):
        try:
            verify_positive(probe)
        except ValueError:
            continue
        raise ValueError("inconsistent native event negative control passed")


def inspect(name, row):
    if name != "native_one_step":
        return INSPECT_SOURCE(name, row)
    verify_positive(row)
    controls(row)
    return "original_owner_step_reproduced_with_exact_nested_boundaries"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plan = original.read(SPEC)
    for key, value in plan["inputs_sha256"].items():
        original.require(
            original.sha(original.ROOT / key) == value, f"recovery input changed: {key}"
        )
    with patch.object(original, "inspect_probe", inspect):
        original.cold(args.output)


if __name__ == "__main__":
    main()
