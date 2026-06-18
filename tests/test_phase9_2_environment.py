"""Phase 9.2 跨后端和 Isaac 环境回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from cloud_edge_robot_arm.simulation.phase9_2.verification import (
    CommandResult,
    Phase92RuntimeConfig,
    build_isaac_runtime_command,
    collect_environment_compatibility,
    run_isaac_smoke_runtime,
)


def test_standalone_runtime_command_uses_isaac_python_not_core_python() -> None:
    config = Phase92RuntimeConfig(
        mode="standalone",
        repo_root=Path("/repo/BIG-small"),
        output_dir=Path("/repo/BIG-small/artifacts/phase9_2/isaac"),
        isaac_sim_root=Path("/opt/isaac-sim-6.0"),
    )

    command = build_isaac_runtime_command(config, ["--smoke"])

    assert command.argv[:2] == [
        "/opt/isaac-sim-6.0/python.sh",
        "scripts/phase9/isaac_standalone_app.py",
    ]
    assert "--headless" in command.argv
    assert "--smoke" in command.argv
    assert command.env["ISAAC_SIM_ROOT"] == "/opt/isaac-sim-6.0"
    assert "PYTHONPATH" not in command.env


def test_container_runtime_command_records_fixed_image_and_eula() -> None:
    config = Phase92RuntimeConfig(
        mode="container",
        repo_root=Path("/repo/BIG-small"),
        output_dir=Path("/repo/BIG-small/artifacts/phase9_2/isaac"),
        container_image="nvcr.io/nvidia/isaac-sim:6.0.0",
        container_digest="sha256:1234",
    )

    command = build_isaac_runtime_command(config, ["--smoke"])

    assert command.argv[:5] == ["docker", "run", "--rm", "--gpus", "all"]
    assert "--network" in command.argv
    assert "host" in command.argv
    assert "-e" in command.argv
    assert "ACCEPT_EULA=Y" in command.argv
    assert "nvcr.io/nvidia/isaac-sim:6.0.0" in command.argv
    assert "latest" not in " ".join(command.argv)
    assert command.image_digest == "sha256:1234"
    assert any("/repo/BIG-small:/workspace/BIG-small" in item for item in command.argv)


def test_environment_compatibility_records_blocked_commands(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], timeout: float = 20.0) -> CommandResult:
        calls.append(argv)
        joined = " ".join(argv)
        if "nvidia-smi" in joined:
            return CommandResult(argv, 1, "", "nvidia-smi unavailable")
        if "vulkaninfo" in joined:
            return CommandResult(argv, 127, "", "vulkaninfo: not found")
        if "isaac_standalone_app.py" in joined:
            return CommandResult(argv, 2, "", "Isaac imports unavailable")
        return CommandResult(argv, 0, "ok", "")

    report = collect_environment_compatibility(tmp_path, runner=fake_runner)

    assert report["status"] == "BLOCKED_BY_ENV"
    blockers = cast(list[str], report["blockers"])
    assert "NVIDIA GPU is not visible" in blockers
    assert "Vulkan runtime is not usable" in blockers
    assert "Isaac Sim compatibility checker failed" in blockers
    assert (tmp_path / "compatibility_report.json").exists()
    assert (tmp_path / "compatibility_report.md").exists()
    assert (tmp_path / "nvidia_smi.txt").read_text(encoding="utf-8")
    assert (tmp_path / "vulkan_summary.txt").read_text(encoding="utf-8")
    assert (tmp_path / "isaac_compatibility_checker.log").read_text(encoding="utf-8")
    assert any("nvidia-smi" in " ".join(call) for call in calls)


def test_environment_auto_discovers_local_isaac_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    venv = home / ".venvs" / "bigsmall-isaacsim-6.0.0.1"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("#!/usr/bin/env python\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ISAAC_SIM_ROOT", raising=False)
    monkeypatch.delenv("ISAAC_RUNTIME_MODE", raising=False)
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], timeout: float = 20.0) -> CommandResult:
        calls.append(argv)
        joined = " ".join(argv)
        if "nvidia-smi" in joined:
            return CommandResult(argv, 0, "NVIDIA GPU, 595.71.05, 16376 MiB", "")
        if "vulkaninfo" in joined:
            return CommandResult(argv, 0, "VULKANINFO", "")
        return CommandResult(argv, 1, "Do you accept the EULA? (Yes/No):", "EOF")

    report = collect_environment_compatibility(tmp_path / "artifacts", runner=fake_runner)

    blockers = cast(list[str], report["blockers"])
    assert "ISAAC_SIM_ROOT is not set" not in blockers
    assert "Isaac Sim compatibility checker failed" in blockers
    assert calls[2][0] == str(venv / "bin" / "python")
    details = cast(dict[str, object], report["details"])
    assert details["isaac_runtime_mode"] == "standalone"
    assert details["isaac_runtime_source"] == "auto_detected"


def test_isaac_smoke_runtime_uses_configured_standalone_command(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], timeout: float = 20.0) -> CommandResult:
        calls.append(argv)
        return CommandResult(argv, 2, '{"status": "BLOCKED_BY_ENV"}', "Isaac unavailable")

    config = Phase92RuntimeConfig(
        mode="standalone",
        repo_root=Path("/repo/BIG-small"),
        output_dir=tmp_path,
        isaac_sim_root=Path("/opt/isaac-sim-6.0"),
    )

    result = run_isaac_smoke_runtime(tmp_path, config=config, runner=fake_runner)

    assert result["status"] == "INCOMPLETE"
    assert calls
    assert calls[0][0] == "/opt/isaac-sim-6.0/python.sh"
    assert "--smoke" in calls[0]
    assert "--output" in calls[0]
    assert (tmp_path / "process_stdout.log").read_text(encoding="utf-8")
    assert (tmp_path / "process_stderr.log").read_text(encoding="utf-8")
    assert (tmp_path / "isaac_commands.log").read_text(encoding="utf-8")
