"""Replay only immutable scoped sources and fixtures, with environment-only venv link."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
manifest = json.loads((HERE / "source-hashes.json").read_bytes())
overlay = Path(tempfile.mkdtemp(prefix="risk-supervision-514-frozen-"))
for name, digest in manifest.items():
    source = HERE / "source" / name
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, name
    target = overlay / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
(overlay / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
python = str(overlay / ".venv/bin/python")
owned = ["src/cloud_edge_robot_arm/research/risk_supervision.py", "tests/test_research_risk_supervision.py"]
commands = {
    "frozen-cpu": [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", f"pythonpath={overlay}/src", f"--confcutdir={overlay}", "tests/test_research_risk_supervision.py", "tests/test_research_risk_sources.py", "tests/test_research_admission.py", "tests/test_pose_marker_evidence.py", "tests/test_rgbd_risk_calibration.py", "-k", "not compiled"],
    "frozen-ruff": [str(ROOT / ".venv/bin/ruff"), "check", *owned],
    "frozen-format": [str(ROOT / ".venv/bin/ruff"), "format", "--check", *owned],
    "frozen-cold-mypy": [python, "-m", "mypy", "--no-incremental", "--follow-imports=silent", "src/cloud_edge_robot_arm/research/risk_supervision.py"],
}
env = dict(os.environ)
env["PYTHONPATH"] = str(overlay / "src")
results = {}
for label, command in commands.items():
    with (HERE / f"{label}.log").open("w") as handle:
        result = subprocess.run(command, cwd=overlay, env=env, stdout=handle, stderr=subprocess.STDOUT)
    results[label] = result.returncode
    print(label, result.returncode, flush=True)
post = {}
for name, digest in manifest.items():
    post[name] = {"archive": hashlib.sha256((HERE / "source" / name).read_bytes()).hexdigest() == digest,
                  "overlay": hashlib.sha256((overlay / name).read_bytes()).hexdigest() == digest,
                  "live": hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest}
(HERE / "post-frozen-source-check.json").write_text(json.dumps(post, sort_keys=True, indent=2) + "\n")
(HERE / "frozen-overlay-setup.json").write_text(json.dumps({"overlay": str(overlay), "cwd": str(overlay), "commands": commands, "results": results, "source_count": len(manifest), "source_manifest_sha256": hashlib.sha256((HERE / "source-hashes.json").read_bytes()).hexdigest(), "interpreter_link": "environment only; no live source fallback", "compiled_dynamics_test_excluded": True}, indent=2, sort_keys=True) + "\n")
assert all(value == 0 for value in results.values()), results
assert all(all(value.values()) for value in post.values())
