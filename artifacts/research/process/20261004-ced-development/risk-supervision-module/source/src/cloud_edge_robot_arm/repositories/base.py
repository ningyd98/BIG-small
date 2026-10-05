"""基础仓储协议，定义持久化层必须满足的最小方法。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from cloud_edge_robot_arm.contracts import TaskContract
from cloud_edge_robot_arm.repositories.models import (
    AcceptedCommandDecision,
    ActionExecutionRecord,
    AuditEventRecord,
    StateTransitionRecord,
    StepExecutionRecord,
    TaskRecord,
)


class TaskRepository(ABC):
    @abstractmethod
    def create_task_from_contract(self, contract: TaskContract) -> TaskRecord: ...

    @abstractmethod
    def get_task(self, task_id: str) -> TaskRecord | None: ...

    @abstractmethod
    def update_task_state(self, task_id: str, state: str) -> None: ...

    @abstractmethod
    def list_tasks_by_state(self, state: str) -> list[TaskRecord]: ...

    @abstractmethod
    def record_state_transition(
        self,
        *,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> StateTransitionRecord: ...

    @abstractmethod
    def list_state_transitions(self, task_id: str) -> list[StateTransitionRecord]: ...

    @abstractmethod
    def record_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord: ...

    @abstractmethod
    def list_step_executions(self, task_id: str) -> list[StepExecutionRecord]: ...

    @abstractmethod
    def record_action_execution(self, record: ActionExecutionRecord) -> ActionExecutionRecord: ...

    @abstractmethod
    def list_action_executions(self, task_id: str) -> list[ActionExecutionRecord]: ...

    @abstractmethod
    def accept_command(
        self,
        contract: TaskContract,
        *,
        payload_hash: str,
    ) -> AcceptedCommandDecision: ...

    @abstractmethod
    def record_audit_event(
        self,
        *,
        task_id: str,
        event_type: str,
        details: dict[str, object] | None = None,
    ) -> AuditEventRecord: ...

    @abstractmethod
    def list_audit_events(self, task_id: str) -> list[AuditEventRecord]: ...

    def close(self) -> None:
        return None
