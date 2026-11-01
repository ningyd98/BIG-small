"""Bound one approved argv, retain source/exit evidence, clean only owned children."""
from datetime import UTC, datetime
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def snapshot(paths):
    rows = []
    for name in paths:
        path = Path(name)
        raw = path.read_bytes() if path.is_file() else None
        rows.append({"path": name, "bytes": len(raw) if raw is not None else None,
                     "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None})
    return rows


def processes():
    rows = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            rows[int(path.name)] = {"pid": int(path.name), "state": fields[0],
                "ppid": int(fields[1]), "pgid": int(fields[2]), "sid": int(fields[3]),
                "starttime_ticks": fields[19]}
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return rows


def run(spec_path):
    spec = json.loads(spec_path.read_text())
    directory = Path(spec["directory"])
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "invocation.json").exists():
        raise RuntimeError("Refusing to overwrite an existing invocation")
    if time.time() + spec["timeout_s"] + 15 > spec["round_end_epoch_s"]:
        save(directory / "result.json", {"state": "NOT_RUN_BUDGET", "launched": False})
        return
    before = snapshot(spec["source_paths"])
    save(directory / "source-before.json", before)
    save(directory / "invocation.json", {**spec, "started_utc": datetime.now(UTC).isoformat(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest()})
    ports = []
    for port in spec.get("ports", []):
        try:
            with socket.socket() as connection:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                connection.bind(("127.0.0.1", port))
            ports.append({"port": port, "available": True})
        except OSError as error:
            ports.append({"port": port, "available": False,
                          "exception": type(error).__name__, "message": str(error)})
    save(directory / "ports-before.json", ports)
    if any(not row["available"] for row in ports):
        save(directory / "result.json", {"state": "BLOCKED_PRECONDITION", "launched": False,
              "ports": ports, "reason": "No child/test behavior launched; no listener reused"})
        return
    # Adopt detached webserver/browser descendants so they remain attributable and reapable.
    subreaper = ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)
    if subreaper != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER")
    owned, errors, signals, cancelled = {}, [], [], []
    process = None
    cleanup_active = False
    state = "FINISHED"
    began = time.monotonic()

    def refresh():
        current = processes()
        parents = {os.getpid()} | {pid for pid, row in owned.items()
                    if pid in current and current[pid]["starttime_ticks"] == row["starttime_ticks"]}
        changed = True
        while changed:
            changed = False
            for pid, row in current.items():
                if row["ppid"] in parents and pid not in parents:
                    parents.add(pid)
                    owned.setdefault(pid, row)
                    changed = True
        return [row for pid, row in current.items() if pid in owned
                and row["starttime_ticks"] == owned[pid]["starttime_ticks"] and row["state"] != "Z"]

    def deliver(sig):
        for row in refresh():
            try:
                os.kill(row["pid"], sig)
                signals.append({"pid": row["pid"], "signal": signal.Signals(sig).name})
            except ProcessLookupError:
                pass

    def interrupted(signum, frame):
        cancelled.append(signal.Signals(signum).name)
        if not cleanup_active:
            raise InterruptedError(signal.Signals(signum).name)

    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        try:
            process = subprocess.Popen(spec["argv"], cwd=spec["cwd"], env=spec["env"],
                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, start_new_session=True)
            while process.poll() is None:
                refresh()
                if time.monotonic() - began >= spec["timeout_s"]:
                    state = "TIMEOUT"
                    break
                time.sleep(0.1)
        except BaseException as error:
            state = "INTERRUPTED" if process is not None else "INFRASTRUCTURE_ERROR"
            errors.append({"type": type(error).__name__, "message": str(error),
                           "traceback": traceback.format_exc()})
        finally:
            cleanup_active = True
            cleanup_started = time.monotonic()
            deliver(signal.SIGTERM)
            while refresh() and time.monotonic() - cleanup_started < 5:
                if process is not None:
                    process.poll()
                time.sleep(0.05)
            if refresh():
                deliver(signal.SIGKILL)
            if process is not None:
                try:
                    process.wait(timeout=max(0.01, 15 - (time.monotonic() - cleanup_started)))
                except subprocess.TimeoutExpired:
                    errors.append({"reason": "driver_child_not_reaped"})
            while refresh() and time.monotonic() - cleanup_started < 15:
                deliver(signal.SIGKILL)
                time.sleep(0.05)
            reaped_adopted = []
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if not pid:
                        break
                    reaped_adopted.append({"pid": pid, "status": status})
                except ChildProcessError:
                    break
            remaining = refresh()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    save(directory / "owned-process-identities.json", list(owned.values()))
    after = snapshot(spec["source_paths"])
    save(directory / "source-after.json", after)
    ports_after = []
    for port in spec.get("ports", []):
        try:
            with socket.socket() as connection:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                connection.bind(("127.0.0.1", port))
            ports_after.append({"port": port, "available": True})
        except OSError as error:
            ports_after.append({"port": port, "available": False, "message": str(error)})
    result = {"state": state, "launched": process is not None,
        "returncode": process.returncode if process is not None else None,
        "elapsed_s": time.monotonic() - began, "ended_utc": datetime.now(UTC).isoformat(),
        "source_drift": [] if before == after else ["SOURCE_SNAPSHOT_CHANGED"],
        "signals": signals, "cancellations": cancelled, "errors": errors,
        "remaining_live": remaining, "reaped": bool(process is not None and process.returncode is not None),
        "adopted_children_reaped": reaped_adopted, "ports_after": ports_after,
        "permission_profile": spec["permission_profile"]}
    save(directory / "result.json", result)
    print(json.dumps({key: value for key, value in result.items() if key != "adopted_children_reaped"}), flush=True)
    if errors or remaining or before != after or not result["reaped"] or any(not p["available"] for p in ports_after):
        raise RuntimeError("Infrastructure/cleanup/source integrity failed; no automatic retry")


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
