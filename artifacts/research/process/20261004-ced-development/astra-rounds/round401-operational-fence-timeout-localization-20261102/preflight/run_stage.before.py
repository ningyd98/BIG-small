"""执行 R399 已批准阶段，保留真实退出和原始证据；不自动重试。"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
PLAN = json.loads((HERE / "plan.json").read_text())
ALLOWED = {row["path"] for row in PLAN["changes"]}
AUDIT = json.loads((HERE / "input-audit.json").read_text())
INPUTS = AUDIT["source_pins"] + AUDIT["evidence_pins"]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def sources():
    original = json.loads((HERE / "preflight/source-before.json").read_text())
    paths = {r["path"] for r in original["files"]} | ALLOWED
    return [pin(ROOT / name) for name in sorted(paths) if (ROOT / name).is_file()]


def members(pgid):
    found = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            if int(fields[2]) == pgid and fields[0] != "Z":
                found.append({"pid": int(path.name), "pgid": pgid,
                              "starttime_ticks": fields[19], "state": fields[0]})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def run(stage_id):
    stage = next(row for row in PLAN["commands"] if row["id"] == stage_id)
    drift = []
    for row in INPUTS:
        if row["path"] not in ALLOWED and pin(ROOT / row["path"]) != row:
            drift.append(row["path"])
    before = sources()
    frozen = json.loads((HERE / "preflight/source-before.json").read_text())["files"]
    frozen_test = next(row for row in frozen if row["path"] == "tests/test_eteac_retry_lock_regression.py")
    assert pin(ROOT / frozen_test["path"]) == frozen_test, "New regression source must remain frozen"
    initial = json.loads((HERE / "preflight/source-before.json").read_text())
    before_map = {r["path"]: r for r in before}
    drift.extend(r["path"] for r in initial["files"]
                 if r["path"] not in ALLOWED and before_map.get(r["path"]) != r)
    if drift:
        raise RuntimeError({"unplanned_input_drift": sorted(set(drift))})
    directory = HERE / "implementation" / stage_id
    directory.mkdir(parents=True, exist_ok=False)
    start = json.loads((HERE / "round-start.json").read_text())
    remaining = start["started_epoch_s"] + start["max_wall_s"] - time.time()
    if remaining < stage["child_timeout_s"] + 15:
        save(directory / "result.json", {"stage_id": stage_id, "state": "NOT_RUN_BUDGET",
                                        "remaining_s": remaining})
        return
    order = [row["id"] for row in PLAN["commands"]]
    position = order.index(stage_id)
    if position:
        previous = json.loads((HERE / "implementation" / order[position - 1] / "result.json").read_text())
        assert previous["expected_accepted"] and previous["reaped"], "Previous stage must be accepted"
    for name in ["resources", "resources-a", "r223/resources", "r223/cases", "runtime/artifacts", "tmp"]:
        (directory / name).mkdir(parents=True)
    env = {key: value.replace("{STAGE_DIR}", str(directory))
           for key, value in PLAN["environment_template"].items()}
    assert all(key not in env for key in PLAN["environment_absent"])
    argv = [arg.replace("{STAGE_DIR}", str(directory)) for arg in stage["argv"]]
    save(directory / "source-before.json", before)
    invocation = {"stage_id": stage_id, "argv": argv, "env": env, "cwd": str(ROOT),
                  "started_utc": datetime.now(UTC).isoformat(),
                  "child_timeout_s": stage["child_timeout_s"], "cleanup_reserve_s": 15,
                  "launcher": pin(Path(__file__)), "plan": pin(HERE / "plan.json"),
                  "permission_profile": "workspace-write/network restricted (calling executor)",
                  "retry": False}
    save(directory / "invocation.json", invocation)
    process = None
    identity = None
    errors = []
    signals = []
    state = "FINISHED"
    began = time.monotonic()
    previous_handlers = {}

    def interrupted(signum, frame):
        raise InterruptedError(signal.Signals(signum).name)

    def owned_signal(sig):
        current = members(identity["pgid"])
        leader = next((row for row in current if row["pid"] == process.pid), None)
        if leader and leader["starttime_ticks"] != identity["starttime_ticks"]:
            errors.append({"identity_changed": current})
            return
        if current:
            try:
                os.killpg(identity["pgid"], sig)
                signals.append(signal.Signals(sig).name)
            except ProcessLookupError:
                pass

    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[sig] = signal.signal(sig, interrupted)
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                initial_members = members(process.pid)
                leader = next(row for row in initial_members if row["pid"] == process.pid)
                identity = {**leader, "members_at_launch": initial_members}
                save(directory / "process-identity.json", identity)
                process.wait(timeout=max(0.01, stage["child_timeout_s"] - (time.monotonic() - began)))
            except subprocess.TimeoutExpired:
                state = "TIMEOUT"
            finally:
                if identity is None:
                    current = members(process.pid)
                    leader = next((row for row in current if row["pid"] == process.pid), None)
                    if leader:
                        identity = {**leader, "members_at_launch": current}
        except BaseException as error:
            state = "INFRASTRUCTURE_ERROR" if process is None else "INTERRUPTED"
            errors.append({"type": type(error).__name__, "message": str(error)})
        finally:
            cleanup_started = time.monotonic()
            if process is not None:
                if identity is not None:
                    owned_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if identity is not None:
                        owned_signal(signal.SIGKILL)
                    else:
                        process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        errors.append({"reason": "child_not_reaped"})
                if identity is not None:
                    remaining_live = members(identity["pgid"])
                    if remaining_live:
                        owned_signal(signal.SIGKILL)
                        until = cleanup_started + 15
                        while members(identity["pgid"]) and time.monotonic() < until:
                            time.sleep(0.05)
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    cleanup = {"signals": signals, "errors": errors,
               "remaining_live": members(identity["pgid"]) if identity else [],
               "reaped": bool(process and process.returncode is not None)}
    save(directory / "cleanup.json", cleanup)
    after = sources()
    save(directory / "source-after.json", after)
    precondition_path = directory / "prerequisite.json"
    prerequisite = json.loads(precondition_path.read_text()) if precondition_path.exists() else {}
    expected_accepted = bool(process and process.returncode == 0 and state == "FINISHED")
    if stage_id == "lock_contract_red":
        child = json.loads((directory / "child-retry-sqlite.json").read_text()) if (directory / "child-retry-sqlite.json").exists() else {}
        child_out = (directory / "child-retry-sqlite.stdout").read_text() if (directory / "child-retry-sqlite.stdout").exists() else ""
        child_err = (directory / "child-retry-sqlite.stderr").read_text() if (directory / "child-retry-sqlite.stderr").exists() else ""
        expected_accepted = bool(process and process.returncode == 1 and state == "FINISHED"
            and child.get("timed_out") and child.get("reaped")
            and "READY; ENTER initialize_retry_budget_if_absent" in child_out
            and "initialize_retry_budget_if_absent" in child_err and "protocol.py" in child_err)
    prerequisite_ok = (prerequisite.get("accepted_prerequisite", False)
                       if stage_id == "operational_fences_green" else True)
    result = {"stage_id": stage_id, "state": state,
              "returncode": process.returncode if process else None,
              "elapsed_s": time.monotonic() - began, "ended_utc": datetime.now(UTC).isoformat(),
              "prerequisite_accepted": prerequisite_ok, "expected_accepted": expected_accepted and prerequisite_ok,
              "source_drift_during_stage": [] if before == after else ["SOURCE_SNAPSHOT_CHANGED"],
              **cleanup}
    save(directory / "result.json", result)
    with (HERE / "step-report.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}, exit={result['returncode']}, {result['elapsed_s']:.3f}s; reaped={result['reaped']}.\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if errors or cleanup["remaining_live"] or not cleanup["reaped"] or before != after or not result["expected_accepted"]:
        raise RuntimeError("Stage infrastructure/cleanup/source check failed; no next launch")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {item["id"] for item in PLAN["commands"]}:
        raise SystemExit("Use one approved R399 stage_id")
    run(sys.argv[1])
