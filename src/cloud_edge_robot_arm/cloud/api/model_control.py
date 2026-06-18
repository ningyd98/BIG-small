"""AI 模型控制中心 API。

本路由只暴露 profile、active planner 状态和安全能力查询；API key 是 write-only，
响应永远不返回 secret 明文。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob
from cloud_edge_robot_arm.model_control.endpoint_security import EndpointSecurityError
from cloud_edge_robot_arm.model_control.models import (
    ModelProviderProfile,
    PlannerProviderKind,
    PlannerRuntimeStatus,
    SecretStoreKind,
)
from cloud_edge_robot_arm.model_control.providers.ollama import OllamaHttpClient, OllamaTransport
from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

router = APIRouter(prefix="/api/v1/model-control", tags=["model-control"])


class ModelCapabilitiesResponse(BaseModel):
    supported_provider_kinds: list[PlannerProviderKind]
    secret_store_modes: list[SecretStoreKind]
    ollama_default_base_url: str = "http://127.0.0.1:11434"
    profile_limit: int = Field(default=64, ge=1)
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)


class ProfileCreateRequest(BaseModel):
    display_name: str
    provider_kind: PlannerProviderKind
    base_url: str = ""
    chat_completions_path: str = "/v1/chat/completions"
    model_name: str
    api_key: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: float = 30.0
    max_retries: int = 2
    json_mode: bool = True


class ProfilePatchRequest(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    chat_completions_path: str | None = None
    model_name: str | None = None
    api_key: str | None = None


class DownloadCreateRequest(BaseModel):
    model_name: str


class PlannerDryRunRequest(BaseModel):
    user_instruction: str
    sample_scene: str
    control_mode: str


@router.get("/capabilities", response_model=ModelCapabilitiesResponse)
async def capabilities() -> ModelCapabilitiesResponse:
    return ModelCapabilitiesResponse(
        supported_provider_kinds=[kind for kind in PlannerProviderKind],
        secret_store_modes=[SecretStoreKind.SESSION_ONLY],
    )


@router.get("/profiles", response_model=list[ModelProviderProfile])
async def list_profiles(request: Request) -> list[ModelProviderProfile]:
    return _service(request).list_profiles()


@router.post(
    "/profiles",
    response_model=ModelProviderProfile,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(request: Request, body: ProfileCreateRequest) -> ModelProviderProfile:
    try:
        return _service(request).create_profile(**body.model_dump())
    except EndpointSecurityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/profiles/{profile_id}", response_model=ModelProviderProfile)
async def update_profile(
    request: Request,
    profile_id: str,
    body: ProfilePatchRequest,
) -> ModelProviderProfile:
    try:
        return _service(request).update_profile(
            profile_id,
            **body.model_dump(exclude_unset=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="profile_not_found") from exc
    except EndpointSecurityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(request: Request, profile_id: str) -> None:
    try:
        _service(request).delete_profile(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="profile_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/profiles/{profile_id}/activate", response_model=PlannerRuntimeStatus)
async def activate_profile(request: Request, profile_id: str) -> PlannerRuntimeStatus:
    try:
        return _service(request).activate_profile(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="profile_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runtime", response_model=PlannerRuntimeStatus)
async def runtime(request: Request) -> PlannerRuntimeStatus:
    return _service(request).runtime_status()


@router.get("/ollama/status")
async def ollama_status(request: Request) -> dict[str, object]:
    return _service(request).ollama_status(_ollama_transport(request))


@router.get("/ollama/models")
async def ollama_models(request: Request) -> list[dict[str, object]]:
    return _service(request).ollama_models(_ollama_transport(request))


@router.get("/catalog")
async def small_model_catalog(request: Request) -> list[dict[str, object]]:
    return _service(request).small_model_catalog(_ollama_transport(request))


@router.post(
    "/ollama/downloads",
    response_model=ModelDownloadJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_ollama_download(request: Request, body: DownloadCreateRequest) -> ModelDownloadJob:
    try:
        return _service(request).start_ollama_download(
            model_name=body.model_name,
            transport=_ollama_transport(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/ollama/downloads", response_model=list[ModelDownloadJob])
async def list_ollama_downloads(request: Request) -> list[ModelDownloadJob]:
    return _service(request).list_downloads()


@router.post("/ollama/models/{model_name:path}/activate", response_model=PlannerRuntimeStatus)
async def activate_ollama_model(request: Request, model_name: str) -> PlannerRuntimeStatus:
    try:
        return _service(request).activate_ollama_model(
            model_name=model_name,
            transport=_ollama_transport(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/planner/dry-run")
async def planner_dry_run(request: Request, body: PlannerDryRunRequest) -> dict[str, object]:
    try:
        return _service(request).planner_dry_run(
            user_instruction=body.user_instruction,
            sample_scene=body.sample_scene,
            control_mode=body.control_mode,
            transport=_ollama_transport(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _service(request: Request) -> ModelControlService:
    service = getattr(request.app.state, "model_control_service", None)
    if service is not None:
        return cast(ModelControlService, service)
    database_path = Path(os.environ.get("MODEL_CONTROL_DB", "data/model_control.db"))
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database_path),
        secret_store=InMemorySecretStore(),
    )
    request.app.state.model_control_service = service
    return service


def _ollama_transport(request: Request) -> OllamaTransport:
    transport = getattr(request.app.state, "ollama_transport", None)
    if transport is not None:
        return cast(OllamaTransport, transport)
    transport = OllamaHttpClient()
    request.app.state.ollama_transport = transport
    return transport
