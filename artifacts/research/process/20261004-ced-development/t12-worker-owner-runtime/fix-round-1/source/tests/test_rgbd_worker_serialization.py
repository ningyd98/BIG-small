"""Worker publication serializes actual episode datetimes before SQLite writes."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionEvent, DecisionEventKind
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from tests.test_rgbd_lease_handoff import _cpu_visual_worker, _successful_visual_episode


def test_worker_publishes_real_event_and_budget_datetimes_as_iso(monkeypatch, tmp_path):
    recorded_at = datetime(2026, 10, 4, 1, 2, 3, tzinfo=UTC)
    budget = VerificationBudgetState.start(VerificationBudget(2, 0, 3, 120), now=recorded_at)
    event = DecisionEvent(
        "event-real-datetime",
        DecisionEventKind.RESULT_VERIFIED,
        recorded_at,
        "rgbd-observation",
        False,
        ConditionStatus.PASS,
    )
    record = {
        "layer": "ONLINE_VERIFICATION",
        "event": asdict(event),
        "budget_before": asdict(budget),
        "budget_after": asdict(budget),
        "route": "CONTINUE",
    }
    source_event_datetime = record["event"]["occurred_at"]
    outcome = replace(_successful_visual_episode(), verification_records=(record,))
    repo, job, worker = _cpu_visual_worker(
        monkeypatch,
        tmp_path,
        lambda *args: outcome,
        instruction="Move the red block to the green region.",
    )
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    assert current.status == "SUCCEEDED", current.error_message
    evidence = next(
        item.payload
        for item in repo.list_events(job.run_id)
        if item.event_type == "rgbd_episode_evidence"
    )
    result = json.loads((tmp_path / current.artifact_paths["result"]).read_text())
    assert result["task_success"] is True, result.get("error")
    for published in (evidence, result["verification_records"][0]):
        assert datetime.fromisoformat(published["event"]["occurred_at"]) == recorded_at
        for key in ("budget_before", "budget_after"):
            assert datetime.fromisoformat(published[key]["deadline_at"]) == (
                recorded_at + timedelta(seconds=120)
            )
    assert record["event"]["occurred_at"] is source_event_datetime
