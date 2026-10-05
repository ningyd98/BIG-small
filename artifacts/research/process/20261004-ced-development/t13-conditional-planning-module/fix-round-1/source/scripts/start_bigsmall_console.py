#!/usr/bin/env python
"""Start BIG-small Console on a local FastAPI server.

默认绑定 loopback，并挂载 ``dashboard/dist`` 到 ``/console``。该脚本不启动真实
硬件服务、不下载模型、不写入 API key。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Start BIG-small Console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if args.host == "0.0.0.0" and not _token_auth_configured():
        print("Refusing 0.0.0.0 without token auth configuration.")
        return 2
    dist = REPO_ROOT / "dashboard/dist"
    if not (dist / "index.html").exists():
        print("Dashboard build missing; /console will show a build missing page.")
    env = os.environ.copy()
    env.setdefault("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    env.setdefault("PYTHONPATH", str(REPO_ROOT / "src"))
    env.setdefault("MODEL_CONTROL_DB", str(REPO_ROOT / "data/model_control.db"))
    env.setdefault("SIMULATION_RUNTIME_DB", str(REPO_ROOT / "data/simulation_runtime.db"))
    url = f"http://{args.host}:{args.port}/console"
    if args.open_browser:
        webbrowser.open(url)
    print(f"Starting BIG-small Console at {url}")
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cloud_edge_robot_arm.cloud.api.console_app:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        cwd=REPO_ROOT,
        env=env,
    )


def _token_auth_configured() -> bool:
    return bool(os.environ.get("DASHBOARD_TOKEN") or os.environ.get("BIGSMALL_CONSOLE_TOKEN"))


if __name__ == "__main__":
    raise SystemExit(main())
