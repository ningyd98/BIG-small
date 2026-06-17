from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from cloud_edge_robot_arm.dashboard.models import (
    AcceptanceLevelSnapshot,
    AuditEventResponse,
    CapabilitiesResponse,
    ComparisonResponse,
    DashboardSummary,
    EvidenceDetailResponse,
    EvidenceIndexErrorRecord,
    EvidenceIndexRecord,
    EvidenceListResponse,
    EvidenceParseErrorResponse,
    ExperimentCreateRequest,
    ExperimentJobRecord,
    ExperimentListResponse,
    RuntimeSnapshot,
    SafetyGateSnapshot,
    SafetyReviewNoteRequest,
    SafetyReviewNoteResponse,
    UserRole,
)
from cloud_edge_robot_arm.dashboard.security import (
    enforce_dashboard_access,
    enforce_dashboard_role,
    enforce_dashboard_websocket_access,
)
from cloud_edge_robot_arm.dashboard.service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
MAX_WEBSOCKET_MESSAGE_BYTES = 2048
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS = 30.0


def _service(request: Request) -> DashboardService:
    service = getattr(request.app.state, "dashboard_service", None)
    if service is None:
        service = DashboardService.from_environment()
        request.app.state.dashboard_service = service
    return service


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(request: Request) -> CapabilitiesResponse:
    enforce_dashboard_access(request)
    return _service(request).capabilities()


@router.get("/summary", response_model=DashboardSummary)
async def summary(request: Request) -> DashboardSummary:
    enforce_dashboard_access(request)
    return _service(request).summary()


@router.get("/runtime", response_model=RuntimeSnapshot)
async def runtime(request: Request) -> RuntimeSnapshot:
    enforce_dashboard_access(request)
    return _service(request).runtime()


@router.get("/safety", response_model=SafetyGateSnapshot)
async def safety(request: Request) -> SafetyGateSnapshot:
    enforce_dashboard_access(request)
    return _service(request).safety()


@router.post("/safety/review-notes", status_code=201, response_model=SafetyReviewNoteResponse)
async def safety_review_note(
    request: Request, body: SafetyReviewNoteRequest
) -> SafetyReviewNoteResponse:
    role = enforce_dashboard_role(request, {UserRole.SAFETY_REVIEWER})
    return _service(request).record_safety_review_note(body, role=role)


@router.get("/acceptance", response_model=AcceptanceLevelSnapshot)
async def acceptance(request: Request) -> AcceptanceLevelSnapshot:
    enforce_dashboard_access(request)
    return _service(request).acceptance()


