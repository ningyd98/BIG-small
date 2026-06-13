from __future__ import annotations

from dataclasses import replace

from cloud_edge_robot_arm.contracts import TaskContract
from cloud_edge_robot_arm.repositories.base import TaskRepository
from cloud_edge_robot_arm.repositories.models import (
    AcceptedCommandDecision,
    AcceptedCommandRecord,
    ActionExecutionRecord,
    AuditEventRecord,
    StateTransitionRecord,
    StepExecutionRecord,
    TaskRecord,
    utc_now,
)


class InMemoryRepository(TaskRepository):
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._state_transitions: list[StateTransitionRecord] = []
        self._step_executions: list[StepExecutionRecord] = []
        self._action_executions: list[ActionExecutionRecord] = []
        self._accepted_commands: dict[tuple[str, int], AcceptedCommandRecord] = {}
        self._audit_events: list[AuditEventRecord] = []

    def create_task_from_contract(self, contract: TaskContract) -> TaskRecord:
        now = utc_now()
        existing = self._tasks.get(contract.task_id)
        created_at = existing.created_at if existing is not None else now
        record = TaskRecord(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            state="CREATED",
            contract_json=contract.model_dump_json(),
            created_at=created_at,
            updated_at=now,
        )
        self._tasks[contract.task_id] = record
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def update_task_state(self, task_id: str, state: str) -> None:
        existing = self._tasks[task_id]
        self._tasks[task_id] = replace(existing, state=state, updated_at=utc_now())

    def list_tasks_by_state(self, state: str) -> list[TaskRecord]:
        return [task for task in self._tasks.values() if task.state == state]

    def record_state_transition(
        self,
        *,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> StateTransitionRecord:
        record = StateTransitionRecord(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        )
        self._state_transitions.append(record)
        self.update_task_state(task_id, to_state)
        return record

    def list_state_transitions(self, task_id: str) -> list[StateTransitionRecord]:
        return [record for record in self._state_transitions if record.task_id == task_id]

    def record_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        self._step_executions.append(record)
        return record

    def list_step_executions(self, task_id: str) -> list[StepExecutionRecord]:
        return [record for record in self._step_executions if record.task_id == task_id]

    def record_action_execution(self, record: ActionExecutionRecord) -> ActionExecutionRecord:
        self._action_executions.append(record)
        return record

    def list_action_executions(self, task_id: str) -> list[ActionExecutionRecord]:
        return [record for record in self._action_executions if record.task_id == task_id]

    def accept_command(
        self,
        contract: TaskContract,
        *,
        payload_hash: str,
    ) -> AcceptedCommandDecision:
        key = (contract.task_id, contract.command_seq)
        existing = self._accepted_commands.get(key)
        if existing is not None:
            if existing.payload_hash == payload_hash:
                return AcceptedCommandDecision(
                    accepted=False,
                    code="COMMAND_SEQ_REPLAYED",
                    message="command_seq has already been accepted for this task",
                    existing_hash=existing.payload_hash,
                )
            return AcceptedCommandDecision(
                accepted=False,
                code="COMMAND_SEQ_CONFLICT",
                message="command_seq was reused with a different payload",
                existing_hash=existing.payload_hash,
            )

        task_records = [
            record
            for record in self._accepted_commands.values()
            if record.task_id == contract.task_id
        ]
        if task_records:
            max_seq = max(record.command_seq for record in task_records)
            max_plan = max(record.plan_version for record in task_records)
            if contract.command_seq <= max_seq:
                return AcceptedCommandDecision(
                    accepted=False,
                    code="COMMAND_SEQ_REPLAYED",
                    message="command_seq is not greater than the last accepted sequence",
                )
            if contract.plan_version < max_plan:
                return AcceptedCommandDecision(
                    accepted=False,
                    code="STALE_PLAN_VERSION",
                    message="plan_version is older than the last accepted command",
                )

        self._accepted_commands[key] = AcceptedCommandRecord(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            payload_hash=payload_hash,
        )
        return AcceptedCommandDecision(
            accepted=True,
            code="ACCEPTED",
            message="command accepted",
        )

    def record_audit_event(
        self,
        *,
        task_id: str,
        event_type: str,
        details: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        record = AuditEventRecord(
            task_id=task_id,
            event_type=event_type,
            details=dict(details or {}),
        )
        self._audit_events.append(record)
        return record

    def list_audit_events(self, task_id: str) -> list[AuditEventRecord]:
        return [event for event in self._audit_events if event.task_id == task_id]
