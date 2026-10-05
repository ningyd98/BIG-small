#!/usr/bin/env bash
# 脚本说明：只读诊断 macOS 本地开发环境，不安装软件、不下载模型、不连接真实硬件。
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/macos/doctor.sh

Checks the native macOS architecture, Python virtual environment, MuJoCo/Rerun
imports, Dashboard Node version and installed npm dependency tree. It does not
modify the machine.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -gt 0 ]]; then
  echo "doctor.sh does not accept positional arguments." >&2
  usage >&2
  exit 2
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "FAIL operating system: expected macOS" >&2
  exit 2
fi

failures=0
pass() {
  echo "PASS $1"
}
fail() {
  echo "FAIL $1" >&2
  failures=$((failures + 1))
}

arch_name="$(uname -m)"
if [[ "${arch_name}" == "arm64" ]]; then
  pass "native Apple Silicon shell (${arch_name})"
else
  fail "native Apple Silicon shell (found ${arch_name})"
fi

if xcode-select -p >/dev/null 2>&1; then
  pass "Xcode Command Line Tools"
else
  echo "WARN Xcode Command Line Tools not detected; run: xcode-select --install"
fi

if command -v brew >/dev/null 2>&1 && brew list --versions node@22 >/dev/null 2>&1; then
  export PATH="$(brew --prefix node@22)/bin:${PATH}"
elif [[ -x /opt/homebrew/bin/brew ]] \
  && /opt/homebrew/bin/brew list --versions node@22 >/dev/null 2>&1; then
  export PATH="$(/opt/homebrew/bin/brew --prefix node@22)/bin:${PATH}"
fi

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ -x "${PYTHON_BIN}" ]]; then
  if (
    cd "${ROOT_DIR}"
    MUJOCO_GL=glfw "${PYTHON_BIN}" - <<'PY'
import platform
import sys
from pathlib import Path

import fastapi
import mujoco
import rerun

from cloud_edge_robot_arm.cloud.api.dev_dashboard_app import app

assert sys.version_info >= (3, 12)
assert platform.machine() == "arm64"
assert app is not None
model = mujoco.MjModel.from_xml_path(str(Path("assets/robots/franka_panda/scene.xml")))
assert model.nq > 0
assert fastapi.__version__
assert rerun is not None
print(f"Python {platform.python_version()}, MuJoCo {mujoco.__version__}, model nq={model.nq}")
PY
  ); then
    pass "Python/FastAPI/MuJoCo/Rerun environment"
  else
    fail "Python/FastAPI/MuJoCo/Rerun environment"
  fi
else
  fail ".venv Python is missing"
fi

if command -v node >/dev/null 2>&1; then
  node_version="$(node -p 'process.versions.node' 2>/dev/null || true)"
  node_major="${node_version%%.*}"
  node_tail="${node_version#*.}"
  node_minor="${node_tail%%.*}"
  if [[ "${node_major}" =~ ^[0-9]+$ && "${node_minor}" =~ ^[0-9]+$ ]] \
    && (( node_major > 22 || (node_major == 22 && node_minor >= 12) )); then
    pass "Node ${node_version}"
  else
    fail "Node 22.12+ (found ${node_version:-unknown})"
  fi
else
  fail "Node is missing"
fi

if command -v npm >/dev/null 2>&1 \
  && npm --prefix "${ROOT_DIR}/dashboard" ls --depth=0 --silent >/dev/null 2>&1; then
  pass "Dashboard npm dependencies"
else
  fail "Dashboard npm dependencies"
fi

if [[ -f "${ROOT_DIR}/.env.macos.local" ]]; then
  pass ".env.macos.local"
else
  echo "WARN .env.macos.local is absent; safe launcher defaults will be used"
fi

echo "INFO Isaac Sim/Isaac Lab and ROS 2 Jazzy are intentionally external to macOS setup."
echo "INFO Real-controller and hardware-write setup is intentionally absent."

if (( failures > 0 )); then
  echo "macOS environment doctor found ${failures} blocker(s)." >&2
  exit 1
fi
echo "macOS environment doctor passed."
