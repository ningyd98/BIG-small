"""R405 single owned diagnostic stage. Historical stages are read-only."""
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
AUDIT = json.loads((HERE / "input-audit.json").read_text())

def save(path, value):
    with path.open("x") as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}

def sources():
    paths = [ROOT / r["path"] for r in AUDIT["inputs"]]
    paths += [Path(__file__), HERE / "adapters/r405_observe.py", HERE / "plan.json", HERE / "input-audit.json"]
    return [pin(p) for p in sorted(set(paths))]

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
    execution = PLAN["execution"]
    assert stage_id == execution["stage_id"] == "foreign_owner_observed_v1"
    assert set(execution) >= {"command", "env", "cwd", "stage_directory", "stage_id"}
    assert hashlib.sha256((HERE / "input-audit.json").read_bytes()).hexdigest() == PLAN["input_audit"]["sha256"]
    rows = AUDIT["inputs"]
    assert type(rows) is list and len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        assert set(row) == {"path", "bytes", "sha256"}
        path = ROOT / row["path"]
        assert not path.is_symlink() and pin(path) == row, row["path"]
    frozen = json.loads((HERE / "preflight/static.json").read_text())
    assert frozen["accepted"]
    for row in frozen["derived_pins"]:
        assert pin(ROOT / row["path"]) == row
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], env={"PATH":"/usr/bin:/bin", "GIT_OPTIONAL_LOCKS":"0"}, text=True).strip() == PLAN["base"]["head"]
    assert subprocess.check_output(["git", "branch", "--show-current"], env={"PATH":"/usr/bin:/bin", "GIT_OPTIONAL_LOCKS":"0"}, text=True).strip() == PLAN["base"]["branch"]
    directory = Path(execution["stage_directory"])
    assert not directory.exists()
    assert directory.is_relative_to(HERE / "implementation") and execution["cwd"] == str(ROOT)
    before = sources()
    directory.mkdir(parents=True, exist_ok=False)
    for name in ["resources", "resources-a", "r223/resources", "r223/cases", "runtime/artifacts", "tmp"]:
        (directory / name).mkdir(parents=True)
    env, argv = execution["env"], execution["command"]
    assert env["R373_STAGE_DIR"] == str(directory)
    assert "tests/test_operational_windows.py::test_foreign_thread_has_no_owner_context" in argv
    stage = {"child_timeout_s": PLAN["budgets"]["pytest_cap_s"]}
    save(HERE / "round-start.json", {"started_utc": datetime.now(UTC).isoformat(),
         "started_monotonic_ns": time.monotonic_ns(), "new_user_authorized_round": True,
         "historical_clocks_unchanged": True, "phase_cap_s":stage["child_timeout_s"], "cleanup_reserve_s":15})
    save(directory / "source-before.json", before)
    invocation = {"stage_id":stage_id,"argv":argv,"env":env,"cwd":str(ROOT),
         "started_utc":datetime.now(UTC).isoformat(),"child_timeout_s":stage["child_timeout_s"],
         "cleanup_reserve_s":15,"launcher":pin(Path(__file__)),"plan":pin(HERE / "plan.json"),
         "permission_profile":"workspace-write/network restricted", "retry":False}
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
    observations_path = directory / "observations.jsonl"
    observations = [json.loads(line) for line in observations_path.read_text().splitlines()] if observations_path.exists() else []
    summary = next((r for r in observations if r.get("observer_summary")), {})
    events_path = directory / "pytest-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    reports = [r for r in events if r.get("event") == "report" and r.get("nodeid", "").endswith("::test_foreign_thread_has_no_owner_context")]
    passed = all(any(r.get("when") == phase and r.get("outcome") == "passed" for r in reports) for phase in ["setup", "call", "teardown"])
    observer_ok = bool(summary.get("target_entered") and summary.get("restored") and summary.get("prior_hooks_empty") and not summary.get("errors"))
    clean = not errors and not cleanup["remaining_live"] and cleanup["reaped"] and before == after
    prerequisite_ok = prerequisite.get("accepted_prerequisite", False)
    diagnostic_complete = bool(process and state == "FINISHED" and clean and prerequisite_ok and observer_ok)
    result = {"stage_id":stage_id,"state":state,"returncode":process.returncode if process else None,
         "elapsed_s":time.monotonic()-began,"ended_utc":datetime.now(UTC).isoformat(),
         "prerequisite_accepted":prerequisite_ok,"observer_accepted":observer_ok,
         "diagnostic_complete":diagnostic_complete,"node_passed":passed,
         "guard_usable":bool(diagnostic_complete and passed and process.returncode == 0),
         "source_drift_during_stage":[] if before == after else ["SOURCE_SNAPSHOT_CHANGED"], **cleanup}
    save(directory / "result.json", result)
    with (HERE / "step-report.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}; exit={result['returncode']}; {result['elapsed_s']:.3f}s; diagnostic_complete={diagnostic_complete}; guard_usable={result['guard_usable']}; reaped={result['reaped']}.\n")
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if not diagnostic_complete:
        raise RuntimeError("Diagnostic incomplete; preserve evidence, next Astra before any rerun")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Use the one approved R405 stage id")
    try:
        run(sys.argv[1])
    except BaseException as error:
        failure = HERE / "preflight/launch-failure.json"
        if not failure.exists():
            save(failure,{"type":type(error).__name__,"message":str(error),"ended_utc":datetime.now(UTC).isoformat()})
        raise
