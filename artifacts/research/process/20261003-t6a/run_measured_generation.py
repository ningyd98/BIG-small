"""Acceptance harness: one CLI renderer, independently sampled per-process GPU memory."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.writer import load_manifest, save_manifest

label, config, destination = sys.argv[1:]
evidence = Path(__file__).resolve().parent
command = [sys.executable, "scripts/generate_rgbd_dataset.py", "--config", config,
           "--output", destination]
started = time.monotonic()
samples = []
errors = []
with (evidence / f"{label}-generate.log").open("w") as output:
    process = subprocess.Popen(command, env={**os.environ, "MUJOCO_GL": "egl"},
                               stdout=output, stderr=subprocess.STDOUT)
    print(f"{label}: CLI PID {process.pid}", flush=True)
    next_report = 0.
    while process.poll() is None:
        elapsed = time.monotonic() - started
        try:
            measured = subprocess.run(["nvidia-smi", "pmon", "-c", "1", "-s", "m"],
                                      capture_output=True, text=True, timeout=5, check=True)
            for line in measured.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 6 and parts[0].isdigit() and parts[1] == str(process.pid):
                    if parts[3].isdigit():
                        samples.append({"elapsed_s": elapsed, "gpu": int(parts[0]),
                                        "pid": process.pid, "type": parts[2],
                                        "memory_bytes": int(parts[3]) * 1024 * 1024})
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
        if elapsed >= next_report:
            manifest_path = Path(destination) / "manifest.json"
            current = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            print(f"{label}: {elapsed:.1f}s, groups={current.get('completed_groups', 0)}, "
                  f"status={current.get('status', 'STARTING')}", flush=True)
            next_report = elapsed + 10
        time.sleep(.5)
code = process.wait()
measurement = {"command": command, "environment": {"MUJOCO_GL": "egl"},
               "exit_code": code, "wall_time_s": time.monotonic() - started,
               "sampler": "nvidia-smi pmon -c 1 -s m", "pid": process.pid,
               "interval_s": .5, "measurement": "observed sampled per-process framebuffer peak",
               "limitation": "sampling plus command latency can miss transient peaks",
               "peak_bytes": max((s["memory_bytes"] for s in samples), default=None),
               "samples": samples, "errors": errors}
(evidence / f"{label}-resources.json").write_text(json.dumps(measurement, indent=2) + "\n")
manifest = load_manifest(Path(destination))
if manifest is not None:
    manifest.resources["acceptance_cli_wall_time_s"] = measurement["wall_time_s"]
    manifest.resources["gpu_peak_memory_bytes"] = measurement["peak_bytes"] or "NOT_MEASURED"
    manifest.resources["gpu_peak_memory_reason"] = measurement["measurement"]
    manifest.resources["gpu_memory_sampling_interval_s"] = .5
    manifest.resources["gpu_memory_sampling_limitation"] = measurement["limitation"]
    manifest.resources["gpu_measurement_artifact"] = str(evidence / f"{label}-resources.json")
    save_manifest(Path(destination), manifest)
print(f"{label}: exit={code}, elapsed={measurement['wall_time_s']:.2f}s, "
      f"GPU observed peak={measurement['peak_bytes']}", flush=True)
raise SystemExit(code)
