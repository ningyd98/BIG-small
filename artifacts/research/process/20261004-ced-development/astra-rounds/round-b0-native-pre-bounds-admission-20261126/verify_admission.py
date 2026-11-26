"""Check the real B0 stage entry with frozen pools and no usable credential service."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.run_rgbd_pilot import run_ced_pilot


class CredentialSentinel:
    def __init__(self):
        self.calls = 0

    def has_secret(self, _profile):
        self.calls += 1
        raise RuntimeError("sentinel has no credentials")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("expected_has_secret_calls", type=int, choices=(0, 1))
    args = parser.parse_args()
    result = {}
    for stage, count in (("selection", 480), ("foundation", 120)):
        credential = CredentialSentinel()
        stage_path = args.output / stage
        summary = run_ced_pilot(
            args.config,
            stage_path,
            stage,
            service=SimpleNamespace(secret_store=credential),
            profile_id="isolated-sentinel",
            execute=True,
            allow_paid=True,
        )
        cases = json.loads((stage_path / "results.json").read_bytes())
        expected_reason = (
            "B0_NATIVE_PRE_BOUNDS_UNAVAILABLE"
            if args.expected_has_secret_calls == 0
            else "actual stage prerequisites unavailable: RuntimeError"
        )
        if (
            summary["reasons"] != [expected_reason]
            or summary["execution_mode"] != "NOT_EXECUTED"
            or summary["assigned_denominator"] != count
            or len(cases) != count
            or not all(x["status"] == "NOT_EXECUTED" and x["cloud_requests"] == 0 for x in cases)
            or credential.calls != args.expected_has_secret_calls
        ):
            raise ValueError(f"unexpected admission boundary for {stage}")
        result[stage] = {
            "cases_unexecuted": count,
            "reason": expected_reason,
            "has_secret_calls": credential.calls,
            "remote_requests": 0,
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
