from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return create_app(PlanningPipeline(planner=MockPlannerAdapter()))


def test_dashboard_websocket_requires_auth_and_replays_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _app(tmp_path, monkeypatch)
    from cloud_edge_robot_arm.dashboard.service import DashboardService

    service = DashboardService(artifact_root=tmp_path / "artifacts")
    app.state.dashboard_service = service
    service.events.publish("summary_update", "test", {"status": "READY"})
    client = TestClient(app)

    with client.websocket_connect("/api/v1/dashboard/stream?last_sequence=0") as ws:
        replayed = ws.receive_json()
        assert replayed["event_type"] == "summary_update"
        assert replayed["sequence"] == 1
        heartbeat = ws.receive_json()
        assert heartbeat["event_type"] == "heartbeat"
        assert heartbeat["sequence"] == 2


def test_dashboard_websocket_rejects_missing_token_before_accept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN", "phase10-token")
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)

    with pytest.raises(WebSocketDenialResponse):
        with client.websocket_connect("/api/v1/dashboard/stream?last_sequence=0"):
            pass


def test_dashboard_websocket_token_mode_accepts_cookie_not_query_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN", "phase10-token")
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)

    with pytest.raises(WebSocketDenialResponse):
        with client.websocket_connect(
            "/api/v1/dashboard/stream?last_sequence=0&token=phase10-token"
        ):
            pass

    with client.websocket_connect(
        "/api/v1/dashboard/stream?last_sequence=0",
        headers={"cookie": "dashboard_token=phase10-token"},
    ) as ws:
        heartbeat = ws.receive_json()
        assert heartbeat["event_type"] == "heartbeat"


def test_dashboard_websocket_closes_oversized_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/api/v1/dashboard/stream?last_sequence=0") as ws:
        ws.receive_json()
        ws.send_json({"last_sequence": 0, "padding": "x" * 4096})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
