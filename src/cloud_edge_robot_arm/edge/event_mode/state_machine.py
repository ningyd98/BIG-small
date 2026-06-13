"""Event-triggered mode state machine.

Manages all legal state transitions for Phase 6 event-triggered edge autonomy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventModeState(StrEnum):
    """States for the event-triggered edge autonomy controller."""

    IDLE = "IDLE"
    EXECUTING_AUTONOMOUSLY = "EXECUTING_AUTONOMOUSLY"
    EVENT_DETECTED = "EVENT_DETECTED"
    EVALUATING_LOCAL_RECOVERY = "EVALUATING_LOCAL_RECOVERY"
    LOCAL_RECOVERY_RUNNING = "LOCAL_RECOVERY_RUNNING"
    WAITING_FOR_NEW_OBSERVATION = "WAITING_FOR_NEW_OBSERVATION"
    PREPARING_REPLAN_REQUEST = "PREPARING_REPLAN_REQUEST"
    WAITING_CLOUD_REPLAN = "WAITING_CLOUD_REPLAN"
    VALIDATING_REPLAN = "VALIDATING_REPLAN"
    RESUMING = "RESUMING"
    PAUSED = "PAUSED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


# Legal transitions for EventModeState machine
LEGAL_EVENT_MODE_TRANSITIONS: dict[EventModeState, set[EventModeState]] = {
    EventModeState.IDLE: {EventModeState.EXECUTING_AUTONOMOUSLY},
    EventModeState.EXECUTING_AUTONOMOUSLY: {
        EventModeState.EVENT_DETECTED,
        EventModeState.COMPLETED,
        EventModeState.SAFETY_STOPPED,
        EventModeState.PAUSED,
        EventModeState.FAILED,
    },
    EventModeState.EVENT_DETECTED: {
        EventModeState.EVALUATING_LOCAL_RECOVERY,
        EventModeState.SAFETY_STOPPED,
    },
    EventModeState.EVALUATING_LOCAL_RECOVERY: {
        EventModeState.LOCAL_RECOVERY_RUNNING,
        EventModeState.PREPARING_REPLAN_REQUEST,
        EventModeState.WAITING_FOR_NEW_OBSERVATION,
        EventModeState.PAUSED,
        EventModeState.FAILED,
        EventModeState.SAFETY_STOPPED,
    },
    EventModeState.LOCAL_RECOVERY_RUNNING: {
        EventModeState.EXECUTING_AUTONOMOUSLY,
        EventModeState.EVENT_DETECTED,
        EventModeState.FAILED,
    },
    EventModeState.WAITING_FOR_NEW_OBSERVATION: {
        EventModeState.EXECUTING_AUTONOMOUSLY,
        EventModeState.PREPARING_REPLAN_REQUEST,
        EventModeState.PAUSED,
        EventModeState.FAILED,
    },
    EventModeState.PREPARING_REPLAN_REQUEST: {
        EventModeState.WAITING_CLOUD_REPLAN,
        EventModeState.FAILED,
    },
    EventModeState.WAITING_CLOUD_REPLAN: {
        EventModeState.VALIDATING_REPLAN,
        EventModeState.PAUSED,
        EventModeState.FAILED,
    },
    EventModeState.VALIDATING_REPLAN: {
        EventModeState.RESUMING,
        EventModeState.PAUSED,
        EventModeState.FAILED,
    },
    EventModeState.RESUMING: {
        EventModeState.EXECUTING_AUTONOMOUSLY,
        EventModeState.FAILED,
    },
    EventModeState.PAUSED: {
        EventModeState.EXECUTING_AUTONOMOUSLY,
        EventModeState.SAFETY_STOPPED,
        EventModeState.FAILED,
    },
    EventModeState.SAFETY_STOPPED: set(),  # Terminal
    EventModeState.FAILED: set(),  # Terminal
    EventModeState.COMPLETED: set(),  # Terminal
}


@dataclass(frozen=True)
class EventModeStateTransition:
    """Record of a state transition."""

    task_id: str
    from_state: EventModeState
    to_state: EventModeState
    reason: str
    event_id: str = ""


class EventModeStateMachine:
    """State machine for event-triggered mode controller.

    Enforces legal transitions. Prevents:
    - COMPLETED → anything
    - SAFETY_STOPPED → automatic recovery
    - Starting new steps while waiting for cloud
    - Simultaneous local recovery and cloud replanning
    """

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id
        self._state: EventModeState = EventModeState.IDLE
        self._history: list[EventModeStateTransition] = []

    @property
    def current_state(self) -> EventModeState:
        return self._state

    @property
    def history(self) -> list[EventModeStateTransition]:
        return list(self._history)

    def transition(
        self,
        to_state: EventModeState,
        reason: str = "",
        event_id: str = "",
    ) -> bool:
        """Attempt a state transition. Returns True if legal and performed."""
        if not self._is_legal(self._state, to_state):
            return False

        transition = EventModeStateTransition(
            task_id=self._task_id,
            from_state=self._state,
            to_state=to_state,
            reason=reason,
            event_id=event_id,
        )
        self._history.append(transition)
        self._state = to_state
        return True

    def is_terminal(self) -> bool:
        return self._state in (
            EventModeState.SAFETY_STOPPED,
            EventModeState.FAILED,
            EventModeState.COMPLETED,
        )

    @staticmethod
    def _is_legal(from_state: EventModeState, to_state: EventModeState) -> bool:
        allowed = LEGAL_EVENT_MODE_TRANSITIONS.get(from_state, set())
        return to_state in allowed
