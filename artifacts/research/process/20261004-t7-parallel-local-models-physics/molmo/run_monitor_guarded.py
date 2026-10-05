"""Root-authorized empty-window retry monitor; abort only isolated owned group.

Same 0.5-second driver telemetry as the original monitor. A newly arrived
foreign compute client aborts this attempt; its PID is never signalled. All raw
native journals and incomplete allocations remain in the exclusive output.
"""
import argparse
import json
import os
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from run_monitored import query


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.telemetry.exists() or args.log.exists():
        raise FileExistsError("exclusive monitor output exists")
    initial = query("pid,process_name,used_memory", "compute-apps")
    if initial:
        raise RuntimeError("GPU not empty before owned launch: " + repr(initial))
    started = time.perf_counter()
    samples, foreign, errors, abort_actions = [], [], [], []
    stop = threading.Event()
    with args.log.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

        def monitor():
            while not stop.is_set():
                try:
                    apps = query("pid,process_name,used_memory", "compute-apps")
                    elapsed = time.perf_counter() - started
                    sample = {"elapsed_s": elapsed,
                              "gpu": query("memory.used,memory.total,utilization.gpu"),
                              "compute_apps": apps}
                    samples.append(sample)
                    outsiders = [a for a in apps if int(a[0]) != process.pid]
                    for app in outsiders:
                        foreign.append({"elapsed_s": elapsed, "pid": int(app[0]),
                                        "name": app[1], "memory_MiB": app[2]})
                    if outsiders and not abort_actions:
                        abort_actions.append({"elapsed_s": elapsed,
                                              "signal": "SIGTERM",
                                              "target": "isolated owned process group only",
                                              "owned_pgid": process.pid,
                                              "foreign_PIDs_signalled": []})
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            abort_actions.append({"elapsed_s": time.perf_counter() - started,
                                                  "signal": "SIGKILL",
                                                  "target": "isolated owned process group only",
                                                  "owned_pgid": process.pid,
                                                  "foreign_PIDs_signalled": []})
                            os.killpg(process.pid, signal.SIGKILL)
                        break
                except Exception as exc:
                    errors.append({"elapsed_s": time.perf_counter() - started, "error": str(exc)})
                stop.wait(.5)

        worker = threading.Thread(target=monitor)
        worker.start()
        exit_code = process.wait()
        stop.set()
        worker.join()
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(), "command": command,
        "owned_pid": process.pid, "owned_pgid": process.pid, "exit_code": exit_code,
        "startup_and_full_screen_wall_s": time.perf_counter() - started,
        "driver_wide_peak_memory_MiB": max((float(s["gpu"][0][0]) for s in samples), default=None),
        "driver_memory_scope": "whole GPU including context/display/all clients sampled every0.5s",
        "foreign_compute_clients": foreign, "foreign_abort_actions": abort_actions,
        "aborted_for_contention": bool(abort_actions), "monitor_errors": errors,
        "initial_compute_apps": initial,
        "final_compute_apps": query("pid,process_name,used_memory", "compute-apps"),
        "samples": samples,
    }
    with args.telemetry.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}), flush=True)
    raise SystemExit(exit_code if not abort_actions else 75)


if __name__ == "__main__":
    main()
