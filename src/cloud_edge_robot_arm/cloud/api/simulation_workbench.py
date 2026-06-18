"""仿真工作台 API 路由。

该路由暴露 /api/v1/simulation 能力、场景、run、batch、runtime health 和 WebSocket
stream。浏览器只能提交高层实验配置，不能直接连接 MuJoCo、Isaac、ROS 或真实硬件。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from cloud_edge_robot_arm.dashboard.models import UserRole
from cloud_edge_robot_arm.dashboard.security import (
    enforce_dashboard_access,
    enforce_dashboard_role,
    enforce_dashboard_websocket_access,
)
from cloud_edge_robot_arm.simulation_runtime.models import (
    AttemptListResponse,
    QueueStatusResponse,
    RecoveryResponse,
    RuntimeHealthResponse,
    WorkerListResponse,
)
from cloud_edge_robot_arm.simulation_workbench.models import (
    BatchRecord,
    ComparisonRequest,
    ComparisonResponse,
    ExperimentDraft,
    ExportRequest,
    ExportResponse,
    ParameterSchemaResponse,
    ReproductionResponse,
    ScenarioDefinitionView,
    ScenarioListResponse,
    SimulationArtifactsResponse,
    SimulationCapabilitiesResponse,
    SimulationEventsResponse,
    SimulationMetricsResponse,
    SimulationRunListResponse,
    SimulationRunRecord,
    ValidationResponse,
)
from cloud_edge_robot_arm.simulation_workbench.service import SimulationWorkbenchService

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation-workbench"])
MAX_WEBSOCKET_MESSAGE_BYTES = 2048
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS = 30.0


def _service(request: Request) -> SimulationWorkbenchService:
    service = getattr(request.app.state, "simulation_workbench_service", None)
    if service is None:
        service = SimulationWorkbenchService(
            artifact_root=Path(os.environ.get("DASHBOARD_ARTIFACT_ROOT", "artifacts"))
        )
        request.app.state.simulation_workbench_service = service
    return service


def _ws_service(websocket: WebSocket) -> SimulationWorkbenchService:
    service = getattr(websocket.app.state, "simulation_workbench_service", None)
    if service is None:
        service = SimulationWorkbenchService(
            artifact_root=Path(os.environ.get("DASHBOARD_ARTIFACT_ROOT", "artifacts"))
        )
        websocket.app.state.simulation_workbench_service = service
    return service


@router.get("/capabilities", response_model=SimulationCapabilitiesResponse)
async def capabilities(request: Request) -> SimulationCapabilitiesResponse:
    enforce_dashboard_access(request)
    return _service(request).capabilities()


@router.get("/scenarios", response_model=ScenarioListResponse)
async def scenarios(request: Request) -> ScenarioListResponse:
    enforce_dashboard_access(request)
    return _service(request).scenarios()


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDefinitionView)
async def scenario(request: Request, scenario_id: str) -> ScenarioDefinitionView:
    enforce_dashboard_access(request)
    try:
        return _service(request).scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="scenario_not_found") from exc


@router.get("/parameter-schema", response_model=ParameterSchemaResponse)
async def parameter_schema(request: Request) -> ParameterSchemaResponse:
    enforce_dashboard_access(request)
    return _service(request).parameter_schema()


@router.post("/validate", response_model=ValidationResponse)
async def validate(request: Request, body: ExperimentDraft) -> ValidationResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).validate(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runs", status_code=202, response_model=SimulationRunRecord)
async def create_run(request: Request, body: ExperimentDraft) -> SimulationRunRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).create_run(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs", response_model=SimulationRunListResponse)
async def list_runs(request: Request) -> SimulationRunListResponse:
    enforce_dashboard_access(request)
    return _service(request).list_runs()


@router.get("/runs/{run_id}", response_model=SimulationRunRecord)
async def get_run(request: Request, run_id: str) -> SimulationRunRecord:
    enforce_dashboard_access(request)
    try:
        return _service(request).get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.get("/runs/{run_id}/events", response_model=SimulationEventsResponse)
async def run_events(request: Request, run_id: str) -> SimulationEventsResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).events_for(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.get("/runs/{run_id}/metrics", response_model=SimulationMetricsResponse)
async def run_metrics(request: Request, run_id: str) -> SimulationMetricsResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).metrics_for(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.get("/runs/{run_id}/artifacts", response_model=SimulationArtifactsResponse)
async def run_artifacts(request: Request, run_id: str) -> SimulationArtifactsResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).artifacts_for(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.post("/runs/{run_id}/cancel", response_model=SimulationRunRecord)
async def cancel_run(request: Request, run_id: str) -> SimulationRunRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.get("/runs/{run_id}/attempts", response_model=AttemptListResponse)
async def run_attempts(request: Request, run_id: str) -> AttemptListResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).runtime.attempts_for(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.post("/runs/{run_id}/retry", status_code=202, response_model=SimulationRunRecord)
async def retry_run(request: Request, run_id: str) -> SimulationRunRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).retry_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/clone", response_model=ReproductionResponse)
async def clone_run(request: Request, run_id: str) -> ReproductionResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).clone_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.post("/runs/{run_id}/reproduce", response_model=ReproductionResponse)
async def reproduce_run(request: Request, run_id: str) -> ReproductionResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).reproduce_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.post("/batches", status_code=202, response_model=BatchRecord)
async def create_batch(request: Request, body: ExperimentDraft) -> BatchRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).create_batch(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/batches/{batch_id}", response_model=BatchRecord)
async def get_batch(request: Request, batch_id: str) -> BatchRecord:
    enforce_dashboard_access(request)
    try:
        return _service(request).get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="batch_not_found") from exc


@router.get("/batches/{batch_id}/runs", response_model=SimulationRunListResponse)
async def batch_runs(request: Request, batch_id: str) -> SimulationRunListResponse:
    enforce_dashboard_access(request)
    try:
        return _service(request).batch_runs(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="batch_not_found") from exc


@router.post("/batches/{batch_id}/cancel", response_model=BatchRecord)
async def cancel_batch(request: Request, batch_id: str) -> BatchRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).cancel_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="batch_not_found") from exc


@router.post("/batches/{batch_id}/retry-failed", response_model=BatchRecord)
async def retry_failed_batch(request: Request, batch_id: str) -> BatchRecord:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return _service(request).retry_failed_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="batch_not_found") from exc


@router.post("/comparisons", response_model=ComparisonResponse)
async def comparisons(request: Request, body: ComparisonRequest) -> ComparisonResponse:
    enforce_dashboard_access(request)
    return _service(request).compare(body)


@router.post("/exports", response_model=ExportResponse)
async def exports(request: Request, body: ExportRequest) -> ExportResponse:
    enforce_dashboard_access(request)
    return _service(request).export(body)


@router.get("/runtime/health", response_model=RuntimeHealthResponse)
async def runtime_health(request: Request) -> RuntimeHealthResponse:
    enforce_dashboard_access(request)
    return _service(request).runtime.health()


@router.get("/runtime/workers", response_model=WorkerListResponse)
async def runtime_workers(request: Request) -> WorkerListResponse:
    enforce_dashboard_access(request)
    return _service(request).runtime.workers()


@router.get("/runtime/queue", response_model=QueueStatusResponse)
async def runtime_queue(request: Request) -> QueueStatusResponse:
    enforce_dashboard_access(request)
    return _service(request).runtime.queue()


@router.post("/runtime/recover", response_model=RecoveryResponse)
async def runtime_recover(request: Request) -> RecoveryResponse:
    enforce_dashboard_role(request, {UserRole.SAFETY_REVIEWER})
    return _service(request).runtime.recover()


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    enforce_dashboard_websocket_access(websocket)
    await websocket.accept()
    service = _ws_service(websocket)
    last_sequence = int(websocket.query_params.get("last_sequence", "0") or 0)
    try:
        replayed = service.runtime.replay_stream_after(last_sequence)
        if not replayed:
            replayed = service.events.replay_after(last_sequence)
        for event in replayed:
            await websocket.send_json(event.model_dump(mode="json"))
        await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
        while True:
            message = await _receive_message(websocket)
            if message is None:
                await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
                continue
            if "last_sequence" in message:
                try:
                    replay_after = int(str(message["last_sequence"]))
                except (TypeError, ValueError):
                    replay_after = last_sequence
                replayed = service.runtime.replay_stream_after(replay_after)
                if not replayed:
                    replayed = service.events.replay_after(replay_after)
                for event in replayed:
                    await websocket.send_json(event.model_dump(mode="json"))
                last_sequence = max(last_sequence, replay_after)
                continue
            await websocket.send_json(service.events.heartbeat().model_dump(mode="json"))
    except WebSocketDisconnect:
        return


async def _receive_message(websocket: WebSocket) -> dict[str, object] | None:
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
