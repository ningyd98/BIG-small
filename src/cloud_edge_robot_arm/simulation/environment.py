from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnvironmentReport:
    level: str
    blockers: list[str]
    details: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {"level": self.level, "blockers": self.blockers, "details": self.details}

    def write(self, artifact_dir: Path) -> None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = self.to_jsonable()
        (artifact_dir / "environment_report.json").write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        blockers = "\n".join(f"- {item}" for item in self.blockers) or "- none"
        details = "\n".join(
            f"- `{key}`: {value if value != '' else '<unset>'}"
            for key, value in sorted(self.details.items())
        )
        (artifact_dir / "environment_report.md").write_text(
            f"# Phase 9 Environment Report\n\n"
            f"Level: `{self.level}`\n\n"
            f"## Blockers\n\n{blockers}\n\n"
            f"## Details\n\n{details}\n",
            encoding="utf-8",
        )


def detect_environment() -> EnvironmentReport:
    details: dict[str, Any] = {
        "os": platform.platform(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "cpu": _command(["bash", "-lc", "lscpu | sed -n 's/Model name:[[:space:]]*//p' | head -1"]),
        "cpu_count": os.cpu_count(),
        "memory": _command(["bash", "-lc", "free -h | awk '/Mem:/ {print $2}'"]),
        "disk_available": _command(["bash", "-lc", "df -h . | awk 'NR==2 {print $4}'"]),
        "python": sys.version.split()[0],
        "nvidia_gpu": _command(
            ["bash", "-lc", "nvidia-smi --query-gpu=name --format=csv,noheader | head -1"]
        ),
        "nvidia_vram": _command(
            ["bash", "-lc", "nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1"]
        ),
        "nvidia_driver": _command(
            ["bash", "-lc", "nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1"]
        ),
        "cuda_visible": shutil.which("nvidia-smi") is not None,
        "vulkan_available": shutil.which("vulkaninfo") is not None,
        "display": os.environ.get("DISPLAY", ""),
        "egl_available": os.environ.get("MUJOCO_GL") == "egl"
        or bool(os.environ.get("EGL_PLATFORM")),
        "ros_distro": os.environ.get("ROS_DISTRO", ""),
        "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", ""),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
        "colcon": shutil.which("colcon") or "",
        "rosdep": shutil.which("rosdep") or "",
        "docker": shutil.which("docker") or "",
        "isaac_sim_root": os.environ.get("ISAAC_SIM_ROOT", ""),
        "isaac_sim_version": _isaac_version(),
        "moveit2_available": _ros_package_available("moveit_ros_planning_interface"),
        "mujoco_version": _package_version("mujoco"),
        "headless_egl_supported": os.environ.get("MUJOCO_GL") == "egl"
        or shutil.which("nvidia-smi") is not None,
        "camera_rendering_conditions": shutil.which("vulkaninfo") is not None
        or bool(os.environ.get("DISPLAY")),
    }
    blockers: list[str] = []
    if not sys.version.startswith("3.12"):
        blockers.append("Python 3.12 is required for CORE_READY")
    if not details["mujoco_version"]:
        blockers.append("MuJoCo Python package is required for CORE_READY")
    level = "CORE_READY" if not blockers else "BLOCKED_BY_ENV"

    ros_blockers = []
    if details["ros_distro"] != "jazzy":
        ros_blockers.append("ROS_DISTRO is not jazzy")
    if not details["colcon"]:
        ros_blockers.append("colcon is not available")
    if not details["rosdep"]:
        ros_blockers.append("rosdep is not available")
    if not details["moveit2_available"]:
        ros_blockers.append("MoveIt 2 package not found")
    if level == "CORE_READY" and not ros_blockers:
        level = "ROS_READY"
    else:
        details["ros_blockers"] = ros_blockers

    isaac_blockers = []
    if not details["isaac_sim_root"]:
        isaac_blockers.append("ISAAC_SIM_ROOT is not set")
    if not details["nvidia_gpu"]:
        isaac_blockers.append("NVIDIA GPU is not visible")
    if not details["vulkan_available"]:
        isaac_blockers.append("vulkaninfo is not available")
    if level == "ROS_READY" and not isaac_blockers:
        level = "ISAAC_READY"
    else:
        details["isaac_blockers"] = isaac_blockers

    if level == "BLOCKED_BY_ENV":
        details["core_blockers"] = blockers
    return EnvironmentReport(level=level, blockers=blockers, details=details)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _command(argv: list[str]) -> str:
    try:
        result = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _isaac_version() -> str:
    root = os.environ.get("ISAAC_SIM_ROOT")
    if not root:
        return ""
    candidates = [Path(root) / "VERSION", Path(root) / "kit" / "VERSION"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0]
    return "unknown"


def _ros_package_available(package: str) -> bool:
    if shutil.which("ros2") is None:
        return False
    result = _command(["bash", "-lc", f"ros2 pkg prefix {package} >/dev/null 2>&1 && echo yes"])
    return result == "yes"
