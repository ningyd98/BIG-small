#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${DASHBOARD_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${DASHBOARD_BACKEND_PORT:-8000}"
FRONTEND_HOST="${DASHBOARD_FRONTEND_HOST:-127.0.0.1}"

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
export DASHBOARD_ARTIFACT_ROOT="${DASHBOARD_ARTIFACT_ROOT:-${ROOT_DIR}/artifacts}"
export DASHBOARD_AUTH_MODE="${DASHBOARD_AUTH_MODE:-LOCAL_ONLY}"
export DASHBOARD_EXPERIMENT_WRITES_ENABLED="${DASHBOARD_EXPERIMENT_WRITES_ENABLED:-false}"

backend_pid=""

cleanup() {
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

python -m uvicorn cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app \
  --host "${BACKEND_HOST}" \
  --port "${BACKEND_PORT}" \
  --log-level info &
backend_pid="$!"

cd "${ROOT_DIR}/dashboard"
npm run dev -- --host "${FRONTEND_HOST}"
