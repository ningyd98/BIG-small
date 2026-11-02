"""R396 one-shot diagnostic. Product implementations and locks remain untouched."""
from __future__ import annotations

import argparse
import ctypes
import datetime
import enum
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback
import _thread

SCRIPT = Path(__file__).resolve()
DIAG = SCRIPT.parent
ROUND = DIAG.parent
ROOT = SCRIPT.parents[7]
HEAD = "9abf127ab0d7d64fb02670eb278519f8d3bde5e9"
AUDIT_SHA = "2bc88e98cb417e566380f49b24f1c8eb64790a253d2df83e5addb8ce8bf050b1"
BOUNDARIES = {
    "simulation_runtime/worker.py": {"poll_once", "_execute", "_run", "_run_mock", "_raise_if_cancelled_or_timed_out"},
    "experiments/runner.py": {"__init__", "run", "_execute_scenario", "_build_result"},
    "experiments/runtime_harness.py": {"__init__", "submit_contract", "close"},
    "edge/runtime/task_executor.py": {"submit_contract", "_execute_runtime", "_save_checkpoint"},
    "edge/event_mode/controller.py": {"initialize_task"},
    "edge/recovery/retry_budget.py": {"initialize"},
    "repositories/event_autonomy/sqlite.py": {"__init__", "initialize_retry_budget_if_absent", "get_retry_budget", "close"},
    "repositories/event_autonomy/protocol.py": {"dispatch"},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": digest(data)}


def check_inputs(audit_path):
    assert digest(audit_path.read_bytes()) == AUDIT_SHA
    audit = json.loads(audit_path.read_text())
    records = []
    for expected in audit["source_pins"] + audit["evidence_pins"]:
        actual = pin(ROOT / expected["path"])
        assert actual == expected, expected["path"]
        records.append(actual)
    return audit, records


def code_key(frame):
    prefix = str(ROOT / "src/cloud_edge_robot_arm") + "/"
    filename = frame.f_code.co_filename
    return filename[len(prefix):] if filename.startswith(prefix) else ""


def selected(frame):
    key = code_key(frame)
    if frame.f_code.co_name not in BOUNDARIES.get(key, ()):
        return False
    if key.endswith("protocol.py"):
        return frame.f_locals.get("name") in {"initialize_retry_budget_if_absent", "get_retry_budget"}
    return True


def primitive(value):
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, enum.Enum):
        return primitive(value.value)
    return None


def frame_detail(frame):
    local = frame.f_locals
    obj = local.get("self")
    attrs = getattr(obj, "__dict__", {}) if obj is not None else {}
    lock = attrs.get("_write_lock")
    row = {"file": code_key(frame), "function": frame.f_code.co_name,
           "line": frame.f_lineno, "self_id": id(obj) if obj is not None else None,
           "self_class": type(obj).__name__ if obj is not None else None}
    if isinstance(lock, _thread.LockType):
        row.update(lock_id=id(lock), lock_type=type(lock).__name__, lock_locked=lock.locked())
    if frame.f_code.co_name == "dispatch":
        row.update(dispatch_name=local.get("name"), scope_present="scope" in local,
                   scope_is_none=(local["scope"] is None) if "scope" in local else None)
    clock = attrs.get("clock")
    clock_attrs = getattr(clock, "__dict__", {}) if clock is not None else {}
    if type(clock_attrs.get("_now_ms")) is int:
        row["virtual_now_ms"] = clock_attrs["_now_ms"]
    return row


