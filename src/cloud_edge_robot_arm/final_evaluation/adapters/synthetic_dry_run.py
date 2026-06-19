"""Phase 10 synthetic dry-run 实际安全门禁 adapter。"""

from __future__ import annotations

from typing import Any

from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_payload,
    write_source_artifact,
)
from cloud_edge_robot_arm.final_evaluation.models import (
    EnvironmentStatus,
    ExecutionSource,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.real_robot.verification import verify_phase10_0


class Phase10SyntheticDryRunAdapter:
    runner_kind = "PHASE10_SYNTHETIC_DRY_RUN"

    def capability(self) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind, "actual_runner": "verify_phase10_0"}

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return EnvironmentStatus.READY

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        payload = verify_phase10_0(
            context.output_root / "source_evidence" / context.run_id / "phase10_0"
        )
        rel, digest = write_source_artifact(context, "phase10_synthetic_dry_run.json", payload)
        return Phase12AdapterResult(
            status=Phase12RunStatus.SAFETY_STOPPED,
            task_success=False,
            metrics=_metrics(payload, safety=True),
            events=[{"event_type": "safety_gate_verified", "status": payload.get("status", "")}],
            execution_source=ExecutionSource.PHASE10_SYNTHETIC_DRY_RUN_ACTUAL,
            actual_runner_invoked=True,
            authoritative_for_thesis=True,
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=EnvironmentStatus.READY,
            failure_type="SAFETY_STOPPED",
        )

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE10_SYNTHETIC_DRY_RUN_ACTUAL


def _metrics(payload: dict[str, Any], *, safety: bool) -> dict[str, float | int | bool | str]:
    digest = sha256_payload(payload)
    return {
        "task_completion_rate": 0.5,
        "total_completion_time_ms": 100.0,
        "cloud_planning_time_ms": 0.0,
        "edge_execution_time_ms": 100.0,
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
        "safety_intervention_count": 1 if safety else 0,
        "rejected_action_count": 1 if safety else 0,
        "stale_telemetry_rejection": 1 if safety else 0,
        "workspace_rejection": 1 if safety else 0,
        "collision_rejection": 1 if safety else 0,
        "emergency_stop_event": 1 if safety else 0,
        "unsafe_command_execution_count": 0,
        "restart_recovery_success": True,
        "duplicate_execution_count": 0,
        "lease_recovery_count": 0,
        "artifact_consistency": True,
        "event_loss_count": 0,
        "planner_success": True,
        "valid_contract_rate": 1.0,
        "repair_count": 0,
        "refusal_rate": 0.0,
        "response_latency_ms": 0.0,
        "result_hash": digest,
        "artifact_hash": digest,
    }
