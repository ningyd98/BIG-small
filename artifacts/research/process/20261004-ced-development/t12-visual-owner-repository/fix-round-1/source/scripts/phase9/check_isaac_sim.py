#!/usr/bin/env python
"""仓库回归环境检查入口，只读取依赖和配置状态，不执行真实机械臂动作。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "artifacts/phase9_1/install"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    root = os.environ.get("ISAAC_SIM_ROOT", "")
    root_path = Path(root) if root else None
    python_sh = root_path / "python.sh" if root_path else None
    version_files = [root_path / "VERSION", root_path / "kit" / "VERSION"] if root_path else []
    version = ""
    for version_file in version_files:
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
            break
    commands = [
        _run(["bash", "-lc", "command -v vulkaninfo && vulkaninfo --summary"]),
        _run(
            [
                "bash",
                "-lc",
                "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
            ]
        ),
        _run(["bash", "-lc", 'test -n "$ISAAC_SIM_ROOT"']),
    ]
    if python_sh is not None:
        commands.append(_run(["bash", "-lc", f"test -x {str(python_sh)!r}"]))
        commands.append(_run([str(python_sh), "-c", "print('isaac-python-ready')"]))
    blockers = []
    if not root:
        blockers.append("ISAAC_SIM_ROOT is unset or missing")
    elif root_path is not None and not root_path.exists():
        blockers.append("ISAAC_SIM_ROOT does not exist")
    if python_sh is None or not python_sh.exists():
        blockers.append("Isaac Sim python.sh is unavailable")
    if commands[0]["exit_code"] != 0:
        blockers.append("vulkaninfo is unavailable or Vulkan runtime is unusable")
    if commands[1]["exit_code"] != 0:
        blockers.append("nvidia-smi is unavailable")
    blocked = bool(blockers)
    payload = {
        "status": "BLOCKED_BY_ENV" if blocked else "READY_TO_SMOKE",
        "isaac_sim_root": root,
        "isaac_sim_version": version,
        "core_python_environment": "unchanged",
        "isaac_python_environment": str(python_sh) if python_sh else "",
        "commands": commands,
        "blockers": blockers,
    }
    (artifact_dir / "isaac_compatibility_report.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _run(argv: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "exit_code": 124, "stdout": "", "stderr": str(exc)}
    return {
        "argv": [_sanitize(item) for item in argv],
        "exit_code": result.returncode,
        "stdout": _sanitize(result.stdout.strip()[-4000:]),
        "stderr": _sanitize(result.stderr.strip()[-4000:]),
    }


def _sanitize(value: str) -> str:
    home = str(Path.home())
    sanitized = value.replace(sys.executable, "python")
    if home:
        sanitized = sanitized.replace(home, "$HOME")
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main())
