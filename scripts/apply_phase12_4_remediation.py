#!/usr/bin/env python
"""Apply the audited Phase 12.4 security and CI remediation patch."""

from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_trusted_contract_time() -> None:
    path = "src/cloud_edge_robot_arm/edge/runtime/task_executor.py"
    replace_once(
        path,
        ").accept_payload(payload, now=self._validation_now(payload))",
        ").accept_payload(payload, now=self._clock.now())",
    )
    replace_once(
        path,
        '''    def _validation_now(self, payload: dict[str, Any]) -> datetime:
        raw_timestamp = payload.get("timestamp")
        if isinstance(raw_timestamp, datetime):
            return raw_timestamp
        if isinstance(raw_timestamp, str):
            try:
                parsed = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                return datetime.now(UTC)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return datetime.now(UTC)
''',
        "",
    )


def write_dashboard_security() -> None:
    Path("src/cloud_edge_robot_arm/dashboard/security.py").write_text(
        '''"""Dashboard transport authentication and server-side role authorization."""

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
''',
        encoding="utf-8",
    )


def patch_model_control_auth() -> None:
    path = "src/cloud_edge_robot_arm/cloud/api/model_control.py"
    replace_once(
        path,
        "from fastapi import APIRouter, HTTPException, Request, WebSocket, status",
        "from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status",
    )
    replace_once(
        path,
        "from pydantic import BaseModel, Field\n",
        "from pydantic import BaseModel, Field\nfrom starlette.requests import HTTPConnection\n",
    )
    replace_once(
        path,
        "from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob\n",
        "from cloud_edge_robot_arm.dashboard.models import UserRole\n"
        "from cloud_edge_robot_arm.dashboard.security import (\n"
        "    DashboardAuthMode,\n"
        "    enforce_dashboard_access,\n"
        "    enforce_dashboard_role,\n"
        "    enforce_dashboard_websocket_access,\n"
        ")\n"
        "from cloud_edge_robot_arm.model_control.downloads import ModelDownloadJob\n",
    )
    replace_once(
        path,
        'router = APIRouter(prefix="/api/v1/model-control", tags=["model-control"])',
        '''def enforce_model_control_access(connection: HTTPConnection) -> None:
    """Keep local mode usable and authorize network requests server-side."""

    mode = DashboardAuthMode(os.environ.get("DASHBOARD_AUTH_MODE", "LOCAL_ONLY"))
    if mode == DashboardAuthMode.LOCAL_ONLY:
        enforce_dashboard_access(connection)
        return
    if connection.scope.get("type") == "websocket":
        enforce_dashboard_access(connection)
        return
    method = str(connection.scope.get("method", "GET"))
    if method in {"GET", "HEAD", "OPTIONS"}:
        enforce_dashboard_access(connection)
        return
    enforce_dashboard_role(connection, {UserRole.EXPERIMENT_OPERATOR})


router = APIRouter(
    prefix="/api/v1/model-control",
    tags=["model-control"],
    dependencies=[Depends(enforce_model_control_access)],
)''',
    )
    replace_once(
        path,
        '''async def model_control_stream(websocket: WebSocket, last_sequence: int = 0) -> None:
    await websocket.accept()''',
        '''async def model_control_stream(websocket: WebSocket, last_sequence: int = 0) -> None:
    enforce_dashboard_websocket_access(websocket)
    await websocket.accept()''',
    )


def patch_ci() -> None:
    path = ".github/workflows/ci.yml"
    replace_once(
        path,
        '''      - name: Project CI profile
        run: python scripts/verify_project.py --profile ci

''',
        "",
    )
    replace_once(
        path,
        '''      - name: Phase 12 smoke evaluation
        run: |
          python scripts/run_phase12_experiments.py --profile smoke --output artifacts/phase12
          python scripts/analyze_phase12_results.py --profile smoke --output artifacts/phase12
          python scripts/export_phase12_thesis_assets.py --profile smoke --output artifacts/phase12
          python scripts/verify_phase12.py --smoke --output artifacts/phase12/verification --artifact-root artifacts/phase12

      - name: Upload Phase 12 smoke artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase12-smoke-artifacts
          path: artifacts/phase12
          if-no-files-found: ignore''',
        '''      - name: Phase 12 smoke evaluation
        run: |
          output="artifacts/phase12_ci/${GITHUB_RUN_ID}-${GITHUB_SHA}"
          rm -rf "$output"
          python scripts/run_phase12_experiments.py --profile smoke --output "$output"
          python scripts/analyze_phase12_results.py --profile smoke --output "$output"
          python scripts/export_phase12_thesis_assets.py --profile smoke --output "$output"
          python scripts/verify_phase12.py --smoke --output "$output/verification" --artifact-root "$output"

      - name: Upload Phase 12 smoke artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase12-smoke-artifacts
          path: artifacts/phase12_ci/${{ github.run_id }}-${{ github.sha }}
          if-no-files-found: ignore''',
    )


