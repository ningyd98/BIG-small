"""Phase 10 MoveIt runtime dry-run adapter，默认环境阻塞。"""

from __future__ import annotations

from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_payload,
    write_source_artifact,
)
from cloud_edge_robot_arm.final_evaluation.adapters.synthetic_dry_run import _metrics
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    EnvironmentStatus,
    ExecutionSource,
    MetricProvenance,
    MetricSource,
    Phase12RunStatus,
)


class Phase10MoveItDryRunAdapter:
    runner_kind = "PHASE10_MOVEIT_RUNTIME_DRY_RUN"

    def capability(self) -> dict[str, object]:
        return {
            "runner_kind": self.runner_kind,
            "actual_runner": "MoveIt runtime dry-run",
            "default": "blocked",
        }

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return EnvironmentStatus.BLOCKED_BY_ENV

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        payload = {
            "runner": self.runner_kind,
            "status": "BLOCKED_BY_ENV",
            "reason": "MoveIt runtime is not enabled in Phase 12.1 validation",
        }
        rel, digest = write_source_artifact(context, "phase10_moveit_dry_run_blocked.json", payload)
        return Phase12AdapterResult(
            status=Phase12RunStatus.BLOCKED_BY_ENV,
            task_success=False,
            metrics=_metrics({"hash": sha256_payload(payload)}, safety=False),
            events=[{"event_type": "moveit_dry_run_blocked_by_env"}],
            execution_source=ExecutionSource.PHASE10_MOVEIT_ENVIRONMENT_CHECK,
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

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, object]:
        return {"runner_kind": self.runner_kind}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE10_MOVEIT_ENVIRONMENT_CHECK


def _blocked_metric_provenance(source_artifact: str) -> dict[str, MetricProvenance]:
    return {
        "total_completion_time_ms": MetricProvenance(
            source=MetricSource.NOT_AVAILABLE,
            source_field="environment_check",
            source_artifact=source_artifact,
            unit="ms",
        )
    }
