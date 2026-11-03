"""R407 independent unchanged writer guards with passive native stack samples."""
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
    paths += [Path(__file__), HERE / "adapters/r407_stack_samples.py", HERE / "plan.json", HERE / "input-audit.json"]
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
    stage = next(row for row in PLAN["stages"] if row["id"] == stage_id)
    assert hashlib.sha256((HERE / "plan.json").read_bytes()).hexdigest() == "b3223bda15e03199f873a0e97804eec78479f33b36a7167174015e8397d2053e"
    assert hashlib.sha256((HERE / "input-audit.json").read_bytes()).hexdigest() == PLAN["input_audit"]["sha256"]
    rows = AUDIT["inputs"]
    assert type(rows) is list and len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        assert set(row) == {"path","bytes","sha256"}
        path = ROOT / row["path"]
        assert not path.is_symlink() and pin(path) == row,row["path"]
    frozen = json.loads((HERE / "preflight/static.json").read_text())
    assert frozen["accepted"]
    for row in frozen["derived_pins"]:
        assert pin(ROOT / row["path"]) == row
    assert subprocess.check_output(["git","rev-parse","HEAD"],env={"PATH":"/usr/bin:/bin","GIT_OPTIONAL_LOCKS":"0"},text=True).strip() == PLAN["base_head"]
    assert subprocess.check_output(["git","branch","--show-current"],env={"PATH":"/usr/bin:/bin","GIT_OPTIONAL_LOCKS":"0"},text=True).strip() == PLAN["branch"]
    position = [row["id"] for row in PLAN["stages"]].index(stage_id)
    if position:
        previous = PLAN["stages"][position-1]
        result = json.loads((Path(previous["directory"]) / "result.json").read_text())
        assert result["expected_accepted"] and result["reaped"]
    directory = Path(stage["directory"])
    assert not directory.exists() and directory.is_relative_to(HERE / "implementation")
    before = sources()
    directory.mkdir(parents=True,exist_ok=False)
    for name in ["resources","resources-a","r223/resources","r223/cases","runtime/artifacts","tmp"]:
        (directory / name).mkdir(parents=True)
    if not (HERE / "round-start.json").exists():
        save(HERE / "round-start.json",{"started_utc":datetime.now(UTC).isoformat(),"started_monotonic_ns":time.monotonic_ns(),"phase_bounded":True,"historical_clocks_unchanged":True})
    env,argv = stage["env"],stage["argv"]
    stage["child_timeout_s"] = stage["child_cap_s"]
    save(directory / "source-before.json",before)
    save(directory / "invocation.json",{"stage_id":stage_id,"argv":argv,"env":env,"cwd":str(ROOT),"started_utc":datetime.now(UTC).isoformat(),"child_timeout_s":stage["child_cap_s"],"cleanup_reserve_s":15,"launcher":pin(Path(__file__)),"retry":False})
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
    events = [json.loads(line) for line in (directory / "pytest-events.jsonl").read_text().splitlines()]
    reports = [r for r in events if r.get("event") == "report"]
    calls = [r for r in reports if r.get("when") == "call"]
    counts = {outcome:sum(r["outcome"] == outcome for r in calls) for outcome in ["passed","failed","skipped"]}
    phases_clean = all(r["outcome"] == "passed" for r in reports if r["when"] in {"setup","teardown"})
    if stage_id.endswith("_red"):
        text = (directory / "stdout.log").read_text()
        expected_signature = ("original transition obligations unavailable or exhausted" in text if stage_id == "legacy_contract_red" else "assert False is True" in text and "_check_observation" in text)
        outcome_ok = bool(process and process.returncode == 1 and counts == {"passed":0,"failed":1,"skipped":0} and expected_signature)
    else:
        outcome_ok = bool(process and process.returncode == 0 and calls and all(r["outcome"] == "passed" for r in calls))
    passive = json.loads((directory / "stacks-observer.json").read_text())
    assert passive["hooks_restored"] and passive["timer_cancelled"]
    clean = not errors and not cleanup["remaining_live"] and cleanup["reaped"] and before == after
    prerequisite_ok = prerequisite.get("accepted_prerequisite",False)
    accepted = bool(state == "FINISHED" and clean and prerequisite_ok and phases_clean and outcome_ok)
    result = {"stage_id":stage_id,"state":state,"returncode":process.returncode if process else None,"elapsed_s":time.monotonic()-began,"ended_utc":datetime.now(UTC).isoformat(),"counts":counts,"prerequisite_accepted":prerequisite_ok,"expected_accepted":accepted,"stack_bytes":(directory / "stacks.txt").stat().st_size,"observer":passive,"source_drift_during_stage":[] if before == after else ["SOURCE_SNAPSHOT_CHANGED"],**cleanup}
    save(directory / "result.json",result)
    with (HERE / "step-report.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}; exit={result['returncode']}; counts={counts}; {result['elapsed_s']:.3f}s; expected_accepted={accepted}; reaped={result['reaped']}.\n")
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if not accepted:
        raise RuntimeError("Stage not accepted; preserve evidence and next Astra before affected fixes/rerun")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {r["id"] for r in PLAN["stages"]}:
        raise SystemExit("Use one approved R407 stage id")
    run(sys.argv[1])
