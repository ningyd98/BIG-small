import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
report_dir = Path(sys.argv[2]).absolute()
report_dir.mkdir(parents=True, exist_ok=False)
output = report_dir / "episode"
gate = report_dir / "start"
mode = sys.argv[3]
child_code = """import sys,time
from pathlib import Path
from cloud_edge_robot_arm.harness.cli import main
ready,gate,*args=sys.argv[1:]
Path(ready).touch()
while not Path(gate).is_file():
    time.sleep(0.001)
raise SystemExit(main(args))
"""
env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": ""}
if mode == "source":
    env["PYTHONPATH"] = str(root / "src")
entry = Path(sys.executable)
launches = []
prototype = json.loads((root / "src/cloud_edge_robot_arm/harness/s01-component.json").read_bytes())
for seed in (42001, 42002, 42003, 42004):
    config = report_dir / f"config-{seed}.json"
    config.write_text(json.dumps(prototype | {"seed": seed}, indent=2) + "\n")
    ready = report_dir / f"ready-{seed}"
    cmd = [str(entry), "-B", "-c", child_code, str(ready), str(gate),
           "prepare", "--source-checkout", str(root), "--output", str(output), "--config",
           str(config)]
    launched = subprocess.Popen(cmd, cwd=report_dir, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    launches.append((seed, ready, cmd, launched))
deadline = time.monotonic() + 10
while not all(ready.is_file() for _, ready, _, _ in launches) and time.monotonic() < deadline:
    time.sleep(0.002)
gate.touch()
rows = []
for seed, _, cmd, launched in launches:
    stdout, stderr = launched.communicate(timeout=20)
    (report_dir / f"stdout-{seed}.json").write_text(stdout)
    (report_dir / f"stderr-{seed}.txt").write_text(stderr)
    try:
        body = json.loads(stdout)
    except ValueError:
        body = {}
    rows.append({"seed": seed, "command": cmd, "exit_code": launched.returncode,
                 "status": body.get("status"), "reported_episode": body.get("episode"),
                 "reported_evidence": body.get("evidence")})
assignment = json.loads((output / "scene-assignment.json").read_bytes())
manifest = output / "evidence-manifest.json"
matches = [row for row in rows if row["exit_code"] == 0 and row["status"] == "PREPARED"]
losers = [row for row in rows if row not in matches]
summary = {
    "mode": mode, "scope": "CPU_OFFLINE_PREPARE_ONLY",
    "children": rows, "winning_assignment_seed": assignment["seed"],
    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    "episode_directories": sorted(path.name for path in report_dir.iterdir() if path.is_dir()),
    "sidecar_names": sorted(path.name for path in report_dir.glob("*.lock")),
    "only_owner_reported": (
        len(matches) == 1 and matches[0]["seed"] == assignment["seed"]
        and all(row["exit_code"] == 2 and row["status"] == "NOT_STARTED"
                and row["reported_episode"] is None and row["reported_evidence"] is None
                for row in losers)
    ),
}
(report_dir / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "children"}, indent=2))
print([(row["seed"], row["exit_code"], row["status"], bool(row["reported_episode"])) for row in rows])
assert summary["only_owner_reported"], "a losing invocation reported another invocation's episode"
assert summary["episode_directories"] == ["episode"]
