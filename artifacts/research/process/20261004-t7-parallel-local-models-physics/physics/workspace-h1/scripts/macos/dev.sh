#!/usr/bin/env bash
# 脚本说明：新检出分支上的一键入口，缺少依赖时先安装，再启动本地开发服务。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: scripts/macos/dev.sh [start.sh options]

On the first run this installs the macOS development environment, then starts
FastAPI and Vite. Later runs start immediately. Use install.sh and start.sh
separately when you need installation flags.
EOF
  exit 0
fi

if [[ ! -f "${ROOT_DIR}/.venv/.bigsmall-macos-ready" \
  || ! -d "${ROOT_DIR}/dashboard/node_modules" ]]; then
  "${ROOT_DIR}/scripts/macos/install.sh"
fi

exec "${ROOT_DIR}/scripts/macos/start.sh" "$@"
