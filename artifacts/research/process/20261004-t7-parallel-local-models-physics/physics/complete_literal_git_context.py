"""补充 Git 引号编码下漏复制的中文路径；保留首次恢复记录作为中间证据。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from restore_private_git_context import ROOT, PHYSICS, HEAD, ENV, digest, file_map, verify_source, git


def tracked(cwd: Path, arguments: list[str]) -> list[str]:
    raw = subprocess.check_output(["git", *arguments], cwd=cwd, env=ENV)
    return sorted(name for name in raw.decode().split("\0") if name)


def main() -> None:
    output = PHYSICS / "private-git-context-final-verification.json"
    if output.exists():
        raise FileExistsError(output)
    names = tracked(ROOT, ["ls-tree", "-r", "--name-only", "-z", HEAD])
    selected = [name for name in names if not (name.split("/")[0] in {"artifacts", "datasets"} or "node_modules" in name.split("/") or "dist" in name.split("/"))]
    index_before = digest(ROOT / ".git/index")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "head": HEAD, "supersedes_context_completeness_claim": "private-git-context-restoration.json", "first_attempt_note": "Initial non-NUL Git listings escaped Unicode names. Retained intermediate log; corrected using NUL-delimited names, no source overwrite.", "tracked_entries": len(names), "selected_entries": len(selected), "workspaces": {}}
    for role in ("baseline", "h3"):
        workspace = PHYSICS / f"workspace-{role}"
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
        git(workspace, "config", "core.quotePath", "false")
        actual_names = tracked(workspace, ["ls-files", "-z"])
        if actual_names != names or any(name.startswith("../") for name in actual_names):
            raise RuntimeError("Tracked path mismatch")
        after = file_map(workspace)
        if any(after.get(name) != sha for name, sha in before.items()):
            raise RuntimeError("Existing context changed")
        manifest = PHYSICS / f"private-git-context-final-{role}-files.json"
        manifest.write_text(json.dumps({"existing_before_sha256": before, "additional_literal_copies_sha256": copied, "all_context_after_sha256": after, "missing_literal_paths": missing}, ensure_ascii=False, indent=2) + "\n")
        probe_env = {**ENV, "MUJOCO_GL": "egl", "PYTHONPATH": str(workspace / "src")}
        code = "from cloud_edge_robot_arm.final_evaluation.provenance import source_tree_hash; print(source_tree_hash())"
        source_hash = subprocess.check_output([str(ROOT / ".venv/bin/python"), "-c", code], cwd=workspace, env=probe_env, text=True).strip()
        if source_hash == hashlib.sha256(b"").hexdigest():
            raise RuntimeError("Empty source hash")
        report["workspaces"][role] = {"private_git_head": git(workspace, "rev-parse", "HEAD"), "tracked_count": len(actual_names), "paths_literal_relative": True, "copied_additional_unicode_files": len(copied), "context_files": len(after), "missing_literal_paths": missing, "source_tree_hash": source_hash, "source_hash_nonempty": True, "frozen_source_verified": verify_source(workspace, role), "manifest": str(manifest), "manifest_sha256": digest(manifest), "private_git_config": git(workspace, "config", "--local", "--list")}
    report["original_git_index_sha_before"] = index_before
    report["original_git_index_sha_after"] = digest(ROOT / ".git/index")
    report["original_git_index_unchanged"] = index_before == report["original_git_index_sha_after"]
    report["patch_sha256"] = digest(PHYSICS / "final-h3-review.patch")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
