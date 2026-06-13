"""FastAPI application for the cloud planning service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from cloud_edge_robot_arm.cloud.api.schemas import (
    CapabilitiesResponse,
    CompletionReportRequest,
    CompletionReportResponse,
    DispatchRequest,
    DispatchResponse,
    EdgeEventListResponse,
    EdgeEventResponse,
    EdgeStatusSnapshotRequest,
    EventControlCapabilitiesResponse,
    FailureSummaryResponse,
    HealthResponse,
    PlanningRequest,
    PlanningResponse,
    ReplanRequest,
    ReplanResponse,
    RobotStatusIngestResponse,
    SupervisionCapabilitiesResponse,
    SupervisionDecisionListResponse,
    SupervisionStartRequest,
    SupervisionStatusResponse,
    TaskContractSchemaResponse,
)
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningResponse,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.supervision.models import (
    SupervisionConfig,
    SupervisoryDecision,
    SupervisoryDecisionType,
)
from cloud_edge_robot_arm.cloud.supervision.service import PeriodicSupervisorService
from cloud_edge_robot_arm.contracts import SkillName, TaskContract


_event_repo: Any = None


def create_app(
    pipeline: PlanningPipeline,
    *,
    supervisor: PeriodicSupervisorService | None = None,
    event_controller: Any = None,
    event_repo: Any = None,
) -> FastAPI:
    """Build the FastAPI application wired to a PlanningPipeline and optional event controller."""
    global _event_repo
    _event_repo = event_repo

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup — nothing needed yet
        yield
        # Shutdown — nothing needed yet

    app = FastAPI(
        title="BIG-small Cloud Planning API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Health ───────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version="0.1.0",
            timestamp=datetime.now(UTC),
        )

    # ── Capabilities ─────────────────────────────────────────────────────

    @app.get("/api/v1/planning/capabilities", response_model=CapabilitiesResponse)
    async def capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse(
            supported_skills=[s.value for s in SkillName],
            supported_control_modes=[
                "PERIODIC_CLOUD_SUPERVISION",
                "EVENT_TRIGGERED_EDGE_AUTONOMY",
            ],
            planner_name=pipeline._planner.planner_name,
            model_name=pipeline._planner.model_name,
        )

    # ── TaskContract Schema ──────────────────────────────────────────────

    @app.get(
        "/api/v1/planning/schemas/task-contract",
        response_model=TaskContractSchemaResponse,
    )
    async def task_contract_schema() -> TaskContractSchemaResponse:
        from cloud_edge_robot_arm.contracts import TaskContract as TC

        raw_schema: dict[str, Any] = TC.model_json_schema()
        return TaskContractSchemaResponse(task_contract_schema=raw_schema, version="1.0")

    # ── Create plan ──────────────────────────────────────────────────────

    @app.post("/api/v1/plans", response_model=PlanningResponse, status_code=201)
    async def create_plan(body: PlanningRequest) -> PlanningResponse:
        from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest

        ireq = InitialPlanningRequest(
            request_id=body.request_id,
            user_instruction=body.user_instruction,
            control_mode=body.control_mode,
            scene=body.scene,
            capabilities=body.capabilities,
            safety_policy=body.safety_policy,
        )
        result = pipeline.process(ireq)
        return _planning_response(result)

    # ── Get plan ─────────────────────────────────────────────────────────

    @app.get("/api/v1/plans/{planning_id}", response_model=PlanningResponse)
    async def get_plan(planning_id: str) -> PlanningResponse:
        cached = pipeline._cache.get(planning_id)
        if cached is None:
            raise HTTPException(status_code=404, detail="Planning request not found")
        _, result = cached
        return _planning_response(result)

    # ── Dispatch plan ────────────────────────────────────────────────────

    @app.post(
        "/api/v1/plans/{planning_id}/dispatch",
        response_model=DispatchResponse,
    )
    async def dispatch_plan(
        planning_id: str, body: DispatchRequest | None = None
    ) -> DispatchResponse:
        cached = pipeline._cache.get(planning_id)
        if cached is None:
            raise HTTPException(status_code=404, detail="Planning request not found")
        _, result = cached
        if result.contract is None:
            raise HTTPException(
                status_code=409,
                detail="No contract to dispatch — planning did not succeed",
            )
        # Dispatch requires the gateway to be set
        gateway = getattr(pipeline, "_gateway", None)
        if gateway is None:
            raise HTTPException(
                status_code=501,
                detail="Edge gateway not configured for this pipeline instance",
            )
        edge_result = gateway.dispatch(result.contract)
        return DispatchResponse(
            request_id=planning_id,
            task_id=result.contract.task_id,
            dispatched=edge_result.dispatched,
            edge_accepted=edge_result.edge_accepted,
            edge_reason=edge_result.edge_reason,
        )

    # ── Supervision ──────────────────────────────────────────────────────

    @app.get(
        "/api/v1/supervision/capabilities",
        response_model=SupervisionCapabilitiesResponse,
    )
    async def supervision_capabilities() -> SupervisionCapabilitiesResponse:
        config = supervisor._config if supervisor is not None else SupervisionConfig()
        return SupervisionCapabilitiesResponse(
            supported_decisions=[decision.value for decision in SupervisoryDecisionType],
            allowed_periods_ms=SupervisionConfig.allowed_periods(),
            configured_period_ms=config.supervision_period_ms,
            command_ttl_ms=config.command_ttl_ms,
        )

    @app.post(
        "/api/v1/robots/{robot_id}/status",
        response_model=RobotStatusIngestResponse,
        status_code=202,
    )
    async def ingest_robot_status(
        robot_id: str,
        body: EdgeStatusSnapshotRequest,
    ) -> RobotStatusIngestResponse:
        sv = _require_supervisor(supervisor)
        if body.robot_id != robot_id:
            raise HTTPException(status_code=409, detail="robot_id_mismatch")
        sv.record_status_snapshot(body)
        return RobotStatusIngestResponse(
            accepted=True,
            robot_id=robot_id,
            task_id=body.task_id,
            scene_version=body.scene_version,
        )

    @app.post(
        "/api/v1/plans/{plan_id}/supervise",
        response_model=SupervisoryDecision,
    )
    async def supervise_plan(
        plan_id: str,
        body: EdgeStatusSnapshotRequest,
    ) -> SupervisoryDecision:
        sv = _require_supervisor(supervisor)
        contract = _contract_for_plan_id(pipeline, sv, plan_id)
        if contract is None:
            raise HTTPException(status_code=404, detail="plan_not_found")
        if body.task_id != contract.task_id:
            raise HTTPException(status_code=409, detail="task_id_mismatch")
        return sv.evaluate_snapshot(body, contract)

    @app.get(
        "/api/v1/plans/{plan_id}/supervision/decisions",
        response_model=SupervisionDecisionListResponse,
    )
    async def list_supervision_decisions(plan_id: str) -> SupervisionDecisionListResponse:
        sv = _require_supervisor(supervisor)
        contract = _contract_for_plan_id(pipeline, sv, plan_id)
        task_id = contract.task_id if contract is not None else plan_id
        return SupervisionDecisionListResponse(decisions=sv.decisions_for_task(task_id))

    @app.post(
        "/api/v1/plans/{plan_id}/supervision/start",
        response_model=SupervisionStatusResponse,
    )
    async def start_supervision(
        plan_id: str,
        body: SupervisionStartRequest | None = None,
    ) -> SupervisionStatusResponse:
        sv = _require_supervisor(supervisor)
        contract = _contract_for_plan_id(pipeline, sv, plan_id)
        if contract is None:
            raise HTTPException(status_code=404, detail="plan_not_found")
        sv.start(contract)
        return _supervision_status_response(sv, contract.task_id)

    @app.post(
        "/api/v1/plans/{plan_id}/supervision/stop",
        response_model=SupervisionStatusResponse,
    )
    async def stop_supervision(plan_id: str) -> SupervisionStatusResponse:
        sv = _require_supervisor(supervisor)
        contract = _contract_for_plan_id(pipeline, sv, plan_id)
        task_id = contract.task_id if contract is not None else plan_id
        if sv.status_for_task(task_id) is None:
            raise HTTPException(status_code=404, detail="plan_not_found")
        sv.stop(task_id)
        return _supervision_status_response(sv, task_id)

    @app.get(
        "/api/v1/plans/{plan_id}/supervision/status",
        response_model=SupervisionStatusResponse,
    )
    async def supervision_status(plan_id: str) -> SupervisionStatusResponse:
        sv = _require_supervisor(supervisor)
        contract = _contract_for_plan_id(pipeline, sv, plan_id)
        task_id = contract.task_id if contract is not None else plan_id
        if sv.status_for_task(task_id) is None:
            raise HTTPException(status_code=404, detail="plan_not_found")
        return _supervision_status_response(sv, task_id)

    # ── Phase 6: Event-Triggered Edge Autonomy ────────────────────────────

    def _require_event_repo() -> Any:
        if _event_repo is None:
            raise HTTPException(status_code=503, detail="event_autonomy_unavailable")
        return _event_repo

    @app.get(
        "/api/v1/event-control/capabilities",
        response_model=EventControlCapabilitiesResponse,
    )
    async def event_control_capabilities() -> EventControlCapabilitiesResponse:
        from cloud_edge_robot_arm.contracts.models import EdgeEventType, RecoveryAction, ReplanScope

        repo = _event_repo
        is_sqlite = repo is not None and hasattr(repo, "path")
        return EventControlCapabilitiesResponse(
            mode="EVENT_TRIGGERED_EDGE_AUTONOMY",
            supported_event_types=[et.value for et in EdgeEventType],
            supported_recovery_actions=[ra.value for ra in RecoveryAction],
            supported_replan_scopes=[rs.value for rs in ReplanScope],
            max_local_retries=10,
            configured=is_sqlite,
        )

    @app.post(
        "/api/v1/robots/{robot_id}/events",
        response_model=EdgeEventResponse,
        status_code=201,
    )
    async def post_event(robot_id: str, body: dict[str, Any]) -> EdgeEventResponse:
        repo = _require_event_repo()
        event_id = str(body.get("event_id", ""))
        if not event_id:
            raise HTTPException(status_code=400, detail="event_id is required")
        existing = getattr(repo, "get_event", lambda eid: None)(event_id)
        if existing is not None:
            if getattr(existing, "robot_id", "") and existing.robot_id != robot_id:
                raise HTTPException(status_code=403, detail="access_denied: robot_id mismatch")
            return EdgeEventResponse(
                event_id=existing.event_id,
                task_id=existing.task_id,
                event_type=existing.event_type.value if hasattr(existing.event_type, 'value') else str(existing.event_type),
                severity=str(existing.severity),
                step_id=existing.step_id,
                reason_code=existing.reason_code,
                reason_detail=existing.reason_detail,
                details=existing.details,
            )
        from cloud_edge_robot_arm.contracts.models import EdgeEvent as EE
        now = datetime.now(UTC)
        event = EE(
            event_id=event_id,
            task_id=str(body.get("task_id", "")),
            event_type=str(body.get("event_type", "UNKNOWN")),
            step_id=body.get("step_id"),
            severity=str(body.get("severity", "ERROR")),
            reason_code=str(body.get("reason_code", "")),
            reason_detail=str(body.get("reason_detail", "")),
            details=body.get("details", {}),
            robot_id=robot_id,
            plan_version=0,
            command_seq=0,
            timestamp=now,
        )
        repo.save_event(event)
        return EdgeEventResponse(
            event_id=event.event_id,
            task_id=event.task_id,
            event_type=event.event_type.value,
            severity=str(event.severity),
            step_id=event.step_id,
            reason_code=event.reason_code,
            reason_detail=event.reason_detail,
            details=event.details,
        )

    @app.get(
        "/api/v1/tasks/{task_id}/events",
        response_model=EdgeEventListResponse,
    )
    async def list_task_events(task_id: str) -> EdgeEventListResponse:
        repo = _require_event_repo()
        events = getattr(repo, "list_events", lambda tid: [])(task_id)
        return EdgeEventListResponse(
            task_id=task_id,
            events=[
                EdgeEventResponse(
                    event_id=e.event_id,
                    task_id=e.task_id,
                    event_type=e.event_type.value if hasattr(e.event_type, 'value') else str(e.event_type),
                    severity=str(e.severity),
                    step_id=e.step_id,
                    reason_code=e.reason_code,
                    reason_detail=e.reason_detail,
                    details=e.details,
                )
                for e in events
            ],
        )

    @app.get(
        "/api/v1/events/{event_id}",
        response_model=EdgeEventResponse,
    )
    async def get_event(event_id: str) -> EdgeEventResponse:
        repo = _require_event_repo()
        event = getattr(repo, "get_event", lambda eid: None)(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event_not_found")
        return EdgeEventResponse(
            event_id=event.event_id,
            task_id=event.task_id,
            event_type=event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
            severity=str(event.severity),
            step_id=event.step_id,
            reason_code=event.reason_code,
            reason_detail=event.reason_detail,
            details=event.details,
        )

    @app.post(
        "/api/v1/tasks/{task_id}/failure-summaries",
        response_model=FailureSummaryResponse,
        status_code=201,
    )
    async def post_failure_summary(task_id: str, body: dict[str, Any]) -> FailureSummaryResponse:
        repo = _require_event_repo()
        summary_id = str(body.get("summary_id", f"fs-{task_id}"))
        existing = getattr(repo, "get_failure_summary", lambda sid: None)(summary_id)
        if existing is not None:
            if existing.task_id != task_id:
                raise HTTPException(status_code=403, detail="access_denied: task_id mismatch")
            return FailureSummaryResponse(
                summary_id=existing.summary_id,
                task_id=existing.task_id,
                failure_event_id=existing.failure_event_id,
                failed_step_id=existing.failed_step_id,
                completed_step_ids=list(existing.completed_step_ids),
                failure_type=existing.failure_type,
                severity=existing.severity,
                reason=existing.reason,
                recovery_hint=existing.recovery_hint,
                local_retry_count=existing.local_retry_count,
                requested_replan_scope=existing.requested_replan_scope,
            )
        from cloud_edge_robot_arm.contracts.models import FailureSummary
        now = datetime.now(UTC)
        summary = FailureSummary(
            summary_id=summary_id,
            task_id=task_id,
            failure_event_id=str(body.get("failure_event_id", "")),
            failed_step_id=str(body.get("failed_step_id", "")),
            completed_step_ids=list(body.get("completed_step_ids", [])),
            failure_type=str(body.get("failure_type", "")),
            severity=str(body.get("severity", "ERROR")),
            reason=str(body.get("reason", "")),
            recovery_hint=str(body.get("recovery_hint", "")),
            local_retry_count=int(body.get("local_retry_count", 0)),
            requested_replan_scope=str(body.get("requested_replan_scope", "")),
            plan_version=0,
            command_seq=0,
            timestamp=now,
        )
        repo.save_failure_summary(summary)
        return FailureSummaryResponse(
            summary_id=summary.summary_id,
            task_id=summary.task_id,
            failure_event_id=summary.failure_event_id,
            failed_step_id=summary.failed_step_id,
            completed_step_ids=list(summary.completed_step_ids),
            failure_type=summary.failure_type,
            severity=summary.severity,
            reason=summary.reason,
            recovery_hint=summary.recovery_hint,
            local_retry_count=summary.local_retry_count,
            requested_replan_scope=summary.requested_replan_scope,
        )

    @app.get(
        "/api/v1/failure-summaries/{summary_id}",
        response_model=FailureSummaryResponse,
    )
    async def get_failure_summary(summary_id: str) -> FailureSummaryResponse:
        repo = _require_event_repo()
        summary = getattr(repo, "get_failure_summary", lambda sid: None)(summary_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="failure_summary_not_found")
        return FailureSummaryResponse(
            summary_id=summary.summary_id,
            task_id=summary.task_id,
            failure_event_id=summary.failure_event_id,
            failed_step_id=summary.failed_step_id,
            completed_step_ids=list(summary.completed_step_ids),
            failure_type=summary.failure_type,
            severity=summary.severity,
            reason=summary.reason,
            recovery_hint=summary.recovery_hint,
            local_retry_count=summary.local_retry_count,
            requested_replan_scope=summary.requested_replan_scope,
        )

    @app.post(
        "/api/v1/plans/{plan_id}/replan",
        response_model=ReplanResponse,
        status_code=201,
    )
    async def replan_plan(plan_id: str, body: ReplanRequest) -> ReplanResponse:
        repo = _require_event_repo()
        if body.plan_id and body.plan_id != plan_id:
            raise HTTPException(status_code=409, detail="plan_id_mismatch")
        request_id = body.idempotency_key or f"replan-{plan_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        # Check idempotency
        existing = getattr(repo, "get_replan_result", lambda rid: None)(request_id)
        if existing is not None:
            return ReplanResponse(
                request_id=existing.request_id,
                outcome=existing.outcome,
                reason=existing.reason,
                new_plan_version=existing.new_plan_version,
                new_command_seq=existing.new_command_seq,
                new_steps=[s.model_dump(mode="json") for s in existing.new_steps],
                planner_name=existing.planner_name,
                prompt_version=existing.prompt_version,
                created_at=existing.created_at,
            )
        from cloud_edge_robot_arm.contracts.models import LocalReplanningRequest
        now = datetime.now(UTC)
        lrr = LocalReplanningRequest(
            request_id=request_id,
            trigger_event_id=body.trigger_event_id,
            failure_summary_id=body.failure_summary_id,
            robot_id=body.robot_id,
            task_id=body.task_id,
            plan_id=plan_id,
            current_plan_version=body.current_plan_version,
            current_command_seq=body.current_command_seq,
            requested_replan_scope=body.requested_replan_scope,
            completed_step_ids=list(body.completed_step_ids),
            failed_step_id=body.failed_step_id,
            last_successful_step_id=body.last_successful_step_id,
            current_scene_version=body.current_scene_version,
            scene_confidence=body.scene_confidence,
            idempotency_key=body.idempotency_key or request_id,
            requested_at=now,
        )
        repo.save_replan_request(lrr)
        return ReplanResponse(
            request_id=request_id,
            outcome="PENDING",
            reason="Replan request queued",
            new_plan_version=body.current_plan_version,
            new_command_seq=body.current_command_seq,
            planner_name="",
            prompt_version="",
            created_at=now,
        )

    @app.get(
        "/api/v1/replanning/requests/{request_id}",
        response_model=ReplanResponse,
    )
    async def get_replan_request(request_id: str) -> ReplanResponse:
        repo = _require_event_repo()
        req = getattr(repo, "get_replan_request", lambda rid: None)(request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="replan_request_not_found")
        return ReplanResponse(
            request_id=req.request_id,
            outcome="PENDING",
            reason="Request exists",
            new_plan_version=req.current_plan_version,
            new_command_seq=req.current_command_seq,
        )

    @app.get(
        "/api/v1/replanning/requests/{request_id}/result",
        response_model=ReplanResponse,
    )
    async def get_replan_result(request_id: str) -> ReplanResponse:
        repo = _require_event_repo()
        result = getattr(repo, "get_replan_result", lambda rid: None)(request_id)
        if result is None:
            raise HTTPException(status_code=404, detail="replan_result_not_found")
        return ReplanResponse(
            request_id=result.request_id,
            outcome=result.outcome,
            reason=result.reason,
            new_plan_version=result.new_plan_version,
            new_command_seq=result.new_command_seq,
            new_steps=[s.model_dump(mode="json") for s in result.new_steps],
            planner_name=result.planner_name,
            prompt_version=result.prompt_version,
            created_at=result.created_at,
        )

    @app.post(
        "/api/v1/tasks/{task_id}/completion",
        response_model=CompletionReportResponse,
        status_code=201,
    )
    async def post_task_completion(
        task_id: str, body: CompletionReportRequest
    ) -> CompletionReportResponse:
        repo = _require_event_repo()
        now = datetime.now(UTC)
        summary_id = f"cs-{task_id}-{now.strftime('%Y%m%d%H%M%S%f')}"
        from cloud_edge_robot_arm.contracts.models import CompletionSummary
        cs = CompletionSummary(
            summary_id=summary_id,
            task_id=task_id,
            completed_step_ids=list(body.completed_step_ids),
            result=str(body.result),
            local_retry_count=int(body.local_retry_count),
            cloud_replan_count=int(body.cloud_replan_count),
            completed_at=now,
            plan_version=0,
            command_seq=0,
            timestamp=now,
        )
        repo.save_completion_summary(cs)
        return CompletionReportResponse(
            summary_id=summary_id,
            task_id=task_id,
            result=body.result,
            local_retry_count=body.local_retry_count,
            cloud_replan_count=body.cloud_replan_count,
            completed_at=now,
        )

    @app.get(
        "/api/v1/tasks/{task_id}/completion",
        response_model=CompletionReportResponse,
    )
    async def get_task_completion(task_id: str) -> CompletionReportResponse:
        repo = _require_event_repo()
        # Find the latest completion summary for this task
        completions = getattr(repo, "_completion_summaries", {})
        for sid, cs in reversed(list(completions.items())):
            if getattr(cs, "task_id", "") == task_id:
                return CompletionReportResponse(
                    summary_id=cs.summary_id,
                    task_id=cs.task_id,
                    result=cs.result,
                    local_retry_count=cs.local_retry_count,
                    cloud_replan_count=cs.cloud_replan_count,
                    completed_at=cs.completed_at,
                )
        raise HTTPException(status_code=404, detail="completion_not_found")

    # ── Exception handlers ───────────────────────────────────────────────

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "bad_request", "message": str(exc)},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    return app


def _planning_response(result: InitialPlanningResponse) -> PlanningResponse:
    from cloud_edge_robot_arm.cloud.api.schemas import PlanningResponse

    return PlanningResponse(
        request_id=result.request_id,
        outcome=result.outcome.value,
        reason=result.reason,
        contract=result.contract.model_dump(mode="json") if result.contract else None,
        validation_errors=result.validation.errors,
        validation_warnings=result.validation.warnings,
        attempt_count=len(result.attempts),
        created_at=result.created_at.isoformat(),
    )


def _require_supervisor(
    supervisor: PeriodicSupervisorService | None,
) -> PeriodicSupervisorService:
    if supervisor is None:
        raise HTTPException(status_code=503, detail="supervision_unavailable")
    return supervisor


def _contract_for_plan_id(
    pipeline: PlanningPipeline,
    supervisor: PeriodicSupervisorService,
    plan_id: str,
) -> TaskContract | None:
    cached = pipeline._cache.get(plan_id)
    if cached is not None:
        _, result = cached
        if result.contract is not None:
            return result.contract
    for _, result in pipeline._cache.values():
        if result.contract is not None and result.contract.task_id == plan_id:
            return result.contract
    status = supervisor.status_for_task(plan_id)
    return status.contract if status is not None else None


def _supervision_status_response(
    supervisor: PeriodicSupervisorService,
    task_id: str,
) -> SupervisionStatusResponse:
    status = supervisor.status_for_task(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return SupervisionStatusResponse(
        task_id=task_id,
        running=bool(status.running),
        last_plan_version=int(status.last_plan_version),
        last_command_seq=int(status.last_command_seq),
    )
