from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from enum import StrEnum

from fastapi import HTTPException, Request, WebSocket

from cloud_edge_robot_arm.dashboard.models import UserRole


class DashboardAuthMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    TOKEN = "TOKEN"


def enforce_dashboard_access(request: Request) -> None:
    _enforce_transport_auth(request)


def enforce_dashboard_websocket_access(websocket: WebSocket) -> None:
    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))
    if mode == DashboardAuthMode.LOCAL_ONLY:
        host = websocket.client.host if websocket.client else ""
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="dashboard_local_only")
        return
    expected = os.environ.get("DASHBOARD_TOKEN", "")
    provided = _provided_token(websocket.headers, websocket.cookies)
    if not expected or not provided:
        raise HTTPException(status_code=401, detail="dashboard_token_required")
    if _hash(expected) != _hash(provided):
        raise HTTPException(status_code=403, detail="dashboard_token_invalid")


def enforce_dashboard_role(request: Request, allowed: set[UserRole]) -> UserRole:
    _enforce_transport_auth(request)
    role = _request_role(request)
    if role not in allowed:
        raise HTTPException(status_code=403, detail="dashboard_role_forbidden")
    return role


def _enforce_transport_auth(request: Request) -> None:
    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))
    if mode == DashboardAuthMode.LOCAL_ONLY:
        host = request.client.host if request.client else ""
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="dashboard_local_only")
        return
    expected = os.environ.get("DASHBOARD_TOKEN", "")
    provided = _provided_token(request.headers, request.cookies)
    if not expected or not provided:
        raise HTTPException(status_code=401, detail="dashboard_token_required")
    if _hash(expected) != _hash(provided):
        raise HTTPException(status_code=403, detail="dashboard_token_invalid")


def _request_role(request: Request) -> UserRole:
    raw = request.headers.get("x-dashboard-role", UserRole.VIEWER.value)
    try:
        return UserRole(raw)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="dashboard_role_invalid") from exc


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provided_token(headers: Mapping[str, str], cookies: Mapping[str, str]) -> str:
    authorization = headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return cookies.get("dashboard_token", "").strip()
