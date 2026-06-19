"""Phase 11.1 运行时回归测试。

这些测试使用真实 FastAPI app、临时 SQLite 和 Mock 仿真任务，覆盖状态机、CAS、
租约、取消、超时、重试、恢复和 WebSocket replay；普通 CI 不运行 MuJoCo 或真实硬件。
"""

from __future__ import annotations

import json
import os
import threading
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


def _wait_for_artifact_paths(
    client: TestClient, run_id: str, *, artifact_root: Path | None = None
) -> dict[str, str]:
    deadline = time.monotonic() + 10.0
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/simulation/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        artifact_paths = last.get("artifact_paths", {})
        evidence_path = artifact_paths.get("evidence_consistency")
        if evidence_path:
            typed_paths = {str(key): str(value) for key, value in artifact_paths.items()}
            if artifact_root is None:
                return typed_paths
            if (artifact_root / evidence_path).exists():
                return typed_paths
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


def test_verifier_reads_result_from_runtime_artifacts_for_nested_outputs(tmp_path: Path) -> None:
    # 当 verifier 输出目录位于 artifacts/phase11_2/verification/phase11_1_runtime
    # 这类嵌套位置时，运行时实际 evidence 会落在兄弟 runtime_artifacts 目录。
    # MuJoCo 验收必须能读取该位置，不能误拼成仓库根下的 phase11_1/runtime。
    from scripts.verify_phase11_1_simulation_runtime import _read_result

    artifact_root = tmp_path / "verification" / "runtime_artifacts"
    result_path = artifact_root / "phase11_1" / "runtime" / "sim-path" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps({"status": "SUCCEEDED", "backend": "MUJOCO"}) + "\n",
        encoding="utf-8",
    )

    result = _read_result(
        tmp_path / "verification" / "phase11_1_runtime",
        {"result": "phase11_1/runtime/sim-path/result.json"},
    )

    assert result == {"status": "SUCCEEDED", "backend": "MUJOCO"}


def test_verifier_waits_for_result_artifact_after_terminal_status(tmp_path: Path) -> None:
    # MuJoCo job 的数据库终态可能比最终 evidence 文件早几个调度 tick 可见；
    # verifier 必须等待 result.json 原子落盘，不能因一次 FileNotFound 退出并杀掉 daemon worker。
    from scripts.verify_phase11_1_simulation_runtime import _read_result

    artifact_root = tmp_path / "artifacts"
    result_path = artifact_root / "phase11_1" / "runtime" / "sim-delayed" / "result.json"

    def write_later() -> None:
        time.sleep(0.15)
        result_path.parent.mkdir(parents=True)
        result_path.write_text(
            json.dumps({"status": "SUCCEEDED", "runtime_executed": True}) + "\n",
            encoding="utf-8",
        )

    writer = threading.Thread(target=write_later)
    writer.start()
    try:
        result = _read_result(
            artifact_root,
            {"result": "phase11_1/runtime/sim-delayed/result.json"},
        )
    finally:
        writer.join(timeout=2.0)

    assert result["status"] == "SUCCEEDED"
    assert result["runtime_executed"] is True


def test_verifier_waits_for_terminal_evidence_consistency(tmp_path: Path) -> None:
    # cancel/timeout 的 DB 终态也可能先于 evidence_consistency.json 可见；
    # MuJoCo M11-07/M11-08 验收必须等待完整 evidence，而不只看状态字段。
    from scripts.verify_phase11_1_simulation_runtime import _wait_for_terminal_evidence

    artifact_root = tmp_path / "artifacts"
    evidence_path = (
        artifact_root / "phase11_1" / "runtime" / "sim-timeout" / "evidence_consistency.json"
    )

    def write_later() -> None:
        time.sleep(0.15)
        evidence_path.parent.mkdir(parents=True)
        evidence_path.write_text(
            json.dumps({"consistent": True, "expected_terminal_status": "TIMED_OUT"}) + "\n",
            encoding="utf-8",
        )

    writer = threading.Thread(target=write_later)
    writer.start()
    try:
        evidence = _wait_for_terminal_evidence(
            artifact_root,
            {"evidence_consistency": "phase11_1/runtime/sim-timeout/evidence_consistency.json"},
        )
    finally:
        writer.join(timeout=2.0)

    assert evidence["consistent"] is True
    assert evidence["expected_terminal_status"] == "TIMED_OUT"


