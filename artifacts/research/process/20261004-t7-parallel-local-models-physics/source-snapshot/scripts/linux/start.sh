#!/usr/bin/env bash
# 启动 Linux loopback API、内置仿真 worker 与 Dashboard，不启动真实机械臂。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$BIGSMALL_ROOT"
export SIMULATION_RUNTIME_DB="${SIMULATION_RUNTIME_DB:-${BIGSMALL_ROOT}/data/simulation_runtime.db}"
export MODEL_CONTROL_DB="${MODEL_CONTROL_DB:-${BIGSMALL_ROOT}/data/model_control.db}"
export DASHBOARD_EXPERIMENT_WRITES_ENABLED=true
mkdir -p data "$SIM_ARTIFACT_DIR"
python scripts/init_simulation_runtime_db.py --database "$SIMULATION_RUNTIME_DB"
exec bash scripts/start_dashboard_dev.sh
