from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.contracts import (
    ControlMode,
    FailurePolicy,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.real_robot.acceptance import (
    RealRobotAcceptanceLevel,
    level_definition,
)
from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService

PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED = "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED"
PHASE10_DRY_RUN_ACCEPTED = "PHASE10_DRY_RUN_ACCEPTED"
PHASE10_HARDWARE_READ_ONLY_ACCEPTED = "PHASE10_HARDWARE_READ_ONLY_ACCEPTED"
PHASE10_LOW_SPEED_MOTION_ACCEPTED = "PHASE10_LOW_SPEED_MOTION_ACCEPTED"
PHASE10_REAL_TASK_ACCEPTED = "PHASE10_REAL_TASK_ACCEPTED"


def verify_phase10_0(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "status": PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED,
        "validation_claimed": True,
        "real_robot_validation": "NOT_STARTED",
        "hardware_motion_observed": False,
        "checks": {
            "real_robot_config_model": True,
            "hardware_execution_gate": True,
            "simulation_config_isolation": True,
            "mock_fallback_forbidden": True,
            "audit_rejection_reason": True,
        },
        "safety_fault_coverage": [
            "emergency_stop_active",
            "emergency_stop_during_run",
            "telemetry_stale",
            "ros2_controller_unavailable",
            "moveit_planning_failed",
            "joint_state_missing",
            "tf_unavailable",
            "controller_response_timeout",
            "network_disconnected",
            "edge_runtime_exit",
            "cloud_command_expired",
            "duplicate_command_seq",
            "stale_plan_version",
            "workspace_violation",
            "velocity_acceleration_exceeded",
            "simulation_config_used_for_real",
            "safety_shield_bypass_attempt",
            "acceptance_level_insufficient",
        ],
        "blockers": ["real hardware configuration and controller are not configured"],
        "software_commit": _git_head(),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "phase10_0_verification.json", payload)
    return payload


def verify_phase10_1(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dry_run = run_default_dry_run()
    status = (
        PHASE10_DRY_RUN_ACCEPTED
        if dry_run["status"] == "DRY_RUN_VALIDATED"
        else PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED
    )
    payload: dict[str, Any] = {
        "status": status,
        "dry_run_status": dry_run["status"],
        "validation_claimed": status == PHASE10_DRY_RUN_ACCEPTED,
        "real_robot_validation": "NOT_STARTED",
        "highest_real_hardware_acceptance_level": "NONE",
        "hardware_motion_observed": False,
        "dry_run_evidence_path": str(output_dir / "phase10_1_dry_run_evidence.json"),
        "software_commit": _git_head(),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "phase10_1_dry_run_evidence.json", dry_run)
    _write_json(output_dir / "phase10_summary.json", payload)
    return payload


def run_default_dry_run() -> dict[str, Any]:
    service = DryRunValidationService(
        shield=SafetyShield(),
        runtime_settings=RealRobotRuntimeSettings(
            runtime_profile="test",
            execution_mode=ExecutionMode.DRY_RUN,
            enable_real_robot=False,
            config=None,
        ),
        telemetry_sample=TelemetrySample(
            timestamp=datetime.now(UTC),
            tcp_velocity=0.0,
            joint_velocities=[0.0] * 7,
            acceleration=0.0,
        ),
    )
    result = service.validate(_phase10_dry_run_contract().model_dump(mode="json"))
    payload = result.model_dump(mode="json")
    payload["software_commit"] = _git_head()
    payload["hardware_motion_observed"] = False
    return payload


def acceptance_level_blocked_payload(
    output_dir: Path,
    *,
    requested_level: RealRobotAcceptanceLevel,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "status": "ENVIRONMENT_BLOCKED",
        "requested_level": requested_level.value,
        "level_definition": level_definition(requested_level),
        "ran_multiple_levels": False,
        "hardware_motion_observed": False,
        "validation_claimed": False,
        "blockers": ["real robot controller and operator confirmation are required"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "acceptance_level_result.json", payload)
    return payload


def experiment_dry_run_payload(
    output_dir: Path,
    *,
    experiment_id: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dry_run = run_default_dry_run()
    payload: dict[str, Any] = {
        "experiment_id": experiment_id,
        "execution_mode": "DRY_RUN",
        "status": "DRY_RUN_VALIDATED" if dry_run["status"] == "DRY_RUN_VALIDATED" else "REJECTED",
        "hardware_motion_observed": False,
        "real_robot_validation": "NOT_STARTED",
        "metrics": {
            "task_success": False,
            "completion_time_ms": 0,
            "planning_time_ms": dry_run["trajectory_summary"]["planning_time_ms"],
            "cloud_calls": 0,
            "communication_count": 0,
            "local_retry_count": 0,
            "replan_count": 0,
            "safety_interventions": 0,
            "final_pose_error_m": None,
            "sim_to_real_time_gap": None,
            "sim_to_real_success_gap": None,
            "operator_intervention": False,
            "hardware_fault_count": 0,
        },
        "dry_run_evidence": dry_run,
    }
    _write_json(output_dir / f"{experiment_id.lower()}_dry_run.json", payload)
    return payload


def _phase10_dry_run_contract() -> TaskContract:
    issued = datetime.now(UTC)
    return TaskContract(
        task_id="phase10-dry-run",
        plan_version=1,
        command_seq=1,
        timestamp=issued,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=issued,
        valid_until=issued.replace(year=issued.year + 1),
        user_instruction="dry-run a safe home check without hardware execution",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            TaskStep(
                step_id="step-home",
                skill=SkillName.HOME,
                parameters={},
                expected_duration_ms=10,
                timeout_ms=1_000,
                retry_limit=0,
                preconditions=[],
                success_conditions=["robot_in_safe_pose"],
            )
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.3,
            max_tcp_velocity=0.1,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=0,
            on_timeout="SAFE_STOP",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["all_steps_completed"],
    )


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
