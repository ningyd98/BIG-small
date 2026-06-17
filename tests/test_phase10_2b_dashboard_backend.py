from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def _dashboard_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    return TestClient(app)


def test_dashboard_summary_never_claims_real_hardware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cloud_edge_robot_arm.dashboard.service import DashboardService

    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    summary = DashboardService.from_environment().summary()

    assert summary.current_project_status == "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
    assert summary.hardware_claim == "PLANNING_ONLY"
    assert summary.real_robot_validation == "NOT_STARTED"
    assert summary.highest_acceptance_level == "NONE"
    assert summary.safety_summary.hardware_motion_authorized is False


def test_evidence_index_rejects_path_traversal_symlink_and_large_files(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.dashboard.evidence_index import EvidenceIndex

    root = tmp_path / "artifacts"
    root.mkdir()
    evidence = root / "phase10_summary.json"
    evidence.write_text(
        json.dumps({"status": "ACCEPTED", "provenance": {"worktree_clean": True}}),
        encoding="utf-8",
    )
    outside = tmp_path / "secret.json"
    outside.write_text('{"token": "raw-secret"}', encoding="utf-8")
    (root / "escape.json").symlink_to(outside)
    (root / "huge.json").write_text("x" * 2048, encoding="utf-8")

    index = EvidenceIndex(root, max_bytes=1024)
    records = index.refresh()

    assert len(records) == 1
    assert records[0].relative_path == "phase10_summary.json"
    with pytest.raises(ValueError, match="path traversal"):
        index.resolve_user_path("../secret.json")
    with pytest.raises(FileNotFoundError):
        index.get_detail("missing")


def test_experiment_job_manager_allowlist_blocks_shell_script_env_and_runs_mock(
    tmp_path: Path,
) -> None:
    from cloud_edge_robot_arm.dashboard.experiment_jobs import ExperimentJobManager
    from cloud_edge_robot_arm.dashboard.models import ExperimentCreateRequest, ExperimentKind

    manager = ExperimentJobManager(artifact_root=tmp_path, writes_enabled=True)
    job = manager.start(
        ExperimentCreateRequest(
            kind=ExperimentKind.MOCK_SOFTWARE,
            scenario_id="S01_NORMAL_STATIC",
            seed=1,
            control_mode="PCSC",
            repetitions=1,
        )
    )

    assert job.status == "SUCCEEDED"
    assert job.hardware_claim == "SIMULATION_ONLY"
    assert job.evidence_id

    for forbidden in ("command", "script", "executable", "shell", "environment", "path"):
        with pytest.raises(ValueError, match="forbidden experiment field"):
            manager.start(
                ExperimentCreateRequest.model_validate(
                    {
                        "kind": "MOCK_SOFTWARE",
                        "scenario_id": "S01_NORMAL_STATIC",
                        "seed": 1,
                        "control_mode": "PCSC",
                        "repetitions": 1,
                        forbidden: "bad",
                    }
                )
            )

    with pytest.raises(ValueError, match="forbidden experiment field"):
        manager.start(
            ExperimentCreateRequest.model_validate(
                {
                    "kind": "MOCK_SOFTWARE",
                    "scenario_id": "S01_NORMAL_STATIC",
                    "seed": 1,
                    "control_mode": "PCSC",
                    "repetitions": 1,
                    "cmd": "bad",
                }
            )
        )


def test_dashboard_api_capabilities_summary_safety_acceptance_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "phase10_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE10_MOVEIT_DRY_RUN_ACCEPTED",
                "hardware_motion_observed": False,
                "provenance": {"generated_from_commit": "abc", "worktree_clean": True},
            }
        ),
        encoding="utf-8",
    )
    client = _dashboard_client(monkeypatch, tmp_path)

    capabilities = client.get("/api/v1/dashboard/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["hardware_write_operations"] == []

    summary = client.get("/api/v1/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["real_robot_validation"] == "NOT_STARTED"
    assert summary.json()["hardware_claim"] == "PLANNING_ONLY"

    safety = client.get("/api/v1/dashboard/safety")
    assert safety.status_code == 200
    assert safety.json()["hardware_motion_authorized"] is False

    acceptance = client.get("/api/v1/dashboard/acceptance")
    assert acceptance.status_code == 200
    assert acceptance.json()["current_level"] == "NONE"
    assert all(level["hardware_motion_allowed"] is False for level in acceptance.json()["levels"])

    evidence = client.get("/api/v1/dashboard/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["records"]
    evidence_id = evidence.json()["records"][0]["evidence_id"]
    detail = client.get(f"/api/v1/dashboard/evidence/{evidence_id}")
    assert detail.status_code == 200
    assert "raw-secret" not in detail.text
    assert client.get("/api/v1/dashboard/evidence/..%2Fsecret").status_code in {400, 404}


def test_dashboard_api_write_default_disabled_and_auth_roles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _dashboard_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/dashboard/experiments",
        json={
            "kind": "MOCK_SOFTWARE",
            "scenario_id": "S01_NORMAL_STATIC",
            "seed": 0,
            "control_mode": "PCSC",
            "repetitions": 1,
        },
    )
    assert response.status_code == 403
    assert "disabled" in response.text


def test_dashboard_dev_app_exposes_dashboard_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cloud_edge_robot_arm.cloud.api.dev_dashboard_app import app

    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    client = TestClient(app)

    response = client.get("/api/v1/dashboard/capabilities")

    assert response.status_code == 200
    assert response.json()["hardware_write_operations"] == []


def test_dashboard_event_stream_sequence_heartbeat_and_replay() -> None:
    from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream

    stream = DashboardEventStream(max_replay=8)
    first = stream.publish("summary_update", "test", {"status": "READY"})
    second = stream.heartbeat()
    replay = stream.replay_after(0)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in replay] == [1, 2]
    assert len({first.event_id, second.event_id}) == 2
