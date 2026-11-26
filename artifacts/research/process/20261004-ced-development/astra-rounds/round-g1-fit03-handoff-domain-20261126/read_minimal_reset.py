"""Remove all native reset facts except the actual exposure identity."""

import argparse
import os
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import check_handoff as original
from scripts.graduation.g1_complete_worker import native_reset_ids

ROOT, INITIAL, HERE = original.ROOT, original.OUT, original.HERE
SPEC = HERE / "plan-addendum.json"
PLAN = original.read(SPEC)
OUT = ROOT / PLAN["out"]
require = original.require
read = original.read
sha = original.sha
store = original.store_json
SCENE = "g1.continuous-payload/dense-fit-03"
RESET_FIELDS = (
    "episode_id error error_type kind operation_id parameters phase physics_step result sim_time_s"
)
SLOT_FIELDS = (
    "arm_commands command_seq frame_file frame_sha256 gripper_command key observable_reset "
    "physical_robot pose_baseline registered_actuation robot role witness_camera_hash "
    "witness_encoder_f64"
)
COMMAND = "accepted after_emergency_stop command_seq episode_id physics_step reason sim_time_s type"
ATTRIBUTES = {
    "physical_robot": "arm_target control dq open_command q tick time_s",
    "registered_actuation": "applied_arm applied_fingers command_seq goal velocity",
    "robot": (
        "camera_encoder_sim_time_s "
        "camera_finger_positions_m camera_joint_positions_rad checksum_sha256 frame_id "
        "last_accepted_gripper_command_step last_accepted_gripper_open physics_step "
        "previous_native_return_step previous_native_successful_skill sim_time_s"
    ),
    "pose_baseline": (
        "anchor_error_object_m anchor_object_m anchor_world_m basis_error_object center_error_m "
        "center_m center_world_m checksum_sha256 dense_plane_samples frame_id ids method "
        "plane_inliers rotation rotation_error_rad rotation_object_to_world"
    ),
}


def exact(row, fields):
    require(type(row) is dict and set(row) == set(fields.split()), "unregistered blinded field")


def values_only(value):
    if type(value) is list:
        for element in value:
            values_only(element)
    else:
        require(
            value is None or type(value) in {int, bool, float, str},
            "unexpected structured data in a measured scalar/vector field",
        )


def reset_identity_only(source):
    native_reset_ids(source["resets"], SCENE, source["episode"])
    result = []
    for event in source["resets"]:
        row = {k: event[k] for k in RESET_FIELDS.split()}
        row["parameters"] = {
            "requested": {"scenario_id": event["parameters"]["requested"]["scenario_id"]}
        }
        row["result"] = (
            None if event["phase"] == "BEGIN" else {"physics_dt_s": event["result"]["physics_dt_s"]}
        )
        result.append(row)
    return {"episode": source["episode"], "resets": result}


def validate_blind(payload):
    exact(payload, "source_capture_sha256 frames")
    require(type(payload["frames"]) is list and len(payload["frames"]) == 4, "wrong slot count")
    for n, slot in enumerate(payload["frames"]):
        exact(slot, SLOT_FIELDS)
        require(
            slot["key"] == f"c{n}" and slot["frame_file"] == f"c{n}.json.gz", "wrong slot packet"
        )
        for name, definition in ATTRIBUTES.items():
            props = slot[name]
            if name != "pose_baseline" or props is not None:
                exact(props, definition)
                for value in props.values():
                    values_only(value)
        for cmd in slot["arm_commands"]:
            exact(cmd, COMMAND + " applied_target_positions_rad target_positions_rad")
            for value in cmd.values():
                values_only(value)
        exact(slot["gripper_command"], COMMAND + " target_open")
        for value in slot["gripper_command"].values():
            values_only(value)
        reset = slot["observable_reset"]
        exact(reset, "episode resets")
        for key in slot.keys() - {
            *ATTRIBUTES,
            "arm_commands",
            "gripper_command",
            "observable_reset",
        }:
            values_only(slot[key])
        require(len(reset["resets"]) == 2, "wrong reset event count")
        for event in reset["resets"]:
            exact(event, RESET_FIELDS)
            for key in event.keys() - {"parameters", "result"}:
                values_only(event[key])
            exact(event["parameters"], "requested")
            requested = event["parameters"]["requested"]
            exact(requested, "scenario_id")
            require(requested["scenario_id"] == SCENE, "wrong native reset scope")
            if event["phase"] == "BEGIN":
                require(event["result"] is None, "BEGIN contains a result")
            else:
                exact(event["result"], "physics_dt_s")
                require(type(event["result"]["physics_dt_s"]) is float, "invalid reset clock")
        native_reset_ids(reset["resets"], SCENE, reset["episode"])


