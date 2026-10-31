#!/usr/bin/env python3
"""R370 finite runner: bounded pipe capture, segmented timing, always-finalize.

Three literal commands: one 7-case self-test, one expected RED, one GREEN.
No product import, no ancestor gate, no long-run allowance.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).absolute().parent.parent
IMPL = Path(os.environ.get("R370_IMPL", D / "implementation"))
PLAN = D / "plan.json"
PLAN_SHA = "321210ef94acb7130d61db69a5fef25e6810c553a60715b28fa433f09da90a6b"
LEDGER = IMPL / "r370-ledger.json"
KEYS = ("external_utc_green_01",)
MIB = 1024 * 1024
LIMITS = {"stdout_mib": 32, "stderr_mib": 32, "chunk": 65536,
          "cleanup_seconds": 15, "term_grace_seconds": 5, "capture_seconds": 10}


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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def source_identity(path: Path) -> dict:
    identity = {
        "head": git("rev-parse", "HEAD"),
        "src_tree": git("rev-parse", "HEAD:src"),
        "tests_tree": git("rev-parse", "HEAD:tests"),
        "staged": hashlib.sha256(subprocess.run(["git", "diff", "--cached", "--binary", "--", "src", "tests"],
                                                cwd=ROOT, capture_output=True).stdout).hexdigest(),
        "unstaged": hashlib.sha256(subprocess.run(["git", "diff", "--binary", "--", "src", "tests"],
                                                  cwd=ROOT, capture_output=True).stdout).hexdigest(),
        "untracked": {rel: pin(ROOT / rel) for rel in git("ls-files", "--others", "--exclude-standard",
                                                          "src", "tests").splitlines() if (ROOT / rel).is_file()},
        "inputs": {rel: pin(ROOT / rel) for rel in (
            "src/cloud_edge_robot_arm/vision/local_temporal.py",
            "tests/test_operational_runtime_closure.py",
            "tests/test_operational_external_utc_scene_contract.py")},
    }
    write_json(path, identity)
    return identity


def consume(key: str) -> dict:
    ledger = json.loads(LEDGER.read_text())
    slot = ledger["commands"][key]
    require(slot["state"] == "HELD" and slot["used"] == 0 and slot["remaining"] == 1,
            "ledger slot is not an unused allowance")
    token = hashlib.sha256(f"{key}:{now()}:{os.getpid()}".encode()).hexdigest()[:32]
    slot.update({"state": "CONSUMED", "used": 1, "remaining": 0, "token": token, "consumed_utc": now()})
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return token


def settle(key: str, value: dict) -> None:
    ledger = json.loads(LEDGER.read_text())
    ledger["commands"][key].update({"state": "SPENT", "settled_utc": now(), **value})
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Capture:
    """Bounded, non-blocking pipe capture. Never writes more than the cap."""

    def __init__(self, proc: subprocess.Popen, out: Path, limits: dict) -> None:
        self.proc = proc
        self.limits = limits
        self.selector = selectors.DefaultSelector()
        self.discarding = False
        self.over_limit = None
        self.state = {}
        for name, cap_mib in (("stdout", limits["stdout_mib"]), ("stderr", limits["stderr_mib"])):
            handle = (out / f"{name}.txt").open("xb")
            self.state[name] = {"handle": handle, "cap": cap_mib * MIB, "written": 0,
                                "observed": 0, "complete": False, "truncated": False}
            self.selector.register(getattr(proc, name), selectors.EVENT_READ, name)

    def pump(self, timeout: float = 0.2) -> None:
        for key, _ in self.selector.select(timeout=timeout):
            name = key.data
            state = self.state[name]
            chunk = os.read(key.fd, self.limits["chunk"])
            if not chunk:
                self.selector.unregister(key.fileobj)
                state["complete"] = True
                continue
            state["observed"] += len(chunk)
            if self.discarding:
                state["truncated"] = True
                continue
            room = state["cap"] - state["written"]
            take = chunk[:room]
            if take:
                state["handle"].write(take)
                state["written"] += len(take)
            if len(chunk) > len(take):
                state["truncated"] = True
                self.over_limit = f"{name}_limit"
                return

    def drain(self, seconds: float = 2.0) -> None:
        end = time.monotonic() + seconds
        while self.selector.get_map() and time.monotonic() < end:
            if self.over_limit:
                self.discarding = True
                self.over_limit = None
            self.pump(timeout=0.05)

    def close(self) -> dict:
        summary = {}
        for name, state in self.state.items():
            state["handle"].close()
            summary[name] = {k: state[k] for k in ("cap", "written", "observed", "complete", "truncated")}
        self.selector.close()
        return summary


def terminate(proc: subprocess.Popen, reason: str, started: float) -> dict:
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


def supervise(spec: dict, out: Path, child_seconds: float, limits: dict | None = None) -> dict:
    limits = {**LIMITS, **(limits or {})}
    marks = {"launch": time.monotonic()}
    record: dict = {"limits": limits, "started_utc": now()}
    proc = None
    capture = None
    closed = False
    try:
        proc = subprocess.Popen(spec["child_argv"], cwd=spec["cwd"], env=spec["child_env"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, bufsize=0)
        marks["spawn"] = time.monotonic()
        record["process"] = {"pid": proc.pid, "pgid": os.getpgid(proc.pid)}
        capture = Capture(proc, out, limits)
        deadline = marks["launch"] + child_seconds
        reason = None
        while True:
            capture.pump(timeout=0.05)
            if capture.over_limit:
                reason = capture.over_limit
                break
            if proc.poll() is not None:
                break
            if time.monotonic() >= deadline:
                reason = "child_deadline"
                break
        marks["stop"] = time.monotonic()
        if reason:
            record["termination"] = terminate(proc, reason, marks["stop"])
        else:
            proc.wait()
            record["termination"] = {"reason": None, "cleanup_seconds": 0.0,
                                     "events": [{"kind": "reaped", "returncode": proc.returncode,
                                                 "monotonic": time.monotonic()}]}
        marks["reaped"] = time.monotonic()
        capture.drain(limits["capture_seconds"])
        marks["capture_end"] = time.monotonic()
        record["streams"] = capture.close()
        closed = True
    finally:
        if capture is not None and not closed:
            try:
                record["streams"] = capture.close()
            except Exception:
                record["streams"] = {}
        marks["wrapper_end"] = time.monotonic()
        base = marks["launch"]
        spawn = marks.get("spawn", base)
        stop = marks.get("stop", marks["wrapper_end"])
        reaped = marks.get("reaped", marks["wrapper_end"])
        capture_end = marks.get("capture_end", marks["wrapper_end"])
        record["marks"] = {k: round(v - base, 6) for k, v in marks.items()}
        record["durations"] = {
            "spawn": round(spawn - base, 6),
            "run_to_stop": round(stop - spawn, 6),
            "cleanup": round(reaped - stop, 6),
            "capture": round(capture_end - reaped, 6),
            "wrapper": round(marks["wrapper_end"] - base, 6),
        }
        record["duration_seconds"] = record["durations"]["wrapper"]
        record["duration_definition"] = "launch-to-reaped-plus-capture; see durations"
    return record


def junit(path: Path) -> dict:
    tree = ET.parse(path)
    cases = []
    for case in tree.iter("testcase"):
        module = (case.get("classname") or "").replace(".", "/") + ".py"
        outcome = "passed"
        text = ""
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = child.tag
                text = (child.get("message") or "") + " " + (child.text or "")
                break
        cases.append({"nodeid": f"{module}::{case.get('name')}", "outcome": outcome,
                      "text": " ".join(text.split())[:400]})
    return {"available": True, "tests": len(cases),
            "failures": sum(c["outcome"] == "failure" for c in cases),
            "errors": sum(c["outcome"] == "error" for c in cases),
            "skips": sum(c["outcome"] == "skipped" for c in cases),
            "nodeids": sorted(c["nodeid"] for c in cases), "cases": cases}


def finalize(key: str, out: Path, record: dict, before: dict, spec: dict, expected: list[str] | None) -> dict:
    capture_start = time.monotonic()
    result: dict = {"schema": "bigsmall.r370.run.v1", "command_id": f"R370:{key}", **record}
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
    result["capture_seconds_recorded"] = round(time.monotonic() - capture_start, 3)
    return result


def judge(result: dict, expectation: str) -> tuple[bool, str]:
    junit_result = result.get("junit", {})
    if not junit_result.get("available"):
        return False, "junit_absent"
    if not result.get("nodeids_exact"):
        return False, "nodeids_differ"
    if not result.get("sources_unchanged"):
        return False, "sources_changed"
    if result["termination"].get("reason") is not None:
        return False, f"terminated:{result['termination']['reason']}"
    code = result["termination"]["events"][-1].get("returncode")
    if expectation == "RED":
        cases = junit_result["cases"]
        if code != 1 or junit_result["tests"] != 1 or junit_result["failures"] != 1:
            return False, "red_shape"
        if "updated_at" not in cases[0]["text"] or "Field required" not in cases[0]["text"]:
            return False, "red_text"
        return True, "EXPECTED_RED"
    if code != 0 or junit_result["failures"] or junit_result["errors"] or junit_result["skips"]:
        return False, "green_shape"
    return True, "PASS"


def finish(key: str, out: Path, result: dict, expectation: str) -> int:
    passed, outcome = judge(result, expectation)
    result.update({"validation_pass": passed, "outcome": outcome, "finished_utc": now()})
    write_json(out / "result.json", result)
    write_json(out / "completion.json", {"schema": "bigsmall.r370.completion.v1", "command_id": f"R370:{key}",
                                         "finalization_complete": True, "validation_pass": passed,
                                         "outcome": outcome, "result": pin(out / "result.json"),
                                         "missingness": result["missingness"]})
    settle(key, {"validation_pass": passed, "outcome": outcome, "result": pin(out / "result.json")})
    print(json.dumps({"command_id": f"R370:{key}", "outcome": outcome, "validation_pass": passed,
                      "duration_seconds": result.get("duration_seconds"),
                      "streams": result.get("streams"), "missingness": result["missingness"]}, ensure_ascii=False))
    return 0 if passed else 1


def preflight_probe(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    scratch = root / "scratch-ledger.json"
    scratch.write_text(json.dumps({"commands": {"probe": {"state": "HELD", "used": 0, "remaining": 1}}}))
    global LEDGER
    original, LEDGER = LEDGER, scratch
    try:
        consume("probe")
        out = root / "already-exists"
        out.mkdir(exist_ok=True)
        rejected = False
        try:
            out.mkdir(exist_ok=False)
        except FileExistsError:
            rejected = True
        try:
            consume("probe")
            reusable = True
        except Failure:
            reusable = False
    finally:
        LEDGER = original
    return {"rejected_before_child": rejected, "cannot_reuse": not reusable}


def self_test(key: str) -> int:
    consume(key)
    try:
        out = IMPL / key
        require(not out.exists(), "exclusive output path exists")
        out.mkdir(mode=0o700)
        (out / "work").mkdir()
        cases = []

        def case(name: str, code: str, seconds: float, limits: dict | None = None) -> dict:
            spec = {"child_argv": [sys.executable, "-c", code], "cwd": str(out / "work"),
                    "child_env": {"PATH": "/usr/bin:/bin"}}
            case_dir = out / "cases" / name
            case_dir.mkdir(parents=True)
            before = source_identity(case_dir / "source-before.json")
            record = supervise(spec, case_dir, seconds, limits)
            result = finalize(f"{key}:{name}", case_dir, record, before, spec, None)
            entry = {"case": name, "termination": record["termination"], "streams": record["streams"],
                     "missingness": result["missingness"], "duration_seconds": record["duration_seconds"],
                     "durations": record["durations"]}
            write_json(case_dir / "result.json", entry)
            cases.append(entry)
            return entry

        missing = case("missing_junit", "import sys; sys.exit(0)", 5)
        term = case("deadline_term", "import time; time.sleep(60)", 2)
        kill = case("ignore_term_kill",
                    "import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(60)", 2)
        stdout_over = case("stdout_over",
                           "import sys,time\n[sys.stdout.write('x'*65536) for _ in range(64)]\nsys.stdout.flush()\ntime.sleep(60)",
                           30, {"stdout_mib": 1})
        stderr_over = case("stderr_over",
                           "import sys,time\n[sys.stderr.write('e'*65536) for _ in range(64)]\nsys.stderr.flush()\ntime.sleep(60)",
                           30, {"stderr_mib": 1})
        exact = case("exactly_at_cap",
                     "import sys\nsys.stdout.write('x'*1048576)\nsys.stdout.flush()", 30, {"stdout_mib": 1})
        probe = preflight_probe(out / "cases" / "preflight")
        checks = {
            "missing_junit_finalized": missing["missingness"].get("junit") == "absent",
            "deadline_term_clean": term["termination"].get("reason") == "child_deadline"
                                   and any(e["kind"] == "TERM" for e in term["termination"]["events"]),
            "kill_within_cleanup": kill["termination"].get("reason") == "child_deadline"
                                   and any(e["kind"] == "KILL" for e in kill["termination"]["events"])
                                   and kill["termination"]["cleanup_seconds"] <= LIMITS["cleanup_seconds"],
            "stdout_cap_exact": stdout_over["termination"].get("reason") == "stdout_limit"
                                and stdout_over["streams"]["stdout"]["written"] == 1 * MIB
                                and stdout_over["streams"]["stdout"]["observed"] > 1 * MIB,
            "stderr_cap_exact": stderr_over["termination"].get("reason") == "stderr_limit"
                                and stderr_over["streams"]["stderr"]["written"] == 1 * MIB,
            "exact_cap_no_false_positive": exact["termination"].get("reason") is None
                                           and exact["streams"]["stdout"]["written"] == 1 * MIB
                                           and exact["streams"]["stdout"]["complete"] is True,
            "preflight_zero_child": probe["rejected_before_child"] and probe["cannot_reuse"],
        }
        passed = all(checks.values())
        result = {"schema": "bigsmall.r370.selfcheck.v1", "command_id": f"R370:{key}", "cases": cases,
                  "probe": probe, "checks": checks, "validation_pass": passed, "missingness": {},
                  "finished_utc": now()}
        write_json(out / "result.json", result)
        write_json(out / "completion.json", {"schema": "bigsmall.r370.completion.v1",
                                             "command_id": f"R370:{key}", "finalization_complete": True,
                                             "validation_pass": passed, "result": pin(out / "result.json")})
        settle(key, {"validation_pass": passed, "outcome": "PASS" if passed else "NOT_PASSED",
                     "result": pin(out / "result.json")})
        print(json.dumps({"command_id": f"R370:{key}", "checks": checks, "validation_pass": passed}, ensure_ascii=False))
        return 0 if passed else 1
    except BaseException as error:
        settle(key, {"validation_pass": False, "outcome": f"ERROR_{type(error).__name__}"})
        raise


def normalize(spec: dict) -> dict:
    return {"child_argv": spec.get("child_argv") or spec.get("argv"),
            "child_env": spec.get("child_env") or spec.get("env"),
            "cwd": spec["cwd"], "child_seconds": spec["child_seconds"],
            "expected_nodeids": spec.get("expected_nodeids")}


def run_command(key: str, spec: dict, expectation: str) -> int:
    spec = normalize(spec)
    consume(key)
    out = IMPL / key
    try:
        require(not out.exists(), "exclusive output path exists")
        out.mkdir(mode=0o700)
        before = source_identity(out / "source-before.json")
        write_json(out / "invocation.json", {"schema": "bigsmall.r370.invocation.v1", "command_id": f"R370:{key}",
                                             "spec": spec, "runner": pin(Path(__file__)), "plan": pin(PLAN),
                                             "env": dict(os.environ)})
        record = supervise(spec, out, spec["child_seconds"])
        result = finalize(key, out, record, before, spec, spec.get("expected_nodeids"))
        return finish(key, out, result, expectation)
    except BaseException as error:
        settle(key, {"validation_pass": False, "outcome": f"ERROR_{type(error).__name__}"})
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in KEYS:
        print(json.dumps({"error": "one literal R370 key required", "allowed": list(KEYS)}, ensure_ascii=False))
        return 2
    key = argv[1]
    try:
        require(pin(PLAN)["sha256"] == PLAN_SHA, "plan.json changed")
        plan = json.loads(PLAN.read_text())
        if key == "runner_contract_01":
            return self_test(key)
        spec = plan["command"]
        return run_command(key, spec, "RED" if key.endswith("red_01") else "GREEN")
    except BaseException as error:
        print(json.dumps({"command_id": f"R370:{key}", "error": {"type": type(error).__name__,
                                                                 "message": str(error)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
