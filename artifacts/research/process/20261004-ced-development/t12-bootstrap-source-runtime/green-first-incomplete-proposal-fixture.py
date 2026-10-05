"""Initial source/budget software tests; no real capture, request or authority."""

from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts.models import RobotState
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
from tests.test_visual_owner_registration import values


def api():
    return import_module("cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap")


@pytest.fixture
def source():
    now = datetime.now(UTC)
    lease = WorkerLeaseObservation(
        "bootstrap-job", "bootstrap-run", "bootstrap-worker", "bootstrap-lease", 1,
        now - timedelta(seconds=2), now, now + timedelta(seconds=60),
        "1" * 64, "2" * 64, "3" * 64,
    )
    definition = api().VisualBootstrapDefinition(
        lease=lease, episode_id="bootstrap-episode", user_instruction="move the visible box",
        task_started_at=now - timedelta(seconds=1), task_timeout_s=120.0,
        verification_limits=VerificationBudget(2, 0, 3, 100.0),
        role_bundle_hash="4" * 64, model_snapshot_hash="5" * 64,
        source_hashes={"source.py": "6" * 64}, registered_at=now,
    )
    return lease, definition, now


def transition(source, record, kind, *, now=None, **kwargs):
    lease, _, clock = source
    request = api().VisualBootstrapTransitionInput(
        record=record, kind=kind, event_key=kwargs.pop("event_key", f"event-{record.revision}-{kind}"),
        current_lease=lease, robot_state=kwargs.pop("robot_state", RobotState(connected=True)),
        **kwargs,
    )
    result = api().derive_bootstrap(record, request, now=now or clock)
    assert result.record.scope == "BOOTSTRAP_SOURCE_ONLY"
    assert not hasattr(result, "execution_permission")
    return result, request


def frame(source, *, frame_id="bootstrap-frame", at=None):
    _, _, now = source
    base = values()["online"].observation
    data = base.model_dump()
    data.update(frame_id=frame_id, observation_id=frame_id, episode_id="bootstrap-episode",
                captured_at=at or now, checksum_sha256="")
    return base.model_validate(data)


def captured(source):
    record = api().VisualBootstrapRecord.start(source[1])
    first, _ = transition(source, record, "RESERVE_INITIAL_CAPTURE")
    observation = frame(source)
    second, _ = transition(source, first.record, "COMPLETE_CAPTURE",
                           claim_id=first.record.pending_claim_id, observation=observation)
    return second.record, observation


def planned(source, *, usable):
    record, observation = captured(source)
    claim, _ = transition(source, record, "RESERVE_PLAN")
    draft = PlannerDraft(
        raw_text='{"diagnostic":"software-only"}',
        parsed_json={"steps": [{"skill": "GRASP"}]} if usable else {"_sentinel": "REQUEST_MORE_OBSERVATION"},
        observation_evidence={**observation.evidence(), "model_snapshot_hash": "5" * 64,
                              "role_bundle_hash": "4" * 64},
    )
    complete, request = transition(source, claim.record, "COMPLETE_PLAN",
                                   claim_id=claim.record.pending_claim_id, draft=draft)
    return complete.record, request


def test_initial_deadlines_are_from_task_start_not_registration(source):
    record = api().VisualBootstrapRecord.start(source[1])
    assert record.verification_state.deadline_at == source[1].task_started_at + timedelta(seconds=100)
    assert record.task_deadline_at == source[1].task_started_at + timedelta(seconds=120)
    assert record.revision == 0


def test_initial_capture_claim_spent_once_before_completion(source):
    record = api().VisualBootstrapRecord.start(source[1])
    result, request = transition(source, record, "RESERVE_INITIAL_CAPTURE")
    duplicate = api().derive_bootstrap(result.record, request, now=source[2])
    assert duplicate.write_disposition == "HISTORICAL_DUPLICATE"
    assert duplicate.record.digest() == result.record.digest()
    with pytest.raises(ValueError):
        transition(source, result.record, "RESERVE_INITIAL_CAPTURE", event_key="new-uuid")
    assert result.record.verification_state.remaining_reobservations == 2


def test_completed_capture_cannot_restart_initial_capture(source):
    record, observation = captured(source)
    assert record.observation.checksum_sha256 == observation.checksum_sha256
    with pytest.raises(ValueError):
        transition(source, record, "RESERVE_INITIAL_CAPTURE", event_key="restart")


