"""Phase 12 provenance 工具。

provenance 只记录 commit、源树哈希、配置哈希和环境摘要，不写入本机绝对路径、
用户名、secret、controller address 或真实设备信息。
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def stable_hash(payload: Any) -> str:
    """对 JSON 可序列化 payload 生成稳定 SHA-256。"""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def git_commit(repo_root: Path = Path(".")) -> str:
    """读取当前 commit；失败时返回 UNKNOWN，不访问网络。"""

    return _git(["rev-parse", "HEAD"], repo_root) or "UNKNOWN"


def source_tree_hash(repo_root: Path = Path(".")) -> str:
    """计算 tracked source/doc/config 文件哈希，排除 artifacts 和运行缓存。"""

    files = (_git(["ls-files"], repo_root) or "").splitlines()
    digest = hashlib.sha256()
    for name in sorted(files):
        if name.startswith(("artifacts/", "dashboard/node_modules/", "dashboard/dist/")):
            continue
        path = repo_root / name
        if not path.is_file():
            continue
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def worktree_clean(repo_root: Path = Path(".")) -> bool:
    """检查源码工作树是否干净；Phase 12 输出目录不参与源码脏检查。"""

    status = _git(
        [
            "status",
            "--short",
            "--",
            "src",
            "scripts",
            "tests",
            "configs",
            "docs",
            "README.md",
            "CHANGELOG.md",
        ],
        repo_root,
    )
    return status == ""


def environment_summary() -> dict[str, str]:
    """返回脱敏环境摘要，不包含用户名、绝对路径或 IP。"""

    return {
        "python_version": sys.version.split()[0],
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
    }


def environment_hash() -> str:
    """生成环境摘要哈希。"""

    return stable_hash(environment_summary())


def _git(args: list[str], repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""
