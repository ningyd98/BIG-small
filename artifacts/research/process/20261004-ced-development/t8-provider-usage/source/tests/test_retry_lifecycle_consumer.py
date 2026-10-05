"""Actual memory/SQLite authorization transactions with software T10 fixtures."""

from dataclasses import replace

import pytest

from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from tests.test_recovery_lifecycle_module import authorization_proof, detected_record


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    value = (SQLiteEventAutonomyRepository(tmp_path / "consumer.sqlite")
             if request.param == "sqlite" else InMemoryEventAutonomyRepository())
    yield value
    if request.param == "sqlite":
        value.close()


def test_retry_consumer_uses_single_lifecycle_transaction_and_duplicate_cannot_dispatch(repo):
    saved = repo.initialize_recovery_if_absent(detected_record(repo))
    proof = authorization_proof(saved)
    service = RetryBudgetService(repository=repo)
    before = repo.get_retry_budget("task").retry_count_used
    repo.consume_retry_if_available = lambda **kwargs: pytest.fail("split retry transaction used")
    first = service.consume_for_recovery(proof)
    assert first.authorized
    assert first.recovery.state == "RECOVERY_AUTHORIZED"
    assert first.retry_budget.retry_count_used == before + 1
    second = service.consume_for_recovery(proof)
    assert not second.authorized
    assert second.retry_budget.retry_count_used == before + 1
    assert repo.list_unresolved_recoveries("task")[0].state == "RECOVERY_AUTHORIZED"


def test_retry_consumer_invalid_current_version_does_not_consume(repo):
    saved = repo.initialize_recovery_if_absent(detected_record(repo))
    proof = authorization_proof(saved)
    proof = replace(proof, current=replace(proof.current, plan_version=999))
    before = repo.get_retry_budget("task").model_dump()
    result = RetryBudgetService(repository=repo).consume_for_recovery(proof)
    assert not result.authorized
    assert repo.get_retry_budget("task").model_dump() == before
    assert repo.get_recovery(saved.recovery_id).state == "DETECTED"


def test_retry_consumer_missing_recovery_cannot_initialize_or_spend(repo):
    proposal = detected_record(repo)
    before = repo.get_retry_budget("task").model_dump()
    result = RetryBudgetService(repository=repo).consume_for_recovery(authorization_proof(proposal))
    assert not result.authorized
    assert result.recovery is None
    assert repo.get_retry_budget("task").model_dump() == before
    assert repo.list_unresolved_recoveries("task") == []