def test_verifier_waits_for_terminal_status_with_artifact_paths() -> None:
    # API 可能先暴露 CANCELLED/TIMED_OUT，再由 worker 补齐 artifact_paths；
    # MuJoCo verifier 需要等待二者同时成立，才能进入 evidence_consistency 校验。
    from dataclasses import dataclass

    from scripts.verify_phase11_1_simulation_runtime import _wait_for_terminal

    @dataclass
    class StatusValue:
        value: str

    @dataclass
    class RunRecord:
        status: StatusValue
        artifact_paths: dict[str, str]

    class DelayedArtifactService:
        def __init__(self) -> None:
            self.calls = 0

        def get_run(self, run_id: str) -> RunRecord:
            self.calls += 1
            if self.calls < 3:
                return RunRecord(StatusValue("CANCELLED"), {})
            return RunRecord(
                StatusValue("CANCELLED"),
                {"evidence_consistency": "phase11_1/runtime/sim-cancel/evidence_consistency.json"},
            )

    service = DelayedArtifactService()
    terminal = _wait_for_terminal(
        service,  # type: ignore[arg-type]
        "sim-cancel",
        timeout=1.0,
        require_artifacts=True,
    )

    assert terminal.status.value == "CANCELLED"
    assert "evidence_consistency" in terminal.artifact_paths
    assert service.calls >= 3


def test_verifier_waits_for_running_state_before_mujoco_cancel() -> None:
    # M11-07 要验证运行中 MuJoCo cooperative cancellation；如果刚入队就取消，
    # repository 会直接把 QUEUED 标成 CANCELLED，且没有 worker attempt/evidence。
    from dataclasses import dataclass

    from scripts.verify_phase11_1_simulation_runtime import _wait_for_non_queued

    @dataclass
    class StatusValue:
        value: str

    @dataclass
    class RunRecord:
        status: StatusValue
        artifact_paths: dict[str, str]

    class DelayedStartService:
        def __init__(self) -> None:
            self.calls = 0

        def get_run(self, run_id: str) -> RunRecord:
            self.calls += 1
            if self.calls < 3:
                return RunRecord(StatusValue("QUEUED"), {})
            return RunRecord(StatusValue("RUNNING"), {})

    service = DelayedStartService()
    record = _wait_for_non_queued(
        service,  # type: ignore[arg-type]
        "sim-cancellable",
        timeout=1.0,
    )

    assert record.status.value == "RUNNING"
    assert service.calls >= 3


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


def test_sqlite_repository_closes_connections_between_calls(tmp_path: Path) -> None:
    """SQLite repository 方法返回后不得泄漏 DB fd，避免 validation 退出阶段卡住。"""

    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    database_path = tmp_path / "runtime.db"
    repo = SQLiteSimulationJobRepository(database_path)
    for _ in range(30):
        repo.list_jobs()

    assert _sqlite_fd_targets(database_path) == []


def test_simulation_worker_closes_experiment_runtime_sqlite_handles(tmp_path: Path) -> None:
    """Worker 运行 Mock experiment 后必须关闭 harness 内部 SQLite 仓库。"""

    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    artifact_root = tmp_path / "artifacts"
    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="sim-runtime-fd-clean",
        batch_id="",
        backend="MOCK",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest-runtime-fd-clean",
        reproducibility_hash="hash-runtime-fd-clean",
        draft=_draft(),
        timeout_seconds=30,
        max_attempts=1,
        artifact_root="phase11_1/runtime/sim-runtime-fd-clean",
        source_commit="commit",
        source_tree_hash="tree",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="queued_by_test",
        worker_id="",
        lease_id="",
    )

    consumed = SimulationWorker(
        worker_id="worker-fd-clean",
        backend="MOCK",
        repository=repo,
        artifact_root=artifact_root,
    ).poll_once()

    assert consumed is True
    assert _sqlite_fd_targets(artifact_root / "phase11_1/runtime/sim-runtime-fd-clean") == []


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
    artifact_paths = _wait_for_artifact_paths(
        client, created["run_id"], artifact_root=tmp_path / "artifacts"
    )

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
    cancelled_paths = _wait_for_artifact_paths(
        client, cancellable["run_id"], artifact_root=tmp_path / "artifacts"
    )

    timed = client.post(
        "/api/v1/simulation/runs",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=_draft(parameter_overrides={"runtime_delay_ms": 1500, "timeout_seconds": 1}),
    ).json()
    timed_out = _wait_for_status(client, timed["run_id"], {"TIMED_OUT"})
    timed_out_paths = _wait_for_artifact_paths(
        client, timed["run_id"], artifact_root=tmp_path / "artifacts"
    )

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


