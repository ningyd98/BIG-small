#!/usr/bin/env bash
# 脚本说明：在 macOS 本机安装 BIG-small 的 Python、MuJoCo、Rerun 和前端开发依赖。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIN_NODE_MAJOR=22
MIN_NODE_MINOR=12
DRY_RUN=false
NO_BREW=false
SKIP_CHECKS=false

usage() {
  cat <<'EOF'
Usage: scripts/macos/install.sh [options]

Options:
  --dry-run       Print the installation plan without changing the machine.
  --no-brew       Do not install missing Python or Node packages with Homebrew.
  --skip-checks   Skip frontend typecheck/build and the final environment doctor.
  -h, --help      Show this help.

Environment:
  BIGSMALL_PYTHON  Preferred Python 3.12+ interpreter.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-brew)
      NO_BREW=true
      shift
      ;;
    --skip-checks)
      SKIP_CHECKS=true
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
  echo "This installer only supports macOS. Use README.md quick start on other systems." >&2
  exit 2
fi

if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" == "1" ]]; then
  echo "Rosetta shell detected. Reopen a native terminal with: arch -arm64 /bin/zsh" >&2
  exit 2
fi

BREW_BIN=""
if command -v brew >/dev/null 2>&1; then
  BREW_BIN="$(command -v brew)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  BREW_BIN=/opt/homebrew/bin/brew
elif [[ -x /usr/local/bin/brew ]]; then
  BREW_BIN=/usr/local/bin/brew
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  cat <<EOF
BIG-small macOS installation plan
  repository: ${ROOT_DIR}
  architecture: $(uname -m)
  Homebrew: ${BREW_BIN:-not found}
  Python: 3.12+ (Homebrew formula: python@3.12 when missing)
  Node: 22.12+ (Homebrew formula: node@22 when missing)
  Python extras: dev, sim-mujoco, sim-analysis, sim-observability
  frontend: npm ci
  local config: .env.macos.local (created only when absent)
  hardware/Isaac/ROS installation: disabled
EOF
  exit 0
fi

python_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
    >/dev/null 2>&1
}

node_supported() {
  local version major minor
  version="$($1 -p 'process.versions.node' 2>/dev/null || true)"
  major="${version%%.*}"
  version="${version#*.}"
  minor="${version%%.*}"
  [[ "${major}" =~ ^[0-9]+$ ]] || return 1
  [[ "${minor}" =~ ^[0-9]+$ ]] || return 1
  (( major > MIN_NODE_MAJOR || (major == MIN_NODE_MAJOR && minor >= MIN_NODE_MINOR) ))
}

install_formula() {
  local formula="$1"
  if [[ -z "${BREW_BIN}" || "${NO_BREW}" == "true" ]]; then
    echo "Missing ${formula}. Install Homebrew from https://brew.sh and rerun this script." >&2
    exit 1
  fi
  if ! "${BREW_BIN}" list --versions "${formula}" >/dev/null 2>&1; then
    echo "Installing ${formula} with Homebrew..."
    "${BREW_BIN}" install "${formula}"
  fi
}

PYTHON_BIN="${BIGSMALL_PYTHON:-}"
if [[ -n "${PYTHON_BIN}" ]] && ! python_supported "${PYTHON_BIN}"; then
  echo "BIGSMALL_PYTHON must point to Python 3.12 or newer." >&2
  exit 1
fi
if [[ -z "${PYTHON_BIN}" ]] && command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
fi
if [[ -z "${PYTHON_BIN}" ]] && command -v python3 >/dev/null 2>&1 \
  && python_supported "$(command -v python3)"; then
  PYTHON_BIN="$(command -v python3)"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  install_formula python@3.12
  PYTHON_BIN="$(${BREW_BIN} --prefix python@3.12)/bin/python3.12"
fi

if ! command -v node >/dev/null 2>&1 || ! node_supported "$(command -v node)"; then
  install_formula node@22
  export PATH="$(${BREW_BIN} --prefix node@22)/bin:${PATH}"
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found after Node installation." >&2
  exit 1
fi

VENV_DIR="${ROOT_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
if [[ -e "${VENV_DIR}" ]]; then
  venv_valid=false
  if [[ -x "${VENV_PYTHON}" ]] && python_supported "${VENV_PYTHON}"; then
    venv_arch="$(${VENV_PYTHON} -c 'import platform; print(platform.machine())')"
    if [[ "$(uname -m)" != "arm64" || "${venv_arch}" == "arm64" ]]; then
      venv_valid=true
    fi
  fi
  if [[ "${venv_valid}" != "true" ]]; then
    backup="${VENV_DIR}.backup.$(date +%Y%m%d%H%M%S)"
    echo "Preserving incompatible virtual environment at ${backup}"
    mv "${VENV_DIR}" "${backup}"
  fi
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Creating ${VENV_DIR} with ${PYTHON_BIN}..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

echo "Installing Python development and simulation dependencies..."
"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel
"${VENV_PYTHON}" -m pip install -e \
  "${ROOT_DIR}[dev,sim-mujoco,sim-analysis,sim-observability]"

echo "Installing Dashboard dependencies from package-lock.json..."
(
  cd "${ROOT_DIR}/dashboard"
  npm ci --no-audit --no-fund
)

if [[ ! -f "${ROOT_DIR}/.env.macos.local" ]]; then
  cp "${ROOT_DIR}/.env.macos.example" "${ROOT_DIR}/.env.macos.local"
  echo "Created .env.macos.local with loopback-only simulation defaults."
fi

mkdir -p "${ROOT_DIR}/data" "${ROOT_DIR}/artifacts"
(
  cd "${ROOT_DIR}"
  "${VENV_PYTHON}" scripts/init_simulation_runtime_db.py
)

if [[ "${SKIP_CHECKS}" != "true" ]]; then
  (
    cd "${ROOT_DIR}/dashboard"
    npm run typecheck
    npm run build
  )
  "${ROOT_DIR}/scripts/macos/doctor.sh"
fi

touch "${VENV_DIR}/.bigsmall-macos-ready"
echo
echo "macOS environment is ready. Start it with: ./scripts/macos/start.sh"
