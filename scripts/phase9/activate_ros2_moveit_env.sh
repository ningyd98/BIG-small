#!/usr/bin/env bash
set -euo pipefail

CONDA_ENV="${BIGSMALL_CONDA_ENV:-bigsmall-ros2-jazzy-moveit}"
ROS2_WS="${BIGSMALL_ROS2_WS:-$HOME/bigsmall_runtime/ros2_ws}"
BIGSMALL_ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-91}"
BIGSMALL_RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"

if [[ -z "${CONDA_EXE:-}" ]]; then
  if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base)"
  else
    CONDA_BASE="${CONDA_BASE:-$HOME/anaconda3}"
  fi
else
  CONDA_BASE="$(dirname "$(dirname "$CONDA_EXE")")"
fi

CONDA_SH="$CONDA_BASE/etc/profile.d/conda.sh"
if [[ ! -r "$CONDA_SH" ]]; then
  echo "BLOCKED_BY_ENV: conda activation script not found at $CONDA_SH" >&2
  return 2 2>/dev/null || exit 2
fi

# shellcheck disable=SC1090
source "$CONDA_SH"
set +u
conda activate "$CONDA_ENV"
set -u

export ROS_DOMAIN_ID="$BIGSMALL_ROS_DOMAIN_ID"
export RMW_IMPLEMENTATION="$BIGSMALL_RMW_IMPLEMENTATION"

SETUP="$ROS2_WS/install/setup.bash"
if [[ ! -r "$SETUP" ]]; then
  echo "BLOCKED_BY_ENV: persistent ROS workspace setup not found at $SETUP" >&2
  echo "Run: scripts/phase9/build_ros2_workspace.sh" >&2
  return 2 2>/dev/null || exit 2
fi

# shellcheck disable=SC1090
set +u
source "$SETUP"
set -u

export AMENT_PREFIX_PATH="$ROS2_WS/install${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"
export CMAKE_PREFIX_PATH="$ROS2_WS/install${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export ROS_DOMAIN_ID="$BIGSMALL_ROS_DOMAIN_ID"
export RMW_IMPLEMENTATION="$BIGSMALL_RMW_IMPLEMENTATION"

printf 'ROS_DISTRO=%s\n' "${ROS_DISTRO:-<unset>}"
printf 'Python=%s\n' "$(command -v python)"
printf 'Workspace=%s\n' "$ROS2_WS"
printf 'ROS_DOMAIN_ID=%s\n' "$BIGSMALL_ROS_DOMAIN_ID"
printf 'RMW_IMPLEMENTATION=%s\n' "$BIGSMALL_RMW_IMPLEMENTATION"
