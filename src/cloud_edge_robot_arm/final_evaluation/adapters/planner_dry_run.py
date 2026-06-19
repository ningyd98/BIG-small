"""Phase 11.2 规划器 dry-run adapter，保持 dispatch=false。"""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter, RuleBasedPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
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


class Phase112PlannerDryRunAdapter:
    runner_kind = "PHASE11_2_PLANNER_DRY_RUN"

    def capability(self) -> dict[str, object]:
        return {"runner_kind": self.runner_kind, "actual_runner": "PlannerAdapter dry-run"}

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        if context.planner_provider in {"OPENAI_COMPATIBLE", "OLLAMA"}:
            return EnvironmentStatus.BLOCKED_BY_ENV
        return EnvironmentStatus.READY

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        provider = context.planner_provider or "RULE_BASED"
        started = perf_counter()
        if provider in {"OPENAI_COMPATIBLE", "OLLAMA"}:
            blocked_payload = {
                "runner": self.runner_kind,
                "provider": provider,
                "status": "BLOCKED_BY_ENV",
                "reason": "provider profile or local model is not configured for validation",
                "dispatch": False,
                "hardware_execution": False,
            }
            latency_ms = (perf_counter() - started) * 1000.0
            rel, digest = write_source_artifact(
                context, "phase11_2_planner_environment_check.json", blocked_payload
            )
            metrics = _metrics(blocked_payload, success=False, latency_ms=latency_ms)
            return Phase12AdapterResult(
                status=Phase12RunStatus.BLOCKED_BY_ENV,
                task_success=False,
                metrics=metrics,
                events=[{"event_type": "planner_provider_blocked", "provider": provider}],
                execution_source=ExecutionSource.PHASE11_2_PLANNER_ACTUAL,
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
                metric_provenance=_metric_provenance(rel, blocked=True),
                planner_provider=provider,
                model_name=context.model_name,
                failure_type="BLOCKED_BY_ENV",
            )
        planner = MockPlannerAdapter() if provider == "MOCK" else RuleBasedPlannerAdapter()
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
        latency_ms = (perf_counter() - started) * 1000.0
        success = draft.parsed_json is not None and not draft.parse_error
        payload: dict[str, object] = {
            "runner": self.runner_kind,
            "provider": provider,
            "adapter_class": planner.__class__.__name__,
            "raw_text": draft.raw_text,
            "parsed_json": draft.parsed_json,
            "parse_error": draft.parse_error,
            "dispatch": False,
            "hardware_execution": False,
        }
        rel, digest = write_source_artifact(context, "phase11_2_planner_dry_run.json", payload)
        metrics = _metrics(payload, success=success, latency_ms=latency_ms)
        return Phase12AdapterResult(
            status=Phase12RunStatus.SUCCESS if success else Phase12RunStatus.FAILED,
            task_success=success,
            metrics=metrics,
            events=[{"event_type": "planner_dry_run_completed", "provider": payload["provider"]}],
            execution_source=ExecutionSource.PHASE11_2_PLANNER_ACTUAL,
            actual_runner_invoked=True,
            adapter_attempted=True,
            environment_check_completed=True,
            runtime_invoked=True,
            runtime_completed=success,
            authoritative_for_thesis=True,
            blocker_stage=BlockerStage.NONE,
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=EnvironmentStatus.READY,
            metric_provenance=_metric_provenance(rel, blocked=False),
            planner_provider=provider,
            model_name=context.model_name,
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


def _metrics(
    payload: dict[str, object], *, success: bool, latency_ms: float
) -> dict[str, float | int | bool | str]:
    digest = sha256_payload(payload)
    return {
        "task_completion_rate": 1.0 if success else 0.0,
        "total_completion_time_ms": latency_ms,
        "cloud_planning_time_ms": latency_ms,
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
        "response_latency_ms": latency_ms,
        "result_hash": digest,
        "artifact_hash": digest,
    }


def _metric_provenance(source_artifact: str, *, blocked: bool) -> dict[str, MetricProvenance]:
    source = MetricSource.NOT_AVAILABLE if blocked else MetricSource.MEASURED
    return {
        "total_completion_time_ms": MetricProvenance(
            source=source,
            source_field="perf_counter.elapsed_ms",
            source_artifact=source_artifact,
            unit="ms",
        ),
        "cloud_planning_time_ms": MetricProvenance(
            source=source,
            source_field="perf_counter.elapsed_ms",
            source_artifact=source_artifact,
            unit="ms",
        ),
        "response_latency_ms": MetricProvenance(
            source=source,
            source_field="perf_counter.elapsed_ms",
            source_artifact=source_artifact,
            unit="ms",
        ),
        "valid_contract_rate": MetricProvenance(
            source=MetricSource.EVENT_DERIVED if not blocked else MetricSource.NOT_AVAILABLE,
            source_field="planner.parse_result",
            source_artifact=source_artifact,
            unit="ratio",
        ),
    }
