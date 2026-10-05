"""按登记节点与正确环境执行相关回归；日志和状态分母全部保留。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import time

from restore_private_git_context import ROOT, PHYSICS, digest, verify_source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("baseline", "h3"))
    parser.add_argument("--root-gpu-release", required=True)
    args = parser.parse_args()
    role = args.role
    registration = PHYSICS / "relevant-regression-registration.json"
    prereg = json.loads(registration.read_text())
    selected = prereg["roles"][role]
    workspace = PHYSICS / f"workspace-{role}"
    log = PHYSICS / "logs" / f"relevant-private-context-{role}.log"
    started = PHYSICS / f"relevant-private-context-{role}-started.json"
    output = PHYSICS / f"relevant-private-context-{role}-result.json"
    database = selected["environment_overrides"]["MODEL_CONTROL_DB"]
    if log.exists() or started.exists() or output.exists() or os.path.exists(database):
        raise FileExistsError("Exclusive relevant regression output already exists")
    env = {**os.environ, **selected["environment_overrides"]}
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    record = {"role": role, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "wrapper_pid": os.getpid(), "root_gpu_release": args.root_gpu_release, "registration_sha256": digest(registration), "command": selected["command"], "environment_overrides": selected["environment_overrides"], "source_before": verify_source(workspace, role), "patch_sha256": digest(PHYSICS / "final-h3-review.patch"), "full_suite_completed": False, "log": str(log)}
    start = time.monotonic()
    with log.open("x") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        process = subprocess.Popen(selected["command"], cwd=workspace, env=env, stdout=stream, stderr=subprocess.STDOUT)
        record["pytest_pid"] = process.pid
        started.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        exit_code = process.wait()
    text = log.read_text()
    statuses = {}
    for line in text.splitlines():
        match = re.match(r"^(tests/[^ ]+::.*?)\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\s*(?:\[.*)?$", line)
        if match:
            node, status = match.groups()
            if node in statuses:
                raise RuntimeError(f"Duplicate node status: {node}")
            statuses[node] = status
    missing = sorted(set(selected["expected_nodes"]) - set(statuses))
    unexpected = sorted(set(statuses) - set(selected["expected_nodes"]))
    summary_lines = [line for line in text.splitlines() if re.search(r"\d+ (?:passed|failed|skipped).* in [\d.]+s", line)]
    record.update({"status": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat(), "elapsed_s": time.monotonic() - start, "exit_code": exit_code, "expected_count": selected["expected_count"], "observed_node_count": len(statuses), "node_statuses": statuses, "missing_nodeids": missing, "unexpected_nodeids": unexpected, "all_assigned_nodeids_scored": not missing and not unexpected, "summary": summary_lines[-1] if summary_lines else None, "source_after": verify_source(workspace, role), "patch_sha256_after": digest(PHYSICS / "final-h3-review.patch"), "log_sha256": digest(log)})
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: record[key] for key in ("role", "status", "exit_code", "expected_count", "observed_node_count", "all_assigned_nodeids_scored", "summary", "elapsed_s")}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
