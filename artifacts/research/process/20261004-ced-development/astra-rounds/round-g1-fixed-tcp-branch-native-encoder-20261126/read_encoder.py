"""Join the assigned pose and independent inverse camera encoders in their own domains."""

import argparse
import inspect
import math
import struct
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAIR = HERE.parent / "round-g1-fixed-tcp-branch-native-readback-20261126"
sys.path.insert(0, str(PAIR))
import read_sealed as pair  # noqa: E402

capture = pair.capture
PLAN = capture.read(HERE / "plan.json")
require = capture.require


def values(robot):
    q = robot["camera_joint_positions_rad"]
    fingers = robot["camera_finger_positions_m"]
    require(len(q) == 7 and len(fingers) == 2, "invalid camera encoder shape")
    return q + fingers


def token(q):
    require(len(q) == 9 and all(math.isfinite(component) for component in q), "invalid pose")
    return struct.pack("<9d", *q)


def compare(assignment, registered, encoder, index, receipt, clock):
    require(token(assignment) == token(registered) == token(receipt["source_step_end_encoders"]),
            "assigned source q differs")
    require(token(values(encoder)) == token(values(index)) == token(values(receipt["robot"])),
            "independently reconstructed exposure encoder differs")
    require(clock == encoder["camera_encoder_sim_time_s"] == index["camera_encoder_sim_time_s"]
            == receipt["robot"]["camera_encoder_sim_time_s"], "exposure encoder clock differs")


def controls(assignment, registered, encoder, index, receipt, clock, other_assignment):
    changed_q = deepcopy(receipt)
    changed_q["source_step_end_encoders"][0] = math.nextafter(assignment[0], math.inf)
    changed_encoder = deepcopy(index)
    changed_encoder["camera_joint_positions_rad"][0] = math.nextafter(values(index)[0], math.inf)
    changed_clock = deepcopy(index)
    changed_clock["camera_encoder_sim_time_s"] -= 1 / 240
    probes = (
        (other_assignment, index, receipt),
        (assignment, index, changed_q),
        (assignment, changed_encoder, receipt),
        (assignment, changed_clock, receipt),
    )
    for q, i, r in probes:
        try:
            compare(q, registered, encoder, i, r, clock)
        except ValueError:
            continue
        raise ValueError("independent encoder checker accepted a negative control")


def read():
    pinned = {
        "capture_script": pair.ORIGINAL / "branch_native.py",
        "registered": capture.PRIVATE / "registration.json",
        "sealed": capture.PRIVATE / "capture-seal.json",
        "pair_reader": PAIR / "read_sealed.py",
        "pair_plan": PAIR / "plan.json",
        "first_failure": PAIR / "original-failure.txt",
    }
    for name, path in pinned.items():
        require(capture.sha(path) == PLAN["sha256"][name], f"frozen input changed: {name}")

    registration = capture.read(pinned["registered"])
    checks = registration["checks"]
    calibration = registration["calibration"]
    model = capture.mujoco.MjModel.from_xml_path(str(capture.native.ASSET))
    model.opt.timestep = 1 / 240
    residuals = {}

    def restored(slots, cal):
        selected, rebuilt = capture.static_states(slots, cal)
        pair.negative_controls(rebuilt, checks)
        return selected, pair.normalized_checks(rebuilt, checks)

    def check_slot(key, row, slot, folder, tick):
        source = slot["row"]["q"]
        receipt = capture.read(folder / f"{tick}-receipt.json")
        data = capture.mujoco.MjData(model)
        capture.native.restore(model, data, slot, calibration)
        encoder = capture.native.camera_encoder_pose(model, data)
        clock = slot["source"]["source_time_s"]
        index = row["robot"]
        compare(source, checks[key]["q"], encoder, index, receipt, clock)
        require(index == receipt["robot"], "capture index robot record differs from receipt")
        if not residuals:
            swapped = checks["r1/" + key.split("/", 1)[1]]["q"]
            controls(source, checks[key]["q"], encoder, index, receipt, clock, swapped)
        errors = [abs(a - b) for a, b in zip(source, values(encoder), strict=True)]
        residuals[key] = {"arm_rad": max(errors[:7]), "finger_m": max(errors[7:])}

    # Keep the frozen file and every other validator intact.
    original = capture.cold_read
    old_call = ('check_encoder(selected[key]["row"]["q"],\n'
                '                              row["robot"]["camera_joint_positions_rad"]'
                ' + row["robot"]["camera_finger_positions_m"])')
    source = inspect.getsource(original)
    require(source.count(old_call) == 1, "frozen encoder call site changed")
    source = source.replace(old_call, "check_slot(key, row, selected[key], folder, tick)")
    namespace = {**original.__globals__, "static_states": restored, "check_slot": check_slot}
    exec(compile(source, str(pinned["capture_script"]), "exec"), namespace)
    result = namespace["cold_read"]()
    require(set(residuals) == set(result["slots"]), "missing independent encoder verification")
    return dict(result, encoder_reconstruction=residuals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=("first", "second"))
    args = parser.parse_args()
    root = capture.ROOT / "experiments/results/g1-fixed-tcp-branch-native-encoder-20261126"
    result = read()
    root.mkdir(exist_ok=True)
    capture.write(root / f"{args.name}.json", result)
