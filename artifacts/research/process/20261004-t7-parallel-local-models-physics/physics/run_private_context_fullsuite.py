"""在已恢复且冻结的副本上运行完整回归，保留进程、上下文和完整日志。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from restore_private_git_context import ROOT, PHYSICS, ENV, digest, verify_source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("baseline", "h3"))
    role = parser.parse_args().role
    workspace = PHYSICS / f"workspace-{role}"
    output = PHYSICS / f"full-suite-private-context-{role}-result.json"
    started_file = PHYSICS / f"full-suite-private-context-{role}-started.json"
    log = PHYSICS / "logs" / f"full-pytest-{role}-private-context.log"
    runtime = PHYSICS / "regression-runtime"
    runtime.mkdir(exist_ok=True)
    database = runtime / f"{role}-model-control.db"
    if output.exists() or started_file.exists() or log.exists() or database.exists():
        raise FileExistsError("Exclusive regression output already exists")
    before = verify_source(workspace, role)
    removed_caches = []
    for directory in workspace.rglob("__pycache__"):
        if directory.is_dir() and not directory.is_symlink():
            removed_caches.append(str(directory.relative_to(workspace)))
            shutil.rmtree(directory)
    env = {**ENV, "MUJOCO_GL": "egl", "PYTHONPATH": str(workspace / "src"), "MODEL_CONTROL_DB": str(database), "PYTHONDONTWRITEBYTECODE": "1"}
    command = [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-vv", "--tb=short", "--durations=25"]
    record = {"status": "RUNNING_PRIVATE_GIT_CONTEXT", "role": role, "started_at": datetime.now(timezone.utc).isoformat(), "wrapper_pid": os.getpid(), "workspace": str(workspace), "command": command, "environment_overrides": {name: env[name] for name in ("MUJOCO_GL", "PYTHONPATH", "MODEL_CONTROL_DB", "PYTHONDONTWRITEBYTECODE", "GIT_OPTIONAL_LOCKS")}, "private_git_config": subprocess.check_output(["git", "config", "--local", "--list"], cwd=workspace, env=env, text=True), "source_before": before, "context_verification_sha256": digest(PHYSICS / "private-git-context-final-verification.json"), "paired_context_comparison_sha256": digest(PHYSICS / "private-git-context-paired-comparison-final.json"), "patch_sha256": digest(PHYSICS / "final-h3-review.patch"), "removed_generated_pycache_only": removed_caches, "old_incomplete_logs_counted": False, "log": str(log)}
    start = time.monotonic()
    with log.open("x") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        process = subprocess.Popen(command, cwd=workspace, env=env, stdout=stream, stderr=subprocess.STDOUT)
        record["pytest_pid"] = process.pid
        started_file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        exit_code = process.wait()
    record.update({"status": "COMPLETED", "exit_code": exit_code, "elapsed_s": time.monotonic() - start, "completed_at": datetime.now(timezone.utc).isoformat(), "source_after": verify_source(workspace, role), "log_sha256": digest(log), "patch_sha256_after": digest(PHYSICS / "final-h3-review.patch")})
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: record[key] for key in ("role", "status", "exit_code", "elapsed_s", "log")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
