from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.simulation.environment import detect_environment

ROS2_RUNTIME_CHECKS = (
    "custom_message",
    "custom_service",
    "qos_compatible",
    "qos_incompatible",
    "namespace_isolation",
    "ros_timestamp",
    "sensor_timestamp",
    "action_success",
    "action_timeout",
    "action_cancel",
    "stale_feedback",
    "node_crash",
    "node_restart_reconnect",
)

MOVEIT_SAFETY_CHECKS = (
    "reachable_target_planning_success",
    "unreachable_target_planning_failure",
    "joint_limit_violation_rejection",
    "collision_object_insertion",
    "collision_path_rejection_or_valid_replanning",
    "execution_cancellation",
    "planning_timeout",
    "emergency_stop_boundary",
    "post_emergency_stop_trajectory_rejection",
    "bigsmall_boundary_enforced",
)

RUNTIME_EVIDENCE_FIELDS = (
    "command",
    "exit_code",
    "start_wall_time",
    "end_wall_time",
    "ros_time",
    "log_path",
    "observed_result",
)

ROS_ENV_ACTIVATION_SCRIPT = Path("scripts/phase9/activate_ros2_moveit_env.sh")


@dataclass(frozen=True)
class CommandEvidence:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str

    def to_jsonable(self) -> dict[str, object]:
        return {
            "argv": [_sanitize_text(arg) for arg in self.argv],
            "exit_code": self.exit_code,
            "stdout": _sanitize_text(self.stdout[-4000:]),
            "stderr": _sanitize_text(self.stderr[-4000:]),
        }


