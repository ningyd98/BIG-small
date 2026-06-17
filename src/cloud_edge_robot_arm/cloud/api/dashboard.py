from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from cloud_edge_robot_arm.dashboard.models import (
    AuditEventResponse,
    EvidenceListResponse,
    ExperimentCreateRequest,
    ExperimentListResponse,
)
from cloud_edge_robot_arm.dashboard.security import enforce_dashboard_access
from cloud_edge_robot_arm.dashboard.service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _service(request: Request) -> DashboardService:
    service = getattr(request.app.state, "dashboard_service", None)
    if service is None:
        service = DashboardService.from_environment()
        request.app.state.dashboard_service = service
    return service


@router.get("/capabilities")
async def capabilities(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).capabilities()


@router.get("/summary")
async def summary(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).summary()


@router.get("/runtime")
async def runtime(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).runtime()


@router.get("/safety")
async def safety(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).safety()


@router.get("/acceptance")
async def acceptance(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).acceptance()


@router.get("/evidence", response_model=EvidenceListResponse)
async def evidence(request: Request) -> EvidenceListResponse:
    enforce_dashboard_access(request)
    return EvidenceListResponse(records=_service(request).evidence_index.refresh())


@router.get("/evidence/{evidence_id}")
async def evidence_detail(request: Request, evidence_id: str) -> object:
    enforce_dashboard_access(request)
    if ".." in evidence_id or "/" in evidence_id or "\\" in evidence_id:
        raise HTTPException(status_code=400, detail="invalid_evidence_id")
    try:
        return _service(request).evidence_index.get_detail(evidence_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="evidence_not_found") from exc


@router.get("/evidence/{evidence_id}/download")
async def evidence_download(request: Request, evidence_id: str) -> object:
    return await evidence_detail(request, evidence_id)


@router.get("/experiments", response_model=ExperimentListResponse)
async def experiments(request: Request) -> ExperimentListResponse:
    enforce_dashboard_access(request)
    return ExperimentListResponse(jobs=_service(request).jobs.list_jobs())


@router.get("/experiments/{experiment_id}")
async def experiment_detail(request: Request, experiment_id: str) -> object:
    enforce_dashboard_access(request)
    job = _service(request).jobs.get(experiment_id)
    if job is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return job


@router.post("/experiments", status_code=202)
async def start_experiment(request: Request, body: ExperimentCreateRequest) -> object:
    enforce_dashboard_access(request)
    try:
        return _service(request).jobs.start(body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/experiments/{experiment_id}/cancel")
async def cancel_experiment(request: Request, experiment_id: str) -> object:
    enforce_dashboard_access(request)
    try:
        return _service(request).jobs.cancel(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="experiment_not_found") from exc


@router.get("/comparisons")
async def comparisons(request: Request) -> object:
    enforce_dashboard_access(request)
    return _service(request).comparisons()


@router.get("/audit-events", response_model=AuditEventResponse)
async def audit_events(request: Request) -> AuditEventResponse:
    enforce_dashboard_access(request)
    events = _service(request).events.replay_after(0)
    return AuditEventResponse(events=events)


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    service = DashboardService.from_environment()
    try:
        await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
        while True:
            await websocket.receive_text()
            await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
    except WebSocketDisconnect:
        return
