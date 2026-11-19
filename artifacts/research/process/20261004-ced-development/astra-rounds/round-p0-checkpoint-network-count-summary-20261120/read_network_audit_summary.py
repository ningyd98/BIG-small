"""Read the archived development process and count its Python audit events."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

PROCESS = (
    "experiments/results/phase9/p0-first-teacher-20261119/checkpoint-egl-development-20261120/"
)
READERS = "experiments/results/phase9/p0-teacher-checkpoint-independent-reader-20261120/"
EVENT_SCOPE = "PYTHON_AUDIT_HOOK_ADDRESS_LOOKUP_CONNECT_SEND"
AUDIT_EVENTS = {
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyaddr",
    "socket.connect",
    "socket.sendto",
    "socket.sendmsg",
}
FORMAL_ERROR = "ValueError: registered operational calibration protocol required"


def audit_count(process_end):
    if not isinstance(process_end, dict):
        raise ValueError("original process end object required")
    attempts = process_end.get("network_attempts")
    if (
        process_end.get("network_control") != EVENT_SCOPE
        or type(attempts) is not list
        or any(type(event) is not str or event not in AUDIT_EVENTS for event in attempts)
    ):
        raise ValueError("original Python network audit array and event scope required")
    return {
        "event_count": len(attempts),
        "events": attempts,
        "zero_events": len(attempts) == 0,
        "scope": EVENT_SCOPE,
    }


def verify_process_pair(begin, end):
    if (
        type(begin.get("pid")) is not int
        or begin["pid"] <= 0
        or (type(end.get("pid")) is not int or end["pid"] != begin["pid"])
    ):
        raise ValueError("original process PID mismatch")
    for name in ("freeze_sha256", "registration_file_sha256"):
        if not isinstance(begin.get(name), str) or not re.fullmatch("[0-9a-f]{64}", begin[name]):
            raise ValueError("missing process source SHA256")
        if begin[name] != end.get(name):
            raise ValueError("process source SHA256 mismatch")
    started = datetime.fromisoformat(begin["started_at"])
    closed = datetime.fromisoformat(end["closed_at"])
    if (
        started.utcoffset() != UTC.utcoffset(started)
        or closed.utcoffset() != UTC.utcoffset(closed)
        or not started < closed
        or end.get("source_match") is not True
    ):
        raise ValueError("original process time and source match required")


def summary(checkout):
    plan = json.loads(Path(__file__).with_name("plan.json").read_bytes())
    originals = {}
    sha256 = plan["inputs_sha256"]
    for path, expected in sha256.items():
        contents = (checkout / path).read_bytes()
        if hashlib.sha256(contents).hexdigest() != expected:
            raise ValueError("Astra input SHA256 changed: " + path)
        originals[path] = contents

    begin = json.loads(originals[PROCESS + "process-begin.json"])
    end = json.loads(originals[PROCESS + "process-end.json"])
    verify_process_pair(begin, end)
    first = originals[READERS + "actual-first.json"]
    repeat = originals[READERS + "actual-repeat.json"]
    exits = [int(originals[READERS + f"actual-{tag}.exit"]) for tag in ("first", "repeat")]
    reader = json.loads(first)
    if (
        first != repeat
        or exits != [0, 0]
        or (
            type(reader.get("requested_task_model_calls")) is not int
            or reader["requested_task_model_calls"] != 0
            or reader.get("formal_eligibility") is not False
        )
    ):
        raise ValueError("independent development reader proof differs")
    formal_exit = int(originals[READERS + "formal-verify-negative.exit"])
    formal_lines = originals[READERS + "formal-verify-negative.stderr"].decode().splitlines()
    if formal_exit != 1 or not formal_lines or formal_lines[-1] != FORMAL_ERROR:
        raise ValueError("formal reader rejection proof differs")
    observed = json.loads(originals[READERS + "supplementary-readback-first-exit.json"])
    if observed.get("observed_terminal_only") is not True or observed.get("returncode") != 1:
        raise ValueError("original supplementary error observation changed")
    return {
        "scope": "OFFLINE_DEVELOPMENT_NETWORK_AUDIT_SUMMARY",
        "audit": audit_count(end),
        "same_recorded_process": True,
        "frozen_sources_match": True,
        "requested_task_model_calls": reader["requested_task_model_calls"],
        "formal_eligibility": reader["formal_eligibility"],
        "original_development_reader": {
            "exit_codes": exits,
            "file_sha256": sha256[READERS + "actual-first.json"],
            "byte_identical": True,
        },
        "original_formal_reader": {
            "exit_code": formal_exit,
            "reported_error": formal_lines[-1],
            "stderr_sha256": sha256[READERS + "formal-verify-negative.stderr"],
        },
        "original_failed_supplement": {
            "observed_terminal_only": observed["observed_terminal_only"],
            "exit_code": observed["returncode"],
            "error_type": observed["observed_error"].splitlines()[-1],
            "observation_sha256": sha256[READERS + "supplementary-readback-first-exit.json"],
        },
        "input_sha256": sha256,
    }


def self_test():
    empty = {"network_control": EVENT_SCOPE, "network_attempts": []}
    if audit_count(empty)["zero_events"] is not True:
        raise AssertionError("empty array must be recognized")
    events = ["socket.connect", "socket.connect", "socket.getaddrinfo"]
    nonempty = audit_count({**empty, "network_attempts": events})
    if nonempty["zero_events"] is not False or nonempty["event_count"] != 3:
        raise AssertionError("nonempty events must be preserved and counted")
    if nonempty["events"] != events:
        raise AssertionError("network event evidence changed")
    bad = [
        None,
        False,
        0,
        "",
        {},
        "socket.connect",
        [None],
        ["socket.unknown"],
        [[]],
    ]
    malformed = [{**empty, "network_attempts": value} for value in bad] + [
        {"network_control": EVENT_SCOPE},
        {"network_attempts": []},
    ]
    for value in malformed:
        try:
            audit_count(value)
        except ValueError:
            continue
        raise AssertionError("malformed audit record accepted")
    return {"passed": len(malformed) + 2, "source": "offline audit examples"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test == (args.checkout is not None):
        parser.error("choose a checkout or --self-test")
    result = self_test() if args.self_test else summary(args.checkout)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
