"""Default runs capture real images; absent services never produce fake success."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from tests.test_phase11_1_simulation_runtime import _draft, _wait_for_artifact_paths, _wait_for_status


def test_capture_api_returns_actual_pair(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SIMULATION_RUNTIME_DB", str(tmp_path / "runtime.db"))
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/vision/observations", json={"backend": "MUJOCO", "seed": 0}, headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["source"] == "mujoco_camera"
    assert payload["width"] * payload["height"] == 76800
    assert payload["rgb_png_base64"] and payload["depth_float32_base64"]
    assert "objects" not in payload


def test_default_worker_missing_model_blocks_with_camera_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SIMULATION_RUNTIME_DB", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("BIGSMALL_VLM_BASE_URL", "http://127.0.0.1:1")
    payload = _draft(backend="MUJOCO", input_mode="RGBD")
    with TestClient(create_app()) as client:
        submitted = client.post("/api/v1/simulation/runs", json=payload, headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"})
        assert submitted.status_code == 202
        run_id = submitted.json()["run_id"]
        run = _wait_for_status(client, run_id, {"BLOCKED_BY_ENV", "FAILED", "SUCCEEDED"})
        assert run["status"] == "BLOCKED_BY_ENV"
        paths = _wait_for_artifact_paths(client, run_id, artifact_root=tmp_path / "artifacts")
    result = json.loads((tmp_path / "artifacts" / paths["result"]).read_text())
    assert result["status"] == "BLOCKED_BY_ENV"
    assert result["task_success"] is False
    assert result["mock_fallback_used"] is False
    observation = json.loads((tmp_path / "artifacts" / paths["observation"]).read_text())
    assert observation["input_mode"] == "RGBD"
    assert (tmp_path / "artifacts" / paths["rgb"]).exists()
    assert (tmp_path / "artifacts" / paths["depth"]).stat().st_size == 76800 * 4
