#!/usr/bin/env bash
# 脚本说明：Phase 9 MoveIt 演示入口，委托固定验证脚本执行，不拼接任意命令。
set -euo pipefail
python scripts/verify_phase9_ros2.py
