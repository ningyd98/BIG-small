"""One R166 legacy control, only after ROOT reservation and exact source gate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013"
PARENT = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013"
PLAN_SHA = "b3b9d5fa8ce19a4f304909f59e239a63898e0019019910006eead8c357aacd5b"
PARENT_PLAN_SHA = "70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError("exact JSON metadata object required")
    return value


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_ledger(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".reserved")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def check_record(record: dict) -> None:
    path = Path(record["path"])
    raw = path.read_bytes()
    if not path.is_absolute() or len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("input byte pin changed: " + str(path))


def main() -> int:
    if sys.argv[1:] != ["legacy_control"]:
        raise ValueError("only exact R166 legacy_control command permitted")
    if Path.cwd().resolve() != ROOT or Path(sys.executable).absolute() != ROOT / ".venv/bin/python":
        raise ValueError("exact project Python and cwd required")
    if digest(ROUND / "plan.json") != PLAN_SHA or digest(PARENT / "plan.json") != PARENT_PLAN_SHA:
        raise ValueError("frozen R166/R158 plan changed")
    plan = read_json(ROUND / "plan.json")
    if plan["round"] != "R166" or list(plan["commands"]) != ["legacy_control"]:
        raise ValueError("exact one-command plan schema required")
    command = plan["commands"]["legacy_control"]
    root_ledger = read_json(ROUND / "root-command-ledger.json")
    reserved = root_ledger["commands"]["legacy_control"]
    if (reserved["state"], reserved["authorized"], reserved["used"], reserved["remaining"]) != ("RESERVED_BY_ROOT", 1, 1, 0):
        raise ValueError("ROOT must consume its separate R166 slot before launch")
    for key in ("argv", "cwd", "actual_environment", "timeout_seconds"):
        if reserved[key] != command[key]:
            raise ValueError("ROOT reservation does not match exact command " + key)
    reservation = reserved["reservation_id"]
    if type(reservation) is not str or not reservation:
        raise ValueError("nonempty reservation required")
    ledger_path = ROUND / "command-ledger.json"
    ledger = read_json(ledger_path)
    entry = ledger["commands"]["legacy_control"]
    if (entry["authorized"], entry["used"], entry["remaining"], entry["state"]) != (1, 0, 1, "HELD"):
        raise ValueError("author R166 slot is unavailable; no retry")
    for key in ("argv", "cwd", "actual_environment", "timeout_seconds"):
        if entry[key] != command[key]:
            raise ValueError("author ledger exact command changed")
    entry.update(used=1, remaining=0, state="RESERVED", reservation_id=reservation)
    write_ledger(ledger_path, ledger)
    evidence = Path(command["evidence_dir"])
    created = False
    outcome = {"round": "R166", "command_id": "legacy_control", "reservation_id": reservation,
               "used": 1, "remaining": 0, "retry": 0, "started": False, "exit_code": None,
               "timed_out": False, "classification": "UNKNOWN", "stdout": None, "stderr": None, "junit": None}
    started = time.monotonic()
    try:
        evidence.mkdir(exist_ok=False)
        created = True
        gate = read_json(ROUND / "script-gate.json")
        approved = gate["commands"]["legacy_control"]
        if gate["schema_version"] != "bigsmall.r166-script-gate.v1" or approved["state"] != "APPROVED":
            raise ValueError("ROOT full-text script gate required")
        if approved["reservation_id"] != reservation or approved["launcher_sha256"] != digest(Path(__file__)):
            raise ValueError("ROOT reservation/source identity mismatch")
        for key in ("argv", "cwd", "actual_environment", "timeout_seconds"):
            if approved[key] != command[key]:
                raise ValueError("ROOT gate differs from frozen command " + key)
        if command["timeout_seconds"] != 600 or command["max_attempts"] != 1 or command["shell"] is not False or command["expected_exit"] != 0:
            raise ValueError("exact bounded command contract required")
        if command["expected_junit"] != {"tests": 1, "pass": 1, "fail": 0, "error": 0, "skip": 0}:
            raise ValueError("exact one-case expected JUnit contract required")
        records = approved["input_records"]
        if type(records) is not list or not records:
            raise ValueError("current ROOT input pins required")
        mandatory = {str(ROUND / "plan.json"), str(PARENT / "plan.json"), str(ROOT / "tests/test_operational_runtime_closure.py"), str(PARENT / "implementation/run-budgeted-command.py"), str(Path(__file__).absolute())}
        if not mandatory.issubset({record["path"] for record in records}):
            raise ValueError("missing exact plan/test/runner source pin")
        for record in records:
            check_record(record)
        manifest_record = next(record for record in plan["inputs"] if record["path"] == str(PARENT / "input-pins.json"))
        check_record(manifest_record)
        manifest = read_json(PARENT / "input-pins.json")
        production = [record for record in manifest["owned_existing"] if record["relative_path"].startswith("src/")]
        if len(production) != 22 or len(manifest["protected"]) != 211:
            raise ValueError("exact original source guard counts required")
        for record in production + manifest["protected"]:
            check_record(record)
        test_bytes = (ROOT / "tests/test_operational_runtime_closure.py").read_bytes()
        if hashlib.sha256(test_bytes[:80556]).hexdigest() != "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861":
            raise ValueError("original A prefix changed")
        if (ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py").exists():
            raise ValueError("product implementation must remain absent before control")
        golden = Path(plan["golden_contract"]["path"])
        if golden.exists() or (PARENT / "implementation/t1_red/legacy-goldens.json").exists():
            raise ValueError("new and failed-run goldens must remain absent before control")
        basetemps = [arg.split("=", 1)[1] for arg in command["argv"] if arg.startswith("--basetemp=")]
        if basetemps != ["/tmp/bigsmall-p6-r166-legacy-control"] or Path(basetemps[0]).exists():
            raise ValueError("fresh exact control basetemp required")
        parent_ledger = read_json(PARENT / "command-ledger.json")
        if sum(item["used"] for item in parent_ledger["commands"].values()) != 2 or sum(item["remaining"] for item in parent_ledger["commands"].values()) != 13:
            raise ValueError("parent actual spent budget must remain 2/13")
        for name, item in parent_ledger["commands"].items():
            expected = (1, 0, "SPENT") if name in {"mypy_baseline", "t1_red"} else (0, 1, "HELD")
            if (item["used"], item["remaining"], item["state"]) != expected:
                raise ValueError("parent allowance changed")
        stdout_path, stderr_path = evidence / "stdout.txt", evidence / "stderr.txt"
        invocation = {"round": "R166", "command_id": "legacy_control", "reservation_id": reservation,
                      "argv": command["argv"], "cwd": command["cwd"], "actual_environment": command["actual_environment"],
                      "timeout_seconds": 600, "shell": False, "max_attempts": 1,
                      "fixture_phase": "t1_red", "fixture_phase_is_not_parent_command_identity": True,
                      "golden_path": str(golden), "producing_pytest_node": command["argv"][6],
                      "launcher_sha256": digest(Path(__file__)), "R166_plan_sha256": PLAN_SHA, "R158_plan_sha256": PARENT_PLAN_SHA,
                      "parent_runner_sha256": digest(PARENT / "implementation/run-budgeted-command.py"),
                      "gate_sha256": digest(ROUND / "script-gate.json"), "resource_caps": plan["resource_caps"]}
        write_new(evidence / "invocation.json", invocation)
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(command["argv"], cwd=command["cwd"], env=command["actual_environment"],
                                       stdout=stdout, stderr=stderr, shell=False, start_new_session=True)
            outcome["started"], outcome["pid"] = True, process.pid
            try:
                outcome["exit_code"] = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                outcome["timed_out"] = True
                os.killpg(process.pid, signal.SIGKILL)
                outcome["exit_code"] = process.wait()
        for key, path in (("stdout", stdout_path), ("stderr", stderr_path), ("junit", evidence / "junit.xml")):
            if path.is_file():
                outcome[key] = {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
        outcome["expected_exit"] = 0
        outcome["expected_numeric_exit_matched"] = outcome["exit_code"] == 0 and not outcome["timed_out"]
        outcome["golden"] = {"path": str(golden), "bytes": golden.stat().st_size, "sha256": digest(golden)} if golden.is_file() else None
        outcome["classification"] = "ACTUAL_CONTROL_RESULT_REQUIRES_ROOT_JUNIT_GOLDEN_REVIEW" if outcome["expected_numeric_exit_matched"] and outcome["junit"] and outcome["golden"] else "UNEXPECTED_CONTROL_FAILURE_STOP_NEXT_ASTRA"
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError) as error:
        outcome["runner_failure"] = {"type": type(error).__name__, "message": str(error)}
        outcome["classification"] = "RUNNER_FAILURE_STOP_NEXT_ASTRA"
    finally:
        outcome["elapsed_seconds"] = time.monotonic() - started
        if created:
            write_new(evidence / "result.json", outcome)
        entry.update(state="SPENT", result_path=str(evidence / "result.json") if created else None)
        write_ledger(ledger_path, ledger)
    print(json.dumps(outcome, ensure_ascii=False))
    if outcome["classification"].endswith("STOP_NEXT_ASTRA"):
        return outcome["exit_code"] if type(outcome["exit_code"]) is int and outcome["exit_code"] != 0 else 2
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
