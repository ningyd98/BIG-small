"""Bounded read-only empty-window checks and root-authorized unchanged retry.

No unowned process/model is stopped. Any interrupted contended run is retained
and restarted from all20 cases. A genuine compatibility/resource error is not
silently retried or treated as model quality.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = HERE.parents[4]
LEASE = "SERIAL_ROOT_MOLMOPOINT_EMPTY_WINDOW_RETRY_20261004_0642"
STEM = "point-development-full20-toolchain-fixed-v2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exclusive(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def actual_window():
    compute = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    with build_opener(ProxyHandler({})).open("http://127.0.0.1:11434/api/ps", timeout=10) as response:
        resident = json.load(response)
    processes = subprocess.run(["ps", "-eo", "pid,ppid,args"], capture_output=True, text=True, check=True).stdout
    renderers = [line for line in processes.splitlines()
                 if "/physics/workspace-" in line
                 and any(word in line for word in ("pytest", "run_validation_pipeline", "capture"))
                 and "/bin/bash -c " not in line]
    return {"checked_at": datetime.now(UTC).isoformat(), "compute_apps": compute,
            "GPU": gpu, "Ollama_resident": resident,
            "owned_physics_renderer_processes": renderers,
            "root_renderer_release_confirmation": "conditional lease root message",
            "empty": not compute.strip() and not resident.get("models") and not renderers}


def main():
    evidence = HERE / "point-empty-window-retry-evidence"
    evidence.mkdir(exist_ok=False)
    exclusive(evidence / "watcher.json", {"pid": os.getpid(), "root_conditional_lease": LEASE,
                                          "watcher_sha256": digest(Path(__file__)),
                                          "poll_interval_s": 30, "unowned_PIDs_signalled": []})
    amendment_path = HERE / "point-toolchain-environment-prospective-amendment.json"
    amendment = json.loads(amendment_path.read_text())
    expected_hashes = amendment["source_and_model_metadata_hashes"]
    check_number, attempt_number = 0, 0
    while True:
        check_number += 1
        try:
            window = actual_window()
        except Exception as exc:
            exclusive(evidence / f"check-{check_number:04d}.json",
                      {"checked_at": datetime.now(UTC).isoformat(), "error": str(exc), "empty": False})
            time.sleep(30)
            continue
        exclusive(evidence / f"check-{check_number:04d}.json", window)
        print(json.dumps({"check": check_number, "checked_at": window["checked_at"],
                          "empty": window["empty"], "compute_apps": window["compute_apps"],
                          "resident_model_count": len(window["Ollama_resident"].get("models", []))}), flush=True)
        if not window["empty"]:
            time.sleep(30)
            continue
        for name, expected in expected_hashes.items():
            if digest(HERE / name) != expected:
                raise ValueError("frozen source changed before retry: " + name)
        headers = json.loads((HERE / "point-toolchain-header-provenance.json").read_text())
        for name, record in headers["files"].items():
            if digest(HERE / "toolchain/include" / name) != record["sha256"]:
                raise ValueError("header changed before retry: " + name)
        attempt_number += 1
        stem = STEM if attempt_number == 1 else STEM + f"-attempt{attempt_number}"
        out = HERE / stem
        precision = HERE / ("point-retry-loaded-precision.json" if attempt_number == 1
                            else f"point-retry-loaded-precision-attempt{attempt_number}.json")
        telemetry, log = HERE / (stem + "-gpu-telemetry.json"), HERE / (stem + ".log")
        command = [sys.executable, str(HERE / "run_monitor_guarded.py"),
                   "--telemetry", str(telemetry), "--log", str(log), "--", sys.executable,
                   str(HERE / "observe_point_precision.py"), "--precision-observation", str(precision),
                   "--", "--model", "MolmoPoint-8B", "--mode", "screen", "--bank",
                   str(BASE / "shared/scene-bank"), "--full-contract", "--gpu-lease", LEASE,
                   "--out", str(out)]
        activation = {"attempt": attempt_number, "root_conditional_lease": LEASE,
                      "fresh_actual_empty_window": window,
                      "source_and_model_metadata_hashes": expected_hashes,
                      "toolchain_amendment_sha256": digest(amendment_path),
                      "header_provenance_sha256": digest(HERE / "point-toolchain-header-provenance.json"),
                      "guarded_monitor_sha256": digest(HERE / "run_monitor_guarded.py"),
                      "watcher_sha256": digest(Path(__file__)),
                      "bank_manifest_sha256": digest(BASE / "shared/scene-bank/bank-manifest.json"),
                      "process_env": amendment["process_env"], "command": command,
                      "all20_same_allocation": True, "no_method_retuning": True}
        exclusive(evidence / f"activation-{attempt_number:02d}.json", activation)
        print(json.dumps({"activated_attempt": attempt_number, "output": str(out)}), flush=True)
        with (evidence / f"monitor-stdout-{attempt_number:02d}.log").open("x") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, **amendment["process_env"]}, cwd=ROOT)
        report = json.loads(telemetry.read_text()) if telemetry.exists() else None
        contended = report is not None and report.get("aborted_for_contention")
        if report is None and not out.exists():
            actual = actual_window()
            contended = not actual["empty"]
        completed = {"at": datetime.now(UTC).isoformat(), "attempt": attempt_number,
                     "exit_code": result.returncode, "output": str(out),
                     "precision_observation": str(precision), "telemetry": str(telemetry),
                     "contended": bool(contended), "full20_quality_measured": result.returncode == 0}
        exclusive(evidence / f"outcome-{attempt_number:02d}.json", completed)
        print(json.dumps(completed), flush=True)
        if contended:
            time.sleep(30)
            continue
        exclusive(evidence / "final-outcome.json", completed)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
