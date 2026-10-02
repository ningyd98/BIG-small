#!/usr/bin/env bash
# Linux 环境入口：使用仓库独立 Python/Node，固定仿真安全边界。
BIGSMALL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="${BIGSMALL_ROOT}/.venv/bin:${BIGSMALL_ROOT}/cache/node-v22.23.3-linux-x64/bin:${PATH}"
export PYTHONPATH="${BIGSMALL_ROOT}/src:${PYTHONPATH:-}"
export RUNTIME_PROFILE=simulation
export SIM_BACKEND=mujoco
export SIM_HEADLESS=true
export REAL_MOTION_DISPATCH_ENABLED=false
export DASHBOARD_AUTH_MODE=LOCAL_ONLY
export DASHBOARD_BACKEND_HOST=127.0.0.1
export DASHBOARD_FRONTEND_HOST=127.0.0.1
export SIM_ARTIFACT_DIR="${BIGSMALL_ROOT}/artifacts/deployment/runtime"
export PLAYWRIGHT_BROWSERS_PATH="${BIGSMALL_ROOT}/cache/playwright"
export PIP_CACHE_DIR="${BIGSMALL_ROOT}/cache/pip"
export npm_config_cache="${BIGSMALL_ROOT}/cache/npm"
export XDG_CACHE_HOME="${BIGSMALL_ROOT}/cache"
export MAMBA_ROOT_PREFIX="${BIGSMALL_ROOT}/cache/mamba"
export BIGSMALL_MAMBA_EXE="${BIGSMALL_ROOT}/cache/micromamba/bin/micromamba"
export BIGSMALL_ROS2_WS="${BIGSMALL_ROS2_WS:-$HOME/bigsmall_runtime/ubuntu-6bebc95b/ros2_ws}"
if [[ -x "${BIGSMALL_ROOT}/cache/isaac-sim-6.0/bin/python" ]]; then
  export ISAAC_SIM_ROOT="${BIGSMALL_ROOT}/cache/isaac-sim-6.0"
  export ISAAC_RUNTIME_MODE=standalone
  export ISAAC_SIM_BACKEND_CMD="'${ISAAC_SIM_ROOT}/bin/python' '${BIGSMALL_ROOT}/scripts/phase9/isaac_standalone_app.py' --output '${SIM_ARTIFACT_DIR}/isaac_process'"
fi
if [[ -r "${BIGSMALL_ROOT}/cache/eula-consent.env" ]]; then
  source "${BIGSMALL_ROOT}/cache/eula-consent.env"
fi
