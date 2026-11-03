"""R409 original plain guards; raw child terminal is saved before artifact decoding."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

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
    paths += [Path(__file__), HERE / "plan.json", HERE / "input-audit.json"]
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
    assert hashlib.sha256((HERE / "plan.json").read_bytes()).hexdigest() == "59cdd72d11bdbceb10bab7d65abe1d74cf98990607b990a64323553469e112cd"
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
        result = json.loads((Path(previous["directory"]) / "stage-acceptance.json").read_text())
        assert result["expected_accepted"]
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

    resource_samples = []
    def sample_resource(label):
        if len(resource_samples) >= 14 or process is None:
            return
        row = {"label":label,"elapsed_s":time.monotonic()-began,"utc":datetime.now(UTC).isoformat(),"pid":process.pid}
        try:
            base = Path("/proc") / str(process.pid)
            raw = (base / "stat").read_text()
            fields = raw[raw.rfind(")")+2:].split()
            if identity is not None and fields[19] != identity["starttime_ticks"]:
                raise RuntimeError("Child starttime changed")
            row.update(state=fields[0],starttime_ticks=fields[19],utime_ticks=int(fields[11]),stime_ticks=int(fields[12]),statm=(base / "statm").read_text().strip())
            cgroups = (base / "cgroup").read_text().splitlines()
            row["cgroup_membership"] = cgroups
            memory = {}
            for line in cgroups:
                parts = line.split(":",2)
                if len(parts) == 3 and parts[0] == "0":
                    location = Path("/sys/fs/cgroup") / parts[2].lstrip("/")
                    for name in ["memory.current","memory.max","memory.events"]:
                        path = location / name
                        try:
                            memory[name] = path.read_text().strip()
                        except OSError as error:
                            memory[name] = {"unavailable":type(error).__name__}
            row["cgroup_memory"] = memory
        except (OSError,ValueError,RuntimeError) as error:
            row["unavailable"] = {"type":type(error).__name__,"message":str(error)}
        resource_samples.append(row)

    def save_child_exit():
        if process is not None and process.returncode is not None and not (directory / "child-exit.json").exists():
            save(directory / "child-exit.json",{"returncode":process.returncode,"known":True,"state":state,"elapsed_s":time.monotonic()-began,"ended_utc":datetime.now(UTC).isoformat(),"supervisor_signals_so_far":list(signals)})

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
                sample_resource("spawn")
                while process.returncode is None:
                    remaining_s = stage["child_timeout_s"] - (time.monotonic()-began)
                    if remaining_s <= 0:
                        raise subprocess.TimeoutExpired(argv,stage["child_timeout_s"])
                    try:
                        process.wait(timeout=min(20,remaining_s))
                    except subprocess.TimeoutExpired:
                        sample_resource("interval")
                        if time.monotonic()-began >= stage["child_timeout_s"]:
                            raise
                save_child_exit()
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
    save_child_exit()
    sample_resource("final")
    cleanup = {"signals": signals, "errors": errors,
               "remaining_live": members(identity["pgid"]) if identity else [],
               "reaped": bool(process and process.returncode is not None)}
    save(directory / "cleanup.json", cleanup)
    source_check = "UNAVAILABLE"
    try:
        after = sources()
        save(directory / "source-after.json",after)
        source_check = "MATCH" if before == after else "DRIFT"
    except BaseException as error:
        errors.append({"phase":"source-after","type":type(error).__name__,"message":str(error)})
    # Mandatory raw terminal precedes all prerequisite/events/JUnit/report parsing.
    result = {"stage_id":stage_id,"state":state,"returncode":process.returncode if process else None,"child_exit_known":bool(process and process.returncode is not None),"elapsed_s":time.monotonic()-began,"ended_utc":datetime.now(UTC).isoformat(),"source_check":source_check,"acceptance":"NOT_EVALUATED",**cleanup,"errors":errors}
    try:
        save(directory / "result.json",result)
    except BaseException as error:
        print(json.dumps({"mandatory_result_write_failed":str(error),"actual_terminal":result}),file=sys.stderr,flush=True)
        raise
    try:
        save(directory / "resource-samples.json",resource_samples)
    except OSError as error:
        print(json.dumps({"resource_write_error":str(error)}),file=sys.stderr,flush=True)
    parse_errors = []
    def read_json(name):
        try:
            return json.loads((directory / name).read_text())
        except (OSError,ValueError) as error:
            parse_errors.append({"file":name,"type":type(error).__name__,"message":str(error)})
            return None
    prerequisite = read_json("prerequisite.json")
    events = []
    try:
        for line in (directory / "pytest-events.jsonl").read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError as error:
                parse_errors.append({"file":"pytest-events.jsonl","type":type(error).__name__,"message":str(error)})
    except OSError as error:
        parse_errors.append({"file":"pytest-events.jsonl","type":type(error).__name__,"message":str(error)})
    junit_ok = False
    try:
        tree = ET.parse(directory / "junit.xml")
        junit_ok = len(tree.findall(".//testcase")) == 1 and not any(tree.findall(".//"+tag) for tag in ["failure","error","skipped"])
    except (OSError,ET.ParseError) as error:
        parse_errors.append({"file":"junit.xml","type":type(error).__name__,"message":str(error)})
    reports = [r for r in events if r.get("event") == "report"]
    expected_node = f"tests/test_operational_runtime_closure.py::test_b_local_writer_requires_private_scope[{stage['backend']}]"
    phase_pass = all(any(r.get("nodeid") == expected_node and r.get("when") == phase and r.get("outcome") == "passed" for r in reports) for phase in ["setup","call","teardown"])
    calls = [r for r in reports if r.get("when") == "call"]
    counts = {outcome:sum(r.get("outcome") == outcome for r in calls) for outcome in ["passed","failed","skipped"]}
    accepted = bool(state == "FINISHED" and process and process.returncode == 0 and cleanup["reaped"] and not cleanup["remaining_live"] and not errors and source_check == "MATCH" and prerequisite and prerequisite.get("accepted_prerequisite") and junit_ok and phase_pass and not parse_errors)
    acceptance = {"stage_id":stage_id,"expected_accepted":accepted,"counts":counts,"original_node":expected_node,"all_original_phases_passed":phase_pass,"junit_one_pass":junit_ok,"prerequisite_accepted":bool(prerequisite and prerequisite.get("accepted_prerequisite")),"parse_errors":parse_errors,"raw_result_path":str((directory / "result.json").relative_to(ROOT))}
    save(directory / "stage-acceptance.json",acceptance)
    print(json.dumps({"raw_terminal":result,"stage_acceptance":acceptance},ensure_ascii=False),flush=True)
    with (HERE / "step-report.md").open("a") as ledger:
        ledger.write(f"\n- {stage_id}: {state}; actual_exit={result['returncode']}; {result['elapsed_s']:.3f}s; expected_accepted={accepted}; source={source_check}; reaped={result['reaped']}.\n")
    if not accepted:
        raise RuntimeError("Plain guard not accepted; no successor or retry without next Astra")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {r["id"] for r in PLAN["stages"]}:
        raise SystemExit("Use one approved R409 stage id")
    run(sys.argv[1])
