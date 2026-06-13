from __future__ import annotations

import pytest

from cloud_edge_robot_arm.contracts import TaskState
from cloud_edge_robot_arm.edge.runtime.state_machine import (
    LEGAL_TRANSITIONS,
    TaskStateMachine,
)
from cloud_edge_robot_arm.edge.runtime.task_context import TaskRuntimeContext
from tests.phase2_helpers import contract


def test_all_legal_state_transitions_are_accepted() -> None:
    for source, targets in LEGAL_TRANSITIONS.items():
        for target in targets:
            context = TaskRuntimeContext.from_contract(contract(), initial_state=source)
            result = TaskStateMachine().transition(context, target, reason="test")

            assert result.success is True
            assert context.state == target
            assert result.error is None


def test_all_illegal_state_transitions_return_structured_error() -> None:
    machine = TaskStateMachine()
    all_states = {
        TaskState.CREATED,
        TaskState.VALIDATING,
        TaskState.READY,
        TaskState.EXECUTING,
        TaskState.LOCAL_RECOVERY,
        TaskState.WAITING_CLOUD_UPDATE,
        TaskState.PAUSED,
        TaskState.SAFETY_STOPPED,
        TaskState.FAILED,
        TaskState.COMPLETED,
    }

    for source in all_states:
        illegal_targets = all_states - LEGAL_TRANSITIONS.get(source, set()) - {source}
        assert illegal_targets, f"{source} should have at least one illegal transition"
        for target in illegal_targets:
            context = TaskRuntimeContext.from_contract(contract(), initial_state=source)
            result = machine.transition(context, target, reason="test")

            assert result.success is False
            assert result.error is not None
            assert result.error.code == "INVALID_STATE_TRANSITION"
            assert context.state == source


def test_task_context_cannot_bypass_state_machine_assignment() -> None:
    context = TaskRuntimeContext.from_contract(contract())

    with pytest.raises(AttributeError):
        object.__setattr__(context, "state", TaskState.COMPLETED)
