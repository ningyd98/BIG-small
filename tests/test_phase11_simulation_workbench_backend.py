from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    return TestClient(app)


def _app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    return create_app(PlanningPipeline(planner=MockPlannerAdapter()))


def _draft(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "backend": "MOCK",
        "run_type": "SINGLE",
        "scenarios": ["S01_NORMAL_STATIC"],
        "control_modes": ["PCSC"],
        "seeds": [0],
        "repetitions": 1,
        "network_profiles": [
            {
                "name": "NORMAL",
                "base_latency_ms": 40,
                "jitter_ms": 5,
                "packet_loss": 0.0,
                "bandwidth_kbps": 10000,
            }
        ],
        "fault_profiles": [{"name": "none", "parameters": {}}],
        "parameter_overrides": {
            "cache_policy": "CACHE_ENABLED",
            "retry_budget": 2,
            "supervision_period_ms": 300,
            "timeout_ms": 30000,
        },
        "domain_randomization": {"enabled": False, "level": "NONE"},
        "tags": ["phase11-test"],
        "description": "backend contract test",
    }
    payload.update(overrides)
    return payload


def _wait_for_terminal(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10.0
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/simulation/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED_BY_ENV"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run did not finish: {last}")


def test_simulation_capabilities_and_scenarios_are_dynamic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    capabilities = client.get("/api/v1/simulation/capabilities")
    scenarios = client.get("/api/v1/simulation/scenarios")
    scenario = client.get("/api/v1/simulation/scenarios/S14_EMERGENCY_STOP")
    parameter_schema = client.get("/api/v1/simulation/parameter-schema")

    assert capabilities.status_code == 200
    payload = capabilities.json()
    assert {item["backend"] for item in payload["backends"]} == {
        "MOCK",
        "MUJOCO",
        "ISAAC_SIM",
        "MOVEIT_DRY_RUN",
    }
    assert payload["hardware_write_operations"] == []
    assert payload["real_controller_contacted"] is False
    assert payload["hardware_motion_observed"] is False
    assert set(payload["runner_allowlist"]) == {
        "MOCK_SCENARIO",
        "MUJOCO_SCENARIO",
        "PHASE8_BATCH",
        "PHASE8_SWEEP",
        "PHASE9_MUJOCO_BENCHMARK",
        "ISAAC_BENCHMARK",
        "CROSS_BACKEND_PAIRED",
    }
    assert any(
        item["backend"] == "MOCK" and item["readiness"] == "READY" for item in payload["backends"]
    )
    assert all("runner_allowlist" in item for item in payload["backends"])
    assert not any(
        item["backend"] == "ISAAC_SIM" and item["readiness"] == "READY" and item["blockers"]
        for item in payload["backends"]
    )

    assert scenarios.status_code == 200
    scenario_items = scenarios.json()["scenarios"]
    assert len(scenario_items) == 15
    assert scenario_items[0]["scenario_id"] == "S01_NORMAL_STATIC"
    assert {item["scenario_id"] for item in scenario_items} >= {
        "S01_NORMAL_STATIC",
        "S07_NETWORK_DEGRADED",
        "S14_EMERGENCY_STOP",
        "S15_SQLITE_RESTART_DURING_RUN",
    }
    assert all("category" in item for item in scenario_items)
    assert all("backend_support" in item for item in scenario_items)

    assert scenario.status_code == 200
    detail = scenario.json()
    assert detail["scenario_id"] == "S14_EMERGENCY_STOP"
    assert detail["category"] == "SAFETY"
    assert detail["fault_types"] == ["EMERGENCY_STOP"]
    assert detail["scheduled_faults"][0]["trigger_time_ms"] == 600
    assert detail["allowed_result_statuses"] == ["SAFETY_STOPPED"]

    assert parameter_schema.status_code == 200
    schema = parameter_schema.json()
    assert schema["schema_version"] == "phase11.simulation.v1"
    assert "ExperimentConfig" in schema["authoritative_models"]
    assert set(schema["enums"]["control_modes"]) == {"PCSC", "ETEAC", "AUTO"}
    assert set(schema["enums"]["backends"]) == {
        "MOCK",
        "MUJOCO",
        "ISAAC_SIM",
        "MOVEIT_DRY_RUN",
    }
    assert "CROSS_BACKEND_PAIRED" in schema["enums"]["runner_allowlist"]