@router.get("/evidence", response_model=EvidenceListResponse)
async def evidence(
    request: Request,
    phase: str | None = None,
    status: str | None = None,
    backend: str | None = None,
    sort: Literal["generated_at", "relative_path", "status", "phase"] = "generated_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EvidenceListResponse:
    enforce_dashboard_access(request)
    records = _service(request).evidence_index.refresh()
    records = _filter_evidence(records, phase=phase, status=status, backend=backend)
    reverse = order == "desc"
    records = sorted(records, key=lambda record: str(getattr(record, sort)), reverse=reverse)
    return EvidenceListResponse(records=records[offset : offset + limit])


@router.get("/evidence-errors", response_model=EvidenceParseErrorResponse)
async def evidence_errors(request: Request) -> EvidenceParseErrorResponse:
    enforce_dashboard_access(request)
    index = _service(request).evidence_index
    index.refresh()
    return EvidenceParseErrorResponse(
        errors=[EvidenceIndexErrorRecord(path=item.path, error=item.error) for item in index.errors]
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def evidence_detail(request: Request, evidence_id: str) -> EvidenceDetailResponse:
    enforce_dashboard_access(request)
    if ".." in evidence_id or "/" in evidence_id or "\\" in evidence_id:
        raise HTTPException(status_code=400, detail="invalid_evidence_id")
    try:
        return _service(request).evidence_index.get_detail(evidence_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="evidence_not_found") from exc


@router.get("/evidence/{evidence_id}/download")
async def evidence_download(request: Request, evidence_id: str) -> object:
    enforce_dashboard_access(request)
    if ".." in evidence_id or "/" in evidence_id or "\\" in evidence_id:
        raise HTTPException(status_code=400, detail="invalid_evidence_id")
    service = _service(request)
    records = service.evidence_index.refresh()
    record = next((item for item in records if item.evidence_id == evidence_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    path = service.evidence_index.resolve_user_path(record.relative_path)
    return FileResponse(path, filename=Path(record.relative_path).name)


@router.get("/evidence/{left_evidence_id}/compare/{right_evidence_id}")
async def evidence_compare(
    request: Request, left_evidence_id: str, right_evidence_id: str
) -> object:
    enforce_dashboard_access(request)
    try:
        left = _service(request).evidence_index.get_detail(left_evidence_id)
        right = _service(request).evidence_index.get_detail(right_evidence_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="evidence_not_found") from exc
    return {
        "left": left.record,
        "right": right.record,
        "changed_fields": _changed_record_fields(left.record, right.record),
    }


@router.get("/experiments", response_model=ExperimentListResponse)
async def experiments(request: Request) -> ExperimentListResponse:
    enforce_dashboard_access(request)
    return ExperimentListResponse(jobs=_service(request).jobs.list_jobs())


@router.get("/experiments/{experiment_id}", response_model=ExperimentJobRecord)
async def experiment_detail(request: Request, experiment_id: str) -> ExperimentJobRecord:
    enforce_dashboard_access(request)
    job = _service(request).jobs.get(experiment_id)
    if job is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return job


@router.post("/experiments", status_code=202, response_model=ExperimentJobRecord)
async def start_experiment(request: Request, body: ExperimentCreateRequest) -> ExperimentJobRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).jobs.start(body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/experiments/{experiment_id}/cancel", response_model=ExperimentJobRecord)
async def cancel_experiment(request: Request, experiment_id: str) -> ExperimentJobRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).jobs.cancel(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="experiment_not_found") from exc


@router.get("/comparisons", response_model=ComparisonResponse)
async def comparisons(request: Request) -> ComparisonResponse:
    enforce_dashboard_access(request)
    return _service(request).comparisons()


@router.get("/audit-events", response_model=AuditEventResponse)
async def audit_events(request: Request) -> AuditEventResponse:
    enforce_dashboard_access(request)
    events = _service(request).events.replay_after(0)
    return AuditEventResponse(events=events)


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    enforce_dashboard_websocket_access(websocket)
    await websocket.accept()
    service = getattr(websocket.app.state, "dashboard_service", None)
    if service is None:
        service = DashboardService.from_environment()
        websocket.app.state.dashboard_service = service
    last_sequence = int(websocket.query_params.get("last_sequence", "0") or 0)
    try:
        for event in service.events.replay_after(last_sequence):
            await websocket.send_json(event.model_dump(mode="json"))
        await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
        while True:
            message = await _receive_dashboard_message(websocket)
            if message is None:
                await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
                continue
            if isinstance(message, dict) and "last_sequence" in message:
                try:
                    replay_after = int(str(message["last_sequence"]))
                except (TypeError, ValueError):
                    replay_after = last_sequence
                for event in service.events.replay_after(replay_after):
                    await websocket.send_json(event.model_dump(mode="json"))
                last_sequence = max(last_sequence, replay_after)
                continue
            await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
    except WebSocketDisconnect:
        return


async def _receive_dashboard_message(websocket: WebSocket) -> dict[str, object] | None:
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=WEBSOCKET_RECEIVE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return None
    if len(raw.encode("utf-8")) > MAX_WEBSOCKET_MESSAGE_BYTES:
        await websocket.close(code=1009, reason="message_too_large")
        raise WebSocketDisconnect(code=1009)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        await websocket.close(code=1003, reason="invalid_json")
        raise WebSocketDisconnect(code=1003) from exc
    return payload if isinstance(payload, dict) else {}


def _filter_evidence(
    records: list[EvidenceIndexRecord],
    *,
    phase: str | None,
    status: str | None,
    backend: str | None,
) -> list[EvidenceIndexRecord]:
    filtered = records
    if phase:
        filtered = [record for record in filtered if record.phase == phase]
    if status:
        filtered = [record for record in filtered if record.status.value == status]
    if backend:
        filtered = [record for record in filtered if record.backend == backend]
    return filtered


def _changed_record_fields(left: EvidenceIndexRecord, right: EvidenceIndexRecord) -> list[str]:
    left_payload = left.model_dump(mode="json")
    right_payload = right.model_dump(mode="json")
    return sorted(
        key
        for key in set(left_payload).union(right_payload)
        if left_payload.get(key) != right_payload.get(key)
    )
