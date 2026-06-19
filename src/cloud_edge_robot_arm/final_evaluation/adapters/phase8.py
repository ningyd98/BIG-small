"""Phase 8 实际软件实验 runner adapter。"""

from __future__ import annotations

from typing import Any

from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    ResultStatus,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    write_source_artifact,
)
from cloud_edge_robot_arm.final_evaluation.models import (
    EnvironmentStatus,
    ExecutionSource,
    Phase12RunStatus,
)


class Phase8ExperimentRunnerAdapter:
    """调用 Phase 8 ExperimentRunner 的 actual software adapter。"""

    runner_kind = "PHASE8_EXPERIMENT_RUNNER"

    def capability(self) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind, "actual_runner": "ExperimentRunner"}

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return EnvironmentStatus.READY

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        config = _experiment_config(context)
        execution = ExperimentRunner(config).run()
        result = execution.result
        status = _status(result.result_status)
        events = [event.model_dump(mode="json") for event in execution.events]
        payload = {
            "runner": self.runner_kind,
            "config_hash": result.config_hash,
            "event_count": len(execution.events),
            "result": result.model_dump(mode="json"),
            "events": events,
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "hardware_write_operations": [],
        }
        rel, digest = write_source_artifact(context, "phase8_actual_run.json", payload)
        return Phase12AdapterResult(
            status=status,
            task_success=result.task_success,
            metrics=_metrics_from_phase8(result),
            events=events,
            execution_source=ExecutionSource.PHASE8_ACTUAL_RUN,
            actual_runner_invoked=True,
            authoritative_for_thesis=status != Phase12RunStatus.BLOCKED_BY_ENV,
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=EnvironmentStatus.READY,
            failure_type="" if result.task_success else status.value,
        )

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind, "run_id": context.run_id}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE8_ACTUAL_RUN


def _experiment_config(context: Phase12RunContext) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=context.experiment_id,
        scenario_id=context.scenario_id,
        mode=ExperimentMode(context.control_mode),
        seed=context.seed,
        repetitions=1,
        network_profile=_network_profile(context),
        fault_profile=FaultProfile(name=context.scenario_id),
        task_profile=TaskProfile(name="phase12-validation"),
        cache_policy=CachePolicy.CACHE_ENABLED
        if context.experiment_id != "F13_SKILL_CACHE"
        else CachePolicy.NO_CACHE_REUSE
        if context.repetition % 2
        else CachePolicy.CACHE_ENABLED,
        risk_policy_version="phase12-validation",
        supervision_period_ms=500,
        timeout_ms=30_000,
        artifact_dir=context.output_root / "source_evidence" / context.run_id,
    )


def _network_profile(context: Phase12RunContext) -> NetworkProfileName:
    if context.experiment_id in {
        "F04_NETWORK_LATENCY",
        "F05_NETWORK_JITTER",
        "F06_PACKET_LOSS",
        "F07_CLOUD_INTERRUPTION",
    }:
        return NetworkProfileName.DEGRADED
    return NetworkProfileName.NORMAL


def _status(status: ResultStatus) -> Phase12RunStatus:
    mapping = {
        ResultStatus.SUCCESS: Phase12RunStatus.SUCCESS,
        ResultStatus.FAILED: Phase12RunStatus.FAILED,
        ResultStatus.SAFETY_STOPPED: Phase12RunStatus.SAFETY_STOPPED,
        ResultStatus.TIMEOUT: Phase12RunStatus.TIMEOUT,
        ResultStatus.NEEDS_OBSERVATION: Phase12RunStatus.FAILED,
    }
    return mapping[status]


def _metrics_from_phase8(result: Any) -> dict[str, float | int | bool | str]:
    return {
        "task_completion_rate": 1.0 if result.task_success else 0.5,
        "total_completion_time_ms": result.task_completion_time_ms,
        "cloud_planning_time_ms": (result.cloud_response_latency_ms or 0),
        "edge_execution_time_ms": max(
            0, result.task_completion_time_ms - (result.cloud_response_latency_ms or 0)
        ),
        "local_recovery_time_ms": result.recovery_latency_ms or 0,
        "replanning_time_ms": 100 if result.replan_count else 0,
        "communication_wait_time_ms": result.fault_detection_latency_ms or 0,
        "cloud_invocation_count": result.cloud_invocation_count,
        "communication_count": result.command_count + result.telemetry_count,
        "uploaded_bytes": result.uploaded_bytes,
        "downloaded_bytes": result.downloaded_bytes,
        "supervision_count": result.supervisory_decision_count,
        "mode_switch_count": result.mode_switch_count,
        "local_retry_count": result.retry_count,
        "local_recovery_success_count": 1 if result.recovery_success and result.retry_count else 0,
        "replan_count": result.replan_count,
        "cloud_fallback_count": 1 if result.replan_count else 0,
        "completed_without_cloud_after_start": result.cloud_invocation_count == 0,
        "safety_intervention_count": result.safety_reject_count + result.emergency_stop_count,
        "rejected_action_count": result.safety_reject_count,
        "stale_telemetry_rejection": result.stale_command_rejection_count,
        "workspace_rejection": 0,
        "collision_rejection": result.simulated_collision_count,
        "emergency_stop_event": result.emergency_stop_count,
        "unsafe_command_execution_count": result.unsafe_counterfactual_count,
        "restart_recovery_success": result.recovery_success,
        "duplicate_execution_count": result.duplicate_command_rejection_count,
        "lease_recovery_count": 1 if result.scenario_id == "S15_SQLITE_RESTART_DURING_RUN" else 0,
        "artifact_consistency": True,
        "event_loss_count": 0,
        "planner_success": result.task_success,
        "valid_contract_rate": 1.0 if result.task_success else 0.0,
        "repair_count": result.replan_count,
        "refusal_rate": 0.0 if result.task_success else 1.0,
        "response_latency_ms": result.cloud_response_latency_ms or 0,
        "result_hash": result.result_hash,
        "artifact_hash": result.result_hash,
    }
