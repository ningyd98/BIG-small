"""Cold-read the registered capture with its collision pair in JSON representation."""

import argparse
import sys
from copy import deepcopy
from pathlib import Path
from types import FunctionType

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "round-g1-fixed-tcp-branch-native-20261126"
sys.path.insert(0, str(ORIGINAL))
import branch_native as capture  # noqa: E402

PLAN = capture.read(HERE / "plan.json")


def normalized_checks(checks, registered):
    capture.require(len(checks) == len(registered) == PLAN["expected_slots"], "wrong slot count")
    for key, row in checks.items():
        pair = row["static"]["pair"]
        capture.require(
            type(pair) is tuple and len(pair) == 2 and all(type(name) is str for name in pair),
            f"unexpected collision pair representation: {key}",
        )
        row["static"]["pair"] = list(pair)
    capture.require(checks == registered, "independent static preflight changed")
    return checks


def negative_controls(checks, registered):
    slot = next(iter(registered))
    changed_pair = deepcopy(registered)
    changed_pair[slot]["static"]["pair"].reverse()
    changed_gap = deepcopy(registered)
    changed_gap[slot]["static"]["gap_m"] += 1e-12
    missing_slot = {key: value for key, value in registered.items() if key != slot}
    for negative in (changed_pair, changed_gap, missing_slot):
        try:
            normalized_checks(deepcopy(checks), negative)
        except ValueError:
            continue
        raise ValueError("static preflight accepted a tampered registration")


def read():
    for alias, digest in PLAN["input_sha256"].items():
        source, name = alias.split("/", 1)
        path = {"original": ORIGINAL, "sealed": capture.PRIVATE}[source] / name
        capture.require(capture.sha(path) == digest, f"sealed input changed: {alias}")

    registered = capture.read(capture.PRIVATE / "registration.json")["checks"]

    def restored(slots, calibration):
        selected, checks = capture.static_states(slots, calibration)
        negative_controls(checks, registered)
        return selected, normalized_checks(checks, registered)

    original = capture.cold_read
    reader = FunctionType(original.__code__, {**original.__globals__, "static_states": restored})
    return reader()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=("first", "second"))
    args = parser.parse_args()
    root = capture.ROOT / "experiments/results/g1-fixed-tcp-branch-native-readback-20261126"
    result = read()
    root.mkdir(exist_ok=True)
    capture.write(root / f"{args.name}.json", result)
