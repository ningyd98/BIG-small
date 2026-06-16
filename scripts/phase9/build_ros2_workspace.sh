#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT_DIR/artifacts/phase9_1/install}"
PERSISTENT_WS="${BIGSMALL_ROS2_WS:-$HOME/bigsmall_runtime/ros2_ws}"
ROS2_WS="${ROS2_WS:-$PERSISTENT_WS}"
mkdir -p "$ARTIFACT_DIR"
LOG="$ARTIFACT_DIR/build_ros2_workspace.log"
exec > >(tee "$LOG") 2>&1

if ! command -v colcon >/dev/null 2>&1; then
  echo "BLOCKED_BY_ENV: colcon not found"
  exit 2
fi

if [[ "${ROS_DISTRO:-}" != "jazzy" ]]; then
  echo "BLOCKED_BY_ENV: ROS_DISTRO must be jazzy; found '${ROS_DISTRO:-<unset>}'"
  exit 2
fi

mkdir -p "$ROS2_WS/src"
if [[ ! -d "$ROOT_DIR/ros2_ws/src" ]]; then
  echo "BLOCKED_BY_ENV: repository ROS workspace src directory missing"
  exit 2
fi

rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$ROOT_DIR/ros2_ws/src/" "$ROS2_WS/src/"

cd "$ROS2_WS"
DISPLAY_ROS2_WS="${ROS2_WS/#$HOME/\$HOME}"
echo "Building ROS workspace: $DISPLAY_ROS2_WS"
echo "ROS_DISTRO=$ROS_DISTRO"
echo "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-<unset>}"

if [[ "${RUN_ROSDEP_INSTALL:-0}" == "1" ]]; then
  rosdep install --from-paths src --ignore-src -r -y || {
    echo "BLOCKED_BY_ENV: rosdep install failed"
    exit 2
  }
else
  echo "Skipping rosdep install; set RUN_ROSDEP_INSTALL=1 to enable host package installation."
fi

colcon build --merge-install --symlink-install
