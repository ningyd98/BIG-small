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
    root = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
    here = Path(__file__).resolve().parent
    def check(row):
        path = root / row["path"]
        raw = path.read_bytes()
        assert not path.is_symlink() and len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],row["path"]
    assert hashlib.sha256((here / "plan.json").read_bytes()).hexdigest() == "888aa67adc9aa0054c7489951d7a3004a14f597b41652c6dc588027803467749"
    release_path = here.parent / "round409-writer-plain-run-terminal-receipts-20261103/preflight/r408-gate-release.json"
    release = json.loads(release_path.read_text())
    assert release["accepted"] and release["target_plan_sha256"] == "888aa67adc9aa0054c7489951d7a3004a14f597b41652c6dc588027803467749"
    for row in release["terminal_inputs"]:
        check(row)
    audit = json.loads((here / "input-audit.json").read_text())
    assert hashlib.sha256((here / "input-audit.json").read_bytes()).hexdigest() == "176f44aa66ee75cec60bec7adedb12f7bb2c96f48e044d24aa4c5cc4bd035e74"
    index = json.loads((here / "current-source-index.json").read_text())
    for row in audit["inputs"] + index["inputs"]:
        check(row)
    static = json.loads((here / "preflight/static.json").read_text())
    assert static["accepted"]
    for row in static["derived_pins"]:
        check(row)
    prerequisite = json.loads((here / "preflight/local-prerequisite.json").read_text())
    assert prerequisite["accepted"]
    provenance = json.loads((here / "preflight/actual-source-provenance.json").read_text())
    assert provenance["source_tree_hash"] and provenance["source_commit"] == "ac6351b66a6dd05fb67aadd59935ce5726748709"
    if spec["stage_id"] == "browser_research_retest":
        previous = json.loads((here / "implementation/browser_default_retest/result.json").read_text())
        assert previous["reaped"] and not previous["source_drift"] and not previous["errors"] and not previous["remaining_live"]
        assert all(p["available"] for p in previous["ports_after"])
    directory = Path(spec["directory"])
    allowed = {row["path"] for row in static["prepared_assets"]}
    if directory.exists():
        assert all(not p.is_symlink() and (not p.is_file() or str(p.relative_to(root)) in allowed) for p in directory.rglob("*")), "Only declared preparation files may exist"
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "invocation.json").exists():
        raise RuntimeError("Refusing to overwrite an existing invocation")
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
                    process.wait(timeout=max(0.01, spec["cleanup_timeout_s"] - (time.monotonic() - cleanup_started)))
                except subprocess.TimeoutExpired:
                    errors.append({"reason": "driver_child_not_reaped"})
            while refresh() and time.monotonic() - cleanup_started < spec["cleanup_timeout_s"]:
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