def test_simulation_validate_rejects_arbitrary_shell_path_env_and_extra_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    valid = client.post("/api/v1/simulation/validate", json=_draft())
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    assert valid.json()["manifest"]["run_count"] == 1
    assert valid.json()["manifest"]["reproducibility_hash"]

    for forbidden in (
        "shell",
        "command",
        "script",
        "path",
        "module",
        "environment",
        "executable",
    ):
        invalid_payload = _draft()
        invalid_payload["parameter_overrides"][forbidden] = "/tmp/not-allowed"
        rejected = client.post("/api/v1/simulation/validate", json=invalid_payload)
        assert rejected.status_code == 422, forbidden

    rejected_extra = client.post(
        "/api/v1/simulation/validate",
        json=_draft(runner_name="arbitrary-runner"),
    )
    assert rejected_extra.status_code == 422


def test_single_mock_run_writes_phase11_artifacts_events_metrics_and_reproduction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(),
    )
    assert created.status_code == 202
    run = created.json()
    assert run["backend"] == "MOCK"
    assert run["scenario_id"] == "S01_NORMAL_STATIC"
    assert run["hardware_claim"] == "SIMULATION_ONLY"
    assert run["real_controller_contacted"] is False
    assert run["hardware_motion_observed"] is False
    assert run["hardware_write_operations"] == []

    terminal = _wait_for_terminal(client, run["run_id"])
    assert terminal["status"] == "SUCCEEDED"
    assert terminal["manifest"]["reproducibility_hash"]
    assert terminal["provenance"]["source_commit"]
    assert terminal["artifact_paths"]["run_manifest"].endswith("run_manifest.json")

    events = client.get(f"/api/v1/simulation/runs/{run['run_id']}/events")
    metrics = client.get(f"/api/v1/simulation/runs/{run['run_id']}/metrics")
    artifacts = client.get(f"/api/v1/simulation/runs/{run['run_id']}/artifacts")
    clone = client.post(f"/api/v1/simulation/runs/{run['run_id']}/clone")
    reproduce = client.post(f"/api/v1/simulation/runs/{run['run_id']}/reproduce")

    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()["events"]]
    assert "experiment_started" in event_types
    assert "task_completed" in event_types
    assert all("sequence" in item for item in events.json()["events"])

    assert metrics.status_code == 200
    metric_names = {item["name"] for item in metrics.json()["metrics"]}
    assert {
        "task_success",
        "completion_time",
        "cloud_calls",
        "communication_count",
        "safety_interventions",
        "reproducibility_hash",
    }.issubset(metric_names)
    assert all(item["backend"] == "MOCK" for item in metrics.json()["metrics"])
    assert all(item["sample_count"] >= 1 for item in metrics.json()["metrics"])

    assert artifacts.status_code == 200
    assert set(artifacts.json()["artifacts"]) >= {
        "run_manifest",
        "events",
        "metrics",
        "logs",
        "result",
        "provenance",
    }
    assert str(tmp_path) not in json.dumps(artifacts.json())

    assert clone.status_code == 200
    assert clone.json()["draft"]["scenarios"] == ["S01_NORMAL_STATIC"]
    assert reproduce.status_code == 200
    assert reproduce.json()["draft"]["seeds"] == [0]
    assert reproduce.json()["environment_match"] in {True, False}
    assert "warnings" in reproduce.json()


