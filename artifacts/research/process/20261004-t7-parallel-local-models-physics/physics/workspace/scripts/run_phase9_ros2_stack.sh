#!/usr/bin/env bash
# 脚本说明：Phase 9 ROS2 栈验证入口，只调用固定 verifier，不直接发送轨迹。
set -euo pipefail
python scripts/verify_phase9_ros2.py
