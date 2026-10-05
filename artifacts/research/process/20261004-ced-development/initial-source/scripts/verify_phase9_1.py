#!/usr/bin/env python
"""Phase 9.1 ROS2/Isaac/MoveIt 边界验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_1.verification import (  # type: ignore[import-untyped]
    run_safety_pressure,
    verify_cross_backend,
    verify_isaac_smoke,
    verify_moveit_safety,
    verify_ros2_integration,
)

TIME_DOMAINS = [
    "simulation_time",
    "ros_time",
    "wall_clock_time",
    "sensor_timestamp",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Phase 9.1 ROS/MoveIt/Isaac readiness evidence."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_1"),
        help="Directory for verifier artifacts.",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Skip Phase 9 core history regression when only checking Phase 9.1 artifacts.",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    history = _run_history(args.output) if not args.skip_history else _skipped_history()
    install_readiness = _collect_install_readiness(args.output / "install")
    process_protocol_guard = _run_process_protocol_guard(args.output / "process_protocol")
    isaac_backend_guard = _run_isaac_backend_guard(args.output / "isaac_backend")
    isaac_benchmark_guard = _run_isaac_benchmark_guard(args.output / "isaac_benchmark")
    ros_interface_guard = _run_ros_interface_guard(args.output / "ros_interfaces")
    ros_bridge_source_guard = _run_ros_bridge_source_guard(args.output / "ros_bridge_sources")
    moveit_source_guard = _run_moveit_source_guard(args.output / "moveit_sources")
    ros2 = verify_ros2_integration(args.output / "ros2", run_runtime=True)
    if ros2.status == "ROS2_INTEGRATION_VALIDATED":
        time.sleep(2.0)
    moveit = verify_moveit_safety(args.output / "moveit", run_runtime=True)
    isaac = verify_isaac_smoke(args.output / "isaac")
    cross_backend = verify_cross_backend(args.output / "cross_backend")
    safety_pressure = run_safety_pressure(args.output / "safety_pressure", trials=500)

    components = {
        "ros2": ros2.to_jsonable(),
        "moveit": moveit.to_jsonable(),
        "isaac": isaac.to_jsonable(),
    }
    status = _phase9_1_status(
        components=components,
        cross_backend=cross_backend,
        isaac_benchmark_guard=isaac_benchmark_guard,
        safety_pressure=safety_pressure,
        history=history,
        process_protocol_guard=process_protocol_guard,
        isaac_backend_guard=isaac_backend_guard,
        ros_interface_guard=ros_interface_guard,
        ros_bridge_source_guard=ros_bridge_source_guard,
        moveit_source_guard=moveit_source_guard,
    )
    summary: dict[str, Any] = {
        "status": status,
        "components": components,
        "cross_backend": cross_backend,
        "safety_pressure": safety_pressure,
        "install_readiness": install_readiness,
        "process_protocol_guard": process_protocol_guard,
        "isaac_backend_guard": isaac_backend_guard,
        "isaac_benchmark_guard": isaac_benchmark_guard,
        "ros_interface_guard": ros_interface_guard,
        "ros_bridge_source_guard": ros_bridge_source_guard,
        "moveit_source_guard": moveit_source_guard,
        "history": history,
        "time_domains": TIME_DOMAINS,
        "validation_claimed": status == "PHASE9_1_ACCEPTED",
    }
    (args.output / "phase9_1_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "phase9_1_report.md").write_text(_render_report(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 1 if status == "PHASE9_1_REJECTED" else 0


def _run_history(output_dir: Path) -> dict[str, object]:
    command, result = _run_core_python_command(["scripts/verify_phase9.py"])
    payload: dict[str, object] = {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "phase9_history_check.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _skipped_history() -> dict[str, object]:
    return {
        "command": [],
        "returncode": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "skipped": True,
    }


def _phase9_1_acceptance_ready(
    *,
    components: dict[str, dict[str, object]],
    cross_backend: dict[str, object],
    isaac_benchmark_guard: dict[str, object],
    safety_pressure: dict[str, object],
) -> bool:
    ros2 = components["ros2"]
    moveit = components["moveit"]
    isaac = components["isaac"]
    ros_required = (
        "custom_interfaces_checked",
        "qos_checked",
        "namespace_checked",
        "timestamp_checked",
        "action_timeout_checked",
        "cancel_checked",
        "node_crash_reconnect_checked",
    )
    moveit_required = (
        "reachability_checked",
        "joint_limits_checked",
        "collision_scene_checked",
        "planning_failure_checked",
        "execution_cancel_checked",
        "emergency_stop_boundary_checked",
    )
    cross_required = (
        "success_rate_delta",
        "completion_time_delta",
        "joint_rmse",
        "tcp_rmse",
        "collision_count_delta",
        "state_machine_final_state_consistency",
    )
    return (
        ros2.get("validation_claimed") is True
        and all(ros2.get(key) is True for key in ros_required)
        and moveit.get("validation_claimed") is True
        and all(moveit.get(key) is True for key in moveit_required)
        and isaac.get("validation_claimed") is True
        and _int_value(isaac.get("real_isaac_run_count", 0)) > 0
        and isaac_benchmark_guard.get("validation_claimed") is True
        and isaac_benchmark_guard.get("benchmark_status") == "PASSED"
        and cross_backend.get("validation_claimed") is True
        and cross_backend.get("artifact_provenance_complete") is True
        and all(key in cross_backend for key in cross_required)
        and safety_pressure.get("status") == "PASSED"
        and _int_value(safety_pressure.get("trial_count", 0)) >= 500
        and _int_value(safety_pressure.get("illegal_collision_count", -1)) == 0
        and _int_value(safety_pressure.get("emergency_stop_post_command_count", -1)) == 0
        and _int_value(safety_pressure.get("unique_result_hash_count", 0)) > 1
    )


def _phase9_1_status(
    *,
    components: dict[str, dict[str, object]],
    cross_backend: dict[str, object],
    isaac_benchmark_guard: dict[str, object],
    safety_pressure: dict[str, object],
    history: dict[str, object],
    process_protocol_guard: dict[str, object],
    isaac_backend_guard: dict[str, object],
    ros_interface_guard: dict[str, object],
    ros_bridge_source_guard: dict[str, object],
    moveit_source_guard: dict[str, object],
) -> str:
    if (
        history["returncode"] != 0
        or safety_pressure["status"] != "PASSED"
        or process_protocol_guard["status"] != "PASSED"
        or isaac_backend_guard["status"] != "PASSED"
        or isaac_benchmark_guard["status"] == "FAILED"
        or ros_interface_guard["status"] != "PASSED"
        or ros_bridge_source_guard["status"] != "PASSED"
        or moveit_source_guard["status"] != "PASSED"
    ):
        return "PHASE9_1_REJECTED"
    if _phase9_1_acceptance_ready(
        components=components,
        cross_backend=cross_backend,
        isaac_benchmark_guard=isaac_benchmark_guard,
        safety_pressure=safety_pressure,
    ):
        return "PHASE9_1_ACCEPTED"
    if not _component_allows_core_acceptance(components["ros2"], "ROS2_INTEGRATION_VALIDATED"):
        return "PHASE9_1_REJECTED"
    if not _component_allows_core_acceptance(components["moveit"], "MOVEIT_SAFETY_VALIDATED"):
        return "PHASE9_1_REJECTED"
    if _blocked_by_environment(components["isaac"]) and _cross_backend_blocked_by_environment(
        cross_backend
    ):
        return "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK"
    return "PHASE9_1_REJECTED"


def _component_allows_core_acceptance(component: dict[str, object], validated_status: str) -> bool:
    status = str(component.get("status", ""))
    if status == validated_status:
        return component.get("validation_claimed") is True
    return _blocked_by_environment(component)


def _blocked_by_environment(component: dict[str, object]) -> bool:
    return (
        component.get("status") == "BLOCKED_BY_ENV"
        and component.get("validation_claimed") is False
        and component.get("environment_ready") is False
    )


def _cross_backend_blocked_by_environment(cross_backend: dict[str, object]) -> bool:
    return (
        cross_backend.get("status") == "BLOCKED_BY_ENV"
        and cross_backend.get("validation_claimed") is False
        and cross_backend.get("isaac_comparison_status") == "NOT_RUN_BLOCKED_BY_ENV"
    )


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def _collect_install_readiness(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = [
        ["bash", "scripts/phase9/install_ros2_jazzy.sh", "--artifact-dir", str(output_dir)],
        ["bash", "scripts/phase9/install_vulkan_runtime.sh", "--artifact-dir", str(output_dir)],
        [_core_python_executable(), "scripts/phase9/check_isaac_sim.py"],
    ]
    evidence: list[dict[str, object]] = []
    env = os.environ.copy()
    env["ARTIFACT_DIR"] = str(output_dir)
    for command in commands:
        command_env = _core_python_env() if command[0] == _core_python_executable() else env
        command_env["ARTIFACT_DIR"] = str(output_dir)
        result = subprocess.run(
            command, check=False, text=True, capture_output=True, env=command_env
        )
        evidence.append(
            {
                "argv": [
                    "python"
                    if item in {sys.executable, _core_python_executable()}
                    else _sanitize_text(item)
                    for item in command
                ],
                "exit_code": result.returncode,
                "stdout": _sanitize_text(result.stdout[-4000:]),
                "stderr": _sanitize_text(result.stderr[-4000:]),
            }
        )
    payload: dict[str, object] = {
        "status": "RECORDED",
        "execute_mode": "dry_run",
        "core_python_environment": "unchanged",
        "ros_environment": "/opt/ros/jazzy plus ros2_ws/install after explicit install",
        "isaac_environment": "official Isaac Sim runtime selected by ISAAC_SIM_ROOT",
        "commands": evidence,
    }
    (output_dir / "install_readiness.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_process_protocol_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        ["-m", "pytest", "-q", "tests/test_phase9_1_isaac_process_protocol.py"]
    )
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": False,
        "purpose": (
            "verifies external JSONL process protocol and replay rejection; "
            "not an Isaac runtime validation"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "process_protocol_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_isaac_backend_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        ["-m", "pytest", "-q", "tests/test_phase9_1_isaac_backend.py"]
    )
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": False,
        "purpose": (
            "verifies IsaacSimBackend SimulatorBackend protocol adapter; "
            "not an Isaac runtime validation"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "isaac_backend_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_isaac_benchmark_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        [
            "scripts/run_phase9_benchmarks.py",
            "--backend",
            "isaac",
            "--suite",
            "smoke",
            "--output",
            str(output_dir),
        ]
    )
    summary_path = output_dir / "phase9_smoke_isaac" / "summary.json"
    benchmark_status = "MISSING_SUMMARY"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        benchmark_status = str(summary.get("status", summary.get("acceptance_status", "")))
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "benchmark_status": benchmark_status,
        "validation_claimed": benchmark_status == "PASSED",
        "purpose": (
            "runs Isaac smoke benchmark entrypoint; blocked hosts must not fall back to MuJoCo"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "isaac_benchmark_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_ros_interface_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        ["-m", "pytest", "-q", "tests/test_phase9_1_ros2_interfaces.py"]
    )
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": False,
        "purpose": (
            "verifies ROS 2 interface source coverage; not a ROS 2 build or runtime validation"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "ros_interface_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_ros_bridge_source_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        ["-m", "pytest", "-q", "tests/test_phase9_1_ros2_bridge_sources.py"]
    )
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": False,
        "purpose": (
            "verifies ROS 2 bridge node source coverage; not a ROS 2 build or runtime validation"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "ros_bridge_source_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_moveit_source_guard(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command, result = _run_core_python_command(
        ["-m", "pytest", "-q", "tests/test_phase9_1_moveit_sources.py"]
    )
    payload: dict[str, object] = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": False,
        "purpose": (
            "verifies MoveIt boundary node source coverage; "
            "not a MoveIt 2 build or runtime validation"
        ),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "moveit_source_guard.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _run_core_python_command(args: list[str]) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    command = [_core_python_executable(), *args]
    display_command = ["python", *args]
    result = subprocess.run(
        command, check=False, text=True, capture_output=True, env=_core_python_env()
    )
    return display_command, result


def _core_python_executable() -> str:
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if "/envs/" in conda_prefix:
        candidate = Path(conda_prefix.split("/envs/", maxsplit=1)[0]) / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _core_python_env() -> dict[str, str]:
    env = os.environ.copy()
    active_conda_prefix = env.get("CONDA_PREFIX", "")
    for key in (
        "AMENT_PREFIX_PATH",
        "COLCON_PREFIX_PATH",
        "CMAKE_PREFIX_PATH",
        "PYTHONPATH",
        "ROS_DISTRO",
        "ROS_DOMAIN_ID",
        "ROS_PYTHON_VERSION",
        "ROS_VERSION",
        "RMW_IMPLEMENTATION",
    ):
        env.pop(key, None)
    if active_conda_prefix and "/envs/" in active_conda_prefix:
        env.pop("CONDA_PREFIX", None)
        env.pop("CONDA_DEFAULT_ENV", None)
        env.pop("CONDA_PROMPT_MODIFIER", None)
        path_entries = env.get("PATH", "").split(os.pathsep)
        filtered_path = [
            entry
            for entry in path_entries
            if entry
            and not entry.startswith(active_conda_prefix)
            and "bigsmall_runtime/ros2_ws/install" not in entry
        ]
        core_bin = str(Path(_core_python_executable()).parent)
        env["PATH"] = os.pathsep.join([core_bin, *filtered_path])
    return env


def _sanitize_text(value: str) -> str:
    home = str(Path.home())
    sanitized = value.replace(sys.executable, "python")
    sanitized = sanitized.replace(_core_python_executable(), "python")
    if home:
        sanitized = sanitized.replace(home, "$HOME")
    sanitized = re.sub(r"/home/[A-Za-z0-9_.-]+", "$HOME", sanitized)
    for env_name in ("USER", "LOGNAME"):
        env_value = os.environ.get(env_name, "")
        if env_value:
            sanitized = sanitized.replace(env_value, f"${env_name}")
    sanitized = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1<redacted>@", sanitized)
    sanitized = re.sub(
        r"(?i)\b(token|password|secret|https?_proxy)=([^\s]+)",
        lambda match: f"{match.group(1)}=<redacted>",
        sanitized,
    )
    return sanitized


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 9.1 Verification Report",
        "",
        f"Status: `{summary['status']}`",
        "",
        "## Components",
        "",
    ]
    components = summary["components"]
    for name in ("ros2", "moveit", "isaac"):
        item = components[name]
        lines.append(
            f"- `{name}`: `{item['status']}`, validation_claimed={item['validation_claimed']}"
        )
        blockers = item.get("blockers", [])
        if blockers:
            lines.append(f"  blockers: {', '.join(str(blocker) for blocker in blockers)}")
    lines.extend(
        [
            "",
            "## Time Domains",
            "",
            *[f"- `{domain}`" for domain in summary["time_domains"]],
            "",
            "## Cross Backend",
            "",
            f"- status: `{summary['cross_backend']['status']}`",
            f"- Isaac comparison: `{summary['cross_backend']['isaac_comparison_status']}`",
            "",
            "This report does not claim real Isaac Sim, ROS 2, MoveIt 2, "
            "or hardware validation when a component is blocked by environment.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
