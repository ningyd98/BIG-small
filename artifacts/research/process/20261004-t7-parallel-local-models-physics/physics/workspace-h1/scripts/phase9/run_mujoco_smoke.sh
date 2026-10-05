#!/usr/bin/env bash
# 脚本说明：运行 MuJoCo smoke 验证，限定在仿真后端。
set -euo pipefail
python scripts/verify_phase9_mujoco.py
