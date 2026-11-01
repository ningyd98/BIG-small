"""R388 final read-only Git delivery gates; preserves the two exact dirty gitlinks."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[6]
ROUND = Path(__file__).resolve().parent
PRIVATE = ROOT / ".git/r383-github-delivery-20261102"
BRANCH = "research/20261004-continuation"
OID = "ddbeb92a1aa1dfa8039f6260d6b5887c58072383"
LINKS = [
    "artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-baseline",
    "artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-h3",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert len(sys.argv) == 2 and re.fullmatch(r"[0-9a-f]{40}", sys.argv[1])
    expected_head = sys.argv[1]
    assert ROOT == Path.cwd().resolve()
    plan = json.loads((ROUND / "plan.json").read_text())
    for pin in plan["inputs"]:
        file = Path(pin["path"])
        file = file if file.is_absolute() else ROOT / file
        data = file.read_bytes()
        assert len(data) == pin["bytes"] and sha(data) == pin["sha256"], pin["path"]
    logs = PRIVATE / "r388-final-validation"
    logs.mkdir(exist_ok=False)
    index_before = sha((ROOT / ".git/index").read_bytes())
    commands = []

    def git(*args):
        argv = ["git", *args]
        result = subprocess.run(argv, cwd=ROOT, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"), capture_output=True)
        prefix = f"{len(commands):02d}"
        (logs / (prefix + ".stdout.log")).write_bytes(result.stdout)
        (logs / (prefix + ".stderr.log")).write_bytes(result.stderr)
        commands.append({"argv": argv, "exit": result.returncode,
                         "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
        assert result.returncode == 0, (argv, result.returncode)
        return result.stdout

    branch = git("branch", "--show-current").decode().strip()
    assert branch == BRANCH
    local = git("rev-parse", "HEAD").decode().strip()
    upstream = git("rev-parse", "@{upstream}").decode().strip()
    live = git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH).split()
    assert len(live) == 2 and live[1] == ("refs/heads/" + BRANCH).encode()
    remote = live[0].decode()
    assert local == upstream == remote == expected_head
    raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = [entry for entry in raw.split(b"\0") if entry]
    expected_status = {b" M " + os.fsencode(path) for path in LINKS}
    assert len(records) == 2 and set(records) == expected_status, records
    assert not git("diff", "--cached", "--name-only", "-z")
    worktree = {path for path in git("diff", "--name-only", "-z").split(b"\0") if path}
    assert worktree == {os.fsencode(path) for path in LINKS}
    entries = [entry for entry in git("ls-files", "--stage", "-z", "--", *LINKS).split(b"\0") if entry]
    indexed = {}
    for entry in entries:
        header, path = entry.split(b"\t", 1)
        assert header == ("160000 " + OID + " 0").encode()
        indexed[path] = OID
    assert set(indexed) == {os.fsencode(path) for path in LINKS}
    tree_entries = [entry for entry in git("ls-tree", "-z", "HEAD", "--", *LINKS).split(b"\0") if entry]
    tree_paths = set()
    for entry in tree_entries:
        header, path = entry.split(b"\t", 1)
        assert header == ("160000 commit " + OID).encode()
        tree_paths.add(path)
    assert tree_paths == set(indexed)
    for path in LINKS:
        assert git("-C", path, "rev-parse", "HEAD").decode().strip() == OID
    assert git("rev-list", "--left-right", "--count", "HEAD...@{upstream}").split() == [b"0", b"0"]
    index_after = sha((ROOT / ".git/index").read_bytes())
    assert index_after == index_before
    receipt = {
        "schema": "bigsmall.r388.final-delivery.v1", "complete": True,
        "repository": "https://github.com/ningyd98/BIG-small", "branch": branch,
        "checkpoint_commit": "13579b8ed9face9e90cd6947073ab2101b558e96",
        "previous_receipt_commit": "67d02434663fb9cf72aadbb3b743a49a7370f04a",
        "local_head": local, "upstream": upstream, "live_remote": remote,
        "three_shas_equal": True, "ahead": 0, "behind": 0,
        "stage_empty": True, "non_gitlink_worktree_and_untracked_clean": True,
        "preserved_dirty_gitlinks": [{"path": path, "head_and_index_oid": OID} for path in LINKS],
        "index_sha256_before_and_after": index_before,
        "bounded_cpu_tests_passed": 67, "prior_full_fsck_exit": 0,
        "tests_or_full_fsck_rerun_in_r388": False,
        "real_runs": 0, "formal_research_acceptance_promoted": False,
        "private_native_logs": str(logs.relative_to(ROOT)), "commands": commands,
        "verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with (PRIVATE / "final-receipt.json").open("x", encoding="utf-8") as file:
        json.dump(receipt, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(json.dumps({"complete": True, "final_sha": local, "three_shas_equal": True,
                      "preserved_dirty_gitlinks": 2, "non_gitlink_clean": True}))


if __name__ == "__main__":
    main()
