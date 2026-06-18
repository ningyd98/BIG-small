"""Phase 11.1 运行时回归测试。

这些测试使用真实 FastAPI app、临时 SQLite 和 Mock 仿真任务，覆盖状态机、CAS、
租约、取消、超时、重试、恢复和 WebSocket replay；普通 CI 不运行 MuJoCo 或真实硬件。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    # 每个测试使用独立 artifact root 和 runtime DB，避免共享状态影响 CAS/lease 判断。
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SIMULATION_RUNTIME_DB", str(tmp_path / "runtime.db"))
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    return TestClient(app)


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
        "tags": ["phase11-1-test"],
        "description": "runtime test",
    }
    payload.update(overrides)
    return payload


def _wait_for_status(client: TestClient, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 10.0
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/simulation/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run did not reach {statuses}: {last}")


def _wait_for_artifact_paths(client: TestClient, run_id: str) -> dict[str, str]:
    deadline = time.monotonic() + 10.0
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/simulation/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        artifact_paths = last.get("artifact_paths", {})
        if artifact_paths.get("evidence_consistency"):
            return artifact_paths
        time.sleep(0.05)
    raise AssertionError(f"run did not expose final artifact paths: {last}")


def _artifact_json(tmp_path: Path, artifact_paths: dict[str, str], key: str) -> Any:
    path = tmp_path / "artifacts" / artifact_paths[key]
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_jsonl(
    tmp_path: Path, artifact_paths: dict[str, str], key: str
) -> list[dict[str, Any]]:
    path = tmp_path / "artifacts" / artifact_paths[key]
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_runtime_state_machine_rejects_illegal_transition() -> None:
    # 状态机必须拒绝跳过队列/运行阶段的非法终态，防止 API 或 worker 覆盖真实状态。
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.state_machine import validate_transition

    assert validate_transition(RuntimeJobStatus.CREATED, RuntimeJobStatus.QUEUED)
    with pytest.raises(ValueError, match="illegal simulation job transition"):
        validate_transition(RuntimeJobStatus.CREATED, RuntimeJobStatus.SUCCEEDED)


def test_sqlite_repository_uses_cas_sequences_and_unique_leases(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="sim-runtime-repo",
        batch_id="",
        backend="MOCK",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest-runtime",
        reproducibility_hash="hash-runtime",
        draft={"backend": "MOCK"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root="artifacts/phase11_1/runtime/sim-runtime-repo",
        source_commit="commit",
        source_tree_hash="tree",
    )

    updated = repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="queued_by_test",
        worker_id="",
        lease_id="",
    )
    assert updated is not None
    stale = repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="stale_cas",
        worker_id="",
        lease_id="",
    )
    assert stale is None

    first_event = repo.append_event(
        job.job_id,
        event_type="job_queued",
        source="test",
        payload={"status": "QUEUED"},
    )
    second_event = repo.append_event(
        job.job_id,
        event_type="job_started",
        source="test",
        payload={"status": "RUNNING"},
    )
    assert second_event.sequence == first_event.sequence + 1

    lease = repo.acquire_lease(worker_id="worker-a", backend="MOCK", lease_ttl_seconds=30)
    assert lease is not None
    duplicate = repo.acquire_lease(worker_id="worker-b", backend="MOCK", lease_ttl_seconds=30)
    assert duplicate is None


def test_post_run_returns_queued_immediately_then_worker_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(
            parameter_overrides={
                "cache_policy": "CACHE_ENABLED",
                "retry_budget": 2,
                "supervision_period_ms": 300,
                "timeout_ms": 30000,
                "runtime_delay_ms": 250,
            }
        ),
    )

    assert created.status_code == 202
    run = created.json()
    assert run["status"] == "QUEUED"
    assert run["job_id"]
    assert run["queue_position"] >= 1
    assert run["real_controller_contacted"] is False
    assert run["hardware_motion_observed"] is False
    assert run["hardware_write_operations"] == []

    running = _wait_for_status(
        client,
        run["run_id"],
        {"VALIDATING", "LEASED", "STARTING", "RUNNING", "SUCCEEDED"},
    )
    assert running["status"] in {"VALIDATING", "LEASED", "STARTING", "RUNNING", "SUCCEEDED"}
    _wait_for_status(client, run["run_id"], {"SUCCEEDED"})
    artifact_paths = _wait_for_artifact_paths(client, run["run_id"])
    assert artifact_paths["runtime_job"].endswith("runtime_job.json")
    assert artifact_paths["attempts"].endswith("attempts.jsonl")
    assert artifact_paths["lease_history"].endswith("lease_history.jsonl")

    events = client.get(f"/api/v1/simulation/runs/{run['run_id']}/events").json()["events"]
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert {"job_created", "job_queued", "job_leased", "job_completed"}.issubset(
        {event["event_type"] for event in events}
    )

    metrics = client.get(f"/api/v1/simulation/runs/{run['run_id']}/metrics").json()["metrics"]
    assert any(metric["name"] == "task_success" for metric in metrics)


def test_success_terminal_evidence_is_consistent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 终态 evidence 必须从 repository 终态重读生成，不能出现 result 成功但 job/attempt
    # 仍停留在 LEASED/RUNNING 的自相矛盾快照。
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(),
    ).json()
    terminal = _wait_for_status(client, created["run_id"], {"SUCCEEDED"})
    artifact_paths = _wait_for_artifact_paths(client, created["run_id"])

    job = _artifact_json(tmp_path, artifact_paths, "job")
    runtime_job = _artifact_json(tmp_path, artifact_paths, "runtime_job")
    result = _artifact_json(tmp_path, artifact_paths, "result")
    consistency = _artifact_json(tmp_path, artifact_paths, "evidence_consistency")
    attempts = _artifact_jsonl(tmp_path, artifact_paths, "attempts")
    leases = _artifact_jsonl(tmp_path, artifact_paths, "leases")
    transitions = _artifact_jsonl(tmp_path, artifact_paths, "state_transitions")
    events = _artifact_jsonl(tmp_path, artifact_paths, "events")

    assert terminal["status"] == "SUCCEEDED"
    assert consistency["consistent"] is True
    assert job["status"] == "SUCCEEDED"
    assert runtime_job["status"] == "SUCCEEDED"
    assert result["status"] == "SUCCEEDED"
    assert attempts[-1]["result"] == "SUCCEEDED"
    assert attempts[-1]["ended_at"]
    assert leases[-1]["released_at"]
    assert transitions[-1]["next_status"] == "SUCCEEDED"
    assert "artifact_created" in {event["event_type"] for event in events}
    assert "job_completed" in {event["event_type"] for event in events}


def test_cancelled_and_timed_out_terminal_evidence_are_consistent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    cancellable = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 2500}),
    ).json()
    _wait_for_status(
        client,
        cancellable["run_id"],
        {"LEASED", "STARTING", "RUNNING", "CANCELLED", "SUCCEEDED"},
    )
    client.post(
        f"/api/v1/simulation/runs/{cancellable['run_id']}/cancel",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
    )
    cancelled = _wait_for_status(client, cancellable["run_id"], {"CANCELLED"})
    cancelled_paths = _wait_for_artifact_paths(client, cancellable["run_id"])

    timed = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 1500, "timeout_seconds": 1}),
    ).json()
    timed_out = _wait_for_status(client, timed["run_id"], {"TIMED_OUT"})
    timed_out_paths = _wait_for_artifact_paths(client, timed["run_id"])

    for terminal, artifact_paths, expected in [
        (cancelled, cancelled_paths, "CANCELLED"),
        (timed_out, timed_out_paths, "TIMED_OUT"),
    ]:
        consistency = _artifact_json(tmp_path, artifact_paths, "evidence_consistency")
        job = _artifact_json(tmp_path, artifact_paths, "job")
        result = _artifact_json(tmp_path, artifact_paths, "result")
        attempts = _artifact_jsonl(tmp_path, artifact_paths, "attempts")
        transitions = _artifact_jsonl(tmp_path, artifact_paths, "state_transitions")
        events = _artifact_jsonl(tmp_path, artifact_paths, "events")
        assert terminal["status"] == expected
        assert consistency["consistent"] is True
        assert job["status"] == expected
        assert result["status"] == expected
        assert attempts[-1]["result"] == expected
        assert attempts[-1]["ended_at"]
        assert transitions[-1]["next_status"] == expected
        assert consistency["terminal_event_present"] is True
        assert "artifact_created" in {event["event_type"] for event in events}


def test_runtime_cancel_timeout_retry_and_recovery_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    cancellable = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 2500}),
    ).json()
    cancel_response = client.post(
        f"/api/v1/simulation/runs/{cancellable['run_id']}/cancel",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] in {"CANCEL_REQUESTED", "CANCELLING", "CANCELLED"}
    cancelled = _wait_for_status(client, cancellable["run_id"], {"CANCELLED"})
    assert cancelled["status"] == "CANCELLED"

    timed = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 1500, "timeout_seconds": 1}),
    ).json()
    timed_out = _wait_for_status(client, timed["run_id"], {"TIMED_OUT"})
    assert timed_out["status"] == "TIMED_OUT"

    retry = client.post(
        f"/api/v1/simulation/runs/{timed['run_id']}/retry",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
    )
    assert retry.status_code == 202
    assert retry.json()["status"] == "QUEUED"

    attempts = client.get(f"/api/v1/simulation/runs/{timed['run_id']}/attempts")
    assert attempts.status_code == 200
    assert len(attempts.json()["attempts"]) >= 1

    recovery = client.post(
        "/api/v1/simulation/runtime/recover",
        headers={"x-dashboard-role": "SAFETY_REVIEWER"},
    )
    assert recovery.status_code == 200
    assert "recovered_jobs" in recovery.json()


def test_runtime_health_queue_workers_websocket_replay_and_no_hardware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 100}),
    ).json()
    _wait_for_status(client, created["run_id"], {"SUCCEEDED"})

    health = client.get("/api/v1/simulation/runtime/health")
    workers = client.get("/api/v1/simulation/runtime/workers")
    queue = client.get("/api/v1/simulation/runtime/queue")
    assert health.status_code == 200
    assert health.json()["database"] == "sqlite"
    assert health.json()["real_controller_contacted"] is False
    assert health.json()["hardware_motion_observed"] is False
    assert workers.status_code == 200
    assert any(worker["backend"] == "MOCK" for worker in workers.json()["workers"])
    assert queue.status_code == 200
    assert "queued" in queue.json()

    with client.websocket_connect("/api/v1/simulation/stream?last_sequence=0") as ws:
        first = ws.receive_json()
        assert first["sequence"] >= 1
        assert first["event_type"] in {
            "job_created",
            "job_queued",
            "job_leased",
            "job_started",
            "run_event",
            "metric_update",
            "artifact_created",
            "job_completed",
            "heartbeat",
        }
        last_sequence = first["sequence"]

    with client.websocket_connect(f"/api/v1/simulation/stream?last_sequence={last_sequence}") as ws:
        replay_or_heartbeat = ws.receive_json()
        assert replay_or_heartbeat["sequence"] >= last_sequence

    paths = create_app(PlanningPipeline(planner=MockPlannerAdapter())).openapi()["paths"]
    assert "/api/v1/simulation/runtime/health" in paths
    assert not any("level1" in path or "real-robot" in path for path in paths)
    assert "controller" not in json.dumps(paths).lower()
