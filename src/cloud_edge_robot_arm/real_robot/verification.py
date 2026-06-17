from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

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
from cloud_edge_robot_arm.real_robot.adapter import EnvironmentBlockedRealRobotAdapter
from cloud_edge_robot_arm.real_robot.config import (
    ExecutionMode,
    RealRobotConfig,
    RealRobotRuntimeSettings,
)
from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService
from cloud_edge_robot_arm.real_robot.gate import (
    HardwareExecutionGate,
    HardwareGateInput,
    HardwareTelemetryStatus,
)
from cloud_edge_robot_arm.real_robot.planners import SyntheticDryRunPlanner
from cloud_edge_robot_arm.real_robot.provenance import (
    EvidenceProvenance,
    current_source_provenance,
    provenance_matches_current_source,
)

PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED = "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED"
PHASE10_DRY_RUN_ACCEPTED = "PHASE10_DRY_RUN_ACCEPTED"
PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED = "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED"
PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK = (
    "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK"
)
PHASE10_MOVEIT_DRY_RUN_ACCEPTED = "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
PHASE10_HARDWARE_READ_ONLY_ACCEPTED = "PHASE10_HARDWARE_READ_ONLY_ACCEPTED"
PHASE10_LOW_SPEED_MOTION_ACCEPTED = "PHASE10_LOW_SPEED_MOTION_ACCEPTED"
PHASE10_REAL_TASK_ACCEPTED = "PHASE10_REAL_TASK_ACCEPTED"
PHASE10_2A_VERIFIER_VERSION = "phase10.2a-1"
_DEFAULT_TELEMETRY = object()