@pytest.mark.parametrize("change", ["foreign_episode", "before_claim", "checksum"])
def test_capture_completion_requires_exact_episode_clock_and_integrity(source, change):
    record = api().VisualBootstrapRecord.start(source[1])
    claim, _ = transition(source, record, "RESERVE_INITIAL_CAPTURE")
    observation = frame(source)
    if change == "foreign_episode":
        observation = observation.model_copy(update={"episode_id": "foreign"})
    elif change == "before_claim":
        observation = observation.model_copy(update={"captured_at": source[2] - timedelta(seconds=1)})
    else:
        observation = observation.model_copy(update={"checksum_sha256": "a" * 64})
    with pytest.raises(ValueError):
        transition(source, claim.record, "COMPLETE_CAPTURE",
                   claim_id=claim.record.pending_claim_id, observation=observation)


def test_pending_request_never_replayed_or_refunded_on_lost_response(source):
    record, _ = captured(source)
    claim, _ = transition(source, record, "RESERVE_PLAN")
    with pytest.raises(ValueError):
        transition(source, claim.record, "RESERVE_PLAN", event_key="lost-reply-retry")
    with pytest.raises(ValueError):
        transition(source, claim.record, "RESERVE_REOBSERVATION")
    stopped, _ = transition(source, claim.record, "STOP")
    assert stopped.record.verification_state.remaining_reobservations == 2
    assert stopped.record.terminal_reason is not None


def test_failed_plan_reobservation_consumes_original_pool(source):
    record, _ = planned(source, usable=False)
    claim, _ = transition(source, record, "RESERVE_REOBSERVATION")
    assert claim.record.verification_state.remaining_reobservations == 1
    assert claim.record.verification_state.remaining_retries == 0
    assert claim.record.verification_state.deadline_at == record.verification_state.deadline_at
    assert claim.record.verification_state.verification_rounds == 1


def test_usable_source_has_no_verdict_or_execution_authority(source):
    record, _ = planned(source, usable=True)
    assert record.planning_source_usable
    assert record.proposal_hash == api().digest(record.draft.parsed_json)
    assert not hasattr(record, "native_admitted")
    with pytest.raises(ValueError):
        transition(source, record, "RESERVE_REOBSERVATION")
    with pytest.raises(ValueError):
        transition(source, record, "RESERVE_PLAN", event_key="duplicate-frame")


@pytest.mark.parametrize("fault", ["estop", "collision", "disconnected", "deadline"])
def test_hard_stop_or_expiry_cannot_consume_capture_budget(source, fault):
    record, _ = planned(source, usable=False)
    state = RobotState(connected=fault != "disconnected", estop_engaged=fault == "estop",
                       collision_detected=fault == "collision")
    now = record.verification_state.deadline_at if fault == "deadline" else source[2]
    result, _ = transition(source, record, "RESERVE_REOBSERVATION", robot_state=state, now=now)
    assert result.record.terminal_reason is not None
    assert result.record.verification_state.remaining_reobservations == 2
    assert result.record.pending_claim_id is None


def test_record_and_definition_detach_nested_sources(source):
    record, _ = planned(source, usable=False)
    body = record.to_payload()
    body["state"]["remaining_reobservations"] = 99
    assert record.verification_state.remaining_reobservations == 2
    with pytest.raises(ValueError):
        api().VisualBootstrapRecord.from_payload(body)
    copied = record.to_payload()
    copied["state"]["remaining_reobservations"] = True
    with pytest.raises(ValueError):
        api().VisualBootstrapRecord.from_payload(copied)


def test_transaction_clock_rollback_and_stale_cas_reject(source):
    record, _ = captured(source)
    with pytest.raises(ValueError):
        transition(source, record, "RESERVE_PLAN", now=source[2] - timedelta(seconds=1))
    result, request = transition(source, record, "RESERVE_PLAN")
    request_payload = request.to_payload()
    request_payload["event_key"] = "other"
    stale = api().VisualBootstrapTransitionInput.from_payload(request_payload)
    with pytest.raises(ValueError):
        api().derive_bootstrap(result.record, stale, now=source[2])
