"""The experiment facade must preserve the repository's atomic mode commit."""

from datetime import UTC, datetime
from types import SimpleNamespace

from cloud_edge_robot_arm.auto_mode.models import AutoModeState, AutoModeTransitionRequest
from cloud_edge_robot_arm.auto_mode.repository import SQLiteAutoModeRepository
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.contracts import ControlMode
from cloud_edge_robot_arm.experiments.runtime_harness import RuntimeExperimentHarness


def test_harness_commit_does_not_count_atomic_transition_twice(tmp_path):
    now = datetime(2026, 10, 4, tzinfo=UTC)
    repo = SQLiteAutoModeRepository(tmp_path / "auto.sqlite", clock=lambda: now)
    repo.save_status(AutoModeState(
        task_id="task", current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1, switch_count=0, policy_version="frozen-original", updated_at=now,
    ))
    service = ModeTransitionService(repository=repo, clock=lambda: now)
    prepared = service.prepare(AutoModeTransitionRequest(
        task_id="task", from_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        expected_mode_version=1, idempotency_key="boundary-1", decision_id="decision-1",
        reason="verified skill boundary",
    ))
    harness = object.__new__(RuntimeExperimentHarness)
    harness.auto_repo = repo
    harness.transition_service = service
    harness.clock_adapter = SimpleNamespace(now=lambda: now)
    committed = harness.commit_mode_transition(prepared.transition_id)
    status = repo.get_status("task")
    assert status.mode_version == committed.new_mode_version == 2
    assert status.switch_count == 1
    assert status.policy_version == "frozen-original"
    assert status.last_switch_at == now
    assert harness.commit_mode_transition(prepared.transition_id) == committed
    assert repo.get_status("task") == status
    repo.close()
