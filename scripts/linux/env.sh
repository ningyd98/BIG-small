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
export SIMULATION_RUNTIME_DB="${BIGSMALL_ROOT}/data/simulation_runtime.db"
export MODEL_CONTROL_DB="${BIGSMALL_ROOT}/data/model_control.db"
export SIM_ARTIFACT_DIR="${BIGSMALL_ROOT}/artifacts/deployment/runtime"
export PLAYWRIGHT_BROWSERS_PATH="${BIGSMALL_ROOT}/cache/playwright"
export PIP_CACHE_DIR="${BIGSMALL_ROOT}/cache/pip"
export npm_config_cache="${BIGSMALL_ROOT}/cache/npm"
