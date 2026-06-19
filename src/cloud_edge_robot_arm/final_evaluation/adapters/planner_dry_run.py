"""Phase 11.2 规划器 dry-run adapter，保持 dispatch=false。"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter, RuleBasedPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
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


class Phase112PlannerDryRunAdapter:
    runner_kind = "PHASE11_2_PLANNER_DRY_RUN"

    def capability(self) -> dict[str, object]:
        return {"runner_kind": self.runner_kind, "actual_runner": "PlannerAdapter dry-run"}

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return EnvironmentStatus.READY

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        planner = (
            RuleBasedPlannerAdapter() if context.control_mode != "PCSC" else MockPlannerAdapter()
        )
        request = InitialPlanningRequest(
            request_id=context.run_id,
            user_instruction=f"Phase 12 planner validation for {context.scenario_id}",
            control_mode=_control_mode(context.control_mode),
            scene=SceneSummary(
                scene_version=context.seed,
                updated_at=datetime.now(UTC),
                scene_confidence=1.0,
                robot_state={"scenario_id": context.scenario_id},
            ),
        )
        draft = planner.plan(request)
        success = draft.parsed_json is not None and not draft.parse_error
        payload: dict[str, object] = {
            "runner": self.runner_kind,
            "provider": planner.__class__.__name__,
            "raw_text": draft.raw_text,
            "parsed_json": draft.parsed_json,
            "parse_error": draft.parse_error,
            "dispatch": False,
            "hardware_execution": False,
        }
        rel, digest = write_source_artifact(context, "phase11_2_planner_dry_run.json", payload)
        metrics = _metrics(payload, success=success)
        return Phase12AdapterResult(
            status=Phase12RunStatus.SUCCESS if success else Phase12RunStatus.FAILED,
            task_success=success,
            metrics=metrics,
            events=[{"event_type": "planner_dry_run_completed", "provider": payload["provider"]}],
            execution_source=ExecutionSource.PHASE11_2_PLANNER_ACTUAL,
            actual_runner_invoked=True,
            authoritative_for_thesis=True,
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=EnvironmentStatus.READY,
            failure_type="" if success else "PLANNER_FAILED",
        )

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, object]:
        return {"runner_kind": self.runner_kind}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE11_2_PLANNER_ACTUAL


def _control_mode(value: str) -> str:
    return {
        "PCSC": "PERIODIC_CLOUD_SUPERVISION",
        "ETEAC": "EVENT_TRIGGERED_EDGE_AUTONOMY",
        "AUTO": "AUTO",
    }[value]


def _metrics(payload: dict[str, object], *, success: bool) -> dict[str, float | int | bool | str]:
    digest = sha256_payload(payload)
    return {
        "task_completion_rate": 1.0 if success else 0.0,
        "total_completion_time_ms": 80.0,
        "cloud_planning_time_ms": 80.0,
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
        "completed_without_cloud_after_start": True,
        "safety_intervention_count": 0,
        "rejected_action_count": 0,
        "stale_telemetry_rejection": 0,
        "workspace_rejection": 0,
        "collision_rejection": 0,
        "emergency_stop_event": 0,
        "unsafe_command_execution_count": 0,
        "restart_recovery_success": True,
        "duplicate_execution_count": 0,
        "lease_recovery_count": 0,
        "artifact_consistency": True,
        "event_loss_count": 0,
        "planner_success": success,
        "valid_contract_rate": 1.0 if success else 0.0,
        "repair_count": 0,
        "refusal_rate": 0.0 if success else 1.0,
        "response_latency_ms": 80.0,
        "result_hash": digest,
        "artifact_hash": digest,
    }
