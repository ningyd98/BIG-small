"""执行 R376 已批准阶段，保留真实退出和原始证据；不自动重试。"""
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
    for row in PLAN["inputs"]:
        if row["path"] not in ALLOWED and pin(ROOT / row["path"]) != row:
            drift.append(row["path"])
    before = sources()
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
    if stage_id != "fixture_contract_red":
        predecessor = "fixture_contract_red" if stage_id == "fixture_contract_green" else "fixture_contract_green"
        previous = json.loads((HERE / "implementation" / predecessor / "result.json").read_text())
        assert previous["returncode"] == (1 if predecessor.endswith("red") else 0)
        assert previous["prerequisite_accepted"] and previous["reaped"]
        if stage_id.startswith("t3_green_"):
            smoke = json.loads((HERE / "implementation/shared_fixture_smoke/result.json").read_text())
            assert smoke["returncode"] == 0 and smoke["reaped"]
    for name in ["resources", "resources-a", "r223/resources", "r223/cases", "runtime/artifacts"]:
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
    result = {"stage_id": stage_id, "state": state,
              "returncode": process.returncode if process else None,
              "elapsed_s": time.monotonic() - began, "ended_utc": datetime.now(UTC).isoformat(),
              "prerequisite_accepted": prerequisite.get("accepted_prerequisite", False),
              "source_drift_during_stage": [] if before == after else ["SOURCE_SNAPSHOT_CHANGED"],
              **cleanup}
    save(directory / "result.json", result)
    with (HERE / "progress.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}, exit={result['returncode']}, {result['elapsed_s']:.3f}s; reaped={result['reaped']}.\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if errors or cleanup["remaining_live"] or not cleanup["reaped"] or before != after:
        raise RuntimeError("Stage infrastructure/cleanup/source check failed; no next launch")


if __name__ == "__main__":
    if sys.argv[1:] == ["--batch-long"]:
        for item in PLAN["commands"]:
            if item["id"].startswith("t3_green_"):
                print("START " + item["id"], flush=True)
                run(item["id"])
        save(HERE / "long-completion.json", {"state": "ALL_FIVE_ACCOUNTED",
                                            "ended_utc": datetime.now(UTC).isoformat()})
    elif len(sys.argv) == 2:
        run(sys.argv[1])
    else:
        raise SystemExit("Use stage_id or --batch-long")