def negative_controls(payload):
    tests = (
        lambda d: d["frames"][0]["observable_reset"]["resets"][1]["result"].update(
            physics_state={}
        ),
        lambda d: d["frames"][0]["observable_reset"]["resets"][0]["parameters"]["requested"].update(
            seed=7
        ),
        lambda d: d["frames"][0]["observable_reset"].update(extra=1),
        lambda d: d["frames"][0]["observable_reset"]["resets"][1]["parameters"]["requested"].update(
            scenario_id="foreign"
        ),
        lambda d: d["frames"][0]["observable_reset"].update(episode="foreign"),
        lambda d: d["frames"][0]["observable_reset"]["resets"][1]["result"].update(
            physics_dt_s=0.01
        ),
        lambda d: d["frames"][0]["observable_reset"]["resets"][1].update(operation_id=8),
        lambda d: d["frames"][0]["observable_reset"]["resets"][1].update(physics_step=1),
        lambda d: d["frames"][0]["observable_reset"]["resets"].pop(),
        lambda d: d["frames"][0]["physical_robot"]["control"].append({"leak": "nested"}),
    )
    for modify in tests:
        trial = deepcopy(payload)
        modify(trial)
        require(
            original.optics.rejected(validate_blind, trial), "extra or broken reset metadata passed"
        )


def prepare():
    for name, expected in PLAN["source_bindings_sha256"].items():
        require(sha(ROOT / name) == expected, "original defect or source changed")
    original.verify_all_inputs()
    old_seal = read(INITIAL / "preflight-seal.json")
    require(
        all(sha(INITIAL / k) == v for k, v in old_seal["inputs"].items()),
        "original blinded packet has changed",
    )
    require(not OUT.exists() and OUT.resolve() == OUT, "new blind root used already")
    earlier = read(INITIAL / "blinded.json")
    accepted = deepcopy(earlier)
    require(len(accepted["frames"]) == 4, "wrong source sample count")
    code = read(INITIAL / "source-key.json")
    OUT.mkdir(parents=True)
    for source, slot in zip(earlier["frames"], accepted["frames"], strict=True):
        r = slot["observable_reset"]
        group = code[slot["key"]]["source_group"]
        obs_path = original.ARCHIVE / group / "observable.json"
        observable = read(obs_path)
        require(
            r == {"episode": observable["episode"], "resets": observable["resets"]},
            "initial package reset does not bind the raw sealed source",
        )
        slot["observable_reset"] = reset_identity_only(r)
        require(
            {k: v for k, v in slot.items() if k != "observable_reset"}
            == {k: v for k, v in source.items() if k != "observable_reset"},
            "not a pure reset metadata removal",
        )
        file = slot["frame_file"]
        with (OUT / file).open("xb") as stream:
            stream.write((INITIAL / file).read_bytes())
        require(sha(OUT / file) == slot["frame_sha256"], "raw RGB-D differs between packages")
    validate_blind(accepted)
    negative_controls(accepted)
    store(OUT / "blinded.json", accepted)
    store(OUT / "source-key.json", code)
    store(
        OUT / "preflight-seal.json",
        old_seal
        | {
            "inputs": {path.name: sha(path) for path in sorted(OUT.iterdir())},
            "prior_package_sha256": sha(INITIAL / "preflight-seal.json"),
            "addendum_sha256": sha(SPEC),
            "redactor_sha256": sha(Path(__file__).resolve()),
        },
    )


def cold(output):
    permitted = {
        OUT / "preflight-seal.json",
        OUT / "blinded.json",
        *(OUT / f"c{n}.json.gz" for n in range(4)),
        original.ALLOCATION,
        original.ALLOCATION.parents[1] / "allocation.json",
        original.ASSET,
        original.inputs.expand("{D}/runtime-build.json"),
        original.inputs.expand("{D}/scripts/graduation/g1_visibility_vision.py"),
        *(
            original.CALIBRATION / name
            for name in ("manifest.json", "panel-primary.npy", "panel-start.npy")
        ),
        output.resolve(),
    }
    private = ROOT / "experiments"

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            p = Path(os.fsdecode(args[0])).resolve()
            if p.is_relative_to(private) and p not in permitted:
                raise PermissionError("outside minimal reset cold read inputs")

    sys.addaudithook(audit)
    for path in (
        INITIAL / "blinded.json",
        INITIAL.parent / "readback.primary.json",
        OUT / "source-key.json",
        original.ARCHIVE / "b0/observable.json",
        original.ARCHIVE / "b1/native.json",
        original.ARCHIVE / "b1/physical.jsonl.gz",
    ):
        try:
            path.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("cold read accessed a blocked source")
    seal = read(OUT / "preflight-seal.json")
    require(
        seal["addendum_sha256"] == sha(SPEC)
        and seal["redactor_sha256"] == sha(Path(__file__).resolve()),
        "minimal reset seal changed",
    )
    payload = read(OUT / "blinded.json")
    validate_blind(payload)
    negative_controls(payload)
    with patch.object(original, "OUT", OUT):
        original.blinded_read(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "cold"))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    original.cv2.setNumThreads(1)
    if args.mode == "prepare":
        prepare()
    else:
        cold(args.output)


if __name__ == "__main__":
    main()
