"""Verify the frozen Stage56 delivery under the accepted Astra plan.

This is a pre-commit checker for the pinned HEAD and exact staged scope.
Original Git exit 2 is retained separately from archive classification.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path.cwd().resolve()
ARTIFACT = Path("artifacts/research/process/20261004-ced-development")
ROUND = ARTIFACT / "astra-rounds/round56-git-check"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)


def read_json(path: Path) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def verify_blob(row: dict) -> None:
    content = (ROOT / row["path"]).read_bytes()
    assert digest(content) == row["sha256"], row["path"]
    if "bytes" in row:
        assert len(content) == row["bytes"], row["path"]
    staged = git("show", ":" + row["path"])
    assert staged.returncode == 0, row["path"]
    assert staged.stdout == content, row["path"]


def main() -> None:
    plan_path = ROUND / "plan.json"
    assert digest((ROOT / plan_path).read_bytes()) == (
        "9a44fbabc7eb351eaeec9cf9452752a66c7159841feb3ab2c5e2735944847d09"
    )
    assert digest((ROOT / ROUND / "plan.md").read_bytes()) == (
        "df29741d301d0240b93a63d6de3285508eb5ef6cdcfc6389b4bbb1ea124056fc"
    )
    plan = read_json(plan_path)
    pins = plan["input_pins"]
    head = git("rev-parse", "HEAD")
    assert head.returncode == 0 and head.stdout.decode().strip() == pins["head"]
    scope_path = Path(pins["scope_path"])
    scope_bytes = (ROOT / scope_path).read_bytes()
    assert digest(scope_bytes) == pins["scope_sha256"]
    scope = json.loads(scope_bytes)
    assert len(scope["files"]) == 377
    assert sum(row["bytes"] for row in scope["files"]) == 19863389
    original = scope["files"] + [{
        "path": str(scope_path), "bytes": len(scope_bytes),
        "sha256": digest(scope_bytes),
    }]
    for row in original:
        verify_blob(row)
    for row in pins["archive_evidence"]:
        assert digest((ROOT / row["path"]).read_bytes()) == row["sha256"]

    supplemental_paths = [ROUND / name for name in (
        "plan.md", "plan.json", "check_staged.py", "initial-failure.json"
    )]
    extra = [{"path": str(path), "bytes": (ROOT / path).stat().st_size,
              "sha256": digest((ROOT / path).read_bytes())}
             for path in supplemental_paths]
    expected_paths = {row["path"] for row in original + extra}
    initial = git("diff", "--cached", "--name-only", "-z")
    assert initial.returncode == 0
    assert set(initial.stdout.decode().split("\0")[:-1]) == {
        row["path"] for row in original
    }
    added = git("add", "--", *(row["path"] for row in extra))
    assert added.returncode == 0, added.stderr
    for row in extra:
        verify_blob(row)

    whitelist = {row["path"]: row for row in plan["exact_whitelist"]}
    expected_diagnostics = {
        (row["path"], number, row["diagnostic"])
        for row in whitelist.values() for number in row["line_numbers"]
    }
    assert len(expected_diagnostics) == 264
    check = git("diff", "--cached", "--check")
    assert check.returncode == 2 and not check.stderr
    assert digest(check.stdout) == plan["problem"]["readonly_check_stdout_sha256"]
    lines = check.stdout.splitlines()
    assert len(lines) == 528
    diagnostics = []
    for index in range(0, len(lines), 2):
        match = re.fullmatch(rb"([^:\n]+):(\d+): (.+)", lines[index])
        assert match is not None, lines[index]
        path, number, message = (
            match[1].decode(), int(match[2]), match[3].decode()
        )
        assert (path, number, message) in expected_diagnostics
        row = whitelist[path]
        verify_blob(row)
        original_lines = (ROOT / path).read_bytes().splitlines()
        payload = original_lines[number - 1]
        assert lines[index + 1] == b"+" + payload
        if row["kind"] == "frozen_unified_diff_context":
            assert payload == b" " and row["diff_context_bytes_hex"] == "20"
            preceding = original_lines[:number - 1]
            assert any(line.startswith(b"@@ ") for line in preceding)
            last_hunk = max(i for i, line in enumerate(preceding)
                            if line.startswith(b"@@ "))
            assert not any(line.startswith(b"diff --git ")
                           for line in preceding[last_hunk + 1:])
        diagnostics.append({"path": path, "line": number, "message": message})
    assert {(d["path"], d["line"], d["message"]) for d in diagnostics} == (
        expected_diagnostics
    )
    assert len(diagnostics) == len(expected_diagnostics)
    clean_paths = sorted(expected_paths - set(whitelist))
    clean = git("diff", "--cached", "--check", "--", *clean_paths)
    assert clean.returncode == 0 and not clean.stdout and not clean.stderr

    record = {
        "schema_version": "bigsmall.git.stage56-check.v1",
        "head_before": pins["head"],
        "scope_sha256": pins["scope_sha256"],
        "original_scope_files": 377,
        "original_scope_bytes": 19863389,
        "original_scope_and_staged_blobs_match": True,
        "supplemental_files": extra,
        "raw_git_diff_check_exit_code": check.returncode,
        "raw_git_diff_check_stdout_sha256": digest(check.stdout),
        "raw_git_diff_check_stdout": check.stdout.decode(),
        "diagnostics": diagnostics,
        "diagnostics_by_path": dict(Counter(d["path"] for d in diagnostics)),
        "frozen_archive_classification": "PASS_EXACT_264_DIAGNOSTICS",
        "non_archive_and_supplemental_diff_check_exit_code": 0,
        "frozen_logs_and_patches_unchanged": True,
        "initial_failure": str(ROUND / "initial-failure.json"),
        "checker_metadata_self_hash_not_recursive": True,
        "new_runtime_tests_or_actual": 0,
        "native_and_formal_promoted": False,
    }
    output = ARTIFACT / "git-check-step56.json"
    assert not (ROOT / output).exists()
    (ROOT / output).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    added = git("add", "--", str(output))
    assert added.returncode == 0, added.stderr
    metadata_check = git("diff", "--cached", "--check", "--", str(output))
    assert metadata_check.returncode == 0 and not metadata_check.stdout
    final = git("diff", "--cached", "--name-only", "-z")
    assert set(final.stdout.decode().split("\0")[:-1]) == expected_paths | {str(output)}
    for row in original + extra:
        verify_blob(row)
    assert digest((ROOT / scope_path).read_bytes()) == pins["scope_sha256"]
    print(json.dumps({"staged_paths": len(expected_paths) + 1,
                      "raw_diff_check_exit": 2, "exact_archive_diagnostics": 264,
                      "code_docs_supplemental_diff_check_exit": 0,
                      "all_scoped_and_supplemental_staged_blobs_match": True}))


if __name__ == "__main__":
    main()
