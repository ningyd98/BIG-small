#!/usr/bin/env python3
"""R368 finite runner: one self-test command and one sizing command.

No product import, no ancestor gate, no profiler. Every launch consumes its
allowance atomically before spawn; finalization (source-after, missingness,
process chain, resource inventory, ledger settlement) always runs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).absolute().parent.parent
IMPL = D / "implementation"
PLAN = D / "plan.json"
PLAN_SHA = "368416dd92a44ed97d856f9f247a1aebaf8cb191c58e403b5fc08343bcfea540"
LEDGER = IMPL / "r368-ledger.json"
KEYS = ("runner_contract_01", "utc_memory_sizing_01")
MIB = 1024 * 1024
GIB = 1024 * MIB
LIMITS = {
    "stdout_mib": 32, "stderr_mib": 32, "metadata_mib": 16,
    "persistent_gib": 1, "persistent_entries": 10000, "round_gib": 4,
    "min_free_gib": 3, "cleanup_seconds": 15, "term_grace_seconds": 5, "kill_after_seconds": 20,
    "capture_seconds": 240, "check_interval_seconds": 2.0,
}


class Failure(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Failure(message)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def pin(path: Path) -> dict:
    raw = Path(path).read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def tree_size(root: Path) -> tuple[int, int]:
    total = count = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
                count += 1
        except OSError:
            continue
    return total, count


def source_identity(out: Path | None = None) -> dict:
    staged = hashlib.sha256(subprocess.run(["git", "diff", "--cached", "--binary", "--", "src", "tests"],
                                           cwd=ROOT, capture_output=True).stdout).hexdigest()
    unstaged = hashlib.sha256(subprocess.run(["git", "diff", "--binary", "--", "src", "tests"],
                                             cwd=ROOT, capture_output=True).stdout).hexdigest()
    untracked = {}
    for rel in git("ls-files", "--others", "--exclude-standard", "src", "tests").splitlines():
        path = ROOT / rel
        if path.is_file():
            untracked[rel] = {"bytes": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    identity = {
        "head": git("rev-parse", "HEAD"),
        "src_tree": git("rev-parse", "HEAD:src"),
        "tests_tree": git("rev-parse", "HEAD:tests"),
        "staged_overlay": staged,
        "unstaged_overlay": unstaged,
        "untracked": untracked,
        "direct_inputs": {rel: pin(ROOT / rel) for rel in (
            "src/cloud_edge_robot_arm/vision/local_temporal.py",
            "tests/test_local_temporal_sha_contract.py",
            "tests/test_operational_runtime_closure.py",
            "tests/test_local_temporal_decode_memo.py",
            "tests/test_local_temporal_projection_closure.py",
            "tests/test_local_temporal_promotion_bindings.py",
            "pyproject.toml") if (ROOT / rel).exists()},
    }
    if out is not None:
        write_json(out, identity)
    return identity


def environment_identity(spec: dict) -> dict:
    real = Path(os.path.realpath(sys.executable))
    return {
        "runner_interpreter": {"path": sys.executable, "realpath": str(real),
                               "sha256": hashlib.sha256(real.read_bytes()).hexdigest() if real.is_file() else None},
        "child_interpreter": spec.get("child_argv", [None])[0],
        "python_version": sys.version,
        "pytest_version": importlib.metadata.version("pytest"),
        "cwd": spec.get("cwd"),
        "child_env": spec.get("child_env"),
        "pid": os.getpid(),
    }


def process_identity(pid: int) -> dict:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        return {"pid": pid, "ppid": int(fields[3]), "pgrp": int(fields[4]),
                "session": int(fields[5]), "starttime": int(fields[21])}
    except OSError as error:
        return {"pid": pid, "error": str(error)}


def consume(key: str, ledger_path: Path = LEDGER) -> dict:
    ledger = json.loads(ledger_path.read_text())
    slot = ledger["commands"][key]
    require(slot["state"] == "HELD" and slot["used"] == 0 and slot["remaining"] == 1,
            "ledger slot is not an unused allowance")
    token = hashlib.sha256(f"{key}:{now()}:{os.getpid()}".encode()).hexdigest()[:32]
    slot.update({"state": "CONSUMED", "used": 1, "remaining": 0, "token": token, "consumed_utc": now()})
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"token": token, "slot": slot}


def settle(key: str, value: dict) -> None:
    ledger = json.loads(LEDGER.read_text())
    ledger["commands"][key].update({"state": "SPENT", "settled_utc": now(), **value})
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def junit(path: Path) -> dict:
    tree = ET.parse(path)
    cases = []
    for case in tree.iter("testcase"):
        module = (case.get("classname") or "").replace(".", "/") + ".py"
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = child.tag
                break
        cases.append({"nodeid": f"{module}::{case.get('name')}", "outcome": outcome})
    return {"available": True, "tests": len(cases),
            "failures": sum(c["outcome"] == "failure" for c in cases),
            "errors": sum(c["outcome"] == "error" for c in cases),
            "skips": sum(c["outcome"] == "skipped" for c in cases),
            "nodeids": sorted(c["nodeid"] for c in cases), "cases": cases}


def terminate(proc: subprocess.Popen, reason: str) -> dict:
    started = time.monotonic()
    events = [{"kind": "cause", "reason": reason, "monotonic": started}]
    limit = started + LIMITS["cleanup_seconds"]
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        events.append({"kind": "TERM", "monotonic": time.monotonic()})
        try:
            proc.wait(timeout=min(LIMITS["term_grace_seconds"], max(0.0, limit - time.monotonic())))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            events.append({"kind": "KILL", "monotonic": time.monotonic()})
            try:
                proc.wait(timeout=max(0.0, limit - time.monotonic()))
            except subprocess.TimeoutExpired:
                events.append({"kind": "UNREAPED", "monotonic": time.monotonic()})
    events.append({"kind": "reaped", "returncode": proc.returncode, "monotonic": time.monotonic()})
    return {"reason": reason, "events": events, "cleanup_seconds": round(time.monotonic() - started, 3)}


_ROUND_CHECK_TICK = {"n": 0}


def limit_breach(stdout: Path, stderr: Path, sink: Path | None) -> str | None:
    if stdout.stat().st_size > LIMITS["stdout_mib"] * MIB:
        return "stdout_limit"
    if stderr.stat().st_size > LIMITS["stderr_mib"] * MIB:
        return "stderr_limit"
    if sink is not None and sink.exists():
        size, count = tree_size(sink)
        if size > LIMITS["persistent_gib"] * GIB:
            return "persistent_bytes_limit"
        if count > LIMITS["persistent_entries"]:
            return "persistent_entries_limit"
    _ROUND_CHECK_TICK["n"] += 1
    if IMPL.exists() and _ROUND_CHECK_TICK["n"] % 10 == 0:
        size, _ = tree_size(IMPL)
        if size > LIMITS["round_gib"] * GIB:
            return "round_bytes_limit"
    stat = os.statvfs(ROOT)
    if stat.f_bavail * stat.f_frsize < LIMITS["min_free_gib"] * GIB:
        return "free_space_limit"
    return None


def supervise(key: str, spec: dict, out: Path, budget: dict) -> dict:
    sink = Path(spec["child_env"]["BIGSMALL_R158_T2_RESOURCE_DIR"]) if "BIGSMALL_R158_T2_RESOURCE_DIR" in spec.get("child_env", {}) else None
    if sink is not None:
        sink.mkdir(parents=True, exist_ok=True)
    record: dict = {"schema": "bigsmall.r368.launch.v1", "command_id": f"R368:{key}",
                    "started_utc": now(), "origin_monotonic": time.monotonic(), "limits": LIMITS}
    stdout, stderr = out / "stdout.txt", out / "stderr.txt"
    with stdout.open("xb") as fout, stderr.open("xb") as ferr:
        proc = subprocess.Popen(spec["child_argv"], cwd=spec["cwd"], env=spec["child_env"],
                                stdout=fout, stderr=ferr, start_new_session=True)
        record["process"] = process_identity(proc.pid)
        record["deadline_monotonic"] = record["origin_monotonic"] + budget["child_seconds"]
        reason = None
        next_check = time.monotonic()
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() >= record["deadline_monotonic"]:
                reason = "child_deadline"
                break
            if time.monotonic() >= next_check:
                reason = limit_breach(stdout, stderr, sink)
                next_check = time.monotonic() + LIMITS["check_interval_seconds"]
                if reason:
                    break
            time.sleep(0.25)
        if reason:
            record["termination"] = terminate(proc, reason)
        else:
            code = proc.wait()
            record["termination"] = {"reason": None, "cleanup_seconds": 0.0,
                                     "events": [{"kind": "reaped", "returncode": code, "monotonic": time.monotonic()}]}
    return record


def resource_inventory(spec: dict) -> dict:
    if "BIGSMALL_R158_T2_RESOURCE_DIR" not in spec.get("child_env", {}):
        return {"applicable": False}
    path = Path(spec["child_env"]["BIGSMALL_R158_T2_RESOURCE_DIR"])
    size, count = tree_size(path) if path.exists() else (0, 0)
    return {"applicable": True, "root": str(path), "bytes": size, "entries": count,
            "sidecars": sorted(p.name for p in path.glob("*.json")) if path.exists() else []}


def finalize(key: str, out: Path, record: dict, before: dict, spec: dict, expected: list[str] | None) -> dict:
    started = time.monotonic()
    result: dict = {**record, "finished_utc": now()}
    missing: dict = {}
    try:
        after = source_identity(out / "source-after.json")
        result.update({"source_before": before, "source_after": after, "sources_unchanged": after == before})
    except BaseException as error:
        missing["source_after"] = repr(error)
        result["sources_unchanged"] = False
    junit_path = next((Path(a.split("=", 1)[1]) for a in spec["child_argv"] if a.startswith("--junitxml=")), None)
    if junit_path is not None and junit_path.exists():
        try:
            result["junit"] = junit(junit_path)
        except BaseException as error:
            missing["junit"] = repr(error)
            result["junit"] = {"available": False}
    else:
        missing["junit"] = "absent"
        result["junit"] = {"available": False}
    if expected is not None:
        result["expected_nodeids"] = expected
        result["nodeids_exact"] = result["junit"].get("nodeids") == sorted(expected)
    result["missingness"] = missing
    result["resources"] = resource_inventory(spec)
    result["capture_seconds"] = round(time.monotonic() - started, 3)
    return result


def finish(key: str, out: Path, result: dict) -> int:
    passed = bool(result.get("junit", {}).get("available")
                  and result["junit"].get("failures") == 0 and result["junit"].get("errors") == 0
                  and result["junit"].get("skips") == 0 and result.get("nodeids_exact")
                  and result.get("sources_unchanged")
                  and result["termination"].get("reason") is None
                  and result["termination"]["events"][-1].get("returncode") == 0)
    result["validation_pass"] = passed
    write_json(out / "result.json", result)
    write_json(out / "completion.json", {
        "schema": "bigsmall.r368.completion.v1", "command_id": f"R368:{key}",
        "finalization_complete": True, "validation_pass": passed,
        "result": pin(out / "result.json"), "missingness": result["missingness"],
        "finished_utc": result["finished_utc"]})
    settle(key, {"validation_pass": passed, "result": pin(out / "result.json"),
                 "outcome": "PASS" if passed else "NOT_PASSED"})
    print(json.dumps({"command_id": f"R368:{key}", "validation_pass": passed,
                      "missingness": result["missingness"],
                      "reason": result["termination"].get("reason"),
                      "returncode": result["termination"]["events"][-1].get("returncode")}, ensure_ascii=False))
    return 0 if passed else 1


def run_command(key: str, spec: dict, expected: list[str] | None) -> int:
    consume(key)
    out = IMPL / key
    require(not out.exists(), "exclusive output path already exists")
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    before = source_identity(out / "source-before.json")
    write_json(out / "invocation.json", {"schema": "bigsmall.r368.invocation.v1", "command_id": f"R368:{key}",
                                         "spec": spec, "environment": environment_identity(spec),
                                         "runner": pin(Path(__file__)), "plan": pin(PLAN)})
    try:
        record = supervise(key, spec, out, {"child_seconds": spec["child_seconds"]})
        result = finalize(key, out, record, before, spec, expected)
        return finish(key, out, result)
    except BaseException as error:
        settle(key, {"validation_pass": False, "outcome": f"ERROR_{type(error).__name__}"})
        raise


def preflight_probe(root: Path) -> dict:
    scratch = root / "scratch-ledger.json"
    write_json(scratch, {"commands": {"probe": {"state": "HELD", "used": 0, "remaining": 1}}})
    consume("probe", scratch)
    out = root / "already-exists"
    out.mkdir(parents=True, exist_ok=True)
    rejected = False
    try:
        out.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        rejected = True
    try:
        consume("probe", scratch)
        reusable = True
    except Failure:
        reusable = False
    ledger = json.loads(scratch.read_text())
    return {"rejected_before_child": rejected, "cannot_reuse": not reusable,
            "state": ledger["commands"]["probe"]["state"], "used": ledger["commands"]["probe"]["used"]}


def self_test(key: str) -> int:
    consume(key)
    try:
        return _self_test(key)
    except BaseException as error:
        settle(key, {"validation_pass": False, "outcome": f"ERROR_{type(error).__name__}"})
        raise


def _self_test(key: str) -> int:
    out = IMPL / key
    require(not out.exists(), "exclusive output path already exists")
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    cases = []
    results = []

    def case(name: str, code: str, budget: dict, cap_mib: int | None = None) -> dict:
        spec = {"child_argv": [sys.executable, "-c", code], "cwd": str(out / "work"), "child_env": {"PATH": "/usr/bin:/bin"}}
        (out / "work").mkdir(parents=True, exist_ok=True)
        case_dir = out / "cases" / name
        case_dir.mkdir(parents=True, exist_ok=True)
        before = source_identity()
        if cap_mib is not None:
            saved = LIMITS["stdout_mib"]
            LIMITS["stdout_mib"] = cap_mib
            try:
                record = supervise(f"{key}:{name}", spec, case_dir, budget)
            finally:
                LIMITS["stdout_mib"] = saved
        else:
            record = supervise(f"{key}:{name}", spec, case_dir, budget)
        result = finalize(f"{key}:{name}", case_dir, record, before, spec, None)
        cases.append({"case": name, "termination": record["termination"], "missingness": result["missingness"],
                      "sources_unchanged": result["sources_unchanged"]})
        return cases[-1]

    missing = case("missing_junit", "import sys; sys.exit(0)", {"child_seconds": 5})
    term = case("deadline_term", "import time; time.sleep(60)", {"child_seconds": 2})
    kill = case("ignore_term_kill",
                "import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(60)",
                {"child_seconds": 2})
    cap = case("output_cap",
               "import sys,time\nchunk='x'*1048576\n[sys.stdout.write(chunk) for _ in range(40)]\nsys.stdout.flush()\ntime.sleep(60)",
               {"child_seconds": 30}, cap_mib=1)
    probe = preflight_probe(out / "cases" / "preflight")
    checks = {
        "missing_junit_finalized": missing["missingness"].get("junit") == "absent" and missing["sources_unchanged"],
        "deadline_term_clean": term["termination"]["reason"] == "child_deadline"
                               and any(e["kind"] == "TERM" for e in term["termination"]["events"]),
        "kill_within_cleanup": kill["termination"]["reason"] == "child_deadline"
                               and any(e["kind"] == "KILL" for e in kill["termination"]["events"])
                               and kill["termination"]["cleanup_seconds"] <= LIMITS["cleanup_seconds"],
        "output_cap_preserved": cap["termination"]["reason"] == "stdout_limit"
                                and (out / "cases" / "output_cap" / "stdout.txt").stat().st_size > 0,
        "preflight_rejection_zero_child": probe["rejected_before_child"] and probe["cannot_reuse"]
                                          and probe["used"] == 1,
    }
    passed = all(checks.values())
    result = {"schema": "bigsmall.r368.selfcheck.v1", "command_id": f"R368:{key}", "cases": cases,
              "probe": probe, "checks": checks, "validation_pass": passed, "finished_utc": now(),
              "missingness": {}}
    write_json(out / "result.json", result)
    write_json(out / "completion.json", {"schema": "bigsmall.r368.completion.v1", "command_id": f"R368:{key}",
                                         "finalization_complete": True, "validation_pass": passed,
                                         "result": pin(out / "result.json"), "missingness": {}})
    settle(key, {"validation_pass": passed, "result": pin(out / "result.json"),
                 "outcome": "PASS" if passed else "NOT_PASSED"})
    print(json.dumps({"command_id": f"R368:{key}", "validation_pass": passed, "checks": checks}, ensure_ascii=False))
    return 0 if passed else 1


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in KEYS:
        print(json.dumps({"error": "one literal R368 command key required", "allowed": list(KEYS)}, ensure_ascii=False))
        return 2
    key = argv[1]
    try:
        require(pin(PLAN)["sha256"] == PLAN_SHA, "plan.json changed")
        plan = json.loads(PLAN.read_text())
        if key == "runner_contract_01":
            return self_test(key)
        command = plan["commands"][key]
        return run_command(key, command, command.get("expected_nodeids"))
    except BaseException as error:
        print(json.dumps({"command_id": f"R368:{key}", "error": {"type": type(error).__name__,
                                                                 "message": str(error)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
