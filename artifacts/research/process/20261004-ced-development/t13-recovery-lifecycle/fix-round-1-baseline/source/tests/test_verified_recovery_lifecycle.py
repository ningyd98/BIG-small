"""A restart or a new event must not replenish the persistent task retry pool."""

from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from tests.test_phase6_recovery_replanning import _make_contract


@pytest.mark.parametrize("sqlite", [False, True])
def test_restart_initialize_preserves_spent_retry_and_absolute_deadline(tmp_path, sqlite):
    repo = SQLiteEventAutonomyRepository(tmp_path / "event.sqlite") if sqlite else (
        InMemoryEventAutonomyRepository())
    contract = _make_contract(command_ttl_ms=30_000)
    service = RetryBudgetService(repository=repo)
    service.initialize(contract.task_id, contract)
    consumed, before = service.consume_if_available(contract.task_id, "s2", "GRASP", "event-1")
    assert consumed
    if sqlite:
        repo.close()
        repo = SQLiteEventAutonomyRepository(tmp_path / "event.sqlite")
    restarted = RetryBudgetService(repository=repo)
    after = restarted.initialize(contract.task_id, contract)
    assert after == before
    assert after.remaining_retries == 2
    assert after.event_retry_counts == {"event-1": 1}
    assert restarted.consume_if_available(contract.task_id, "s2", "GRASP", "event-1")[0] is False
    assert restarted.consume_if_available(contract.task_id, "s2", "GRASP", "event-2")[0] is True
    assert repo.get_retry_budget(contract.task_id).remaining_retries == 1
    if sqlite:
        repo.close()


def test_initialize_cannot_extend_an_expired_deadline():
    repo = InMemoryEventAutonomyRepository()
    contract = _make_contract(command_ttl_ms=30_000)
    service = RetryBudgetService(repository=repo)
    saved = service.initialize(contract.task_id, contract)
    expired = saved.model_copy(update={"retry_deadline": datetime.now(UTC) - timedelta(seconds=1)})
    repo.save_retry_budget(expired)
    assert RetryBudgetService(repository=repo).initialize(contract.task_id, contract) == expired
    assert service.can_attempt(contract.task_id)[0] is False


def test_retry_initialize_rejects_a_different_task_contract():
    with pytest.raises(ValueError, match="task"):
        RetryBudgetService(repository=InMemoryEventAutonomyRepository()).initialize(
            "different-task", _make_contract())
