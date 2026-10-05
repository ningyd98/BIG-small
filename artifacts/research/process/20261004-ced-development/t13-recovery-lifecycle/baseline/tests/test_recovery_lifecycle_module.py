"""Software-only durable task verification pool; no physical recovery acceptance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository


@pytest.fixture(params=["memory", "sqlite"])
def lifecycle_repo(request, tmp_path):
    repo = (SQLiteEventAutonomyRepository(tmp_path / "lifecycle.sqlite")
            if request.param == "sqlite" else InMemoryEventAutonomyRepository())
    yield repo
    if request.param == "sqlite":
        repo.close()


def verification_pool():
    now = datetime.now(UTC)
    return VerificationBudgetState(
        remaining_reobservations=1, remaining_retries=0, consecutive_no_progress=2,
        deadline_at=now + timedelta(seconds=60),
        limits=VerificationBudget(2, 0, 3, 60),
        previous_conditions={"object_held:obj-1": ("FAIL", .1)}, verification_rounds=3,
    )


def test_task_verification_initialize_preserves_spent_pool_and_deadline(lifecycle_repo):
    original = lifecycle_repo.initialize_verification_budget_if_absent("task", verification_pool())
    replacement = VerificationBudgetState.start(VerificationBudget(99, 99, 99, 999))
    actual = lifecycle_repo.initialize_verification_budget_if_absent("task", replacement)
    assert actual == original
    assert actual.state.remaining_reobservations == 1
    assert actual.state.consecutive_no_progress == 2
    assert actual.state.deadline_at == original.state.deadline_at
    assert actual.state.limits.max_no_progress == 3
    assert actual.revision == original.revision


def test_task_pool_read_and_initialize_do_not_expose_mutable_saved_state(lifecycle_repo):
    proposed = verification_pool()
    original_deadline = proposed.deadline_at
    saved = lifecycle_repo.initialize_verification_budget_if_absent("task", proposed)
    proposed.previous_conditions.clear()
    proposed.remaining_reobservations = 99
    saved.state.previous_conditions.clear()
    saved.state.deadline_at += timedelta(days=1)
    read = lifecycle_repo.get_verification_budget("task")
    assert read.state.remaining_reobservations == 1
    assert read.state.previous_conditions == {"object_held:obj-1": ("FAIL", .1)}
    assert read.state.deadline_at == original_deadline
    read.state.previous_conditions.clear()
    assert lifecycle_repo.get_verification_budget("task").state.previous_conditions


def test_sqlite_restart_preserves_task_pool_complete_bytes(tmp_path):
    path = tmp_path / "restart.sqlite"
    repo = SQLiteEventAutonomyRepository(path)
    original = repo.initialize_verification_budget_if_absent("task", verification_pool())
    row_before = tuple(repo._conn.execute(
        "SELECT * FROM verification_budgets WHERE task_id='task'").fetchone())
    repo.close()
    restarted = SQLiteEventAutonomyRepository(path)
    actual = restarted.initialize_verification_budget_if_absent(
        "task", VerificationBudgetState.start(VerificationBudget(100, 100, 100, 999)))
    assert actual == original
    assert tuple(restarted._conn.execute(
        "SELECT * FROM verification_budgets WHERE task_id='task'").fetchone()) == row_before
    restarted.close()


def test_two_sqlite_initializers_share_one_task_pool_without_refilling(tmp_path):
    path = tmp_path / "race.sqlite"
    first, second = (SQLiteEventAutonomyRepository(path) for _ in range(2))
    proposals = [verification_pool(), verification_pool()]
    proposals[1].remaining_reobservations = 0
    barrier = Barrier(2)
    def initialize(repo, proposal):
        barrier.wait(timeout=5)
        return repo.initialize_verification_budget_if_absent("task", proposal)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(initialize, repo, proposal)
                   for repo, proposal in zip((first, second), proposals, strict=True)]
        results = [future.result(timeout=10) for future in futures]
    assert results[0] == results[1]
    assert first.get_verification_budget("task") == second.get_verification_budget("task")
    assert first._conn.execute("SELECT count(*) FROM verification_budgets").fetchone()[0] == 1
    first.close()
    second.close()


@pytest.mark.parametrize("invalid", ["", "   "])
def test_task_verification_pool_rejects_missing_task_identity(lifecycle_repo, invalid):
    with pytest.raises(ValueError):
        lifecycle_repo.initialize_verification_budget_if_absent(invalid, verification_pool())
    assert lifecycle_repo.get_verification_budget(invalid) is None
