"""Run the separately registered grid-04 attempt with the original PRE boundary."""

import argparse
import hashlib
import math
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.graduation.perception_io import read, sha

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "plan.json"
PLAN = read(PLAN_FILE)
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
sys.path.insert(0, str((ROOT / PLAN["original_capture_path"]).parent))
import capture_handoff_live as capture  # noqa: E402


def preflight():
    for p, expected in PLAN["input_sha256"].items():
        capture.REQUIRE(sha(ROOT / p) == expected, f"changed PRE parity input: {p}")
    historic = subprocess.check_output(
        ["git", "show", PLAN["execution_base"] + ":" + PLAN["original_capture_path"]], cwd=ROOT
    )
    capture.REQUIRE(
        hashlib.sha256(historic).hexdigest() == PLAN["original_capture_sha256"],
        "original stopped attempt driver changed",
    )
    first = read(capture.tail.OUT / "isolated-rgbd-01-reader-1.json")
    old = PLAN["original_refusal"]
    actual = first["checks"][-1]
    capture.REQUIRE(
        actual["phase"] == "PRE"
        and actual["status"] == "CLEAR"
        and actual["step"] == old["step"]
        and actual["capture_through_gate_ms"] == old["capture_to_gate_ms"],
        "first failure did not match registered evidence",
    )
    capture.REQUIRE(
        capture.clearance_is_accepted(actual["status"], True)
        and not capture.clearance_is_accepted("UNKNOWN", True)
        and not capture.clearance_is_accepted("BLOCKED", True)
        and not capture.clearance_is_accepted("CLEAR", False),
        "original isolated PRE decision differs",
    )
    cutoff = float(PLAN["continuous_feedback_and_hold_limit_ms"])
    above = math.nextafter(cutoff, math.inf)
    capture.REQUIRE(
        capture.feedback_is_timely(cutoff, cutoff)
        and not capture.feedback_is_timely(cutoff, above)
        and not capture.feedback_is_timely(above, cutoff),
        "original continuous feedback timing differs",
    )
    return capture.preflight(expected_head=PLAN["execution_base"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("preflight", "run"))
    args = cli.parse_args()
    frozen = preflight()
    if args.phase == "preflight":
        print("Original PRE, clock binding and both continuous 100 ms boundaries verified.")
    else:
        capture.REQUIRE(
            os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
            "EGL mode unavailable",
        )
        out = capture.tail.OUT / PLAN["new_attempt"]
        attempt = {
            "plan_sha256": sha(PLAN_FILE),
            "entry_sha256": sha(Path(__file__)),
            "corrected_driver_sha256": sha(Path(capture.__file__)),
            "first_attempt_seal_sha256": sha(capture.tail.OUT / "isolated-rgbd-01/seal.json"),
        }
        with patch.multiple(capture, OUT=out, ISOLATED_ID=PLAN["new_id"]):
            capture.run(frozen, second_registration=attempt)
