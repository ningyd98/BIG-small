"""Prerequisites and persistent budget for the one registered nominal probe."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN_PATH = HERE / "plan.json"
PLAN = json.loads(PLAN_PATH.read_bytes())
MAX_SENDS = PLAN["historical_nominal_attempts"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(path, data):
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    sync_directory(path.parent)


def preflight_inputs():
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", PLAN["execution_base"], "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for rel, expected in PLAN["source_sha256"].items():
        path = (ROOT / rel).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == expected, f"source changed: {rel}")
    path = (ROOT / PLAN["original_historical_probe"]).resolve()
    manifest = json.loads((ROOT / PLAN["historical_manifest"]).read_bytes())
    require(len(manifest["files"]) == 47, "original probe file coverage lost")
    for name, member in manifest["files"].items():
        original = (path / name).resolve()
        require(
            original.is_relative_to(path) and sha(original) == member["sha256"],
            "historical original drifted",
        )
        if "bytes" in member:
            require(original.stat().st_size == member["bytes"], "historical member size changed")
    role = json.loads((ROOT / PLAN["current_preflight_public"]).read_bytes())
    require(
        role["actual_cloud_requests"] == 0
        and role["case_status_counts"] == {"NOT_EXECUTED": 480}
        and role["assignment_file_sha256"] == PLAN["dry_selection_sha256"],
        "B0 selection is not the bound offline allocation",
    )
    return path, json.loads((path / "role-probe-report.json").read_bytes())


class SendFence:
    """Consume each reserved attempt before the original transport can send."""

    def __init__(self, root, registration):
        require(
            not root.exists() and not root.is_symlink(), "registered probe has previously started"
        )
        root.mkdir(parents=False)
        sync_directory(root.parent)
        self.root = root
        self.cursor = 0
        write_once(root / "startup.json", registration)

    def reserve(self, index, path, raw):
        require(
            type(index) is int and index == self.cursor and index < MAX_SENDS,
            "duplicate, skipped, or excess transport slot",
        )
        slot = self.root / f"send-{index:02d}.json"
        write_once(
            slot,
            {
                "attempt_index": index,
                "chat_path": path,
                "payload_length": len(raw),
                "request_sha256": hashlib.sha256(raw).hexdigest(),
                "state": "RESERVED_BEFORE_DISPATCH",
            },
        )
        self.cursor += 1
