from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from cloud_edge_robot_arm.contracts import TaskContract, TaskState
from cloud_edge_robot_arm.errors import StructuredError


@dataclass
class TaskRuntimeContext:
    task_id: str
    plan_version: int
    command_seq: int
    contract: TaskContract
    current_step_id: str | None
    current_step_index: int
    completed_step_ids: list[str]
    failed_step_id: str | None
    step_attempts: dict[str, int]
    task_started_at: datetime
    task_deadline: datetime
    last_transition_at: datetime
    last_error: StructuredError | None
    _state: TaskState = field(repr=False)
    elapsed_action_ms: int = 0

    @classmethod
    def from_contract(
        cls,
        contract: TaskContract,
        *,
        initial_state: TaskState = TaskState.CREATED,
    ) -> TaskRuntimeContext:
        return cls(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            _state=initial_state,
            contract=contract,
            current_step_id=contract.current_step_id,
            current_step_index=0,
            completed_step_ids=[],
            failed_step_id=None,
            step_attempts={},
            task_started_at=contract.issued_at,
            task_deadline=contract.valid_until,
            last_transition_at=contract.issued_at,
            last_error=None,
        )

    @property
    def state(self) -> TaskState:
        return self._state

    def apply_transition(self, state: TaskState, *, at: datetime) -> None:
        self._state = state
        self.last_transition_at = at

    def set_error(self, error: StructuredError) -> None:
        self.last_error = error
