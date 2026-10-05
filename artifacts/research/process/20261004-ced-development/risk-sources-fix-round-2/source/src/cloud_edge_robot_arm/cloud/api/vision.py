"""Authenticated simulator RGB-D capture; no arbitrary paths or commands."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.dashboard.models import UserRole
from cloud_edge_robot_arm.dashboard.security import enforce_dashboard_role
from cloud_edge_robot_arm.vision.capture import capture_simulated_observation
from cloud_edge_robot_arm.vision.observations import RGBDObservation

router = APIRouter(prefix="/api/v1/vision", tags=["rgbd-vision"])


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["MUJOCO", "ISAAC_SIM"] = "MUJOCO"
    scenario_id: Literal["S01_NORMAL_STATIC"] = "S01_NORMAL_STATIC"
    seed: int = Field(default=0, ge=0, le=2**31 - 1)


@router.post("/observations", response_model=RGBDObservation, status_code=201)
def capture(request: Request, body: CaptureRequest) -> RGBDObservation:
    enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
    try:
        return capture_simulated_observation(backend=body.backend, scenario_id=body.scenario_id, seed=body.seed)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RGBD_CAMERA_UNAVAILABLE: {type(exc).__name__}") from exc
