#!/usr/bin/env bash
# 脚本说明：在 macOS 上同时启动 loopback FastAPI 与 Vite 开发服务器，并安全回收子进程。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -f "${ROOT_DIR}/.env.macos.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env.macos.local"
  set +a
fi

BACKEND_PORT="${BIGSMALL_BACKEND_PORT:-8000}"
FRONTEND_PORT="${BIGSMALL_FRONTEND_PORT:-5173}"
OPEN_BROWSER=true
RELOAD=true

usage() {
  cat <<'EOF'
Usage: scripts/macos/start.sh [options]

Options:
  --backend-port PORT   FastAPI port (default: 8000).
  --frontend-port PORT  Vite port (default: 5173).
  --no-open             Do not open the browser automatically.
  --no-reload           Disable FastAPI source reload.
  -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      [[ $# -ge 2 ]] || { echo "--backend-port requires a value" >&2; exit 2; }
      BACKEND_PORT="$2"
      shift 2
      ;;
    --frontend-port)
      [[ $# -ge 2 ]] || { echo "--frontend-port requires a value" >&2; exit 2; }
      FRONTEND_PORT="$2"
      shift 2
      ;;
    --no-open)
      OPEN_BROWSER=false
      shift
      ;;
    --no-reload)
      RELOAD=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS. Use scripts/start_dashboard_dev.sh elsewhere." >&2
  exit 2
fi
if [[ ! "${BACKEND_PORT}" =~ ^[0-9]+$ || ! "${FRONTEND_PORT}" =~ ^[0-9]+$ ]] \
  || (( BACKEND_PORT < 1 || BACKEND_PORT > 65535 )) \
  || (( FRONTEND_PORT < 1 || FRONTEND_PORT > 65535 )); then
  echo "Ports must be integers between 1 and 65535." >&2
  exit 2
fi

if command -v brew >/dev/null 2>&1 && brew list --versions node@22 >/dev/null 2>&1; then
  export PATH="$(brew --prefix node@22)/bin:${PATH}"
elif [[ -x /opt/homebrew/bin/brew ]] \
  && /opt/homebrew/bin/brew list --versions node@22 >/dev/null 2>&1; then
  export PATH="$(/opt/homebrew/bin/brew --prefix node@22)/bin:${PATH}"
fi

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" || ! -d "${ROOT_DIR}/dashboard/node_modules" ]]; then
  echo "Development dependencies are missing. Run: ./scripts/macos/install.sh" >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm is missing. Run: ./scripts/macos/install.sh" >&2
  exit 1
fi

port_available() {
  "${PYTHON_BIN}" - "$1" "$2" <<'PY'
import socket
import sys

host, raw_port = sys.argv[1:]
with socket.socket() as sock:
    try:
        sock.bind((host, int(raw_port)))
    except OSError:
        raise SystemExit(1)
PY
}

if ! port_available 127.0.0.1 "${BACKEND_PORT}"; then
  echo "Backend port ${BACKEND_PORT} is already in use." >&2
  exit 1
fi
if ! port_available 127.0.0.1 "${FRONTEND_PORT}"; then
  echo "Frontend port ${FRONTEND_PORT} is already in use." >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
export RUNTIME_PROFILE="${RUNTIME_PROFILE:-simulation}"
export SIM_BACKEND="${SIM_BACKEND:-mujoco}"
export SIM_HEADLESS="${SIM_HEADLESS:-true}"
export MUJOCO_GL="${MUJOCO_GL:-glfw}"
export SIM_ARTIFACT_DIR="${SIM_ARTIFACT_DIR:-${ROOT_DIR}/artifacts/macos/simulation}"
export DASHBOARD_ARTIFACT_ROOT="${DASHBOARD_ARTIFACT_ROOT:-${ROOT_DIR}/artifacts}"
export DASHBOARD_AUTH_MODE="${DASHBOARD_AUTH_MODE:-LOCAL_ONLY}"
export DASHBOARD_EXPERIMENT_WRITES_ENABLED="${DASHBOARD_EXPERIMENT_WRITES_ENABLED:-true}"
export MODEL_CONTROL_DB="${MODEL_CONTROL_DB:-${ROOT_DIR}/data/model_control.db}"
export SIMULATION_RUNTIME_DB="${SIMULATION_RUNTIME_DB:-${ROOT_DIR}/data/simulation_runtime.db}"
export DASHBOARD_BACKEND_ORIGIN="http://127.0.0.1:${BACKEND_PORT}"
export DASHBOARD_FRONTEND_HOST=127.0.0.1
export DASHBOARD_FRONTEND_PORT="${FRONTEND_PORT}"

mkdir -p "${ROOT_DIR}/data" "${ROOT_DIR}/artifacts/macos/simulation"
(
  cd "${ROOT_DIR}"
  "${PYTHON_BIN}" scripts/init_simulation_runtime_db.py \
    --database "${SIMULATION_RUNTIME_DB}"
)

backend_pid=""
frontend_pid=""
cleanup_started=false

cleanup() {
  if [[ "${cleanup_started}" == "true" ]]; then
    return
  fi
  cleanup_started=true
  trap - EXIT INT TERM HUP
  for pid in "${frontend_pid}" "${backend_pid}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done
  for pid in "${frontend_pid}" "${backend_pid}"; do
    if [[ -n "${pid}" ]]; then
      wait "${pid}" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM HUP

backend_command=(
  "${PYTHON_BIN}" -m uvicorn
  cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app
  --host 127.0.0.1
  --port "${BACKEND_PORT}"
  --log-level info
)
if [[ "${RELOAD}" == "true" ]]; then
  backend_command+=(--reload --reload-dir "${ROOT_DIR}/src")
fi

echo "Starting FastAPI at http://127.0.0.1:${BACKEND_PORT}"
(
  cd "${ROOT_DIR}"
  exec "${backend_command[@]}"
) &
backend_pid="$!"

echo "Starting Vite at http://127.0.0.1:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/dashboard"
  exec npm run dev -- \
    --host 127.0.0.1 \
    --port "${FRONTEND_PORT}" \
    --strictPort
) &
frontend_pid="$!"

wait_for_url() {
  local name="$1" url="$2" pid="$3" attempt=0
  while (( attempt < 120 )); do
    if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "${name} exited before becoming ready." >&2
      return 1
    fi
    attempt=$((attempt + 1))
    sleep 0.5
  done
  echo "Timed out waiting for ${name}: ${url}" >&2
  return 1
}

wait_for_url FastAPI "http://127.0.0.1:${BACKEND_PORT}/health" "${backend_pid}"
wait_for_url Vite-proxy \
  "http://127.0.0.1:${FRONTEND_PORT}/api/v1/simulation/capabilities" \
  "${frontend_pid}"

echo
echo "BIG-small macOS development environment is ready:"
echo "  Workbench: http://127.0.0.1:${FRONTEND_PORT}/simulation/workbench"
echo "  API docs:  http://127.0.0.1:${BACKEND_PORT}/docs"
echo "  Backend:   MuJoCo (${MUJOCO_GL}), simulation-only"
echo "Press Ctrl-C to stop both services."

if [[ "${OPEN_BROWSER}" == "true" ]]; then
  open "http://127.0.0.1:${FRONTEND_PORT}/simulation/workbench"
fi

while kill -0 "${backend_pid}" 2>/dev/null \
  && kill -0 "${frontend_pid}" 2>/dev/null; do
  sleep 1
done

set +e
if ! kill -0 "${backend_pid}" 2>/dev/null; then
  wait "${backend_pid}"
  exit_status=$?
  echo "FastAPI exited with status ${exit_status}." >&2
else
  wait "${frontend_pid}"
  exit_status=$?
  echo "Vite exited with status ${exit_status}." >&2
fi
set -e
exit "${exit_status}"