def child(run_root, audit_path):
    audit, _ = check_inputs(audit_path)
    log_fds = {name: os.open(DIAG / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_APPEND, 0o600)
               for name in ("boundaries.jsonl", "frame-samples.jsonl", "stacks.txt", "audit-events.jsonl")}
    phase = {"mode": "IMPORT", "started_ns": time.monotonic_ns()}
    counters = {"boundary_events": 0, "suppressed_events": 0, "observation_errors": 0, "denied_operations": 0}
    last_boundary = {}
    stop = threading.Event()
    worker = None
    monitor = None
    child_started_ns = time.monotonic_ns()

    def emit(name, value):
        os.write(log_fds[name], canonical(value) + b"\n")

    def fail_stop_denial(event):
        counters["denied_operations"] += 1
        try:
            record = {"event": event[:160], "allowed": False, "pid": os.getpid(),
                      "thread_id": threading.get_ident(), "mode": phase["mode"],
                      "monotonic_ns": time.monotonic_ns(), "operation_executed": False,
                      "native_cleanup_skipped_on_fail_stop": True}
            try:
                marker_fd = os.open(run_root / "audit-denied.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(marker_fd, canonical(record) + b"\n")
                finally:
                    os.close(marker_fd)
            finally:
                emit("audit-events.jsonl", record)
        finally:
            os._exit(78)

    def require_no_denial():
        if counters["denied_operations"] or (run_root / "audit-denied.json").exists():
            fail_stop_denial("defensive_denial_guard")

    def audit_hook(event, args):
        denied = event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
                           "socket.gethostbyname_ex", "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg",
                           "os.system", "os.exec", "os.posix_spawn", "pty.spawn"}
        if event == "subprocess.Popen":
            allowed = (list(args[1]) == ["git", "rev-parse", "HEAD"]
                       and args[2] is not None and Path(args[2]).resolve() == ROOT)
            denied = not allowed
            if allowed:
                emit("audit-events.jsonl", {"event": event, "allowed": True, "purpose": "native_git_provenance_only"})
        if denied:
            fail_stop_denial(event)

    sys.addaudithook(audit_hook)

    def profile(frame, event, arg):
        nonlocal last_boundary
        if event not in {"call", "return", "c_call", "c_return", "c_exception"} or not selected(frame):
            return
        try:
            lock = getattr(arg, "__self__", None) if event.startswith("c_") else None
            if event.startswith("c_") and not isinstance(lock, _thread.LockType):
                return
            if counters["boundary_events"] >= 5000:
                counters["suppressed_events"] += 1
                return
            counters["boundary_events"] += 1
            row = {"sequence": counters["boundary_events"], "event": event, "mode": phase["mode"],
                   "monotonic_ns": time.monotonic_ns(), "thread_id": threading.get_ident(), **frame_detail(frame)}
            if lock is not None:
                row.update(c_function=getattr(arg, "__name__", ""), c_lock_id=id(lock), c_lock_locked=lock.locked())
            if code_key(frame) == "experiments/runner.py" and frame.f_code.co_name == "__init__" and event == "call":
                cfg = frame.f_locals["config"].__dict__
                row["config"] = {key: primitive(cfg.get(key)) for key in (
                    "experiment_id", "scenario_id", "mode", "seed", "repetitions", "network_profile",
                    "cache_policy", "risk_policy_version", "supervision_period_ms", "timeout_ms")}
                row["config"]["fault_profile_name"] = cfg["fault_profile"].__dict__.get("name")
                row["config"]["task_profile_name"] = cfg["task_profile"].__dict__.get("name")
            last_boundary = {key: row[key] for key in ("sequence", "event", "file", "function", "line", "mode", "thread_id")}
            emit("boundaries.jsonl", row)
        except Exception as exc:
            counters["observation_errors"] += 1
            emit("audit-events.jsonl", {"event": "profile_error", "error_type": type(exc).__name__})

    def sample():
        schedules = {"PCSC": (5, 15, 25), "ETEAC": (5, 15, 35, 65)}
        done = set()
        while not stop.wait(0.02):
            current = dict(phase)
            elapsed = (time.monotonic_ns() - current["started_ns"]) / 1e9
            for due in schedules.get(current["mode"], ()):
                token = (current["mode"], due)
                if elapsed < due or token in done:
                    continue
                done.add(token)
                try:
                    captured = time.monotonic_ns()
                    header = {"mode": current["mode"], "due_s": due, "elapsed_from_mode_s": elapsed,
                              "monotonic_ns": captured}
                    os.write(log_fds["stacks.txt"], b"\nR396_SNAPSHOT " + canonical(header) + b"\n")
                    faulthandler.dump_traceback(file=log_fds["stacks.txt"], all_threads=True)
                    names = {thread.ident: thread.name for thread in threading.enumerate()}
                    threads = []
                    for ident, frame in sys._current_frames().items():
                        frames = []
                        while frame is not None and len(frames) < 64:
                            row = {"file": frame.f_code.co_filename, "function": frame.f_code.co_name, "line": frame.f_lineno}
                            if selected(frame):
                                row.update(frame_detail(frame))
                            frames.append(row)
                            frame = frame.f_back
                        threads.append({"thread_id": ident, "thread_name": names.get(ident, "UNKNOWN"), "frames": frames})
                    emit("frame-samples.jsonl", {**header, "threads": threads, "last_boundary": dict(last_boundary),
                                                  "worker_active_job_id": worker.__dict__.get("active_job_id") if worker else None,
                                                  "counters": dict(counters)})
                except Exception as exc:
                    counters["observation_errors"] += 1
                    emit("audit-events.jsonl", {"event": "sampler_error", "error_type": type(exc).__name__})

    try:
        from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
        from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft, ExperimentManifest, SimulationRunType

        require_no_denial()
        artifacts = run_root / "artifacts"
        repository = SQLiteSimulationJobRepository(run_root / "runtime.sqlite3", artifact_root=artifacts)
        worker = SimulationWorker(worker_id="r396-native-mock", backend="MOCK", repository=repository, artifact_root=artifacts)
        require_no_denial()
        ready = {"state": "READY", "monotonic_ns": time.monotonic_ns(), "pid": os.getpid(),
                 "ready_elapsed_s": (time.monotonic_ns() - child_started_ns) / 1e9}
        save(run_root / "ready.json", ready)
        save(run_root / "state.json", ready)
        replay = {"scope": "DEVELOPMENT_ONLY_DIAGNOSTIC_REPLAY", "source_commit": HEAD,
                  "source_tree_hash": "", "source_tree_hash_reason": "Not computed; actual source pinset independently recorded",
                  "source_pinset_sha256": digest(canonical(audit["source_pins"])),
                  "original_request_sha256": audit["frozen_input"]["request_sha256"],
                  "original_request": audit["frozen_input"]["request"],
                  "original_manifest_historical_only": audit["frozen_input"]["original_manifest"], "runs": []}
        save(DIAG / "input-replay.json", replay)
        sys.setprofile(profile)
        threading.setprofile(profile)
        monitor = threading.Thread(target=sample, name="r396-stack-observer", daemon=True)
        monitor.start()
        for mode in ("PCSC", "ETEAC"):
            require_no_denial()
            phase.update(mode=mode, started_ns=time.monotonic_ns())
            save(run_root / "state.json", {"state": "MODE_STARTED", "mode": mode, "monotonic_ns": phase["started_ns"]})
            base = ExperimentDraft.model_validate(audit["frozen_input"]["request"])
            draft = base.model_copy(update={"run_type": SimulationRunType.SINGLE, "control_modes": [mode],
                                           "scenarios": ["S01_NORMAL_STATIC"], "seeds": [0], "repetitions": 1}, deep=True)
            run_id = "r396-native-" + mode.lower()
            repro = digest(canonical({"draft": draft.model_dump(mode="json"), "source_pinset_sha256": replay["source_pinset_sha256"],
                                      "scope": replay["scope"], "run_id": run_id}))
            manifest = ExperimentManifest(manifest_id="diagnostic-manifest-r396-" + mode.lower(),
                normalized_config=draft.model_dump(mode="json"), source_commit=HEAD, source_tree_hash="", run_count=1,
                reproducibility_hash=repro)
            job = repository.create_job(run_id=run_id, batch_id="r396-native-pair", backend="MOCK",
                scenario_id="S01_NORMAL_STATIC", control_mode=mode, seed=0, manifest_id=manifest.manifest_id,
                reproducibility_hash=repro, draft=draft.model_dump(mode="json"), timeout_seconds=30, max_attempts=2,
                artifact_root=run_id, source_commit=HEAD, source_tree_hash="", manifest=manifest.model_dump(mode="json"),
                provenance={"diagnostic_scope": replay["scope"], "source_tree_hash_reason": replay["source_tree_hash_reason"],
                            "actual_source_pinset_sha256": replay["source_pinset_sha256"], "original_request_sha256": replay["original_request_sha256"]})
            queued = repository.update_status_cas(job.job_id, expected=RuntimeJobStatus.CREATED,
                next_status=RuntimeJobStatus.QUEUED, reason_code="r396_diagnostic_queue", worker_id="", lease_id="")
            assert queued is not None
            replay["runs"].append({"mode": mode, "run_id": run_id, "job_id": job.job_id,
                                   "draft": draft.model_dump(mode="json"), "manifest": manifest.model_dump(mode="json"),
                                   "poll_entry_monotonic_ns": time.monotonic_ns()})
            save(DIAG / "input-replay.json", replay)
            save(run_root / "state.json", {"state": "POLL_ENTERED", "mode": mode, "mode_started_ns": phase["started_ns"],
                                           "monotonic_ns": time.monotonic_ns(), "job_id": job.job_id})
            require_no_denial()
            consumed = worker.poll_once()
            require_no_denial()
            current_job = repository.get_job(job.job_id)
            outcome = {"mode": mode, "consumed": consumed, "status": current_job.status.value,
                       "attempt": current_job.attempt, "job_id": job.job_id, "run_id": run_id,
                       "completed_at": current_job.completed_at.isoformat() if current_job.completed_at else None,
                       "elapsed_s": (time.monotonic_ns() - phase["started_ns"]) / 1e9,
                       "worker_active_job_id_after": worker.active_job_id,
                       "heartbeat_threads_remaining": [t.name for t in threading.enumerate() if t.name == "simulation-lease"]}
            save(DIAG / (mode.lower() + "-native-outcome.json"), outcome)
            if mode == "PCSC" and (not consumed or current_job.status != RuntimeJobStatus.SUCCEEDED or outcome["heartbeat_threads_remaining"]):
                save(run_root / "child-outcome.json", {"state": "PCSC_CONTROL_FAILED", "outcome": outcome})
                return 2
        require_no_denial()
        save(run_root / "child-outcome.json", {"state": "BOTH_POLLS_RETURNED", "counters": dict(counters)})
        return 0
    except Exception as exc:
        save(run_root / "child-outcome.json", {"state": "INFRA_BLOCKED_OR_UNEXPECTED_NATIVE_ERROR", "mode": phase["mode"],
             "error_type": type(exc).__name__, "traceback": traceback.format_exc(), "counters": dict(counters)})
        return 3
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
        stop.set()
        if monitor is not None:
            monitor.join(timeout=1)
        save(DIAG / "observer-final.json", {"counters": dict(counters), "last_boundary": dict(last_boundary),
                                           "observer_thread_alive": monitor.is_alive() if monitor else False})
        for fd in log_fds.values():
            os.close(fd)


