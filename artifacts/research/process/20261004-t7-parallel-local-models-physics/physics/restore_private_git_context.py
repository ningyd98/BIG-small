"""恢复隔离回归的只读来源上下文；私有 Git 元数据仅写到各实验副本。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[5]
PHYSICS = Path(__file__).resolve().parent
EXPERIMENT = PHYSICS.parent
HEAD = "ddbeb92a1aa1dfa8039f6260d6b5887c58072383"
ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    ENV.pop(name, None)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, env=ENV, text=True).strip()


def file_map(base: Path) -> dict[str, str]:
    result = {}
    for file in sorted(base.rglob("*")):
        name = file.relative_to(base)
        if any(part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in name.parts):
            continue
        if name.parts[0] in {"artifacts", "datasets"} or "node_modules" in name.parts or "dist" in name.parts:
            continue
        if file.is_file():
            result[str(name)] = digest(file)
    return result


def verify_source(base: Path, role: str) -> dict:
    snapshot = json.loads((EXPERIMENT / "source-snapshot-manifest.json").read_text())["source_sha256"]
    patches = json.loads((PHYSICS / "patch-file-manifest.json").read_text())["files"]
    expected = dict(snapshot)
    for change in patches:
        sha = change[f"{role}_sha256"]
        if sha:
            expected[change["path"]] = sha
    mismatches = [name for name, sha in expected.items() if not (base / name).is_file() or digest(base / name) != sha]
    if mismatches:
        raise RuntimeError(f"Frozen source mismatch: {role}: {mismatches}")
    return {"expected_files": len(expected), "mismatches": mismatches, "verified": True}


def main() -> None:
    output = PHYSICS / "private-git-context-restoration.json"
    if output.exists():
        raise FileExistsError(output)
    tracked = git(ROOT, "ls-tree", "-r", "--name-only", HEAD).splitlines()
    selected = [name for name in tracked if not (name.split("/")[0] in {"artifacts", "datasets"} or "node_modules" in name.split("/") or "dist" in name.split("/"))]
    original_index_sha = digest(ROOT / ".git/index")
    summary = {"created_at": datetime.now(timezone.utc).isoformat(), "head": HEAD, "source_policy": "No frozen source overwrite, only missing literal non-artifact tracked context. Source code is unchanged.", "original_index_sha_before": original_index_sha, "tracked_entries": len(tracked), "selected_context_entries": len(selected), "workspaces": {}}
    for role in ("baseline", "h3"):
        workspace = PHYSICS / f"workspace-{role}"
        source_before = verify_source(workspace, role)
        before = file_map(workspace)
        copied = {}
        missing = []
        for name in selected:
            target = workspace / name
            if target.exists() or target.is_symlink():
                continue
            source = ROOT / name
            if not source.is_file():
                missing.append(name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied[name] = digest(target)
        after = file_map(workspace)
        changed_existing = [name for name, sha in before.items() if after.get(name) != sha]
        if changed_existing:
            raise RuntimeError(f"Existing file changed: {changed_existing}")
        metadata = workspace / ".git"
        if metadata.exists():
            raise FileExistsError(metadata)
        empty_template = PHYSICS / "private-git-empty-template"
        empty_template.mkdir(exist_ok=True)
        git(workspace, "init", "--template", str(empty_template))
        alternate = metadata / "objects/info/alternates"
        alternate.write_text(str(ROOT / ".git/objects") + "\n")
        hooks = metadata / "disabled-hooks"
        hooks.mkdir()
        git(workspace, "config", "gc.auto", "0")
        git(workspace, "config", "maintenance.auto", "false")
        git(workspace, "config", "core.hooksPath", str(hooks))
        git(workspace, "update-ref", "refs/heads/research-frozen", HEAD)
        git(workspace, "symbolic-ref", "HEAD", "refs/heads/research-frozen")
        git(workspace, "read-tree", "HEAD")
        actual_head = git(workspace, "rev-parse", "HEAD")
        actual_tracked = git(workspace, "ls-files").splitlines()
        if actual_head != HEAD or actual_tracked != tracked or any(name.startswith("../") for name in actual_tracked):
            raise RuntimeError("Private Git context does not match frozen tree")
        mapping = PHYSICS / f"private-git-context-{role}-files.json"
        mapping.write_text(json.dumps({"existing_before_sha256": before, "copied_sha256": copied, "all_context_after_sha256": after, "missing_from_original_workspace": missing}, ensure_ascii=False, indent=2) + "\n")
        summary["workspaces"][role] = {"workspace": str(workspace), "source_before": source_before, "source_after": verify_source(workspace, role), "existing_files_preserved": len(before), "copied_files": len(copied), "missing_files": missing, "context_manifest": str(mapping), "context_manifest_sha256": digest(mapping), "private_git_head": actual_head, "tracked_count": len(actual_tracked), "relative_paths_valid": True, "read_only_object_alternate": str(ROOT / ".git/objects"), "original_git_write": False}
    summary["original_index_sha_after"] = digest(ROOT / ".git/index")
    summary["original_index_unchanged"] = summary["original_index_sha_after"] == original_index_sha
    summary["patch_sha256"] = digest(PHYSICS / "final-h3-review.patch")
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
