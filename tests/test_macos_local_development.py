"""macOS local-development entrypoint contracts."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACOS_SCRIPTS = (
    ROOT / "scripts/macos/install.sh",
    ROOT / "scripts/macos/start.sh",
    ROOT / "scripts/macos/doctor.sh",
    ROOT / "scripts/macos/dev.sh",
)


def test_macos_scripts_are_executable_valid_bash_with_help() -> None:
    for script in MACOS_SCRIPTS:
        assert script.stat().st_mode & stat.S_IXUSR
        subprocess.run(["bash", "-n", str(script)], cwd=ROOT, check=True)
        result = subprocess.run(
            ["bash", str(script), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "Usage:" in result.stdout


def test_macos_install_contract_is_simulation_only() -> None:
    source = (ROOT / "scripts/macos/install.sh").read_text(encoding="utf-8")
    assert "dev,sim-mujoco,sim-analysis,sim-observability" in source
    assert "npm ci" in source
    assert "python@3.12" in source
    assert "node@22" in source
    assert "sudo" not in source
    assert "real_robot" not in source
    assert "ISAAC_SIM_ROOT" not in source


def test_macos_launcher_keeps_local_simulation_boundary() -> None:
    source = (ROOT / "scripts/macos/start.sh").read_text(encoding="utf-8")
    assert "RUNTIME_PROFILE:-simulation" in source
    assert "SIM_BACKEND:-mujoco" in source
    assert "MUJOCO_GL:-glfw" in source
    assert "--host 127.0.0.1" in source
    assert "cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app" in source
    assert "/api/v1/simulation/capabilities" in source
    assert "hardware" not in source.lower()
    assert "real_robot" not in source


def test_vite_proxy_is_configurable_for_macos_ports() -> None:
    source = (ROOT / "dashboard/vite.config.ts").read_text(encoding="utf-8")
    assert "DASHBOARD_BACKEND_ORIGIN" in source
    assert "DASHBOARD_FRONTEND_PORT" in source
