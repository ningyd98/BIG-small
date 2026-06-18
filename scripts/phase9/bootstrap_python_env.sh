#!/usr/bin/env bash
# 脚本说明：准备 Phase 9 Python 环境依赖，不运行仿真或硬件动作。
set -euo pipefail
python -m pip install -e '.[dev,sim-mujoco,sim-analysis]'
