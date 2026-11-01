#!/usr/bin/env python3
"""R367 finite runner: four literal selections, no ancestor inheritance.

Only the four command keys in plan.json.commands may run, each exactly once.
The runner never imports product code; it only executes the planned argv,
records source identity before/after, parses JUnit and settles the local ledger.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

D = Path(__file__).absolute().parent.parent
IMPL = D / "implementation"
PLAN = D / "plan.json"
LEDGER = IMPL / "r367-ledger.json"
PLAN_SHA = "3ab09169fbb65b58eb2c28dd8a525b41ac376ff39b7b267c6060a9ced181e59b"
ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
COMMANDS = ("sha_contract_before_01", "sha_contract_after_01", "codec_regression_01", "utc_both_01")
DIRECT_INPUTS = (
    "src/cloud_edge_robot_arm/vision/local_temporal.py",
    "tests/test_local_temporal_sha_contract.py",
    "tests/test_operational_runtime_closure.py",
    "tests/test_local_temporal_decode_memo.py",
    "tests/test_local_temporal_projection_closure.py",
    "tests/test_local_temporal_promotion_bindings.py",
    "pyproject.toml",
)


class Failure(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Failure(message)


def sha(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def source_identity() -> dict:
    return {
        "head": git("rev-parse", "HEAD"),
        "src_tree": git("rev-parse", "HEAD:src"),
        "tests_tree": git("rev-parse", "HEAD:tests"),
        "status": git("status", "--porcelain=v1").splitlines(),
        "untracked_src_tests": [line for line in git("ls-files", "--others", "--exclude-standard", "src", "tests").splitlines()],
        "direct_inputs": {rel: sha(ROOT / rel) for rel in DIRECT_INPUTS if (ROOT / rel).exists()},
    }


def junit_records(path: Path) -> dict:
    tree = ET.parse(path)
    cases = []
    for case in tree.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        module = classname.replace(".", "/") + ".py"
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = child.tag
                break
        cases.append({"nodeid": f"{module}::{name}", "outcome": outcome, "time": case.get("time")})
    failures = sum(1 for c in cases if c["outcome"] == "failure")
    errors = sum(1 for c in cases if c["outcome"] == "error")
    skips = sum(1 for c in cases if c["outcome"] == "skipped")
    return {"tests": len(cases), "failures": failures, "errors": errors, "skips": skips,
            "cases": cases, "nodeids": sorted(c["nodeid"] for c in cases)}


def main(argv: list[str]) -> int:
    started = utc_now()
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(json.dumps({"error": "one literal R367 command key required", "allowed": COMMANDS}, ensure_ascii=False))
        return 2
    key = argv[1]
    out = IMPL / key
    data: dict = {"schema": "bigsmall.r367.run.v1", "round": "R367", "command_id": f"R367:{key}",
                  "started_utc": started, "key": key}
    try:
        require(sha(PLAN)["sha256"] == PLAN_SHA, "plan.json changed")
        plan = json.loads(PLAN.read_text())
        command = plan["commands"][key]
        ledger = json.loads(LEDGER.read_text())
        slot = ledger["commands"][key]
        require(slot["state"] == "HELD" and slot["used"] == 0 and slot["remaining"] == 1,
                "ledger slot is not an unused allowance")
        require(not out.exists(), "exclusive output path already exists")
        out.mkdir(mode=0o700, parents=False, exist_ok=False)
        identity = source_identity()
        data["source_identity"] = identity
        data["child_argv"] = command["child_argv"]
        data["child_env"] = command["child_env"]
        data["budget"] = {k: command[k] for k in ("child_seconds", "outer_seconds", "cleanup_seconds",
                                                 "TERM_grace_seconds", "kill_after_seconds")}
        write_json(out / "invocation.json", {**data, "runner": sha(Path(__file__)), "plan": sha(PLAN)})
        sink = command["child_env"].get("BIGSMALL_R158_T2_RESOURCE_DIR")
        if sink:
            Path(sink).mkdir(mode=0o700, parents=True, exist_ok=False)
        env = {**command["child_env"]}
        t0 = time.monotonic()
        with (out / "stdout.txt").open("xb") as fout, (out / "stderr.txt").open("xb") as ferr:
            proc = subprocess.Popen(command["child_argv"], cwd=command["cwd"], env=env,
                                    stdout=fout, stderr=ferr, start_new_session=True)
            timed_out = False
            try:
                code = proc.wait(timeout=command["child_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    code = proc.wait(timeout=command["TERM_grace_seconds"])
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    code = proc.wait(timeout=command["kill_after_seconds"])
        duration = time.monotonic() - t0
        try:
            os.killpg(proc.pid, 0)
            group_empty = False
        except ProcessLookupError:
            group_empty = True
        data.update({"child_exit": code, "timed_out": timed_out, "duration_seconds": round(duration, 3),
                     "group_empty": group_empty})
        junit_path = next((Path(a.split("=", 1)[1]) for a in command["child_argv"] if a.startswith("--junitxml=")), None)
        require(junit_path is not None and junit_path.exists(), "junit xml missing")
        junit = junit_records(junit_path)
        expected = sorted(command["expected_nodeids"])
        data["junit"] = junit
        data["expected_nodeids"] = expected
        data["nodeids_exact"] = junit["nodeids"] == expected
        after = source_identity()
        data["sources_unchanged"] = after == identity
        data["expected_tests"] = command.get("expected_tests")
        passed = (code == 0 and not timed_out and group_empty and junit["nodeids"] == expected
                  and junit["failures"] == 0 and junit["errors"] == 0 and junit["skips"] == 0
                  and after == identity)
        data.update({"validation_pass": passed, "finished_utc": utc_now()})
        write_json(out / "result.json", data)
        write_json(out / "completion.json", {
            "schema": "bigsmall.r367.completion.v1", "command_id": f"R367:{key}",
            "finalization_complete": True, "final_summary_state": "COMPLETE",
            "validation_pass": passed, "result": sha(out / "result.json"),
            "junit": sha(junit_path), "stdout": sha(out / "stdout.txt"), "stderr": sha(out / "stderr.txt"),
            "source_identity": identity, "finished_utc": data["finished_utc"],
        })
        slot.update({"state": "SPENT", "used": 1, "remaining": 0, "settled_utc": utc_now(),
                     "validation_pass": passed, "result": sha(out / "result.json"),
                     "completion": sha(out / "completion.json")})
        write_json(LEDGER, ledger)
        print(json.dumps({"command_id": f"R367:{key}", "validation_pass": passed, "child_exit": code,
                          "timed_out": timed_out, "tests": junit["tests"], "failures": junit["failures"],
                          "errors": junit["errors"], "skips": junit["skips"],
                          "duration_seconds": round(duration, 3), "nodeids_exact": data["nodeids_exact"],
                          "sources_unchanged": data["sources_unchanged"]}, ensure_ascii=False))
        return 0 if passed else 1
    except BaseException as error:  # retain pre-launch rejection
        data.update({"error": {"type": type(error).__name__, "message": str(error)}, "finished_utc": utc_now()})
        if out.exists():
            write_json(out / "failure.json", data)
        print(json.dumps({"command_id": f"R367:{key}", "error": {"type": type(error).__name__,
                                                                 "message": str(error)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
