#!/usr/bin/env bash
# 脚本说明：运行 ROS2 bridge smoke 验证，只检查桥接边界。
set -euo pipefail
python scripts/verify_phase9_ros2.py