def test_stale_lease_recovery_requeues_and_worker_b_completes(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="sim-recovery",
        batch_id="",
        backend="MOCK",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest-recovery",
        reproducibility_hash="hash-recovery",
        draft=_draft(),
        manifest={"manifest_id": "manifest-recovery"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root="phase11_1/runtime/sim-recovery",
        source_commit="commit",
        source_tree_hash="tree",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="queued_by_test",
        worker_id="",
        lease_id="",
    )
    lease = repo.acquire_lease(worker_id="worker-a", backend="MOCK", lease_ttl_seconds=1)
    assert lease is not None
    repo.start_attempt(job.job_id, worker_id="worker-a")
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.LEASED,
        next_status=RuntimeJobStatus.STARTING,
        reason_code="starting",
        worker_id="worker-a",
        lease_id=lease.lease_id,
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.STARTING,
        next_status=RuntimeJobStatus.RUNNING,
        reason_code="running",
        worker_id="worker-a",
        lease_id=lease.lease_id,
    )

    time.sleep(1.1)
    recovery = ArtifactRecoveryService(
        repository=repo,
        artifact_root=tmp_path / "artifacts",
        requeue_recoverable=True,
    ).recover_interrupted_jobs()

    recovered_job = repo.get_job(job.job_id)
    transitions = [
        (event.previous_status, event.next_status)
        for event in repo.list_events(job.run_id)
        if event.previous_status or event.next_status
    ]
    assert recovered_job.status == RuntimeJobStatus.QUEUED
    assert recovery.interrupted_jobs == [job.job_id]
    assert recovery.recovered_jobs == [job.job_id]
    assert ("RUNNING", "INTERRUPTED") in transitions
    assert ("INTERRUPTED", "RECOVERY_PENDING") in transitions
    assert ("RECOVERY_PENDING", "QUEUED") in transitions

    worker_b = SimulationWorker(
        worker_id="worker-b",
        backend="MOCK",
        repository=repo,
        artifact_root=tmp_path / "artifacts",
    )
    assert worker_b.poll_once() is True
    terminal = repo.get_job(job.job_id)
    attempts = repo.list_attempts(job.run_id)
    leases = repo.list_leases(job.run_id)
    assert terminal.status == RuntimeJobStatus.SUCCEEDED
    assert [attempt.worker_id for attempt in attempts] == ["worker-a", "worker-b"]
    assert attempts[-1].result == "SUCCEEDED"
    assert len(leases) == 2
    assert leases[-1].released_at is not None


