#!/usr/bin/env bash
# 安装入口：只安装项目 Python/前端依赖；独立仿真器保持外部环境。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$BIGSMALL_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
python -m pip install -c scripts/linux/constraints.txt -e '.[dev,sim-mujoco,sim-analysis,sim-observability]'
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<12))process.exit(1)'
(cd dashboard && npm ci --no-audit --no-fund && npx playwright install chromium)
python -m pip check