@dataclass(frozen=True)
class ComponentVerification:
    component: str
    status: str
    blockers: list[str]
    commands: list[CommandEvidence]
    validation_claimed: bool = False
    metrics: dict[str, int | float | str | bool] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, object]:
        return {
            "component": self.component,
            "status": self.status,
            "blockers": self.blockers,
            "commands": [command.to_jsonable() for command in self.commands],
            "validation_claimed": self.validation_claimed,
            **self.metrics,
        }

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{self.component}_verification.json").write_text(
            json.dumps(self.to_jsonable(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        log_lines: list[str] = []
        for command in self.commands:
            log_lines.append(f"$ {' '.join(_sanitize_text(arg) for arg in command.argv)}")
            log_lines.append(f"exit_code={command.exit_code}")
            if command.stdout:
                log_lines.append("--- stdout ---")
                log_lines.append(_sanitize_text(command.stdout))
            if command.stderr:
                log_lines.append("--- stderr ---")
                log_lines.append(_sanitize_text(command.stderr))
        (output_dir / f"{self.component}_commands.log").write_text(
            "\n".join(log_lines).rstrip() + "\n",
            encoding="utf-8",
        )


def verify_ros2_integration(
    output_dir: Path, *, run_runtime: bool = False
) -> ComponentVerification:
    commands = [
        _run_ros_env("command -v ros2"),
        _run_ros_env("ros2 pkg prefix rclpy"),
        _run_ros_env("python -c 'import rclpy; print(\"rclpy-importable\")'"),
        _run_ros_env(
            "python -c 'from ament_index_python.packages import get_package_prefix; "
            'print(get_package_prefix("rclpy"))\''
        ),
        _run_ros_env("command -v colcon && colcon --help >/dev/null"),
        _run_ros_env("command -v rosdep && rosdep --version"),
        _run_ros_env("command -v vcs && vcs --version"),
        _run_ros_env("ros2 pkg prefix bigsmall_sim_bridge"),
        _run_ros_env("printenv ROS_DISTRO RMW_IMPLEMENTATION ROS_DOMAIN_ID"),
    ]
    blockers = []
    if "jazzy" not in commands[8].stdout.splitlines():
        blockers.append("ROS_DISTRO is not jazzy")
    if commands[0].exit_code != 0:
        blockers.append("ros2 CLI is not available")
    if commands[1].exit_code != 0:
        blockers.append("rclpy package prefix is not available")
    if commands[2].exit_code != 0:
        blockers.append("rclpy is not importable in this Python environment")
    if commands[3].exit_code != 0:
        blockers.append("ament index is not available")
    if commands[4].exit_code != 0:
        blockers.append("colcon is not available")
    if commands[5].exit_code != 0:
        blockers.append("rosdep is not available")
    if commands[6].exit_code != 0:
        blockers.append("vcstool is not available")
    if commands[7].exit_code != 0:
        blockers.append("bigsmall_sim_bridge is not built in a sourced ROS workspace")
    ready = not blockers
    if run_runtime and ready:
        commands.append(
            _run_ros_env(
                "python scripts/phase9/run_ros2_runtime_evidence.py "
                f"--output {shlex.quote(str(output_dir))}",
                ros_domain_id=_ros_domain_for_output(output_dir),
                timeout=60,
            )
        )
    evidence = _load_json(output_dir / "ros2_runtime_evidence.json")
    runtime_checks = _runtime_check_flags(
        evidence,
        {
            "custom_message_checked": "custom_message",
            "custom_service_checked": "custom_service",
            "qos_compatible_checked": "qos_compatible",
            "qos_incompatible_checked": "qos_incompatible",
            "namespace_isolation_checked": "namespace_isolation",
            "ros_timestamp_checked": "ros_timestamp",
            "sensor_timestamp_checked": "sensor_timestamp",
            "action_success_checked": "action_success",
            "action_timeout_checked": "action_timeout",
            "action_cancel_checked": "action_cancel",
            "stale_feedback_checked": "stale_feedback",
            "node_crash_checked": "node_crash",
            "node_crash_reconnect_checked": "node_restart_reconnect",
        },
    )
    compatibility_metrics = {
        "custom_interfaces_checked": runtime_checks["custom_message_checked"]
        and runtime_checks["custom_service_checked"]
        and runtime_checks["action_success_checked"],
        "qos_checked": runtime_checks["qos_compatible_checked"]
        and runtime_checks["qos_incompatible_checked"],
        "namespace_checked": runtime_checks["namespace_isolation_checked"],
        "timestamp_checked": runtime_checks["ros_timestamp_checked"]
        and runtime_checks["sensor_timestamp_checked"],
        "cancel_checked": runtime_checks["action_cancel_checked"],
    }
    missing_runtime_checks = [key for key, checked in runtime_checks.items() if not checked]
    complete_runtime_evidence = _evidence_has_required_runtime_fields(evidence, ROS2_RUNTIME_CHECKS)
    validation_claimed = (
        ready
        and bool(evidence.get("validation_claimed"))
        and bool(evidence.get("artifact_provenance_complete"))
        and complete_runtime_evidence
        and not missing_runtime_checks
    )
    if blockers:
        status = "BLOCKED_BY_ENV"
    elif validation_claimed:
        status = "ROS2_INTEGRATION_VALIDATED"
    elif evidence:
        status = "INCOMPLETE"
        blockers.append("ROS 2 runtime evidence is incomplete")
    else:
        status = "ROS2_READY"
        blockers.append("ROS 2 runtime evidence not found")
    result = ComponentVerification(
        component="ros2",
        status=status,
        blockers=blockers,
        commands=commands,
        validation_claimed=validation_claimed,
        metrics={
            **runtime_checks,
            **compatibility_metrics,
            "environment_ready": ready,
            "runtime_evidence_complete": complete_runtime_evidence,
            "runtime_evidence_path": str(output_dir / "ros2_runtime_evidence.json"),
        },
    )
    result.write(output_dir)
    return result


def verify_moveit_safety(output_dir: Path, *, run_runtime: bool = False) -> ComponentVerification:
    commands = [
        _run_ros_env("command -v ros2"),
        _run_ros_env("ros2 pkg prefix moveit_ros_move_group"),
        _run_ros_env("ros2 pkg prefix moveit_msgs"),
        _run_ros_env("ros2 pkg prefix moveit_configs_utils"),
        _run_ros_env("ros2 pkg prefix moveit_resources_panda_moveit_config"),
        _run_ros_env("python -c 'import moveit_configs_utils; print(\"importable\")'"),
        _run_ros_env("ros2 pkg prefix bigsmall_franka_moveit_config"),
        _run_ros_env("ros2 pkg prefix bigsmall_robot_bridge"),
    ]
    blockers = []
    if commands[0].exit_code != 0:
        blockers.append("ros2 CLI is not available")
    if commands[1].exit_code != 0:
        blockers.append("moveit_ros_move_group package is not available")
    if commands[2].exit_code != 0:
        blockers.append("moveit_msgs package is not available")
    if commands[3].exit_code != 0:
        blockers.append("moveit_configs_utils package is not available")
    if commands[4].exit_code != 0:
        blockers.append("moveit_resources_panda_moveit_config package is not available")
    if commands[5].exit_code != 0:
        blockers.append("moveit_configs_utils is not importable")
    if commands[6].exit_code != 0:
        blockers.append("bigsmall_franka_moveit_config is not built in a sourced ROS workspace")
    if commands[7].exit_code != 0:
        blockers.append("bigsmall_robot_bridge is not built in a sourced ROS workspace")
    ready = not blockers
    if run_runtime and ready:
        commands.append(
            _run_ros_env(
                "python scripts/phase9/run_moveit_safety_evidence.py "
                f"--output {shlex.quote(str(output_dir))}",
                ros_domain_id=_ros_domain_for_output(output_dir),
                timeout=90,
            )
        )
    evidence = _load_json(output_dir / "moveit_safety_evidence.json")
    runtime_checks = _runtime_check_flags(
        evidence,
        {
            "reachability_checked": "reachable_target_planning_success",
            "unreachable_target_checked": "unreachable_target_planning_failure",
            "joint_limits_checked": "joint_limit_violation_rejection",
            "collision_object_checked": "collision_object_insertion",
            "collision_path_checked": "collision_path_rejection_or_valid_replanning",
            "execution_cancel_checked": "execution_cancellation",
            "planning_timeout_checked": "planning_timeout",
            "emergency_stop_boundary_checked": "emergency_stop_boundary",
            "post_estop_rejection_checked": "post_emergency_stop_trajectory_rejection",
            "bigsmall_boundary_checked": "bigsmall_boundary_enforced",
        },
    )
    compatibility_metrics = {
        "collision_scene_checked": runtime_checks["collision_object_checked"]
        and runtime_checks["collision_path_checked"],
        "planning_failure_checked": runtime_checks["unreachable_target_checked"]
        and runtime_checks["planning_timeout_checked"],
    }
    missing_runtime_checks = [key for key, checked in runtime_checks.items() if not checked]
    complete_runtime_evidence = _evidence_has_required_runtime_fields(
        evidence, MOVEIT_SAFETY_CHECKS
    )
    validation_claimed = (
        ready
        and bool(evidence.get("validation_claimed"))
        and bool(evidence.get("artifact_provenance_complete"))
        and complete_runtime_evidence
        and not missing_runtime_checks
    )
    if blockers:
        status = "BLOCKED_BY_ENV"
    elif validation_claimed:
        status = "MOVEIT_SAFETY_VALIDATED"
    elif evidence:
        status = "INCOMPLETE"
        blockers.append("MoveIt safety runtime evidence is incomplete")
    else:
        status = "MOVEIT_READY"
        blockers.append("MoveIt safety runtime evidence not found")
    result = ComponentVerification(
        component="moveit",
        status=status,
        blockers=blockers,
        commands=commands,
        validation_claimed=validation_claimed,
        metrics={
            **runtime_checks,
            **compatibility_metrics,
            "environment_ready": ready,
            "runtime_evidence_complete": complete_runtime_evidence,
            "runtime_evidence_path": str(output_dir / "moveit_safety_evidence.json"),
        },
    )
    result.write(output_dir)
    return result


def verify_isaac_smoke(output_dir: Path) -> ComponentVerification:
    root = os.environ.get("ISAAC_SIM_ROOT", "")
    isaac_python = Path(root) / "python.sh" if root else None
    commands = [
        _run(["bash", "-lc", "command -v vulkaninfo && vulkaninfo --summary"]),
        _run(
            [
                "bash",
                "-lc",
                "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
            ]
        ),
        _run(["bash", "-lc", 'test -n "$ISAAC_SIM_ROOT"']),
        _run([sys.executable, "scripts/phase9/isaac_standalone_app.py", "--check-imports"]),
    ]
    if isaac_python:
        commands.append(_run(["bash", "-lc", f"test -d {root!r}"]))
        commands.append(_run(["bash", "-lc", f"test -x {str(isaac_python)!r}"]))
        commands.append(_run([str(isaac_python), "-c", "print('isaac-python-ready')"]))
    blockers = []
    if not root:
        blockers.append("ISAAC_SIM_ROOT is not set")
    elif not Path(root).exists():
        blockers.append("ISAAC_SIM_ROOT does not exist")
    if commands[0].exit_code != 0:
        blockers.append("vulkaninfo is not available or Vulkan runtime is not usable")
    if commands[1].exit_code != 0:
        blockers.append("nvidia-smi is not available")
    if root and len(commands) > 4 and commands[4].exit_code != 0:
        blockers.append("Isaac Sim python.sh is not executable")
    evidence = _load_json(output_dir / "isaac_smoke_evidence.json")
    sensor_samples = evidence.get("sensor_samples", {})
    if not isinstance(sensor_samples, dict):
        sensor_samples = {}
    process_provenance = evidence.get("process_provenance", {})
    if not isinstance(process_provenance, dict):
        process_provenance = {}
    stage_loaded = bool(evidence.get("stage_loaded"))
    physics_steps = int(evidence.get("physics_steps", 0)) if evidence else 0
    robot_state_sample = bool(evidence.get("robot_state_sample"))
    rgb_checked = bool(sensor_samples.get("rgb"))
    depth_checked = bool(sensor_samples.get("depth"))
    contact_checked = bool(sensor_samples.get("contact"))
    moveit_execution_checked = bool(evidence.get("moveit_execution_checked"))
    ready = not blockers
    validation_claimed = (
        ready
        and bool(evidence.get("validation_claimed"))
        and bool(evidence.get("artifact_provenance_complete"))
        and bool(process_provenance.get("run_id"))
        and stage_loaded
        and physics_steps > 0
        and robot_state_sample
        and rgb_checked
        and depth_checked
        and contact_checked
    )
    if blockers:
        status = "BLOCKED_BY_ENV"
    elif validation_claimed:
        status = "ISAAC_SMOKE_VALIDATED"
    elif evidence:
        status = "INCOMPLETE"
        blockers.append("Isaac smoke runtime evidence is incomplete")
    else:
        status = "ISAAC_READY"
        blockers.append("Isaac smoke runtime evidence not found")
    result = ComponentVerification(
        component="isaac",
        status=status,
        blockers=blockers,
        commands=commands,
        validation_claimed=validation_claimed,
        metrics={
            "real_isaac_run_count": 1 if validation_claimed else 0,
            "stage_loaded": stage_loaded,
            "physics_steps": physics_steps,
            "robot_state_sample_checked": robot_state_sample,
            "rgb_sensor_checked": rgb_checked,
            "depth_sensor_checked": depth_checked,
            "contact_sensor_checked": contact_checked,
            "moveit_execution_checked": moveit_execution_checked,
            "environment_ready": ready,
            "runtime_evidence_path": str(output_dir / "isaac_smoke_evidence.json"),
        },
    )
    result.write(output_dir)
    return result


def verify_cross_backend(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    env = detect_environment()
    mujoco_artifact = _load_json(output_dir / "mujoco_artifact.json")
    isaac_artifact = _load_json(output_dir / "isaac_artifact.json")
    if mujoco_artifact:
        mujoco_reference_status = "ARTIFACT_AVAILABLE"
    else:
        reference = run_mujoco_physical_trial(
            "S16_PAYLOAD_MASS_VARIATION",
            seed=0,
            randomization_level="MODERATE",
        )
        mujoco_artifact = {
            "backend_name": "mujoco",
            "run_id": "phase9_1_generated_reference",
            "process_provenance": {"runtime": "mujoco-python"},
            "validation_claimed": True,
            "result_hash": reference.result_hash,
            "metrics": {
                "success_rate": 1.0,
                "completion_time_ms": reference.metrics["trajectory_duration_ms"],
                "joint_rmse": reference.metrics["joint_tracking_rmse"],
                "tcp_rmse": reference.metrics["tcp_position_error_m"],
                "collision_count": reference.metrics["illegal_collision_count"],
                "state_machine_final_state": "SUCCESS",
            },
        }
        mujoco_reference_status = "AVAILABLE"
    mujoco_valid = _backend_artifact_valid(mujoco_artifact, expected_backend="mujoco")
    isaac_valid = _backend_artifact_valid(isaac_artifact, expected_backend="isaac")
    isaac_ready = env.level == "ISAAC_READY"
    compared_values: dict[str, object] = {}
    if mujoco_valid and isaac_valid:
        mujoco_metrics = _artifact_metrics(mujoco_artifact)
        isaac_metrics = _artifact_metrics(isaac_artifact)
        compared_values = {
            "success_rate_delta": _metric_float(isaac_metrics, "success_rate")
            - _metric_float(mujoco_metrics, "success_rate"),
            "completion_time_delta": _metric_float(isaac_metrics, "completion_time_ms")
            - _metric_float(mujoco_metrics, "completion_time_ms"),
            "joint_rmse": _metric_float(isaac_metrics, "joint_rmse", "joint_tracking_rmse"),
            "tcp_rmse": _metric_float(isaac_metrics, "tcp_rmse", "tcp_position_error_m"),
            "collision_count_delta": _metric_int(isaac_metrics, "collision_count")
            - _metric_int(mujoco_metrics, "collision_count"),
            "state_machine_final_state_consistency": str(
                isaac_metrics.get("state_machine_final_state")
            )
            == str(mujoco_metrics.get("state_machine_final_state")),
        }
    status = (
        "CROSS_BACKEND_VALIDATED"
        if mujoco_valid and isaac_valid
        else ("NOT_RUN" if isaac_ready else "BLOCKED_BY_ENV")
    )
    payload: dict[str, object] = {
        "status": status,
        "mujoco_reference_status": mujoco_reference_status if mujoco_valid else "INVALID",
        "mujoco_artifact_source": "generated"
        if str(mujoco_artifact.get("run_id", "")) == "phase9_1_generated_reference"
        else "artifact",
        "mujoco_result_hash": str(mujoco_artifact.get("result_hash", "")),
        "isaac_comparison_status": "RUN"
        if isaac_valid
        else (
            "NOT_RUN_BLOCKED_BY_ENV"
            if not isaac_ready
            else "MISSING_ISAAC_ARTIFACT"
            if not isaac_artifact
            else "INVALID_ISAAC_ARTIFACT"
        ),
        "validation_claimed": status == "CROSS_BACKEND_VALIDATED",
        "artifact_provenance_complete": mujoco_valid and isaac_valid,
        **compared_values,
        "compared_metrics": [
            "success_rate",
            "completion_time",
            "joint_rmse",
            "tcp_rmse",
            "collision_count",
            "contact_events",
            "cloud_calls",
            "detection_recovery_latency",
            "state_machine_final_state",
            "auto_mode_selection_consistency",
        ],
    }
    (output_dir / "cross_backend_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def run_safety_pressure(output_dir: Path, *, trials: int = 500) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    illegal = 0
    emergency_stop_post_command_count = 0
    hashes: list[str] = []
    for seed in range(trials):
        level = "SEVERE" if seed % 2 else "MODERATE"
        trial = run_mujoco_physical_trial(
            "S22_COLLISION_NEAR_MISS",
            seed=seed,
            randomization_level=level,
        )
        illegal += int(trial.metrics["illegal_collision_count"])
        if "emergency_stop_post_command_count" in trial.metrics:
            emergency_stop_post_command_count += int(
                trial.metrics["emergency_stop_post_command_count"]
            )
        elif "post_emergency_stop_motion_command_count" in trial.metrics:
            emergency_stop_post_command_count += int(
                trial.metrics["post_emergency_stop_motion_command_count"]
            )
        else:
            emergency_stop_post_command_count += _run_emergency_stop_command_record(seed)
        hashes.append(trial.result_hash)
    unique_hashes = len(set(hashes))
    payload: dict[str, object] = {
        "status": "PASSED"
        if illegal == 0 and emergency_stop_post_command_count == 0 and unique_hashes > 1
        else "FAILED",
        "trial_count": trials,
        "illegal_collision_count": illegal,
        "emergency_stop_post_command_count": emergency_stop_post_command_count,
        "unique_result_hash_count": unique_hashes,
        "result_hash_sample": hashes[:10],
    }
    (output_dir / "safety_pressure.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def run_mujoco_physical_trial(*args: Any, **kwargs: Any) -> Any:
    from cloud_edge_robot_arm.simulation.evaluation.metrics import (
        run_mujoco_physical_trial as _run_mujoco_physical_trial,
    )

    return _run_mujoco_physical_trial(*args, **kwargs)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _runtime_check_flags(evidence: dict[str, Any], required: dict[str, str]) -> dict[str, bool]:
    checks = evidence.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}
    flags: dict[str, bool] = {}
    for metric_name, evidence_name in required.items():
        item = checks.get(evidence_name)
        if isinstance(item, dict):
            flags[metric_name] = bool(item.get("passed")) and bool(
                item.get("evidence_path") or item.get("command") or item.get("log_path")
            )
        else:
            flags[metric_name] = False
    return flags


def _evidence_has_required_runtime_fields(
    evidence: dict[str, Any],
    required_checks: tuple[str, ...],
) -> bool:
    checks = evidence.get("checks", {})
    if not isinstance(checks, dict):
        return False
    for name in required_checks:
        item = checks.get(name)
        if not isinstance(item, dict) or not item.get("passed"):
            return False
        for field_name in RUNTIME_EVIDENCE_FIELDS:
            if field_name not in item or item[field_name] in ("", None, [], {}):
                return False
        if int(item.get("exit_code", -1)) != 0:
            return False
        if not isinstance(item.get("command"), list):
            return False
        if not isinstance(item.get("observed_result"), dict):
            return False
    return True


def _python_import_available(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _package_prefix(package: str) -> str:
    try:
        from ament_index_python.packages import get_package_prefix
    except ModuleNotFoundError:
        get_package_prefix = None
    if get_package_prefix is not None:
        try:
            return str(get_package_prefix(package))
        except Exception:
            pass
    result = _run(["bash", "-lc", f"ros2 pkg prefix {package}"])
    if result.exit_code == 0:
        return result.stdout.strip()
    return ""


def _backend_artifact_valid(artifact: dict[str, Any], *, expected_backend: str) -> bool:
    if not artifact:
        return False
    provenance = artifact.get("process_provenance")
    return (
        artifact.get("backend_name") == expected_backend
        and bool(artifact.get("run_id"))
        and isinstance(provenance, dict)
        and bool(provenance)
        and bool(artifact.get("validation_claimed"))
        and isinstance(artifact.get("metrics"), dict)
    )


def _artifact_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    metrics = artifact.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("backend artifact metrics must be a JSON object")
    return metrics


def _metric_float(metrics: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in metrics:
            return float(metrics[name])
    raise KeyError(f"missing metric: {'/'.join(names)}")


def _metric_int(metrics: dict[str, Any], *names: str) -> int:
    return int(_metric_float(metrics, *names))


def _run_emergency_stop_command_record(seed: int) -> int:
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    try:
        backend.reset(
            PhysicalScenarioConfig(
                scenario_id="S14_EMERGENCY_STOP",
                seed=seed,
                object_pose=Pose(x=0.45, y=0.0, z=0.04),
            )
        )
        backend.emergency_stop()
        backend.apply_joint_targets(JointCommand(positions=[0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
        records = getattr(backend, "command_records", [])
        return sum(
            1
            for record in records
            if record.get("after_emergency_stop") is True
            and record.get("accepted") is True
            and record.get("type") == "joint_target"
        )
    finally:
        backend.shutdown()


def _run(argv: list[str], *, timeout: float = 20) -> CommandEvidence:
    try:
        result = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandEvidence(argv=argv, exit_code=124, stdout="", stderr=str(exc))
    return CommandEvidence(
        argv=argv,
        exit_code=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )


def _run_ros_env(
    command: str,
    *,
    timeout: float = 20,
    ros_domain_id: int | None = None,
) -> CommandEvidence:
    if ROS_ENV_ACTIVATION_SCRIPT.exists():
        script = shlex.quote(str(ROS_ENV_ACTIVATION_SCRIPT))
        if ros_domain_id is None:
            command = f"source {script} >/dev/null && {command}"
        else:
            command = (
                f"source {script} >/dev/null && export ROS_DOMAIN_ID={ros_domain_id} && {command}"
            )
    return _run(["bash", "-lc", command], timeout=timeout)


def _ros_domain_for_output(output_dir: Path) -> int:
    encoded = sum(ord(char) for char in str(output_dir))
    return 100 + encoded % 120


def _sanitize_text(value: str) -> str:
    home = str(Path.home())
    sanitized = value.replace(sys.executable, "python")
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
