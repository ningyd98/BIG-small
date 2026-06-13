from __future__ import annotations

from cloud_edge_robot_arm.contracts import TaskState
from cloud_edge_robot_arm.repositories.base import TaskRepository


def recover_interrupted_tasks(repository: TaskRepository) -> list[str]:
    recovered_task_ids: list[str] = []
    for task in repository.list_tasks_by_state(TaskState.EXECUTING.value):
        repository.record_state_transition(
            task_id=task.task_id,
            from_state=TaskState.EXECUTING.value,
            to_state=TaskState.PAUSED.value,
            reason="RUNTIME_RECOVERY_REQUIRED",
        )
        repository.record_audit_event(
            task_id=task.task_id,
            event_type="RUNTIME_RECOVERY_REQUIRED",
            details={
                "previous_state": TaskState.EXECUTING.value,
                "new_state": TaskState.PAUSED.value,
            },
        )
        recovered_task_ids.append(task.task_id)
    return recovered_task_ids