def write_regression_tests() -> None:
    Path("tests/test_phase12_4_security_remediation.py").write_text(
        '''"""Phase 12.4 regressions for trusted time and console authorization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.supervision.core import FakeClock
from cloud_edge_robot_arm.dashboard.models import UserRole
from cloud_edge_robot_arm.dashboard.security import enforce_dashboard_role
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene
from tests.phase2_helpers import contract


def test_contract_expiry_uses_edge_clock_not_message_timestamp() -> None:
    issued = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    payload = contract(task_id="trusted-clock-expiry").model_dump(mode="json")
    payload["timestamp"] = issued.isoformat()
    payload["issued_at"] = issued.isoformat()
    payload["valid_until"] = (issued + timedelta(seconds=1)).isoformat()
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    executor = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        clock=FakeClock(start=issued + timedelta(minutes=1)),
    )

    result = executor.submit_contract(payload)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "CONTRACT_EXPIRED"
    assert robot.history == []


def test_token_viewer_cannot_self_escalate_with_role_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN", "TEST_VIEWER_TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)
    app = FastAPI()

    @app.post("/operator")
    async def operator(request: Request) -> dict[str, str]:
        role = enforce_dashboard_role(request, {UserRole.EXPERIMENT_OPERATOR})
        return {"role": role.value}

    response = TestClient(app).post(
        "/operator",
        headers={
            "authorization": "Bearer TEST_VIEWER_TOKEN",
            "x-dashboard-role": UserRole.EXPERIMENT_OPERATOR.value,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "dashboard_role_forbidden"


def test_model_control_http_routes_require_server_authorized_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN", "TEST_VIEWER_TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN_ROLE", UserRole.VIEWER.value)
    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control.db"))
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    client = TestClient(app)
    headers = {
        "authorization": "Bearer TEST_VIEWER_TOKEN",
        "x-dashboard-role": UserRole.EXPERIMENT_OPERATOR.value,
    }

    read_response = client.get("/api/v1/model-control/capabilities", headers=headers)
    write_response = client.post(
        "/api/v1/model-control/profiles",
        headers=headers,
        json={
            "display_name": "blocked escalation",
            "provider_kind": "MOCK",
            "model_name": "mock-planner",
        },
    )

    assert read_response.status_code == 200
    assert write_response.status_code == 403


def test_model_control_operator_token_can_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    monkeypatch.setenv("DASHBOARD_OPERATOR_TOKEN", "TEST_OPERATOR_TOKEN")
    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control.db"))
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))

    response = TestClient(app).post(
        "/api/v1/model-control/profiles",
        headers={"authorization": "Bearer TEST_OPERATOR_TOKEN"},
        json={
            "display_name": "authorized operator",
            "provider_kind": "MOCK",
            "model_name": "mock-planner",
        },
    )

    assert response.status_code == 201
    assert response.json()["display_name"] == "authorized operator"
''',
        encoding="utf-8",
    )


def patch_existing_test_type() -> None:
    replace_once(
        "tests/test_phase10_2b_dashboard_backend.py",
        "    observed_statuses = {job.status}\n",
        "    observed_statuses: set[ExperimentJobStatus] = {job.status}\n",
    )


def main() -> None:
    patch_trusted_contract_time()
    write_dashboard_security()
    patch_model_control_auth()
    patch_ci()
    write_regression_tests()
    patch_existing_test_type()


if __name__ == "__main__":
    main()
