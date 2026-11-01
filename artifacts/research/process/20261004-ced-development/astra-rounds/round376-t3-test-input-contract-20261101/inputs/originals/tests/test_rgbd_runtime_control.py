"""Cancellation and deadlines must discard results without releasing in-flight capacity."""

from __future__ import annotations

import threading
import time

import pytest


def test_cancelled_or_timed_out_response_cannot_dispatch() -> None:
    from cloud_edge_robot_arm.vision.request_control import (
        ModelCallCancelled,
        ModelCallTimedOut,
        bounded_model_call,
    )

    finished = threading.Event()
    started = threading.Event()
    cancelled = threading.Event()
    dispatched = []

    def slow():
        started.set()
        finished.wait(2)
        return "late response"

    def cancel_later():
        started.wait(2)
        cancelled.set()

    threading.Thread(target=cancel_later, daemon=True).start()
    before = time.monotonic()
    try:
        with pytest.raises(ModelCallCancelled):
            dispatched.append(
                bounded_model_call(
                    slow, timeout_s=2, cancelled=cancelled.is_set, resource_key="cancel-case"
                )
            )
        assert time.monotonic() - before < 1
        assert dispatched == []
        # A cancelled caller cannot free capacity while the actual model still runs.
        with pytest.raises(ModelCallTimedOut):
            bounded_model_call(
                lambda: dispatched.append("second"), timeout_s=0.05, resource_key="cancel-case"
            )
        assert dispatched == []
    finally:
        finished.set()


def test_model_deadline_does_not_wait_for_uncooperative_request() -> None:
    from cloud_edge_robot_arm.vision.request_control import ModelCallTimedOut, bounded_model_call

    release = threading.Event()
    start = time.monotonic()
    try:
        with pytest.raises(ModelCallTimedOut):
            bounded_model_call(lambda: release.wait(2), timeout_s=0.05, resource_key="timeout")
        assert time.monotonic() - start < 0.8
    finally:
        release.set()


def test_model_exception_and_success_are_preserved() -> None:
    from cloud_edge_robot_arm.vision.request_control import bounded_model_call

    assert bounded_model_call(lambda: 42, timeout_s=1, resource_key="ready") == 42

    def failed():
        raise ValueError("model response failed")

    with pytest.raises(ValueError, match="model response failed"):
        bounded_model_call(failed, timeout_s=1, resource_key="failed")


def test_execution_scopes_are_explicit_and_planning_is_default() -> None:
    from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft
    from tests.test_phase11_1_simulation_runtime import _draft

    draft = ExperimentDraft.model_validate(_draft(backend="MUJOCO", input_mode="RGBD"))
    assert draft.execution_scope == "VISUAL_PLANNING"
    assert (
        ExperimentDraft.model_validate(
            _draft(backend="MUJOCO", input_mode="RGBD", execution_scope="CAPTURE_ONLY")
        ).execution_scope
        == "CAPTURE_ONLY"
    )
    with pytest.raises(ValueError):
        ExperimentDraft.model_validate(_draft(execution_scope="VISION_CLOSED_LOOP"))


def test_worker_heartbeat_is_independent_of_blocking_runner(tmp_path) -> None:
    from types import SimpleNamespace

    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    class Repo:
        beats = 0
        released = []

        def acquire_lease(self, **kwargs):
            return SimpleNamespace(job_id="job", lease_id="lease")

        def heartbeat_lease(self, lease_id, **kwargs):
            self.beats += 1

        def release_lease(self, lease_id):
            self.released.append(lease_id)

    repo = Repo()
    worker = SimulationWorker(
        worker_id="w",
        backend="MUJOCO",
        repository=repo,
        artifact_root=tmp_path,
        lease_ttl_seconds=1,
    )
    worker._execute = lambda *args: time.sleep(0.45)
    assert worker.poll_once()
    assert repo.beats >= 2
    assert repo.released == ["lease"]
    assert worker.active_job_id == ""


