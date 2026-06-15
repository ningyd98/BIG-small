#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT_DIR/artifacts/phase9_1/install}"
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

cd "$ROOT_DIR/${ROS2_WS:-ros2_ws}"
if [[ ! -d src ]]; then
  echo "BLOCKED_BY_ENV: ROS workspace src directory missing"
  exit 2
fi

rosdep install --from-paths src --ignore-src -r -y || {
  echo "BLOCKED_BY_ENV: rosdep install failed"
  exit 2
}
colcon build --symlink-install
