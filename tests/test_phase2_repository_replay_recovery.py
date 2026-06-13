from __future__ import annotations

import pytest

from cloud_edge_robot_arm.edge.runtime.recovery import recover_interrupted_tasks
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.repositories.sqlite import SQLiteRepository
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene
from tests.phase2_helpers import contract


@pytest.mark.parametrize("repository_factory", [InMemoryRepository])
def test_command_replay_is_rejected(repository_factory: type[InMemoryRepository]) -> None:
    repository = repository_factory()
    payload = contract().model_dump(mode="json")
    first_robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
    second_robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())

    first = TaskExecutor(robot=first_robot, repository=repository).submit_contract(payload)
    second = TaskExecutor(robot=second_robot, repository=repository).submit_contract(payload)

    assert first.success is True
    assert second.success is False
    assert second.error is not None
    assert second.error.code == "COMMAND_SEQ_REPLAYED"
    assert second_robot.history == []


def test_replay_is_rejected_after_sqlite_restart(tmp_path: object) -> None:
    db_path = tmp_path / "phase2.sqlite3"  # type: ignore[operator]
    payload = contract(task_id="task-restart-replay").model_dump(mode="json")

    first_repo = SQLiteRepository(db_path)
    first = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=first_repo,
    ).submit_contract(payload)
    first_repo.close()

    restarted_repo = SQLiteRepository(db_path)
    second_robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
    second = TaskExecutor(robot=second_robot, repository=restarted_repo).submit_contract(payload)

    assert first.success is True
    assert second.success is False
    assert second.error is not None
    assert second.error.code == "COMMAND_SEQ_REPLAYED"
    assert second_robot.history == []


def test_same_sequence_with_different_payload_is_conflict() -> None:
    repository = InMemoryRepository()
    first_payload = contract(task_id="task-seq-conflict").model_dump(mode="json")
    changed_payload = contract(task_id="task-seq-conflict").model_dump(mode="json")
    changed_payload["user_instruction"] = "different instruction with same command_seq"

    first = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=repository,
    ).submit_contract(first_payload)
    conflict = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=repository,
    ).submit_contract(changed_payload)

    assert first.success is True
    assert conflict.success is False
    assert conflict.error is not None
    assert conflict.error.code == "COMMAND_SEQ_CONFLICT"


def test_crash_recovery_pauses_executing_tasks_and_requires_explicit_resume(
    tmp_path: object,
) -> None:
    db_path = tmp_path / "recovery.sqlite3"  # type: ignore[operator]
    repository = SQLiteRepository(db_path)
    task = contract(task_id="task-interrupted")
    repository.create_task_from_contract(task)
    repository.record_state_transition(
        task_id=task.task_id,
        from_state="READY",
        to_state="EXECUTING",
        reason="simulated crash during execution",
    )
    repository.close()

    restarted_repository = SQLiteRepository(db_path)
    recovered = recover_interrupted_tasks(restarted_repository)

    assert recovered == ["task-interrupted"]
    record = restarted_repository.get_task("task-interrupted")
    assert record is not None
    assert record.state == "PAUSED"
    audit_events = restarted_repository.list_audit_events("task-interrupted")
    assert audit_events[-1].event_type == "RUNTIME_RECOVERY_REQUIRED"


def test_memory_and_sqlite_repositories_store_equivalent_records(tmp_path: object) -> None:
    task = contract(task_id="task-repository-consistency")
    memory = InMemoryRepository()
    sqlite = SQLiteRepository(tmp_path / "consistency.sqlite3")  # type: ignore[operator]

    for repository in (memory, sqlite):
        repository.create_task_from_contract(task)
        accepted = repository.accept_command(task, payload_hash="hash-1")
        repository.record_state_transition(
            task_id=task.task_id,
            from_state="CREATED",
            to_state="VALIDATING",
            reason="test",
        )
        repository.record_audit_event(
            task_id=task.task_id,
            event_type="CONTRACT_ACCEPTED",
            details={"accepted": accepted.accepted},
        )

    memory_task = memory.get_task(task.task_id)
    sqlite_task = sqlite.get_task(task.task_id)
    assert memory_task is not None
    assert sqlite_task is not None
    assert memory_task.task_id == sqlite_task.task_id
    assert memory_task.plan_version == sqlite_task.plan_version
    assert memory_task.command_seq == sqlite_task.command_seq
    assert memory.list_state_transitions(task.task_id)[0].to_state == "VALIDATING"
    assert sqlite.list_state_transitions(task.task_id)[0].to_state == "VALIDATING"
    assert memory.list_audit_events(task.task_id)[0].event_type == "CONTRACT_ACCEPTED"
    assert sqlite.list_audit_events(task.task_id)[0].event_type == "CONTRACT_ACCEPTED"
