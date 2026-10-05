"""Dashboard 传输鉴权与服务端角色授权，禁止客户端自行声明网络权限。"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from enum import StrEnum

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from cloud_edge_robot_arm.dashboard.models import UserRole


class DashboardAuthMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    TOKEN = "TOKEN"


def enforce_dashboard_access(connection: HTTPConnection) -> None:
    _authenticated_role(connection)


def enforce_dashboard_websocket_access(connection: HTTPConnection) -> None:
    _authenticated_role(connection)


def enforce_dashboard_role(
    connection: HTTPConnection,
    allowed: set[UserRole],
) -> UserRole:
    role = _authenticated_role(connection)
    if role not in allowed:
        raise HTTPException(status_code=403, detail="dashboard_role_forbidden")
    return role


def _authenticated_role(connection: HTTPConnection) -> UserRole:
    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))
    if mode == DashboardAuthMode.LOCAL_ONLY:
        _enforce_loopback(connection.client.host if connection.client else "")
        # Role headers remain available only in explicitly trusted loopback mode.
        return _local_role(connection)
    return _token_role(connection.headers, connection.cookies)


def _enforce_loopback(host: str) -> None:
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="dashboard_local_only")


def _token_role(headers: Mapping[str, str], cookies: Mapping[str, str]) -> UserRole:
    provided = _provided_token(headers, cookies)
    configured = _configured_tokens()
    if not configured or not provided:
        raise HTTPException(status_code=401, detail="dashboard_token_required")
    matches = {role for token, role in configured if _token_matches(token, provided)}
    if not matches:
        raise HTTPException(status_code=403, detail="dashboard_token_invalid")
    if len(matches) != 1:
        raise HTTPException(status_code=403, detail="dashboard_token_role_ambiguous")
    return next(iter(matches))


def _configured_tokens() -> list[tuple[str, UserRole]]:
    configured: list[tuple[str, UserRole]] = []
    dedicated = (
        ("DASHBOARD_VIEWER_TOKEN", UserRole.VIEWER),
        ("DASHBOARD_OPERATOR_TOKEN", UserRole.EXPERIMENT_OPERATOR),
        ("DASHBOARD_REVIEWER_TOKEN", UserRole.SAFETY_REVIEWER),
    )
    for env_name, role in dedicated:
        value = os.environ.get(env_name, "").strip()
        if value:
            configured.append((value, role))

    legacy = os.environ.get("DASHBOARD_TOKEN", "").strip()
    if legacy:
        raw_role = os.environ.get("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)
        try:
            role = UserRole(raw_role)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="dashboard_token_role_invalid") from exc
        configured.append((legacy, role))
    return configured


def _local_role(connection: HTTPConnection) -> UserRole:
    raw = connection.headers.get("x-dashboard-role", UserRole.VIEWER.value)
    try:
        return UserRole(raw)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="dashboard_role_invalid") from exc


def _token_matches(expected: str, provided: str) -> bool:
    return hmac.compare_digest(_hash(expected), _hash(provided))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provided_token(headers: Mapping[str, str], cookies: Mapping[str, str]) -> str:
    authorization = headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return cookies.get("dashboard_token", "").strip()
