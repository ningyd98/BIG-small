from __future__ import annotations

import hashlib
import os
from enum import StrEnum

from fastapi import HTTPException, Request


class DashboardAuthMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    TOKEN = "TOKEN"


def enforce_dashboard_access(request: Request) -> None:
    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))
    if mode == DashboardAuthMode.LOCAL_ONLY:
        host = request.client.host if request.client else ""
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="dashboard_local_only")
        return
    expected = os.environ.get("DASHBOARD_TOKEN", "")
    provided = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not expected or not provided:
        raise HTTPException(status_code=401, detail="dashboard_token_required")
    if _hash(expected) != _hash(provided):
        raise HTTPException(status_code=403, detail="dashboard_token_invalid")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