def test_duplicate_worker_competition_executes_runner_once(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="sim-duplicate-worker",
        batch_id="",
        backend="MOCK",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest-duplicate",
        reproducibility_hash="hash-duplicate",
        draft=_draft(),
        manifest={"manifest_id": "manifest-duplicate"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root="phase11_1/runtime/sim-duplicate-worker",
        source_commit="commit",
        source_tree_hash="tree",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="queued_by_test",
        worker_id="",
        lease_id="",
    )

    invocation_count = 0

    class CountingWorker(SimulationWorker):
        def _run_mock(self, job: Any, draft: Any) -> Any:
            nonlocal invocation_count
            invocation_count += 1
            return super()._run_mock(job, draft)

    worker_a = CountingWorker(
        worker_id="worker-a",
        backend="MOCK",
        repository=repo,
        artifact_root=tmp_path / "artifacts",
    )
    worker_b = CountingWorker(
        worker_id="worker-b",
        backend="MOCK",
        repository=repo,
        artifact_root=tmp_path / "artifacts",
    )

    consumed_a = worker_a.poll_once()
    consumed_b = worker_b.poll_once()
    attempts = repo.list_attempts(job.run_id)
    leases = repo.list_leases(job.run_id)
    terminal = repo.get_job(job.job_id)
    completed_events = [
        event for event in repo.list_events(job.run_id) if event.event_type == "job_completed"
    ]

    assert (consumed_a, consumed_b).count(True) == 1
    assert terminal.status == RuntimeJobStatus.SUCCEEDED
    assert len(leases) == 1
    assert len(attempts) == 1
    assert attempts[0].result == "SUCCEEDED"
    assert invocation_count == 1
    assert len(completed_events) == 1


def test_worker_completes_cancel_when_api_wins_cancel_requested_race(tmp_path: Path) -> None:
    # API 和 worker 可能同时观察到取消请求；如果 API 先把 RUNNING 推到
    # CANCEL_REQUESTED，worker 不应因为自己的 CAS 失败而把 job 卡在中间态。
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import (
        CancelledByOperator,
        SimulationWorker,
    )

    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="sim-cancel-race",
        batch_id="",
        backend="MOCK",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest-cancel-race",
        reproducibility_hash="hash-cancel-race",
        draft=_draft(),
        manifest={"manifest_id": "manifest-cancel-race"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root="phase11_1/runtime/sim-cancel-race",
        source_commit="commit",
        source_tree_hash="tree",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="queued_by_test",
        worker_id="",
        lease_id="",
    )

    class CancelRaceRepository:
        def __init__(self, inner: SQLiteSimulationJobRepository) -> None:
            self.inner = inner
            self.race_injected = False

        def __getattr__(self, name: str) -> Any:
            return getattr(self.inner, name)

        def update_status_cas(self, job_id: str, **kwargs: Any) -> Any:
            if (
                kwargs["expected"] == RuntimeJobStatus.RUNNING
                and kwargs["next_status"] == RuntimeJobStatus.CANCEL_REQUESTED
                and not self.race_injected
            ):
                self.race_injected = True
                self.inner.update_status_cas(job_id, **kwargs)
                return None
            return self.inner.update_status_cas(job_id, **kwargs)

    class CancellingWorker(SimulationWorker):
        def _run(self, job: Any, *, start_monotonic: float) -> Any:
            raise CancelledByOperator("cancelled by operator")

    racing_repo = CancelRaceRepository(repo)
    worker = CancellingWorker(
        worker_id="worker-a",
        backend="MOCK",
        repository=racing_repo,
        artifact_root=tmp_path / "artifacts",
    )

    assert worker.poll_once() is True
    terminal = repo.get_job(job.job_id)
    attempts = repo.list_attempts(job.run_id)
    events = [event.event_type for event in repo.list_events(job.run_id)]

    assert racing_repo.race_injected is True
    assert terminal.status == RuntimeJobStatus.CANCELLED
    assert attempts[-1].result == RuntimeJobStatus.CANCELLED.value
    assert "job_cancelled" in events


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


def test_repeated_identical_batches_do_not_merge_historical_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 同一批量配置可以重复提交；batch_id 必须代表一次提交，而不是只代表
    # reproducibility manifest，否则旧 job 会被 list_batch_jobs 合并进新批次。
    client = _client(monkeypatch, tmp_path)
    payload = _draft(seeds=[0, 1, 2])

    first = client.post(
        "/api/v1/simulation/batches",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=payload,
    )
    second = client.post(
        "/api/v1/simulation/batches",
        headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        json=payload,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    first_batch = first.json()
    second_batch = second.json()
    assert first_batch["batch_id"] != second_batch["batch_id"]
    assert first_batch["progress"]["total"] == 3
    assert second_batch["progress"]["total"] == 3
    first_runs = client.get(f"/api/v1/simulation/batches/{first_batch['batch_id']}/runs")
    second_runs = client.get(f"/api/v1/simulation/batches/{second_batch['batch_id']}/runs")
    assert len(first_runs.json()["runs"]) == 3
    assert len(second_runs.json()["runs"]) == 3


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


def test_ci_summary_reports_runtime_evidence_acceptance_status() -> None:
    # Phase 11.1-R 是证据一致性修复，不应再只用普通 CI 状态表达验收结果。
    from scripts.verify_phase11_1_simulation_runtime import build_summary

    summary = build_summary(
        backend={
            "status": "PASSED",
            "retry_api": True,
            "runtime_health_api": True,
            "openapi_path_count": 89,
        },
        persistence={
            "status": "PASSED",
            "async_queue_accepted": True,
            "persistent_repository_accepted": True,
            "terminal_evidence_consistent": True,
            "atomic_artifact_finalization_accepted": True,
        },
        recovery={"status": "PASSED", "restart_recovery_accepted": True},
        frontend={"status": "PASSED"},
        e2e={"status": "PASSED", "playwright_test_count": 37},
        mujoco={"status": "SKIPPED"},
        full_requested=False,
        mujoco_requested=False,
    )

    assert summary["status"] == "PHASE11_1_RUNTIME_EVIDENCE_ACCEPTED"
    assert summary["validation_claimed"] is True
    assert summary["terminal_evidence_consistent"] is True


def test_recovery_verifier_does_not_leave_sqlite_databases_in_artifacts(tmp_path: Path) -> None:
    # Recovery 验收要记录 JSON 证据，不能把临时 SQLite 运行库作为 artifact 提交。
    from scripts.verify_phase11_1_simulation_runtime import verify_recovery

    output = tmp_path / "verification"
    result = verify_recovery(output)

    assert result["status"] == "PASSED"
    assert not list(output.rglob("*.db"))


def _sqlite_fd_targets(database_path: Path) -> list[str]:
    targets: list[str] = []
    database_text = str(database_path)
    for fd in Path("/proc/self/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if database_text in target:
            targets.append(target)
    return targets
