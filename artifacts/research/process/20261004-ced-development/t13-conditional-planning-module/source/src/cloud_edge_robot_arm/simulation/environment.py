"""仿真环境探测，报告 MuJoCo/Isaac/ROS2 可用性和 blocker。"""

from __future__ import annotations

import importlib.metadata
import importlib.util
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
    ros2_ready, ros_details, ros_blockers = _detect_ros2()
    moveit_ready, moveit_details, moveit_blockers = _detect_moveit()
    ros_installation_mode = _ros_installation_mode(
        {
            **ros_details.get("ros_package_prefixes", {}),
            **moveit_details.get("moveit_package_prefixes", {}),
        }
    )
    ros_details["ros_installation_mode"] = ros_installation_mode
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
        "vcstool": shutil.which("vcs") or "",
        "docker": shutil.which("docker") or "",
        "isaac_sim_root": os.environ.get("ISAAC_SIM_ROOT", ""),
        "isaac_sim_version": _isaac_version(),
        "mujoco_version": _package_version("mujoco"),
        "headless_egl_supported": os.environ.get("MUJOCO_GL") == "egl"
        or shutil.which("nvidia-smi") is not None,
        "camera_rendering_conditions": shutil.which("vulkaninfo") is not None
        or bool(os.environ.get("DISPLAY")),
        "core_ready": False,
        "ros2_ready": ros2_ready,
        "moveit_ready": moveit_ready,
        **ros_details,
        **moveit_details,
    }
    blockers: list[str] = []
    if not sys.version.startswith("3.12"):
        blockers.append("Python 3.12 is required for CORE_READY")
    if not details["mujoco_version"]:
        blockers.append("MuJoCo Python package is required for CORE_READY")
    core_ready = not blockers
    details["core_ready"] = core_ready
    if moveit_ready:
        level = "MOVEIT_READY"
    elif ros2_ready:
        level = "ROS2_READY"
    elif core_ready:
        level = "CORE_READY"
    else:
        level = "BLOCKED_BY_ENV"
    details["ros_blockers"] = ros_blockers
    details["moveit_blockers"] = moveit_blockers

    isaac_blockers = []
    if not details["isaac_sim_root"]:
        isaac_blockers.append("ISAAC_SIM_ROOT is not set")
    if not details["nvidia_gpu"]:
        isaac_blockers.append("NVIDIA GPU is not visible")
    if not details["vulkan_available"]:
        isaac_blockers.append("vulkaninfo is not available")
    if not isaac_blockers:
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


def _python_import_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _ros_package_prefix(package: str) -> str:
    try:
        from ament_index_python.packages import get_package_prefix
    except ModuleNotFoundError:
        get_package_prefix = None
    if get_package_prefix is not None:
        try:
            return str(get_package_prefix(package))
        except Exception:
            pass
    if shutil.which("ros2") is None:
        return ""
    return _command(["bash", "-lc", f"ros2 pkg prefix {package} 2>/dev/null"])


def _detect_ros2() -> tuple[bool, dict[str, Any], list[str]]:
    ros2_cli = shutil.which("ros2") or ""
    packages = {
        "rclpy": _ros_package_prefix("rclpy"),
    }
    details: dict[str, Any] = {
        "ros2_cli": ros2_cli,
        "rclpy_importable": _python_import_available("rclpy"),
        "ament_index_importable": _python_import_available("ament_index_python"),
        "ros_package_prefixes": packages,
        "ros_installation_mode": "unknown",
    }
    blockers: list[str] = []
    if os.environ.get("ROS_DISTRO") != "jazzy":
        blockers.append("ROS_DISTRO is not jazzy")
    if not ros2_cli:
        blockers.append("ros2 CLI is not available")
    if not details["rclpy_importable"]:
        blockers.append("rclpy is not importable in this Python environment")
    if not details["ament_index_importable"]:
        blockers.append("ament_index_python is not importable")
    if not packages["rclpy"]:
        blockers.append("rclpy package prefix is not available through ament index")
    return not blockers, details, blockers


def _detect_moveit() -> tuple[bool, dict[str, Any], list[str]]:
    required_packages = (
        "moveit_ros_move_group",
        "moveit_msgs",
        "moveit_configs_utils",
        "moveit_resources_panda_moveit_config",
    )
    prefixes = {package: _ros_package_prefix(package) for package in required_packages}
    details: dict[str, Any] = {
        "moveit_configs_utils_importable": _python_import_available("moveit_configs_utils"),
        "moveit_package_prefixes": prefixes,
        "moveit2_available": all(prefixes.values()),
    }
    blockers: list[str] = []
    if not details["moveit_configs_utils_importable"]:
        blockers.append("moveit_configs_utils is not importable")
    for package, prefix in prefixes.items():
        if not prefix:
            blockers.append(f"{package} package prefix is not available")
    return not blockers, details, blockers


def _ros_installation_mode(packages: dict[str, str]) -> str:
    prefixes = [prefix for prefix in packages.values() if prefix]
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix and any(prefix.startswith(conda_prefix) for prefix in prefixes):
        return "conda-robostack"
    if any(prefix.startswith("/opt/ros/") for prefix in prefixes):
        return "system-apt"
    if prefixes:
        return "sourced-workspace"
    return "unknown"


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
    return bool(_ros_package_prefix(package))
