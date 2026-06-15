#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT_DIR/artifacts/phase9_1/install}"
EXECUTE=0
ASSUME_YES=0

usage() {
  cat <<'USAGE'
Install or plan the Phase 9.1 ROS 2 Jazzy / MoveIt 2 host environment.

Default mode is dry-run: it writes an auditable install plan and does not use sudo.

Options:
  --execute       Actually run apt/sudo installation steps.
  --yes           Pass -y to apt operations in --execute mode.
  --artifact-dir  Directory for install_plan.json and install_ros2_jazzy.log.
  -h, --help      Show this help.

Environment boundaries:
  - Core Python dependencies stay in the BIG-small venv/conda environment.
  - ROS 2 Jazzy and MoveIt 2 are installed as system packages under /opt/ros/jazzy.
  - Isaac Sim is not installed by this script and must use its official runtime.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --artifact-dir)
      ARTIFACT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$ARTIFACT_DIR"
LOG="$ARTIFACT_DIR/install_ros2_jazzy.log"
PLAN="$ARTIFACT_DIR/install_plan.json"
exec > >(tee "$LOG") 2>&1

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
else
  ID="unknown"
  VERSION_ID="unknown"
  VERSION_CODENAME="unknown"
fi

APT_YES=()
if [[ "$ASSUME_YES" == "1" ]]; then
  APT_YES=(-y)
fi

BASE_PACKAGES=(
  curl
  gnupg
  lsb-release
  software-properties-common
  python3-colcon-common-extensions
  python3-rosdep
  python3-vcstool
)
ROS_PACKAGES=(
  ros-jazzy-desktop
  ros-dev-tools
  ros-jazzy-moveit
  ros-jazzy-moveit-resources-panda-moveit-config
  ros-jazzy-joint-state-publisher
  ros-jazzy-robot-state-publisher
  ros-jazzy-tf2-ros
  ros-jazzy-rmw-fastrtps-cpp
)

python - "$PLAN" "$EXECUTE" "$ID" "$VERSION_ID" "$VERSION_CODENAME" <<'PY'
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

plan = {
    "script": "scripts/phase9/install_ros2_jazzy.sh",
    "execute": sys.argv[2] == "1",
    "os": {"id": sys.argv[3], "version_id": sys.argv[4], "codename": sys.argv[5]},
    "requires_sudo": True,
    "core_python_environment": "unchanged",
    "ros_environment": "/opt/ros/jazzy plus ros2_ws/install after colcon build",
    "isaac_environment": "external official Isaac Sim runtime, not core Python",
    "commands": [
        "sudo apt update",
        "sudo apt install curl gnupg lsb-release software-properties-common python3-colcon-common-extensions python3-rosdep python3-vcstool",
        "sudo install -m 0755 -d /etc/apt/keyrings",
        "curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | sudo tee /etc/apt/keyrings/ros-archive-keyring.gpg >/dev/null",
        "echo deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main | sudo tee /etc/apt/sources.list.d/ros2.list",
        "sudo apt update",
        "sudo apt install ros-jazzy-desktop ros-dev-tools ros-jazzy-moveit ros-jazzy-moveit-resources-panda-moveit-config ros-jazzy-joint-state-publisher ros-jazzy-robot-state-publisher ros-jazzy-tf2-ros ros-jazzy-rmw-fastrtps-cpp",
        "sudo rosdep init || true",
        "rosdep update",
        "source /opt/ros/jazzy/setup.bash && scripts/phase9/build_ros2_workspace.sh",
        "python scripts/verify_phase9_1_ros2_integration.py",
        "python scripts/verify_phase9_1_moveit_safety.py",
    ],
    "preflight": {
        "sudo_available": shutil.which("sudo") is not None,
        "apt_available": shutil.which("apt") is not None,
        "curl_available": shutil.which("curl") is not None,
    },
}
Path(sys.argv[1]).write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

echo "Wrote install plan: $PLAN"

if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "24.04" ]]; then
  echo "BLOCKED_BY_ENV: ROS 2 Jazzy binary installation expects Ubuntu 24.04; found ${ID:-unknown} ${VERSION_ID:-unknown}."
  exit 0
fi

if [[ "$EXECUTE" != "1" ]]; then
  echo "DRY_RUN: rerun with --execute --yes on Ubuntu 24.04 to install ROS 2 Jazzy and MoveIt 2."
  exit 0
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "BLOCKED_BY_ENV: sudo is required for apt installation."
  exit 2
fi
if ! sudo -n true >/dev/null 2>&1; then
  echo "BLOCKED_BY_ENV: passwordless sudo is unavailable; run interactively with sudo privileges."
  exit 2
fi

sudo apt update
sudo apt install "${APT_YES[@]}" "${BASE_PACKAGES[@]}"
sudo install -m 0755 -d /etc/apt/keyrings
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  | sudo tee /etc/apt/keyrings/ros-archive-keyring.gpg >/dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list >/dev/null
sudo apt update
sudo apt install "${APT_YES[@]}" "${ROS_PACKAGES[@]}"
sudo rosdep init || true
rosdep update

echo "ROS 2 Jazzy and MoveIt 2 package installation complete."
echo "Next:"
echo "  source /opt/ros/jazzy/setup.bash"
echo "  scripts/phase9/build_ros2_workspace.sh"
echo "  python scripts/verify_phase9_1_ros2_integration.py"
echo "  python scripts/verify_phase9_1_moveit_safety.py"
