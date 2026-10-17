"""R158 finite runner. ROOT must reserve exactly one command before invocation."""
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
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013"
PLAN_SHA = "70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"object metadata required: {path}")
    return value


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def replace_ledger(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".reserved")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError("exactly one R158 command id required")
    command_id = sys.argv[1]
    if Path.cwd().resolve() != ROOT:
        raise ValueError("exact R158 cwd required")
    if Path(sys.executable).absolute() != ROOT / ".venv/bin/python":
        raise ValueError("use the exact project .venv/bin/python")
    if sha(ROUND / "plan.json") != PLAN_SHA:
        raise ValueError("frozen R158 plan changed")
    plan = read_json(ROUND / "plan.json")
    commands = plan["commands"]
    if type(commands) is not dict or len(commands) != 15 or command_id not in commands:
        raise ValueError("exact frozen command dictionary required")
    command = commands[command_id]
    root_ledger = read_json(ROUND / "root-command-ledger.json")
    root_entry = root_ledger["commands"][command_id]
    if (
        root_entry["state"] != "RESERVED_BY_ROOT"
        or root_entry["authorized"] != 1
        or root_entry["used"] != 1
        or root_entry["remaining"] != 0
        or root_entry["argv"] != command["argv"]
        or root_entry["cwd"] != command["cwd"]
    ):
        raise ValueError("ROOT must reserve exact argv/cwd once before calling")
    reservation = root_entry["reservation_id"]
    if type(reservation) is not str or not reservation:
        raise ValueError("nonempty ROOT reservation id required")
    ledger_path = ROUND / "command-ledger.json"
    ledger = read_json(ledger_path)
    entry = ledger["commands"][command_id]
    if entry["used"] != 0 or entry["remaining"] != 1 or entry["state"] != "HELD":
        raise ValueError("author command already consumed or not held")
    # ROOT reservation already consumes the command. Any uncertainty after this
    # point remains spent; the runner never restores an allowance.
    entry.update(used=1, remaining=0, state="RESERVED", reservation_id=reservation)
    replace_ledger(ledger_path, ledger)
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(exist_ok=False)
    stdout_path = evidence / "stdout.txt"
    stderr_path = evidence / "stderr.txt"
    outcome = {
        "command_id": command_id, "reservation_id": reservation, "used": 1,
        "remaining": 0, "retry": 0, "exit_code": None, "timed_out": False,
        "started": False, "classification": "UNKNOWN_NOT_VALIDATED",
    }
    process = None
    started = time.monotonic()
    try:
        gate = read_json(ROUND / "script-gate.json")
        approved = gate["commands"][command_id]
        if (
            gate["schema_version"] != "bigsmall.r158-script-gate.v1"
            or approved["state"] != "APPROVED"
            or approved["reservation_id"] != reservation
            or approved["runner_sha256"] != sha(Path(__file__))
            or approved["argv"] != command["argv"]
            or approved["cwd"] != command["cwd"]
            or approved["env"] != command["env"]
            or approved["timeout_seconds"] != command["timeout_seconds"]
            or approved["timeout_seconds"] != 600
        ):
            raise ValueError("ROOT full-text/hash script gate does not match exact command")
        if command["timeout_seconds"] != 600:
            raise ValueError("exact600s timeout required")
        records = approved["input_records"]
        if type(records) is not list or not records:
            raise ValueError("current exact source/fixture pin gate required")
        for record in records:
            path = Path(record["path"])
            if not path.is_absolute() or len(path.read_bytes()) != record["bytes"] or sha(path) != record["sha256"]:
                raise ValueError(f"gate input changed: {path}")
        if command_id in {"mypy_baseline", "t1_red"}:
            before = read_json(ROUND / "implementation/t1/before.json")
            for source in before["sources"]:
                if source["relative_path"] != "tests/test_operational_runtime_closure.py":
                    if sha(Path(source["path"])) != source["sha256"]:
                        raise ValueError("production edit before baseline/RED")
            if (ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py").exists():
                raise ValueError("new product module must remain absent before RED")
        # No inherited credential or auto-configuration environment is emitted.
        # ROOT approves this exact finite process environment with the command.
        environment = {"PATH": str(ROOT / ".venv/bin") + ":/usr/bin:/bin", "LANG": "C.UTF-8"}
        environment.update(command["env"])
        fixture_controls = {}
        if command_id in {"t1_red", "t1_green", "final_new23"}:
            fixture_controls = {
                "BIGSMALL_R158_COMMAND": command_id,
                "BIGSMALL_R158_LEGACY_GOLDENS": str(ROUND / "implementation/t1_red/legacy-goldens.json"),
            }
        environment.update(fixture_controls)
        if approved["actual_environment"] != environment:
            raise ValueError("ROOT must approve the exact effective finite environment")
        invocation = {
            "command_id": command_id, "reservation_id": reservation,
            "argv": command["argv"], "cwd": command["cwd"],
            "plan_env": command["env"],
            "actual_environment": environment, "fixture_controls": fixture_controls,
            "timeout_seconds": 600, "shell": False, "max_attempts": 1,
            "stdout": str(stdout_path), "stderr": str(stderr_path),
            "fixture_map": str(ROUND / "implementation/t1/fixture-map.json"),
            "runner_sha256": sha(Path(__file__)),
            "root_gate_sha256": sha(ROUND / "script-gate.json"),
            "root_ledger_sha256": sha(ROUND / "root-command-ledger.json"),
            "resource_caps": plan["fixture"]["caps"],
            "acceptance": "Raw actual process result only; ROOT evaluates RED and all later gates.",
        }
        write_new(evidence / "invocation.json", invocation)
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command["argv"], cwd=command["cwd"], env=environment,
                stdout=stdout, stderr=stderr, shell=False, start_new_session=True,
            )
            outcome["started"] = True
            outcome["pid"] = process.pid
            try:
                outcome["exit_code"] = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                outcome["timed_out"] = True
                os.killpg(process.pid, signal.SIGKILL)
                outcome["exit_code"] = process.wait()
        expected = command["expected_exit"]
        allowed = expected if type(expected) is list else [expected]
        outcome["expected_exit"] = expected
        outcome["expected_numeric_exit_matched"] = (
            not outcome["timed_out"] and outcome["exit_code"] in allowed
        )
        outcome["classification"] = (
            "ACTUAL_EXPECTED_NUMERIC_EXIT_REQUIRES_ROOT_CONTENT_REVIEW"
            if outcome["expected_numeric_exit_matched"]
            else "UNEXPECTED_FAILURE_STOP_NEXT_ASTRA"
        )
        for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            outcome[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
        if "-m" in command["argv"] and "pytest" in command["argv"]:
            junit = evidence / "junit.xml"
            outcome["junit"] = (
                {"path": str(junit), "bytes": junit.stat().st_size, "sha256": sha(junit)}
                if junit.is_file() else None
            )
            if outcome["junit"] is None:
                outcome["classification"] = "MISSING_JUNIT_STOP_NEXT_ASTRA"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        outcome["runner_failure"] = {"type": type(error).__name__, "message": str(error)}
        outcome["classification"] = "RUNNER_FAILURE_STOP_NEXT_ASTRA"
    finally:
        outcome["elapsed_seconds"] = time.monotonic() - started
        write_new(evidence / "result.json", outcome)
        entry.update(state="SPENT", result_path=str(evidence / "result.json"))
        replace_ledger(ledger_path, ledger)
    print(json.dumps(outcome, ensure_ascii=False))
    if outcome["classification"].endswith("STOP_NEXT_ASTRA"):
        return 2
    # RED1 and mypy1 remain their actual numeric exits; never relabel as exit0.
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
