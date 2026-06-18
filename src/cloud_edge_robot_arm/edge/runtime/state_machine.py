"""任务运行时状态机。

状态机限定 CREATED、VALIDATING、EXECUTING、PAUSED、COMPLETED、FAILED 等转换，防止非法状态跳转。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts import TaskState
from cloud_edge_robot_arm.edge.runtime.errors import INVALID_STATE_TRANSITION, runtime_error
from cloud_edge_robot_arm.edge.runtime.task_context import TaskRuntimeContext
from cloud_edge_robot_arm.errors import StructuredError

LEGAL_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.VALIDATING},
    TaskState.VALIDATING: {TaskState.READY, TaskState.FAILED},
    TaskState.READY: {TaskState.EXECUTING, TaskState.PAUSED},
    TaskState.EXECUTING: {
        TaskState.LOCAL_RECOVERY,
        TaskState.WAITING_CLOUD_UPDATE,
        TaskState.PAUSED,
        TaskState.SAFETY_STOPPED,
        TaskState.FAILED,
        TaskState.COMPLETED,
    },
    TaskState.LOCAL_RECOVERY: {
        TaskState.EXECUTING,
        TaskState.FAILED,
        TaskState.SAFETY_STOPPED,
    },
    TaskState.WAITING_CLOUD_UPDATE: {TaskState.READY, TaskState.PAUSED, TaskState.FAILED},
    TaskState.PAUSED: {TaskState.EXECUTING, TaskState.SAFETY_STOPPED, TaskState.FAILED},
    TaskState.SAFETY_STOPPED: set(),
    TaskState.FAILED: set(),
    TaskState.COMPLETED: set(),
}


@dataclass(frozen=True)
class StateTransitionResult:
    success: bool
    from_state: TaskState
    to_state: TaskState
    error: StructuredError | None = None


class TaskStateMachine:
    def transition(
        self,
        context: TaskRuntimeContext,
        to_state: TaskState,
        *,
        reason: str,
        at: datetime | None = None,
    ) -> StateTransitionResult:
        from_state = context.state
        if to_state not in LEGAL_TRANSITIONS.get(from_state, set()):
            error = runtime_error(
                INVALID_STATE_TRANSITION,
                f"cannot transition task from {from_state.value} to {to_state.value}",
                details={
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "reason": reason,
                },
            )
            context.set_error(error)
            return StateTransitionResult(
                success=False,
                from_state=from_state,
                to_state=to_state,
                error=error,
            )

        context.apply_transition(to_state, at=at or datetime.now(UTC))
        return StateTransitionResult(
            success=True,
            from_state=from_state,
            to_state=to_state,
            error=None,
        )