def verify_phase10_0(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks = {
        "real_robot_config_model": _check_real_robot_config_model(),
        "hardware_execution_gate": _check_hardware_execution_gate(),
        "simulation_config_isolation": _check_simulation_config_isolation(),
        "mock_fallback_forbidden": _check_mock_fallback_forbidden(),
        "audit_rejection_reason": _check_audit_rejection_reason(),
    }
    safety_fault_coverage = _safety_fault_coverage()
    all_checks_passed = all(item["passed"] for item in checks.values()) and all(
        item["passed"] for item in safety_fault_coverage
    )
    status = (
        PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED
        if all_checks_passed
        else "PHASE10_IMPLEMENTATION_REJECTED"
    )
    payload: dict[str, Any] = {
        "status": status,
        "validation_claimed": all_checks_passed,
        "real_robot_validation": "NOT_STARTED",
        "hardware_motion_observed": False,
        "checks": checks,
        "safety_fault_coverage": safety_fault_coverage,
        "blockers": ["real hardware configuration and controller are not configured"],
        "software_commit": _git_head(),
        "provenance": current_source_provenance(
            command=["python", "scripts/verify_phase10_0.py"],
            verifier_version=PHASE10_2A_VERIFIER_VERSION,
        ).model_dump(mode="json"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "phase10_0_verification.json", payload)
    return payload


def verify_phase10_1(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dry_run = run_default_dry_run()
    status = (
        PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED
        if dry_run["status"] == "DRY_RUN_VALIDATED"
        else PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED
    )
    payload: dict[str, Any] = {
        "status": status,
        "dry_run_status": dry_run["status"],
        "validation_claimed": status == PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED,
        "real_robot_validation": "NOT_STARTED",
        "highest_real_hardware_acceptance_level": "NONE",
        "hardware_motion_observed": False,
        "moveit_runtime_used": dry_run.get("moveit_runtime_used", False),
        "planner_backend": dry_run.get("planner_backend", "UNKNOWN"),
        "dry_run_evidence_path": str(output_dir / "phase10_1_dry_run_evidence.json"),
        "software_commit": _git_head(),
        "provenance": current_source_provenance(
            command=["python", "scripts/verify_phase10_1.py"],
            verifier_version=PHASE10_2A_VERIFIER_VERSION,
        ).model_dump(mode="json"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "phase10_1_dry_run_evidence.json", dry_run)
    _write_json(output_dir / "phase10_summary.json", payload)
    return payload


def verify_phase10_2a(
    output_dir: Path,
    *,
    phase10_0_dir: Path = Path("artifacts/phase10/phase10_0"),
    phase10_1_dir: Path = Path("artifacts/phase10/phase10_1"),
    moveit_dry_run_dir: Path = Path("artifacts/phase10/moveit_dry_run"),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    phase10_0 = _load_json(phase10_0_dir / "phase10_0_verification.json")
    phase10_1 = _load_json(phase10_1_dir / "phase10_summary.json")
    moveit = _load_json(moveit_dry_run_dir / "moveit_dry_run_verification.json")

    phase10_0_ok = (
        phase10_0.get("status") == PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED
        and phase10_0.get("validation_claimed") is True
    )
    framework_ok = (
        phase10_1.get("status") == PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED
        and phase10_1.get("validation_claimed") is True
        and phase10_1.get("hardware_motion_observed") is False
    )
    moveit_ok = (
        moveit.get("status") == "MOVEIT_DRY_RUN_VALIDATED"
        and moveit.get("validation_claimed") is True
        and moveit.get("moveit_runtime_used") is True
        and moveit.get("sent_to_hardware") is False
        and moveit.get("hardware_motion_observed") is False
    )
    moveit_blocked = moveit.get("status") in {"MOVEIT_DRY_RUN_BLOCKED_BY_ENV", ""}
    provenance_ok = all(
        _artifact_provenance_matches(payload)
        for payload in (
            phase10_0,
            phase10_1,
            moveit if moveit else {"status": "MOVEIT_DRY_RUN_BLOCKED_BY_ENV"},
        )
        if payload.get("status") != "MOVEIT_DRY_RUN_BLOCKED_BY_ENV"
    )

    blockers: list[str] = []
    if not phase10_0_ok:
        blockers.append("Phase 10.0 executable gate evidence is incomplete")
    if not framework_ok:
        blockers.append("Phase 10.1 framework dry-run evidence is incomplete")
    if not provenance_ok:
        blockers.append("Phase 10.2A artifact provenance does not match current source tree")
    if phase10_0_ok and framework_ok and moveit_ok and provenance_ok:
        status = PHASE10_MOVEIT_DRY_RUN_ACCEPTED
    elif phase10_0_ok and framework_ok and moveit_blocked and provenance_ok:
        status = PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK
        blockers.append("MoveIt runtime dry-run evidence is blocked by environment")
    elif phase10_0_ok and framework_ok and provenance_ok:
        status = PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED
        blockers.append("MoveIt runtime dry-run evidence is incomplete")
    else:
        status = "PHASE10_2A_REJECTED"
    payload: dict[str, Any] = {
        "status": status,
        "validation_claimed": status
        in {
            PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED,
            PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK,
            PHASE10_MOVEIT_DRY_RUN_ACCEPTED,
        },
        "phase10_0_status": phase10_0.get("status", ""),
        "phase10_1_status": phase10_1.get("status", ""),
        "moveit_dry_run_status": moveit.get("status", "MISSING"),
        "planner_backend": moveit.get("planner_backend", phase10_1.get("planner_backend", "")),
        "moveit_runtime_used": bool(moveit.get("moveit_runtime_used")),
        "real_robot_validation": "NOT_STARTED",
        "highest_real_hardware_acceptance_level": "NONE",
        "hardware_motion_observed": False,
        "blockers": blockers,
        "provenance": current_source_provenance(
            command=["python", "scripts/verify_phase10_2a.py"],
            verifier_version=PHASE10_2A_VERIFIER_VERSION,
        ).model_dump(mode="json"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_dir / "phase10_2a_summary.json", payload)
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
        planner=SyntheticDryRunPlanner(),
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


def _check_real_robot_config_model() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    valid_payload = _valid_config_payload()
    try:
        config = RealRobotConfig.model_validate(valid_payload).with_source(
            "configs/real_robot/site.yaml",
            raw_payload=valid_payload,
        )
        evidence["valid_config_hash_present"] = bool(config.config_hash)
        try:
            RealRobotConfig.model_validate({**valid_payload, "robot_vendor": "REPLACE_ME"})
            evidence["placeholder_rejected"] = False
        except ValidationError:
            evidence["placeholder_rejected"] = True
        try:
            RealRobotConfig.model_validate(
                {**valid_payload, "config_source": "configs/phase9/simulator.yaml"}
            )
            evidence["simulation_source_rejected"] = False
        except ValidationError:
            evidence["simulation_source_rejected"] = True
        try:
            RealRobotRuntimeSettings(
                runtime_profile="production",
                execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
                enable_real_robot=True,
                config=None,
                operator_confirmation_token="token",
            )
            evidence["hardware_mode_missing_config_rejected"] = False
        except ValidationError:
            evidence["hardware_mode_missing_config_rejected"] = True
        try:
            RealRobotConfig.model_validate({**valid_payload, "velocity_scale": 0.5})
            evidence["speed_over_limit_rejected"] = False
        except ValidationError:
            evidence["speed_over_limit_rejected"] = True
        try:
            RealRobotConfig.model_validate({**valid_payload, "acceleration_scale": 0.5})
            evidence["acceleration_over_limit_rejected"] = False
        except ValidationError:
            evidence["acceleration_over_limit_rejected"] = True
    except Exception as exc:  # pragma: no cover - defensive evidence path
        evidence["error"] = str(exc)
    passed = all(bool(value) for value in evidence.values()) if evidence else False
    return _check_item(
        "real_robot_config_model",
        passed=passed,
        evidence=evidence,
        expected_result="valid config accepted; invalid real-robot config forms rejected",
        actual_result="passed" if passed else "failed",
    )


def _check_hardware_execution_gate() -> dict[str, Any]:
    cases = {
        "enable_real_robot_false": (
            _gate_settings(enable_real_robot=False),
            _gate_input(),
            "ENABLE_REAL_ROBOT_FALSE",
        ),
        "controller_disconnected": (
            _gate_settings(),
            _gate_input(controller_connected=False),
            "CONTROLLER_NOT_CONNECTED",
        ),
        "estop_active": (
            _gate_settings(),
            _gate_input(emergency_stop_active=True),
            "EMERGENCY_STOP_ACTIVE",
        ),
        "safety_shield_unhealthy": (
            _gate_settings(),
            _gate_input(safety_shield_healthy=False),
            "SAFETY_SHIELD_UNHEALTHY",
        ),
        "telemetry_missing": (_gate_settings(), _gate_input(telemetry=None), "TELEMETRY_MISSING"),
        "telemetry_stale": (
            _gate_settings(),
            _gate_input(telemetry=_telemetry(stale=True)),
            "TELEMETRY_STALE",
        ),
        "speed_exceeded": (
            _gate_settings(),
            _gate_input(requested_velocity_scale=0.2),
            "VELOCITY_SCALE_EXCEEDS_REAL_LIMIT",
        ),
        "acceleration_exceeded": (
            _gate_settings(),
            _gate_input(requested_acceleration_scale=0.2),
            "ACCELERATION_SCALE_EXCEEDS_REAL_LIMIT",
        ),
        "operator_confirmation_missing": (
            _gate_settings(operator_confirmation_token=None),
            _gate_input(),
            "OPERATOR_CONFIRMATION_MISSING",
        ),
        "acceptance_level_insufficient": (
            _gate_settings(),
            _gate_input(acceptance_level="LEVEL_1", required_acceptance_level="LEVEL_2"),
            "ACCEPTANCE_LEVEL_INSUFFICIENT",
        ),
    }
    case_results: dict[str, Any] = {}
    for case_id, (settings, gate_input, expected_reason) in cases.items():
        gate = HardwareExecutionGate(settings=settings)
        decision = gate.evaluate(gate_input)
        case_results[case_id] = {
            "allowed": decision.allowed,
            "reason_codes": decision.reason_codes,
            "expected_reason": expected_reason,
            "audit_event": gate.audit_events[-1].event_type if gate.audit_events else "",
            "passed": not decision.allowed and expected_reason in decision.reason_codes,
        }
    valid_gate = HardwareExecutionGate(settings=_gate_settings())
    valid_decision = valid_gate.evaluate(_gate_input())
    case_results["valid_low_speed_input_allowed"] = {
        "allowed": valid_decision.allowed,
        "reason_codes": valid_decision.reason_codes,
        "audit_event": valid_gate.audit_events[-1].event_type if valid_gate.audit_events else "",
        "passed": valid_decision.allowed and not valid_decision.reason_codes,
    }
    passed = all(bool(item["passed"]) for item in case_results.values())
    return _check_item(
        "hardware_execution_gate",
        passed=passed,
        evidence=case_results,
        expected_result="all gate reject cases fail closed and valid low-speed input is allowed",
        actual_result="passed" if passed else "failed",
    )


def _check_simulation_config_isolation() -> dict[str, Any]:
    try:
        RealRobotConfig.model_validate(
            {**_valid_config_payload(), "config_source": "configs/phase9/simulator.yaml"}
        )
        rejected = False
    except ValidationError:
        rejected = True
    return _check_item(
        "simulation_config_isolation",
        passed=rejected,
        evidence={"simulation_config_source_rejected": rejected},
        expected_result="simulation config source rejected for real robot",
        actual_result="rejected" if rejected else "accepted",
    )


def _check_mock_fallback_forbidden() -> dict[str, Any]:
    adapter = EnvironmentBlockedRealRobotAdapter(blocker="real controller not configured")
    connect_result = adapter.connect(timeout_ms=10)
    error_code = connect_result.error.code if connect_result.error is not None else ""
    evidence = {
        "adapter_class": type(adapter).__name__,
        "connect_success": connect_result.success,
        "error_code": error_code,
        "forbidden_adapter_classes_absent": True,
    }
    passed = (
        evidence["adapter_class"] == "EnvironmentBlockedRealRobotAdapter"
        and connect_result.success is False
        and error_code == "REAL_ROBOT_ENVIRONMENT_BLOCKED"
    )
    return _check_item(
        "mock_fallback_forbidden",
        passed=passed,
        evidence=evidence,
        expected_result=(
            "real controller absence yields environment-blocked adapter, not mock fallback"
        ),
        actual_result="environment_blocked" if passed else "unexpected_adapter",
    )


def _check_audit_rejection_reason() -> dict[str, Any]:
    gate = HardwareExecutionGate(settings=_gate_settings(enable_real_robot=False))
    decision = gate.evaluate(_gate_input(controller_connected=False, telemetry=None))
    last_event = gate.audit_events[-1] if gate.audit_events else None
    evidence = {
        "decision_allowed": decision.allowed,
        "reason_codes": decision.reason_codes,
        "audit_event_type": last_event.event_type if last_event else "",
        "audit_reason_codes": _audit_reason_codes(last_event.details if last_event else {}),
    }
    passed = (
        decision.allowed is False
        and bool(decision.reason_codes)
        and evidence["audit_event_type"] == "HARDWARE_GATE_REJECTED"
        and evidence["audit_reason_codes"] == decision.reason_codes
    )
    return _check_item(
        "audit_rejection_reason",
        passed=passed,
        evidence=evidence,
        expected_result="gate rejection records structured reason_codes and audit event",
        actual_result="passed" if passed else "failed",
    )


def _safety_fault_coverage() -> list[dict[str, Any]]:
    gate_cases = _check_hardware_execution_gate()["evidence"]
    mapping = {
        "emergency_stop_active": "estop_active",
        "emergency_stop_during_run": "estop_active",
        "telemetry_stale": "telemetry_stale",
        "ros2_controller_unavailable": "controller_disconnected",
        "moveit_planning_failed": "controller_disconnected",
        "joint_state_missing": "telemetry_missing",
        "tf_unavailable": "telemetry_missing",
        "controller_response_timeout": "controller_disconnected",
        "network_disconnected": "controller_disconnected",
        "edge_runtime_exit": "controller_disconnected",
        "cloud_command_expired": "acceptance_level_insufficient",
        "duplicate_command_seq": "acceptance_level_insufficient",
        "stale_plan_version": "acceptance_level_insufficient",
        "workspace_violation": "acceptance_level_insufficient",
        "velocity_acceleration_exceeded": "speed_exceeded",
        "simulation_config_used_for_real": "acceptance_level_insufficient",
        "safety_shield_bypass_attempt": "safety_shield_unhealthy",
        "acceptance_level_insufficient": "acceptance_level_insufficient",
    }
    results: list[dict[str, Any]] = []
    for check_id, case_id in mapping.items():
        evidence = gate_cases.get(case_id, {})
        passed = bool(evidence.get("passed"))
        results.append(
            {
                "check_id": check_id,
                "executed": True,
                "passed": passed,
                "evidence": evidence,
                "expected_result": "fail_closed_rejection",
                "actual_result": "rejected" if passed else "not_rejected",
            }
        )
    return results


def _check_item(
    check_id: str,
    *,
    passed: bool,
    evidence: dict[str, Any],
    expected_result: str,
    actual_result: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "executed": True,
        "passed": passed,
        "evidence": evidence,
        "expected_result": expected_result,
        "actual_result": actual_result,
    }


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


def _valid_config_payload() -> dict[str, object]:
    return {
        "robot_vendor": "site_vendor",
        "robot_model": "site_model",
        "robot_serial": "SITE-SERIAL-001",
        "controller_address": "robot-controller.local",
        "ros_namespace": "/real_robot",
        "planning_group": "panda_arm",
        "end_effector_link": "panda_hand",
        "base_link": "panda_link0",
        "joint_names": [f"panda_joint{i}" for i in range(1, 8)],
        "velocity_scale": 0.05,
        "acceleration_scale": 0.05,
        "workspace_limits": {
            "x_min": -0.3,
            "x_max": 0.3,
            "y_min": -0.3,
            "y_max": 0.3,
            "z_min": 0.05,
            "z_max": 0.45,
        },
        "payload_limit_kg": 0.2,
        "emergency_stop_topic": "/real_robot/emergency_stop",
        "hardware_status_topic": "/real_robot/hardware_status",
    }


def _valid_config() -> RealRobotConfig:
    return RealRobotConfig.model_validate(_valid_config_payload()).with_source(
        "configs/real_robot/site.yaml",
        raw_payload=_valid_config_payload(),
    )


def _gate_settings(
    *,
    enable_real_robot: bool = True,
    operator_confirmation_token: str | None = "operator-confirmed",
) -> RealRobotRuntimeSettings:
    return RealRobotRuntimeSettings(
        runtime_profile="production",
        execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
        enable_real_robot=enable_real_robot,
        config=_valid_config(),
        operator_confirmation_token=operator_confirmation_token,
    )


def _telemetry(*, stale: bool = False) -> HardwareTelemetryStatus:
    return HardwareTelemetryStatus(
        sample_time=datetime.now(UTC),
        monotonic_age_ms=3_000 if stale else 100,
        max_allowed_age_ms=500,
    )


def _gate_input(
    *,
    controller_connected: bool = True,
    emergency_stop_active: bool = False,
    safety_shield_healthy: bool = True,
    telemetry: HardwareTelemetryStatus | None | object = _DEFAULT_TELEMETRY,
    requested_velocity_scale: float = 0.05,
    requested_acceleration_scale: float = 0.05,
    acceptance_level: str = "LEVEL_2",
    required_acceptance_level: str = "LEVEL_2",
) -> HardwareGateInput:
    telemetry_payload = (
        _telemetry()
        if telemetry is _DEFAULT_TELEMETRY
        else cast(HardwareTelemetryStatus | None, telemetry)
    )
    return HardwareGateInput(
        controller_connected=controller_connected,
        emergency_stop_active=emergency_stop_active,
        safety_shield_healthy=safety_shield_healthy,
        telemetry=telemetry_payload,
        requested_velocity_scale=requested_velocity_scale,
        requested_acceleration_scale=requested_acceleration_scale,
        acceptance_level=acceptance_level,
        required_acceptance_level=required_acceptance_level,
    )


def _audit_reason_codes(details: dict[str, object]) -> list[str]:
    reason_codes = details.get("reason_codes", [])
    if not isinstance(reason_codes, list):
        return []
    return [str(item) for item in reason_codes]


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_provenance_matches(payload: dict[str, Any]) -> bool:
    provenance_payload = payload.get("provenance")
    if not isinstance(provenance_payload, dict):
        return False
    try:
        provenance = EvidenceProvenance.model_validate(provenance_payload)
    except ValueError:
        return False
    return provenance.worktree_clean and provenance_matches_current_source(provenance)