def test_batch_sweep_cancel_comparison_export_and_blocked_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    batch = client.post(
        "/api/v1/simulation/batches",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(
            run_type="BATCH",
            scenarios=["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED"],
            control_modes=["PCSC", "ETEAC"],
            seeds=[0, 1],
        ),
    )
    assert batch.status_code == 202
    batch_payload = batch.json()
    assert batch_payload["progress"]["total"] == 8
    assert batch_payload["hardware_write_operations"] == []

    detail = client.get(f"/api/v1/simulation/batches/{batch_payload['batch_id']}")
    runs = client.get(f"/api/v1/simulation/batches/{batch_payload['batch_id']}/runs")
    assert detail.status_code == 200
    assert runs.status_code == 200
    assert len(runs.json()["runs"]) == 8

    too_large = client.post(
        "/api/v1/simulation/batches",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(run_type="SWEEP", scenarios=["S01_NORMAL_STATIC"], seeds=list(range(1000))),
    )
    assert too_large.status_code == 422

    blocked = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(backend="ISAAC_SIM"),
    )
    assert blocked.status_code in {202, 409}
    if blocked.status_code == 202:
        blocked_run = _wait_for_terminal(client, blocked.json()["run_id"])
        assert blocked_run["status"] == "BLOCKED_BY_ENV"
        assert blocked_run["backend"] == "ISAAC_SIM"
        assert blocked_run["hardware_motion_observed"] is False

    comparison = client.post(
        "/api/v1/simulation/comparisons",
        json={
            "comparison_type": "PCSC_VS_ETEAC",
            "run_ids": [item["run_id"] for item in runs.json()["runs"][:2]],
            "paired_key": {
                "scenario_id": "S01_NORMAL_STATIC",
                "seed": 0,
                "network_profile": "NORMAL",
            },
        },
    )
    export = client.post(
        "/api/v1/simulation/exports",
        json={"export_type": "Metrics CSV", "run_ids": [runs.json()["runs"][0]["run_id"]]},
    )

    assert comparison.status_code == 200
    assert comparison.json()["comparison_type"] == "PCSC_VS_ETEAC"
    assert "paired_delta" in comparison.json()["statistics"]

    assert export.status_code == 200
    assert export.json()["format"] == "Metrics CSV"
    assert str(tmp_path) not in json.dumps(export.json())
    assert "token" not in json.dumps(export.json()).lower()


def test_simulation_api_has_no_hardware_or_level1_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    capabilities = client.get("/api/v1/simulation/capabilities").json()
    paths = create_app(PlanningPipeline(planner=MockPlannerAdapter())).openapi()["paths"]

    assert capabilities["real_controller_contacted"] is False
    assert capabilities["hardware_motion_observed"] is False
    assert capabilities["hardware_write_operations"] == []
    assert not any(
        "real-robot" in path or "controller" in path or "level1" in path for path in paths
    )
    assert client.post("/api/v1/simulation/hardware/enable").status_code == 404
    assert client.post("/api/v1/simulation/level1").status_code == 404


def test_simulation_websocket_uses_dashboard_auth_replay_and_size_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cloud_edge_robot_arm.simulation_workbench.service import SimulationWorkbenchService

    app = _app(monkeypatch, tmp_path)
    service = SimulationWorkbenchService(artifact_root=tmp_path / "artifacts")
    app.state.simulation_workbench_service = service
    service.events.publish("run_state", "test", {"status": "RUNNING"}, experiment_id="sim-test")
    client = TestClient(app)

    with client.websocket_connect("/api/v1/simulation/stream?last_sequence=0") as ws:
        replayed = ws.receive_json()
        assert replayed["event_type"] == "run_state"
        assert replayed["sequence"] == 1
        heartbeat = ws.receive_json()
        assert heartbeat["event_type"] == "heartbeat"
        ws.send_json({"last_sequence": 1, "padding": "x" * 4096})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "TOKEN")
    monkeypatch.setenv("DASHBOARD_TOKEN", "phase11-token")
    token_app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    token_client = TestClient(token_app)

    with pytest.raises(WebSocketDenialResponse):
        with token_client.websocket_connect("/api/v1/simulation/stream?token=phase11-token"):
            pass

    with token_client.websocket_connect(
        "/api/v1/simulation/stream",
        headers={"cookie": "dashboard_token=phase11-token"},
    ) as ws:
        assert ws.receive_json()["event_type"] == "heartbeat"
