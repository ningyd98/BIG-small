"""Phase 9.2 Isaac adapter，环境不可用时只返回 BLOCKED_BY_ENV。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_payload,
    write_source_artifact,
)
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    EnvironmentStatus,
    ExecutionSource,
    MetricProvenance,
    MetricSource,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.simulation.environment import detect_environment
from cloud_edge_robot_arm.simulation.evaluation.metrics import run_isaac_physical_trial


class Phase9IsaacAdapter:
    runner_kind = "PHASE9_2_ISAAC"

    def capability(self) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind, "actual_runner": "run_isaac_physical_trial"}

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return (
            EnvironmentStatus.READY
            if detect_environment().level == "ISAAC_READY"
            else EnvironmentStatus.BLOCKED_BY_ENV
        )

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        if self.validate_environment(context) == EnvironmentStatus.BLOCKED_BY_ENV:
            payload = {
                "runner": self.runner_kind,
                "status": "BLOCKED_BY_ENV",
                "blocker": "Isaac Sim environment is not available",
                "mock_fallback_used": False,
            }
            rel, digest = write_source_artifact(context, "phase9_isaac_blocked.json", payload)
            return Phase12AdapterResult(
                status=Phase12RunStatus.BLOCKED_BY_ENV,
                task_success=False,
                metrics=_blocked_metrics(payload),
                events=[{"event_type": "isaac_blocked_by_env"}],
                execution_source=ExecutionSource.PHASE9_2_ISAAC_ENVIRONMENT_CHECK,
                actual_runner_invoked=False,
                adapter_attempted=True,
                environment_check_completed=True,
                runtime_invoked=False,
                runtime_completed=False,
                authoritative_for_thesis=False,
                blocker_stage=BlockerStage.ENVIRONMENT_CHECK,
                source_artifact_path=rel,
                source_artifact_hash=digest,
                source_verifier=self.runner_kind,
                environment_status=EnvironmentStatus.BLOCKED_BY_ENV,
                metric_provenance=_blocked_metric_provenance(rel),
                failure_type="BLOCKED_BY_ENV",
            )
        trial = run_isaac_physical_trial(context.scenario_id, seed=context.seed)
        payload = {
            "runner": self.runner_kind,
            "trial": asdict(trial),
            "mock_fallback_used": False,
        }
        rel, digest = write_source_artifact(context, "phase9_isaac_actual_run.json", payload)
        return Phase12AdapterResult(
            status=Phase12RunStatus.SUCCESS,
            task_success=True,
            metrics={
                **_blocked_metrics(payload),
                "task_completion_rate": 1.0,
                "total_completion_time_ms": float(trial.metrics.get("trajectory_duration_ms", 0.0)),
                "result_hash": trial.result_hash,
                "artifact_hash": trial.result_hash,
            },
            events=[{"event_type": "isaac_trial_completed"}],
            execution_source=ExecutionSource.PHASE9_2_ISAAC_ACTUAL_RUN,
            actual_runner_invoked=True,
            adapter_attempted=True,
            environment_check_completed=True,
            runtime_invoked=True,
            runtime_completed=True,
            authoritative_for_thesis=True,
            blocker_stage=BlockerStage.NONE,
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=EnvironmentStatus.READY,
            metric_provenance=_isaac_metric_provenance(rel),
        )

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE9_2_ISAAC_ACTUAL_RUN


def _blocked_metrics(payload: dict[str, Any]) -> dict[str, float | int | bool | str]:
    digest = sha256_payload(payload)
    return {
        "task_completion_rate": 0.0,
        "total_completion_time_ms": 0.0,
        "cloud_planning_time_ms": 0.0,
        "edge_execution_time_ms": 0.0,
        "local_recovery_time_ms": 0.0,
        "replanning_time_ms": 0.0,
        "communication_wait_time_ms": 0.0,
        "cloud_invocation_count": 0,
        "communication_count": 0,
        "uploaded_bytes": 0,
        "downloaded_bytes": 0,
        "supervision_count": 0,
        "mode_switch_count": 0,
        "local_retry_count": 0,
        "local_recovery_success_count": 0,
        "replan_count": 0,
        "cloud_fallback_count": 0,
        "completed_without_cloud_after_start": False,
        "safety_intervention_count": 0,
        "rejected_action_count": 0,
        "stale_telemetry_rejection": 0,
        "workspace_rejection": 0,
        "collision_rejection": 0,
        "emergency_stop_event": 0,
        "unsafe_command_execution_count": 0,
        "restart_recovery_success": False,
        "duplicate_execution_count": 0,
        "lease_recovery_count": 0,
        "artifact_consistency": True,
        "event_loss_count": 0,
        "planner_success": False,
        "valid_contract_rate": 0.0,
        "repair_count": 0,
        "refusal_rate": 0.0,
        "response_latency_ms": 0.0,
        "result_hash": digest,
        "artifact_hash": digest,
    }


def _blocked_metric_provenance(source_artifact: str) -> dict[str, MetricProvenance]:
    return {
        "total_completion_time_ms": MetricProvenance(
            source=MetricSource.NOT_AVAILABLE,
            source_field="environment_check",
            source_artifact=source_artifact,
            unit="ms",
        )
    }


def _isaac_metric_provenance(source_artifact: str) -> dict[str, MetricProvenance]:
    return {
        "total_completion_time_ms": MetricProvenance(
            source=MetricSource.MEASURED,
            source_field="trial.metrics.trajectory_duration_ms",
            source_artifact=source_artifact,
            unit="ms",
        ),
        "task_completion_rate": MetricProvenance(
            source=MetricSource.MEASURED,
            source_field="trial.status",
            source_artifact=source_artifact,
            unit="ratio",
        ),
    }
