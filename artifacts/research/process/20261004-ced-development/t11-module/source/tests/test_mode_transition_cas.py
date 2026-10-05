"""模式事务必须以仓储原子版本比较提交，跨重启仍保持幂等。"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest

from cloud_edge_robot_arm.auto_mode.models import AutoModeState, AutoModeTransitionRequest
from cloud_edge_robot_arm.auto_mode.repository import (
    InMemoryAutoModeRepository,
    SQLiteAutoModeRepository,
)
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.contracts import AutoModeTransitionStatus, ControlMode
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError

NOW = datetime(2026, 10, 4, tzinfo=UTC)
PCSC = ControlMode.PERIODIC_CLOUD_SUPERVISION
ETEA = ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY


def request(key="first", **changes):
    values = dict(
        task_id="task",
        from_mode=PCSC,
        to_mode=ETEA,
        expected_mode_version=1,
        idempotency_key=key,
        decision_id="decision",
        reason="online boundary",
    )
    values.update(changes)
    return AutoModeTransitionRequest(**values)


def initialize(repo):
    repo.save_status(
        AutoModeState(
            task_id="task",
            current_mode=PCSC,
            mode_version=1,
            policy_version="original",
            updated_at=NOW,
        )
    )


@pytest.mark.parametrize("sqlite", [False, True])
def test_transition_commit_rechecks_mode_version(tmp_path: Path, sqlite):
    repo = (
        SQLiteAutoModeRepository(tmp_path / "mode.db") if sqlite else InMemoryAutoModeRepository()
    )
    initialize(repo)
    service = ModeTransitionService(repository=repo, clock=lambda: NOW)
    a = service.prepare(request())
    b = service.prepare(request("second"))
    service.commit(b.transition_id)
    with pytest.raises(ValueError, match="version|current"):
        service.commit(a.transition_id)
    assert repo.get_status("task").mode_version == 2
    assert repo.get_transition(a.transition_id).status == AutoModeTransitionStatus.PREPARED
    repo.close()


def test_duplicate_transition_is_idempotent_and_preserves_original_time(tmp_path: Path):
    repo = SQLiteAutoModeRepository(tmp_path / "mode.db")
    initialize(repo)
    service = ModeTransitionService(repository=repo, clock=lambda: NOW)
    prepared = service.prepare(request())
    committed = service.commit(prepared.transition_id)
    repo.close()
    repo = SQLiteAutoModeRepository(tmp_path / "mode.db")
    restarted = ModeTransitionService(
        repository=repo, clock=lambda: datetime(2026, 10, 5, tzinfo=UTC)
    )
    assert restarted.prepare(request()) == committed
    assert restarted.commit(prepared.transition_id) == committed
    status = repo.get_status("task")
    assert (
        status.mode_version == 2
        and status.switch_count == 1
        and status.policy_version == "original"
    )
    assert status.last_switch_at == NOW
    repo.close()


def test_abort_prepared_transition_prevents_later_commit_and_committed_is_terminal():
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    service = ModeTransitionService(repository=repo, clock=lambda: NOW)
    prepared = service.prepare(request())
    aborted = service.abort(prepared.transition_id, reason="cancelled")
    with pytest.raises(ValueError, match="ABORTED|prepared"):
        service.commit(aborted.transition_id)
    second = service.prepare(request("second"))
    service.commit(second.transition_id)
    with pytest.raises(ValueError, match="COMMITTED|committed"):
        service.abort(second.transition_id, reason="too late")
    assert repo.get_status("task").mode_version == 2


def test_conflicting_prepare_is_rejected_across_restart(tmp_path: Path):
    path = tmp_path / "mode.db"
    repo = SQLiteAutoModeRepository(path)
    initialize(repo)
    service = ModeTransitionService(repository=repo)
    service.prepare(request())
    repo.close()
    repo = SQLiteAutoModeRepository(path)
    service = ModeTransitionService(repository=repo)
    with pytest.raises(IdempotencyConflictError):
        service.prepare(request(reason="different intent"))
    repo.close()


def test_two_sqlite_connections_cannot_commit_stale_modes(tmp_path: Path):
    path = tmp_path / "mode.db"
    one = SQLiteAutoModeRepository(path)
    initialize(one)
    two = SQLiteAutoModeRepository(path)
    first = ModeTransitionService(repository=one, clock=lambda: NOW)
    second = ModeTransitionService(repository=two, clock=lambda: NOW)
    a = first.prepare(request())
    b = second.prepare(request("second"))
    first.commit(a.transition_id)
    with pytest.raises(ValueError, match="version|current"):
        second.commit(b.transition_id)
    assert two.get_status("task").mode_version == 2
    one.close()
    two.close()


def test_missing_current_state_cannot_commit():
    service = ModeTransitionService(repository=InMemoryAutoModeRepository())
    prepared = service.prepare(request())
    with pytest.raises(ValueError, match="current|state"):
        service.commit(prepared.transition_id)


def test_research_commit_requires_durable_boundary_and_current_guard(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.models")
    assert hasattr(module, "ModeTransitionCheckpoint"), "durable boundary contract is missing"
    from tests.test_runtime_auto_baselines import mode_policy_snapshot

    snapshot = mode_policy_snapshot(tmp_path / "selection")
    repo = SQLiteAutoModeRepository(tmp_path / "mode.db")
    initialize(repo)
    status = repo.get_status("task")
    repo.save_status(
        status.model_copy(
            update={"last_switch_at": NOW - __import__("datetime").timedelta(seconds=600)}
        )
    )
    boundary = module.ModeTransitionCheckpoint(
        task_id="task",
        checkpoint_id="cp",
        plan_version=1,
        command_seq=1,
        mode_version=1,
        atomic_action_active=False,
        confirmation_count=2,
        persisted_at=NOW,
    )
    service = ModeTransitionService(
        repository=repo,
        clock=lambda: NOW,
        require_verified_boundary=True,
        mode_switch_policy=snapshot,
        commit_guard=lambda record: boundary,
    )
    prepared = service.prepare(request())
    with pytest.raises(ValueError, match="checkpoint|boundary"):
        service.commit(prepared.transition_id)
    repo.save_transition_checkpoint(prepared.transition_id, boundary)
    committed = service.commit(prepared.transition_id)
    assert committed.status == AutoModeTransitionStatus.COMMITTED
    repo.close()


def test_non_safety_switch_waits_for_atomic_boundary():
    module = import_module("cloud_edge_robot_arm.auto_mode.models")
    assert hasattr(module, "ModeTransitionCheckpoint")
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    boundary = module.ModeTransitionCheckpoint(
        task_id="task",
        checkpoint_id="cp",
        plan_version=1,
        command_seq=1,
        mode_version=1,
        atomic_action_active=True,
        persisted_at=NOW,
    )
    service = ModeTransitionService(
        repository=repo,
        clock=lambda: NOW,
        require_verified_boundary=False,
        commit_guard=lambda record: boundary,
    )
    prepared = service.prepare(request())
    repo.save_transition_checkpoint(
        prepared.transition_id, boundary.model_copy(update={"atomic_action_active": False})
    )
    with pytest.raises(ValueError, match="atomic"):
        service.commit(prepared.transition_id)
    assert repo.get_status("task").mode_version == 1


def test_research_commit_without_guard_never_falls_back_to_legacy():
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    assert (
        "require_verified_boundary"
        in __import__("inspect").signature(ModeTransitionService).parameters
    )
    service = ModeTransitionService(repository=repo, require_verified_boundary=True)
    prepared = service.prepare(request())
    with pytest.raises(ValueError, match="boundary|guard"):
        service.commit(prepared.transition_id)


@pytest.mark.parametrize("sqlite", [False, True])
def test_public_transition_save_cannot_forge_a_committed_transaction(tmp_path: Path, sqlite):
    repo = (
        SQLiteAutoModeRepository(tmp_path / "mode.db") if sqlite else InMemoryAutoModeRepository()
    )
    initialize(repo)
    service = ModeTransitionService(repository=repo, clock=lambda: NOW)
    prepared = service.prepare(request())
    forged = prepared.model_copy(
        update={"status": AutoModeTransitionStatus.COMMITTED, "committed_at": NOW}
    )
    with pytest.raises(ValueError, match="commit|terminal"):
        repo.save_transition(forged)
    assert repo.get_status("task").mode_version == 1
    repo.close()


def test_checkpoint_model_copy_cannot_bypass_strict_version_validation():
    module = import_module("cloud_edge_robot_arm.auto_mode.models")
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    service = ModeTransitionService(repository=repo, clock=lambda: NOW)
    prepared = service.prepare(request())
    checkpoint = module.ModeTransitionCheckpoint(
        task_id="task",
        checkpoint_id="cp",
        plan_version=1,
        command_seq=1,
        mode_version=1,
        atomic_action_active=False,
        persisted_at=NOW,
    )
    with pytest.raises(ValueError):
        repo.save_transition_checkpoint(
            prepared.transition_id, checkpoint.model_copy(update={"mode_version": True})
        )


def test_research_missing_selection_policy_cannot_commit():
    module = import_module("cloud_edge_robot_arm.auto_mode.models")
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    boundary = module.ModeTransitionCheckpoint(
        task_id="task",
        checkpoint_id="cp",
        plan_version=1,
        command_seq=1,
        mode_version=1,
        atomic_action_active=False,
        confirmation_count=2,
        persisted_at=NOW,
    )
    service = ModeTransitionService(
        repository=repo,
        clock=lambda: NOW,
        require_verified_boundary=True,
        commit_guard=lambda record: boundary,
    )
    prepared = service.prepare(request())
    repo.save_transition_checkpoint(prepared.transition_id, boundary)
    with pytest.raises(ValueError, match="selection"):
        service.commit(prepared.transition_id)
    assert repo.get_status("task").mode_version == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"last_switch_at": NOW - __import__("datetime").timedelta(seconds=100)}, "dwell"),
        ({"last_switch_at": NOW - __import__("datetime").timedelta(seconds=200)}, "cooldown"),
        ({"switch_count": 5}, "limit"),
        ({"last_switch_at": None}, "unknown"),
    ],
)
def test_verified_selection_still_enforces_live_mode_limits(tmp_path: Path, change, reason):
    from datetime import timedelta

    from tests.test_runtime_auto_baselines import mode_policy_snapshot

    module = import_module("cloud_edge_robot_arm.auto_mode.models")
    snapshot = mode_policy_snapshot(tmp_path / "selection")
    repo = InMemoryAutoModeRepository()
    initialize(repo)
    state = repo.get_status("task").model_copy(
        update={"last_switch_at": NOW - timedelta(seconds=600), **change}
    )
    repo.save_status(state)
    boundary = module.ModeTransitionCheckpoint(
        task_id="task",
        checkpoint_id="cp",
        plan_version=1,
        command_seq=1,
        mode_version=1,
        atomic_action_active=False,
        confirmation_count=2,
        persisted_at=NOW,
    )
    service = ModeTransitionService(
        repository=repo,
        clock=lambda: NOW,
        require_verified_boundary=True,
        mode_switch_policy=snapshot,
        commit_guard=lambda record: boundary,
    )
    prepared = service.prepare(request())
    repo.save_transition_checkpoint(prepared.transition_id, boundary)
    with pytest.raises(ValueError, match=reason):
        service.commit(prepared.transition_id)
    assert repo.get_status("task").mode_version == 1
