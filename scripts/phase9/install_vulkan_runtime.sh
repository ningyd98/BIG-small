#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ROOT_DIR/artifacts/phase9_1/install}"
EXECUTE=0
ASSUME_YES=0

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
      sed -n '1,80p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$ARTIFACT_DIR"
LOG="$ARTIFACT_DIR/install_vulkan_runtime.log"
PLAN="$ARTIFACT_DIR/vulkan_install_plan.json"
exec > >(tee "$LOG") 2>&1

APT_YES=()
if [[ "$ASSUME_YES" == "1" ]]; then
  APT_YES=(-y)
fi

cat >"$PLAN" <<'JSON'
{
  "script": "scripts/phase9/install_vulkan_runtime.sh",
  "core_python_environment": "unchanged",
  "packages": ["vulkan-tools", "mesa-vulkan-drivers"],
  "nvidia_note": "Use the distribution NVIDIA driver package or vendor driver appropriate for the host GPU.",
  "post_check": "vulkaninfo --summary"
}
JSON

echo "Wrote Vulkan install plan: $PLAN"
if [[ "$EXECUTE" != "1" ]]; then
  echo "DRY_RUN: rerun with --execute --yes to install vulkan-tools and Mesa Vulkan ICD packages."
  command -v vulkaninfo >/dev/null 2>&1 && vulkaninfo --summary || true
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
sudo apt install "${APT_YES[@]}" vulkan-tools mesa-vulkan-drivers
vulkaninfo --summary
