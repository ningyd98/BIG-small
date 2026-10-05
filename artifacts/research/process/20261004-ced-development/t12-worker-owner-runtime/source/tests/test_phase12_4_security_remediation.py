"""Phase 12.4 安全回归测试，覆盖可信时钟与控制台服务端授权。"""

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