def test_websocket_first_uses_same_active_model_factory(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from cloud_edge_robot_arm.cloud.api import model_control, simulation_workbench

    def marker():
        return "active-profile"

    monkeypatch.setattr(
        model_control, "_service", lambda conn: SimpleNamespace(visual_planner=marker)
    )
    calls = []
    monkeypatch.setattr(
        simulation_workbench,
        "SimulationWorkbenchService",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(),
    )
    connection = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    first = simulation_workbench._ws_service(connection)
    assert calls[0]["planner_factory"] is marker
    assert simulation_workbench._service(connection) is first


def test_capture_works_without_model(monkeypatch, tmp_path) -> None:
    from fastapi.testclient import TestClient

    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from tests.test_phase11_1_simulation_runtime import _draft, _wait_for_status

    def forbidden(self):
        pytest.fail("capture-only must not load or call a model")

    monkeypatch.setattr(ModelControlService, "visual_planner", forbidden)
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SIMULATION_RUNTIME_DB", str(tmp_path / "runtime.db"))
    with TestClient(create_app()) as client:
        submitted = client.post(
            "/api/v1/simulation/runs",
            json=_draft(backend="MUJOCO", input_mode="RGBD", execution_scope="CAPTURE_ONLY"),
            headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        )
        assert submitted.status_code == 202
        run = _wait_for_status(
            client, submitted.json()["run_id"], {"FAILED", "SUCCEEDED", "BLOCKED_BY_ENV"}
        )
        assert run["status"] == "SUCCEEDED"


def _queued_closed_loop_worker(tmp_path, draft=None):
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    repo = SQLiteSimulationJobRepository(tmp_path / "runtime.db")
    job = repo.create_job(
        run_id="terminal-test",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest",
        reproducibility_hash="hash",
        draft=draft or {"input_mode": "RGBD", "execution_scope": "VISION_CLOSED_LOOP"},
        timeout_seconds=60,
        max_attempts=1,
        artifact_root="terminal-test",
        source_commit="test",
        source_tree_hash="test",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="test",
        worker_id="",
        lease_id="",
    )
    worker = SimulationWorker(
        worker_id="worker", backend="MUJOCO", repository=repo, artifact_root=tmp_path
    )
    return repo, job, worker


def _terminal_artifacts(tmp_path, repo, job):
    import json

    current = repo.get_job(job.job_id)
    result = json.loads((tmp_path / current.artifact_paths["result"]).read_text())
    consistency = json.loads(
        (tmp_path / current.artifact_paths["evidence_consistency"]).read_text()
    )
    return current, result, consistency


@pytest.mark.parametrize("failure", ["timeout", "generic"])
def test_cancel_racing_failure_converges_every_record_to_cancelled(tmp_path, failure):
    from cloud_edge_robot_arm.simulation_runtime.worker import TimedOut

    repo, job, worker = _queued_closed_loop_worker(tmp_path)

    def run(current, **kwargs):
        repo.request_cancel(current.job_id)
        if failure == "timeout":
            raise TimedOut("deadline while cancelled")
        raise ValueError("provider failed while cancelled")

    worker._run = run
    assert worker.poll_once()
    current, result, consistency = _terminal_artifacts(tmp_path, repo, job)
    assert current.status == "CANCELLED"
    assert result["status"] == "CANCELLED"
    assert consistency["consistent"]


def test_partial_episode_cancel_preserves_executed_actions_and_failed_result(tmp_path):
    import json

    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    record = {"layer": "SKILL_RETURN", "skill": "GRASP", "success": True}

    def run(current, **kwargs):
        directory = (
            tmp_path / current.artifact_root / "rgbd-attempts" / current.lease_id / "visual_episode"
        )
        directory.mkdir(parents=True)
        (directory / "episode.json").write_text(
            json.dumps(
                {
                    "evaluation_scope": "VISION_CLOSED_LOOP",
                    "executed_actions": 3,
                    "verification_records": [record],
                    "online_reported_complete": False,
                    "physical_success": False,
                    "success": False,
                }
            )
        )
        repo.request_cancel(current.job_id)
        worker._heartbeat_failed.set()
        return {"evaluation_scope": "VISION_CLOSED_LOOP", "task_success": False}, [], []

    worker._run = run
    assert worker.poll_once()
    current, result, consistency = _terminal_artifacts(tmp_path, repo, job)
    assert current.status == "CANCELLED"
    assert result["status"] == "CANCELLED"
    assert result["evaluation_scope"] == "VISION_CLOSED_LOOP"
    assert result["executed_actions"] == 3
    assert result["task_execution"] == "EXECUTED"
    assert result["task_success"] is False
    assert result["verification_records"] == [record]
    assert consistency["consistent"]


@pytest.mark.parametrize("failure", ["timeout", "cancel", "generic"])
def test_late_worker_failure_preserves_interrupted_state_and_artifacts(tmp_path, failure):
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.worker import CancelledByOperator, TimedOut

    repo, job, worker = _queued_closed_loop_worker(tmp_path)

    def run(current, **kwargs):
        repo.update_status_cas(
            current.job_id,
            expected=RuntimeJobStatus.RUNNING,
            next_status=RuntimeJobStatus.INTERRUPTED,
            reason_code="lease_lost",
            worker_id=worker.worker_id,
            lease_id=current.lease_id,
        )
        if failure == "timeout":
            raise TimedOut("late timeout")
        if failure == "cancel":
            raise CancelledByOperator("late cancel")
        raise ValueError("late failure")

    worker._run = run
    assert worker.poll_once()
    current, result, consistency = _terminal_artifacts(tmp_path, repo, job)
    assert current.status == "INTERRUPTED"
    assert result["status"] == "INTERRUPTED"
    assert consistency["consistent"]


def test_closed_loop_verification_failure_cannot_finish_succeeded(tmp_path):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    worker._run = lambda *args, **kwargs: (
        {
            "evaluation_scope": "VISION_CLOSED_LOOP",
            "task_success": False,
            "online_reported_complete": False,
            "physical_success": True,
        },
        [],
        [],
    )
    assert worker.poll_once()
    current, result, consistency = _terminal_artifacts(tmp_path, repo, job)
    assert current.status == "FAILED"
    assert result["status"] == "FAILED"
    assert result["task_success"] is False
    assert consistency["consistent"]


def test_dispatcher_reports_latest_real_worker_heartbeat(tmp_path):
    from datetime import UTC, datetime

    from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    dispatcher = SimulationJobDispatcher(
        repository=SQLiteSimulationJobRepository(tmp_path / "db"), artifact_root=tmp_path
    )
    timestamp = datetime.now(UTC)
    dispatcher._workers[0].heartbeat_at = timestamp.isoformat()
    assert dispatcher.workers()[0].heartbeat_at == timestamp
