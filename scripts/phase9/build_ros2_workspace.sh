#!/usr/bin/env bash
set -euo pipefail
if ! command -v colcon >/dev/null 2>&1; then
  echo "BLOCKED_BY_ENV: colcon not found"
  exit 2
fi
cd "${ROS2_WS:-ros2_ws}"
colcon build --symlink-install
