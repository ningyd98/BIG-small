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


def create_app(
    pipeline: PlanningPipeline,
    *,
    supervisor: PeriodicSupervisorService | None = None,
    event_controller: Any = None,
) -> FastAPI:
    """Build the FastAPI application wired to a PlanningPipeline and optional event controller."""

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
            supported_control_modes=["PERIODIC_CLOUD_SUPERVISION", "AUTO"],
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

    @app.get(
        "/api/v1/event-control/capabilities",
        response_model=EventControlCapabilitiesResponse,
    )
    async def event_control_capabilities() -> EventControlCapabilitiesResponse:
        from cloud_edge_robot_arm.contracts.models import EdgeEventType, RecoveryAction, ReplanScope

        return EventControlCapabilitiesResponse(
            mode="EVENT_TRIGGERED_EDGE_AUTONOMY",
            supported_event_types=[et.value for et in EdgeEventType],
            supported_recovery_actions=[ra.value for ra in RecoveryAction],
            supported_replan_scopes=[rs.value for rs in ReplanScope],
            max_local_retries=3,
            configured=event_controller is not None,
        )

    @app.post(
        "/api/v1/robots/{robot_id}/events",
        response_model=EdgeEventResponse,
        status_code=201,
    )
    async def post_event(robot_id: str, body: dict[str, Any]) -> EdgeEventResponse:
        return EdgeEventResponse(
            event_id=body.get("event_id", "unknown"),
            task_id=body.get("task_id", ""),
            event_type=body.get("event_type", "UNKNOWN"),
            severity=body.get("severity", "INFO"),
            step_id=body.get("step_id"),
            reason_code=body.get("reason_code", ""),
            reason_detail=body.get("reason_detail", ""),
            details=body.get("details", {}),
        )

    @app.get(
        "/api/v1/tasks/{task_id}/events",
        response_model=EdgeEventListResponse,
    )
    async def list_task_events(task_id: str) -> EdgeEventListResponse:
        return EdgeEventListResponse(task_id=task_id, events=[])

    @app.get(
        "/api/v1/events/{event_id}",
        response_model=EdgeEventResponse,
    )
    async def get_event(event_id: str) -> EdgeEventResponse:
        return EdgeEventResponse(
            event_id=event_id,
            task_id="",
            event_type="UNKNOWN",
            severity="INFO",
        )

    @app.post(
        "/api/v1/tasks/{task_id}/failure-summaries",
        response_model=FailureSummaryResponse,
        status_code=201,
    )
    async def post_failure_summary(task_id: str, body: dict[str, Any]) -> FailureSummaryResponse:
        return FailureSummaryResponse(
            summary_id=body.get("summary_id", f"fs-{task_id}"),
            task_id=task_id,
            failure_event_id=body.get("failure_event_id", ""),
            failed_step_id=body.get("failed_step_id", ""),
            completed_step_ids=body.get("completed_step_ids", []),
            failure_type=body.get("failure_type", ""),
            severity=body.get("severity", ""),
            reason=body.get("reason", ""),
            recovery_hint=body.get("recovery_hint", ""),
            local_retry_count=body.get("local_retry_count", 0),
            requested_replan_scope=body.get("requested_replan_scope", ""),
        )

    @app.get(
        "/api/v1/failure-summaries/{summary_id}",
        response_model=FailureSummaryResponse,
    )
    async def get_failure_summary(summary_id: str) -> FailureSummaryResponse:
        return FailureSummaryResponse(
            summary_id=summary_id,
            task_id="",
            failure_event_id="",
            failed_step_id="",
        )

    @app.post(
        "/api/v1/plans/{plan_id}/replan",
        response_model=ReplanResponse,
        status_code=201,
    )
    async def replan_plan(plan_id: str, body: ReplanRequest) -> ReplanResponse:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        return ReplanResponse(
            request_id=f"replan-{now.strftime('%Y%m%d%H%M%S%f')}",
            outcome="REPLANNED",
            reason="Mock replan success",
            new_plan_version=body.current_plan_version + 1,
            new_command_seq=body.current_command_seq + 1,
            new_steps=[],
            planner_name="mock_replanner",
            prompt_version="1.0",
            created_at=now,
        )

    @app.get(
        "/api/v1/replanning/requests/{request_id}",
        response_model=ReplanResponse,
    )
    async def get_replan_request(request_id: str) -> ReplanResponse:
        return ReplanResponse(
            request_id=request_id,
            outcome="UNKNOWN",
            reason="Request not found",
        )

    @app.get(
        "/api/v1/replanning/requests/{request_id}/result",
        response_model=ReplanResponse,
    )
    async def get_replan_result(request_id: str) -> ReplanResponse:
        return ReplanResponse(
            request_id=request_id,
            outcome="UNKNOWN",
            reason="Result not found",
        )

    @app.post(
        "/api/v1/tasks/{task_id}/completion",
        response_model=CompletionReportResponse,
        status_code=201,
    )
    async def post_task_completion(
        task_id: str, body: CompletionReportRequest
    ) -> CompletionReportResponse:
        now = datetime.now(UTC)
        return CompletionReportResponse(
            summary_id=f"cs-{now.strftime('%Y%m%d%H%M%S%f')}",
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
        return CompletionReportResponse(
            summary_id=f"cs-{task_id}",
            task_id=task_id,
            result="UNKNOWN",
        )

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
