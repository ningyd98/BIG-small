"""Completion reader regressions; software fixtures are not recovery proof."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository
from tests.test_phase6_e2e_executor import _event_contract


class ReaderFixture:
    def __init__(self, records=(), events=(), *, unavailable=False):
        self.records, self.events = list(records), list(events)
        self.unavailable = unavailable

    def list_events(self, task_id):
        return [item for item in self.events if item.task_id == task_id]

    def list_recoveries(self, task_id):
        if self.unavailable:
            raise RuntimeError("actual lifecycle reader unavailable")
        return [item for item in self.records if item.task_id == task_id]

    def list_unresolved_recoveries(self, task_id):
        return [item for item in self.list_recoveries(task_id)
                if item.state != "VERIFIED_RESOLVED"]


def evaluate(reader):
    contract = _event_contract()
    now = datetime.now(UTC)
    return CompletionEvaluator(
        repository=cast(EventAutonomyRepository, reader), clock=lambda: now,
    ).evaluate(
        contract=contract,
        completed_step_ids=[item.step_id for item in contract.steps],
        completion_criteria_results={"object_placed": True},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True, "gripper_open": True},
        final_target_state={"object_at_target": True},
        last_scene_update_at=now,
    )


def record(state, event_id="event", task_id="task-e2e-001", scope="ACTUAL_SOURCE"):
    return SimpleNamespace(recovery_id="recovery-" + event_id,
                           task_id=task_id, event_id=event_id, state=state,
                           evidence_scope=scope)


@pytest.mark.parametrize("state", ["DETECTED", "RECOVERY_AUTHORIZED", "RETRY_EXECUTED",
                                  "EXHAUSTED", "UNRECOVERABLE"])
def test_every_unresolved_recovery_blocks_completion_even_without_critical_event(state):
    result = evaluate(ReaderFixture(records=[record(state)]))
    assert not result.completed
    assert "CHECK_8_UNRESOLVED_RECOVERIES" in result.failed_checks
    assert result.evidence["unresolved_recoveries"] == ["recovery-event"]


def test_verified_resolved_reader_state_removes_only_corresponding_critical_event():
    event = SimpleNamespace(task_id="task-e2e-001", event_id="event", severity="CRITICAL")
    result = evaluate(ReaderFixture(records=[record("VERIFIED_RESOLVED")], events=[event]))
    assert result.completed
    assert result.evidence["critical_events"] == 0
    assert result.evidence["resolved_recovery_events"] == ["event"]


def test_verified_resolution_does_not_hide_another_error_recovery():
    result = evaluate(ReaderFixture(records=[record("VERIFIED_RESOLVED"),
                                             record("RETRY_EXECUTED", "other")]))
    assert not result.completed
    assert result.evidence["unresolved_recoveries"] == ["recovery-other"]


def test_critical_event_without_matching_task_resolution_stays_unresolved():
    event = SimpleNamespace(task_id="task-e2e-001", event_id="event", severity="CRITICAL")
    result = evaluate(ReaderFixture(records=[record("VERIFIED_RESOLVED", task_id="other")],
                                    events=[event]))
    assert "CHECK_8_UNRESOLVED_CRITICAL_EVENTS" in result.failed_checks


def test_configured_repository_with_unavailable_resolution_reader_fails_closed():
    result = evaluate(ReaderFixture(unavailable=True))
    assert not result.completed
    assert "CHECK_8_EVENT_STATUS_UNAVAILABLE" in result.failed_checks


@pytest.mark.parametrize("scope", ["SOFTWARE_ONLY", "UNAVAILABLE"])
def test_software_or_unavailable_resolution_never_unblocks_actual_completion(scope):
    event = SimpleNamespace(task_id="task-e2e-001", event_id="event", severity="CRITICAL")
    result = evaluate(ReaderFixture(records=[record("VERIFIED_RESOLVED", scope=scope)],
                                    events=[event]))
    assert not result.completed
    assert "CHECK_8_UNRESOLVED_RECOVERIES" in result.failed_checks
    assert "CHECK_8_UNRESOLVED_CRITICAL_EVENTS" in result.failed_checks
    assert result.evidence["resolved_recovery_events"] == []
