"""Phase 11.2 模型控制中心后端安全回归测试。

这些测试只使用临时 SQLite、内存 secret store 和本地 fake endpoint，不访问真实
收费 API、不下载模型、不连接真实硬件。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.model_control.endpoint_security import EndpointSecurityError
from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository


def _service(tmp_path: Path) -> ModelControlService:
    return ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "model_control.db"),
        secret_store=InMemorySecretStore(),
    )


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control_api.db"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    return TestClient(app)


def test_profile_crud_keeps_api_key_write_only_and_out_of_sqlite(tmp_path: Path) -> None:
    service = _service(tmp_path)

    created = service.create_profile(
        display_name="Cloud compatible",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.test/v1",
        chat_completions_path="/chat/completions",
        model_name="safe-model",
        api_key="TEST_SECRET_VALUE_CREATE",
    )
    profiles = service.list_profiles()
    stored = service.get_profile(created.profile_id)

    assert created.secret_present is True
    assert created.api_key is None
    assert stored.secret_present is True
    assert stored.api_key is None
    assert profiles[0].api_key is None
    assert b"TEST_SECRET_VALUE_CREATE" not in (tmp_path / "model_control.db").read_bytes()

    updated = service.update_profile(
        created.profile_id,
        display_name="Cloud compatible renamed",
        api_key="TEST_SECRET_VALUE_ROTATED",
    )
    assert updated.display_name == "Cloud compatible renamed"
    assert updated.secret_present is True
    assert b"TEST_SECRET_VALUE_ROTATED" not in (tmp_path / "model_control.db").read_bytes()


def test_endpoint_security_rejects_unsafe_remote_targets(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(EndpointSecurityError, match="unsupported_endpoint_scheme"):
        service.create_profile(
            display_name="file",
            provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
            base_url="file:///etc/passwd",
            model_name="bad",
        )

    with pytest.raises(EndpointSecurityError, match="metadata_address_blocked"):
        service.create_profile(
            display_name="metadata",
            provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
            base_url="http://169.254.169.254/latest",
            model_name="bad",
        )

    with pytest.raises(EndpointSecurityError, match="remote_ollama_blocked"):
        service.create_profile(
            display_name="remote ollama",
            provider_kind=PlannerProviderKind.OLLAMA,
            base_url="http://192.0.2.10:11434",
            model_name="llama3.2:3b",
        )

    ollama = service.create_profile(
        display_name="local ollama",
        provider_kind=PlannerProviderKind.OLLAMA,
        base_url="http://127.0.0.1:11434",
        model_name="llama3.2:3b",
    )
    assert ollama.endpoint_hash
    assert ollama.base_url == "http://127.0.0.1:11434"


def test_active_profile_switch_uses_version_cas(tmp_path: Path) -> None:
    service = _service(tmp_path)
    rule_based = service.create_profile(
        display_name="Rule based",
        provider_kind=PlannerProviderKind.RULE_BASED,
        model_name="rule-based",
    )
    mock = service.create_profile(
        display_name="Mock",
        provider_kind=PlannerProviderKind.MOCK,
        model_name="mock",
    )

    activated = service.activate_profile(rule_based.profile_id)
    assert activated.active_profile_id == rule_based.profile_id
    assert activated.active_provider == PlannerProviderKind.RULE_BASED

    stale_version = service.get_profile(mock.profile_id).config_version - 1
    with pytest.raises(ValueError, match="profile_version_conflict"):
        service.activate_profile(mock.profile_id, expected_config_version=stale_version)

    switched = service.activate_profile(mock.profile_id)
    assert switched.active_profile_id == mock.profile_id
    assert switched.active_provider == PlannerProviderKind.MOCK


def test_model_control_api_profiles_runtime_and_write_only_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    capabilities = client.get("/api/v1/model-control/capabilities")
    assert capabilities.status_code == 200
    assert "OPENAI_COMPATIBLE" in capabilities.json()["supported_provider_kinds"]

    created = client.post(
        "/api/v1/model-control/profiles",
        json={
            "display_name": "Cloud profile",
            "provider_kind": "OPENAI_COMPATIBLE",
            "base_url": "https://api.example.test/v1",
            "chat_completions_path": "/chat/completions",
            "model_name": "safe-model",
            "api_key": "TEST_SECRET_VALUE_API_ROUTE",
        },
    )
    assert created.status_code == 201
    profile = created.json()
    assert profile["secret_present"] is True
    assert "api_key" not in profile or profile["api_key"] is None
    assert b"TEST_SECRET_VALUE_API_ROUTE" not in (tmp_path / "model_control_api.db").read_bytes()

    listed = client.get("/api/v1/model-control/profiles")
    assert listed.status_code == 200
    assert listed.json()[0]["secret_present"] is True
    assert "api_key" not in listed.json()[0] or listed.json()[0]["api_key"] is None

    activated = client.post(f"/api/v1/model-control/profiles/{profile['profile_id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["active_profile_id"] == profile["profile_id"]

    runtime = client.get("/api/v1/model-control/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["active_provider"] == "OPENAI_COMPATIBLE"


def test_model_catalog_is_loaded_from_backend_and_marks_installed_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeCatalogOllamaTransport:
        def get_version(self) -> dict[str, str]:
            return {"version": "0.9.0"}

        def list_models(self) -> list[dict[str, Any]]:
            return [{"name": "llama3.2:1b", "size": 1, "modified_at": "2026-01-01T00:00:00Z"}]

        def show_model(self, model_name: str) -> dict[str, Any]:
            return {"model": model_name}

        def pull_model(self, model_name: str) -> list[dict[str, Any]]:
            return []

        def chat(self, model_name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control_api.db"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    app.state.ollama_transport = FakeCatalogOllamaTransport()
    client = TestClient(app)

    response = client.get("/api/v1/model-control/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 5
    models = {item["ollama_model"]: item for item in payload}
    assert models["llama3.2:1b"]["installed"] is True
    assert models["gemma3:4b"]["installed"] is False
    assert models["llama3.2:1b"]["estimated_download_bytes"] is None


def test_model_catalog_still_loads_when_ollama_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingOllamaTransport:
        def get_version(self) -> dict[str, str]:
            raise ConnectionError("offline")

        def list_models(self) -> list[dict[str, Any]]:
            raise ConnectionError("offline")

        def show_model(self, model_name: str) -> dict[str, Any]:
            raise ConnectionError("offline")

        def pull_model(self, model_name: str) -> list[dict[str, Any]]:
            raise ConnectionError("offline")

        def chat(self, model_name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            raise ConnectionError("offline")

    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control_api.db"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    app.state.ollama_transport = FailingOllamaTransport()
    client = TestClient(app)

    catalog = client.get("/api/v1/model-control/catalog")
    models = client.get("/api/v1/model-control/ollama/models")

    assert catalog.status_code == 200
    assert len(catalog.json()) >= 5
    assert all(item["installed"] is False for item in catalog.json())
    assert models.status_code == 200
    assert models.json() == []


def test_fake_ollama_models_download_activate_and_planner_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeOllamaTransport:
        def __init__(self) -> None:
            self.installed = {
                "llama3.2:3b": {
                    "name": "llama3.2:3b",
                    "size": 2_000_000_000,
                    "modified_at": "2026-01-01T00:00:00Z",
                }
            }

        def get_version(self) -> dict[str, str]:
            return {"version": "0.9.0"}

        def list_models(self) -> list[dict[str, Any]]:
            return list(self.installed.values())

        def show_model(self, model_name: str) -> dict[str, Any]:
            if model_name not in self.installed:
                raise KeyError(model_name)
            return {"model": model_name, "details": {"family": "llama"}}

        def pull_model(self, model_name: str) -> list[dict[str, Any]]:
            self.installed[model_name] = {
                "name": model_name,
                "size": 123,
                "modified_at": "2026-01-01T00:00:00Z",
            }
            return [
                {"status": "pulling manifest", "completed": 0, "total": 100},
                {"status": "success", "completed": 100, "total": 100},
            ]

        def chat(self, model_name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            assert model_name in self.installed
            assert messages
            return {"choices": [{"message": {"content": '{"steps": []}'}}]}

    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "model_control_api.db"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    app.state.ollama_transport = FakeOllamaTransport()
    client = TestClient(app)

    status = client.get("/api/v1/model-control/ollama/status")
    assert status.status_code == 200
    assert status.json()["reachable"] is True

    models = client.get("/api/v1/model-control/ollama/models")
    assert models.status_code == 200
    assert models.json()[0]["name"] == "llama3.2:3b"

    download = client.post(
        "/api/v1/model-control/ollama/downloads",
        json={"model_name": "qwen2.5:3b"},
    )
    assert download.status_code == 202
    assert download.json()["status"] == "SUCCEEDED"
    assert download.json()["progress_ratio"] == 1.0

    activated = client.post("/api/v1/model-control/ollama/models/qwen2.5:3b/activate")
    assert activated.status_code == 200
    assert activated.json()["active_provider"] == "OLLAMA"

    dry_run = client.post(
        "/api/v1/model-control/planner/dry-run",
        json={
            "user_instruction": "pick red cube",
            "sample_scene": "S01_NORMAL_STATIC",
            "control_mode": "PCSC",
        },
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["dispatch"] is False
    assert dry_run.json()["hardware_execution"] is False
    assert dry_run.json()["provider_kind"] == "OLLAMA"


def test_phase11_2_command_artifacts_redact_local_python_path() -> None:
    # verifier artifact 只需要可复现命令语义，不应泄露本机 Python 解释器绝对路径。
    from scripts.verify_phase11_2_model_control import run_command

    result = run_command(
        [sys.executable, "-c", "print('ok')"],
        Path.cwd(),
        timeout=30,
    )

    assert result["returncode"] == 0
    assert str(Path(sys.executable).parent) not in str(result["argv"])
    assert result["argv"][0] == "python"