def identity(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        values = text[text.rfind(")") + 2:].split()
        return {"pid": pid, "start_ticks": int(values[19]), "ppid": int(values[1]),
                "pgid": int(values[2]), "session": int(values[3]), "state": values[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def members(session):
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            item = identity(int(entry.name))
            if item and item["session"] == session and item["pgid"] == session:
                found.append(item)
    return found


def supervisor(run_root, audit_path):
    audit, before = check_inputs(audit_path)
    plan = json.loads((ROUND / "plan.json").read_text())
    assert str(run_root) == plan["execution"]["argv"][5]
    assert not (DIAG / "execution-start.json").exists(), "No second diagnostic attempt"
    assert not run_root.exists() or all(p.name == "tmp" and p.is_dir() and not any(p.iterdir()) for p in run_root.iterdir())
    assert not run_root.is_symlink() and all(not p.is_symlink() for p in run_root.parents)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "tmp").mkdir(exist_ok=True)
    denial_marker = run_root / "audit-denied.json"
    assert not denial_marker.exists(), "No stale denial marker before the unique launch"
    env = plan["execution"]["env"]
    assert dict(os.environ) == env, "Supervisor requires the exact approved replacement environment"
    review = json.loads((ROUND / "review/script-static-review.json").read_text())
    assert review["ready_for_single_R396_attempt"] is True
    assert review["driver_sha256"] == digest(SCRIPT.read_bytes())
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.prctl(36, 1, 0, 0, 0) == 0, "Subreaper setup required before launch"
    started_ns = time.monotonic_ns()
    save(DIAG / "execution-start.json", {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "monotonic_ns": started_ns, "round_cap_s": 600, "attempt": 1, "driver_sha256": digest(SCRIPT.read_bytes())})
    save(DIAG / "source-before.json", {"pins": before, "driver": pin(SCRIPT), "head": HEAD})
    argv = [sys.executable, "-B", "-s", str(SCRIPT), "--child", "--run-root", str(run_root), "--input-audit", str(audit_path)]
    save(DIAG / "invocation.json", {"argv": plan["execution"]["argv"], "child_argv": argv, "cwd": str(ROOT),
         "env": env, "budgets": plan["execution"]["budgets"], "driver": pin(SCRIPT), "audit_sha256": AUDIT_SHA})
    stdout = (DIAG / "stdout.log").open("xb")
    stderr = (DIAG / "stderr.log").open("xb")
    launch_ns = time.monotonic_ns()
    launch = time.monotonic()
    process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
    owner = identity(process.pid)
    assert owner and owner["pgid"] == process.pid and owner["session"] == process.pid
    reason = "NATURAL_EXIT"
    last_state = None
    supervisor_error = None
    print(json.dumps({"state": "CHILD_LAUNCHED", "pid": process.pid, "attempt": 1}), flush=True)
    try:
        while process.poll() is None:
            if denial_marker.exists():
                reason = "AUDIT_DENIAL"
                break
            elapsed = time.monotonic() - launch
            status_path = run_root / "state.json"
            if status_path.exists():
                last_state = json.loads(status_path.read_text())
            ready_path = run_root / "ready.json"
            if ready_path.exists():
                ready = json.loads(ready_path.read_text())
                if (ready["monotonic_ns"] - launch_ns) / 1e9 > 10:
                    reason = "READY_CAP"
                    break
            elif elapsed >= 10:
                reason = "READY_CAP"
                break
            if last_state and last_state.get("mode") in {"PCSC", "ETEAC"}:
                mode_start = last_state.get("mode_started_ns", last_state["monotonic_ns"])
                mode_elapsed = (time.monotonic_ns() - mode_start) / 1e9
                cap = 30 if last_state["mode"] == "PCSC" else 75
                if mode_elapsed >= cap:
                    reason = last_state["mode"] + "_DIAGNOSTIC_CAP"
                    break
            if elapsed >= 125:
                reason = "CHILD_TOTAL_CAP"
                break
            time.sleep(0.02)
    except BaseException as exc:
        reason = "SUPERVISOR_INTERRUPTED_OR_ERROR"
        supervisor_error = {"type": type(exc).__name__, "traceback": traceback.format_exc()}
    cleanup_started = time.monotonic()
    signals = []
    owned_before = members(process.pid)
    if process.poll() is None:
        fresh = identity(process.pid)
        assert fresh and fresh["start_ticks"] == owner["start_ticks"] and fresh["pgid"] == owner["pgid"]
        os.killpg(process.pid, signal.SIGTERM)
        signals.append({"signal": "SIGTERM", "pgid": process.pid, "verified_members": owned_before})
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    remaining = [p for p in members(process.pid) if p["state"] != "Z"]
    for item in remaining:
        current = identity(item["pid"])
        if current and current["start_ticks"] == item["start_ticks"] and current["session"] == process.pid:
            os.kill(item["pid"], signal.SIGKILL)
            signals.append({"signal": "SIGKILL", "identity": current})
    process.wait(timeout=max(0.1, 10 - (time.monotonic() - cleanup_started)))
    adopted = []
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if not pid:
            break
        adopted.append({"pid": pid, "status": status})
    stdout.close()
    stderr.close()
    leftover = members(process.pid)
    cleanup = {"owner": owner, "reason": reason, "signals": signals, "returncode": process.returncode,
               "owned_before": owned_before, "owned_remaining": leftover, "adopted_reaped": adopted,
               "reaped": process.poll() is not None, "elapsed_s": time.monotonic() - cleanup_started}
    save(DIAG / "cleanup.json", cleanup)
    marker_present = denial_marker.exists()
    audit_denied = marker_present or process.returncode == 78 or reason == "AUDIT_DENIAL"
    reporting_errors = []
    artifact_reads = {}

    def read_records(path, *, jsonl=False, optional=False, fields=None):
        name = str(path.relative_to(DIAG))
        try:
            raw = path.read_bytes()
        except OSError as exc:
            absent = isinstance(exc, FileNotFoundError) and optional
            artifact_reads[name] = {"state": "ABSENT" if absent else "READ_ERROR"}
            if not absent:
                reporting_errors.append({"file": name, "kind": type(exc).__name__})
            return [] if jsonl else None
        metadata = {"bytes": len(raw), "sha256": digest(raw)}
        artifact_reads[name] = {"state": "READ", **metadata}
        valid = []
        for number, data in enumerate(raw.splitlines() if jsonl else [raw], 1):
            try:
                row = json.loads(data.decode("utf-8"))
                if type(row) is not dict:
                    raise ValueError("record_not_object")
                if fields and any(type(row.get(key)) is not expected for key, expected in fields.items()):
                    raise ValueError("missing_or_wrong_consumed_field")
                if jsonl and path.name == "audit-events.jsonl" and "allowed" in row and type(row["allowed"]) is not bool:
                    raise ValueError("invalid_allowed_field")
                valid.append(row)
            except (UnicodeError, ValueError) as exc:
                reporting_errors.append({"file": name, "line": number if jsonl else None,
                                         "kind": type(exc).__name__, "bytes": len(data), "sha256": digest(data)})
                artifact_reads[name]["state"] = "PARTIAL_OR_INVALID"
        return valid if jsonl else (valid[0] if valid else None)

    _, after = check_inputs(audit_path)
    save(DIAG / "source-after.json", {"pins": after, "driver": pin(SCRIPT), "head": HEAD, "matches_before": after == before})
    db_pins = [pin(path) for path in sorted(run_root.rglob("*")) if path.is_file()
               and (path.suffix in {".db", ".sqlite", ".sqlite3"} or path.name.endswith(("-wal", "-shm")))]
    save(DIAG / "database-files-local-only.json", {"pins": db_pins, "quiescent_after_owned_exit": not leftover,
                                                  "postmortem_sqlite_connections": 0, "not_complete_raw_delivery": True})
    audit_rows = read_records(DIAG / "audit-events.jsonl", jsonl=True, fields={"event": str})
    blocked_operations = [row for row in audit_rows if row.get("allowed") is False]
    marker_record = read_records(denial_marker, optional=not marker_present)
    marker_errors = [row for row in reporting_errors if row["file"] == "run/audit-denied.json"]
    audit_denied = audit_denied or bool(blocked_operations)
    if audit_denied:
        reason = "AUDIT_DENIAL"
    boundary_rows = read_records(DIAG / "boundaries.jsonl", jsonl=True,
                                fields={"event": str, "function": str, "mode": str, "thread_id": int, "sequence": int})
    observed_polls = [{"mode": row["mode"], "thread_id": row["thread_id"], "sequence": row["sequence"]}
                      for row in boundary_rows if row["event"] == "call" and row["function"] == "poll_once"]
    observation_errors = [row for row in audit_rows if row.get("event") in {"profile_error", "sampler_error"}]
    child_outcome = read_records(run_root / "child-outcome.json", optional=True)
    ready_record = read_records(run_root / "ready.json", optional=True)
    result = {"state": "INFRA_BLOCKED_AUDIT_DENIAL" if audit_denied else
                       ("INCOMPLETE_DIAGNOSTIC_OBSERVABILITY" if reporting_errors else
                        ("BOUNDED_DIAGNOSTIC_TERMINATED" if signals else "BOUNDED_DIAGNOSTIC_RETURNED")),
              "reason": reason, "last_child_state": last_state, "child_returncode": process.returncode,
              "elapsed_s": (time.monotonic_ns() - started_ns) / 1e9, "source_drift": before != after,
              "cleanup_ok": not leftover and cleanup["reaped"] and cleanup["elapsed_s"] <= 10,
              "behavior_attempts": 1, "pcsc_poll_quota": 1, "eteac_poll_quota": 1,
              "observed_poll_entries": observed_polls,
              "observed_poll_entries_complete": not reporting_errors,
              "reporting_errors": reporting_errors, "artifact_reads": artifact_reads,
              "audit_denial": {"detected": audit_denied, "marker_present": marker_present,
                              "dedicated_exit_78": process.returncode == 78, "marker": marker_record,
                              "marker_parse_error": marker_errors or None,
                              "operation_executed": False if audit_denied else None,
                              "native_cleanup_skipped_on_fail_stop": audit_denied},
              "ready": ready_record,
              "blocked_operations": blocked_operations, "observation_errors": observation_errors, "child_outcome": child_outcome,
              "supervisor_error": supervisor_error,
              "product_PASS": False, "browser_retest": False, "formal_accepted": False,
              "historical_stack_proven": False, "causal_verdict": "BLOCKED_BY_DIAGNOSTIC_POLICY" if audit_denied
                      else ("UNKNOWN_OBSERVABILITY_INCOMPLETE" if reporting_errors else "PENDING_OFFLINE_EVIDENCE_REVIEW")}
    save(DIAG / "result.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if (not audit_denied and not reporting_errors and result["cleanup_ok"] and result["elapsed_s"] <= 140
                 and supervisor_error is None) else 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--input-audit", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(child(arguments.run_root, arguments.input_audit) if arguments.child
                     else supervisor(arguments.run_root, arguments.input_audit))
