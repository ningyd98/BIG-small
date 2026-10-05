"""Initial source/budget software tests; no real capture, request or authority."""

from dataclasses import asdict, replace
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
        "bootstrap-job",
        "bootstrap-run",
        "bootstrap-worker",
        "bootstrap-lease",
        1,
        now - timedelta(seconds=2),
        now,
        now + timedelta(seconds=60),
        "1" * 64,
        "2" * 64,
        "3" * 64,
    )
    definition = api().VisualBootstrapDefinition(
        lease=lease,
        episode_id="bootstrap-episode",
        user_instruction="move the visible box",
        task_started_at=now - timedelta(seconds=1),
        task_timeout_s=120.0,
        verification_limits=VerificationBudget(2, 0, 3, 100.0),
        role_bundle_hash="4" * 64,
        model_snapshot_hash="5" * 64,
        source_hashes={"source.py": "6" * 64},
        registered_at=now,
    )
    return lease, definition, now


def transition(source, record, kind, *, now=None, **kwargs):
    lease, _, clock = source
    request = api().VisualBootstrapTransitionInput(
        record=record,
        kind=kind,
        event_key=kwargs.pop("event_key", f"event-{record.revision}-{kind}"),
        current_lease=lease,
        robot_state=kwargs.pop("robot_state", RobotState(connected=True)),
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
    data.update(
        frame_id=frame_id,
        observation_id=frame_id,
        episode_id="bootstrap-episode",
        captured_at=at or now,
        checksum_sha256="",
    )
    return base.model_validate(data)


def captured(source):
    record = api().VisualBootstrapRecord.start(source[1])
    first, _ = transition(source, record, "RESERVE_INITIAL_CAPTURE")
    observation = frame(source)
    second, _ = transition(
        source,
        first.record,
        "COMPLETE_CAPTURE",
        claim_id=first.record.pending_claim_id,
        observation=observation,
    )
    return second.record, observation


def planned(source, *, usable):
    record, observation = captured(source)
    claim, _ = transition(source, record, "RESERVE_PLAN")
    draft = PlannerDraft(
        raw_text='{"diagnostic":"software-only"}',
        parsed_json={
            **values()["original"].contract.model_dump(mode="json"),
            "user_instruction": source[1].user_instruction,
        }
        if usable
        else {"_sentinel": "REQUEST_MORE_OBSERVATION"},
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": "5" * 64,
            "role_bundle_hash": "4" * 64,
        },
    )
    complete, request = transition(
        source, claim.record, "COMPLETE_PLAN", claim_id=claim.record.pending_claim_id, draft=draft
    )
    return complete.record, request


def test_initial_deadlines_are_from_task_start_not_registration(source):
    record = api().VisualBootstrapRecord.start(source[1])
    assert record.verification_state.deadline_at == source[1].task_started_at + timedelta(
        seconds=100
    )
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
        observation = observation.model_copy(
            update={"captured_at": source[2] - timedelta(seconds=1)}
        )
    else:
        observation = observation.model_copy(update={"checksum_sha256": "a" * 64})
    with pytest.raises(ValueError):
        transition(
            source,
            claim.record,
            "COMPLETE_CAPTURE",
            claim_id=claim.record.pending_claim_id,
            observation=observation,
        )


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
    state = RobotState(
        connected=fault != "disconnected",
        estop_engaged=fault == "estop",
        collision_detected=fault == "collision",
    )
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


def promotion_sources(source, *, spent=False):
    from cloud_edge_robot_arm.vision.worker_owner import REQUIRED_COMPILER_SOURCES

    lease, definition, now = source
    definition = replace(
        definition,
        source_hashes={
            name: "6" * 64 for name in (*REQUIRED_COMPILER_SOURCES, api().BOOTSTRAP_SOURCE_PATH)
        },
    )
    source = lease, definition, now
    record, _ = planned(source, usable=not spent)
    if spent:
        for index in range(2):
            clock = now + timedelta(milliseconds=index + 1)
            current = lease, definition, clock
            claim, _ = transition(current, record, "RESERVE_REOBSERVATION")
            captured_result, _ = transition(
                current,
                claim.record,
                "COMPLETE_CAPTURE",
                claim_id=claim.record.pending_claim_id,
                observation=frame(current, frame_id=f"promotion-frame-{index}", at=clock),
            )
            plan_claim, _ = transition(current, captured_result.record, "RESERVE_PLAN")
            observation = captured_result.record.observation
            draft = PlannerDraft(
                raw_text="new SOFTWARE_ONLY proposal",
                parsed_json={
                    **values()["original"].contract.model_dump(mode="json"),
                    "user_instruction": definition.user_instruction,
                }
                if index == 1
                else {"_sentinel": "REQUEST_MORE_OBSERVATION"},
                observation_evidence={
                    **observation.evidence(),
                    "model_snapshot_hash": definition.model_snapshot_hash,
                    "role_bundle_hash": definition.role_bundle_hash,
                },
            )
            completed, _ = transition(
                current,
                plan_claim.record,
                "COMPLETE_PLAN",
                claim_id=plan_claim.record.pending_claim_id,
                draft=draft,
            )
            record, source = completed.record, current
    original = api().compile_bootstrap_original_plan(
        record,
        current_lease=lease,
        plan_id="bootstrap-plan",
        robot_id="bootstrap-robot",
        registered_at=source[2],
    )
    retry = api().bootstrap_retry_budget(record, original, created_at=source[2])
    request = api().VisualBootstrapPromotionInput(
        record=record,
        original=original,
        event_key="promote-original",
        current_lease=lease,
        robot_state=RobotState(connected=True),
    )
    return source, record, original, retry, request


def test_bootstrap_compiler_binds_full_original_and_camera_source(source):
    current, record, original, retry, _ = promotion_sources(source)
    contract = api().bootstrap_contract(record, issued_at=current[2])
    assert original.contract == contract
    assert original.proposal_hash == api().bootstrap_proposal_hash(record.draft.parsed_json)
    assert original.task_deadline_at == record.task_deadline_at
    assert original.verification_deadline_at == record.verification_state.deadline_at
    assert retry.remaining_retries == record.verification_state.remaining_retries
    for requirement in original.requirements.values():
        assert requirement.expected_duration_s >= requirement.original_step.timeout_ms / 1000
        assert requirement.allowed_error_m == 0.01
        assert requirement.sensor_requirements == ("rgbd",)
        assert requirement.ordinary_ttl_s == 5
        for condition in (*requirement.preconditions, *requirement.postconditions):
            assert (
                condition.tolerances["camera_source_descriptor_sha256"]
                == (record.to_payload()["camera_descriptor_hash"])
            )
    assert original.contract.safety_constraints == values()["original"].contract.safety_constraints


def test_promotion_preserves_entire_spent_state_and_replays_strict_history(source):
    current, record, original, retry, request = promotion_sources(source, spent=True)
    before = asdict(record.verification_state)
    assert before["remaining_reobservations"] == 0
    assert before["verification_rounds"] == 2 and before["consecutive_no_progress"] == 1
    promoted = api().promote_bootstrap(
        record, request, record.verification_state, retry, now=current[2]
    )
    assert asdict(promoted.verification_state) == before
    assert promoted.terminal_reason == "original_adopted"
    assert promoted.to_payload()["adopted_original_hash"] == original.digest()
    assert api().VisualBootstrapRecord.from_json(promoted.to_json()).digest() == promoted.digest()
    assert not hasattr(promoted, "execution_permission")
    # An exact historical call is idempotent and creates no new effect claim.
    assert (
        api()
        .promote_bootstrap(promoted, request, record.verification_state, retry, now=current[2])
        .digest()
        == promoted.digest()
    )


@pytest.mark.parametrize("change", ["quota", "rounds", "history", "deadline", "limits", "retry"])
def test_promotion_rejects_any_reset_or_changed_original_pool(source, change):
    current, record, _, retry, request = promotion_sources(source, spent=True)
    state = record.verification_state
    if change == "quota":
        state.remaining_reobservations = state.limits.max_reobservations
    elif change == "rounds":
        state.verification_rounds = 0
    elif change == "history":
        state.previous_conditions.clear()
    elif change == "deadline":
        state.deadline_at += timedelta(seconds=1)
    elif change == "limits":
        state.limits = VerificationBudget(3, 0, 3, 100)
    else:
        retry = retry.model_copy(
            update={"retry_deadline": retry.retry_deadline + timedelta(seconds=1)}
        )
    with pytest.raises(ValueError):
        api().promote_bootstrap(record, request, state, retry, now=current[2])


@pytest.mark.parametrize("fault", ["lease", "hard_stop", "deadline", "original"])
def test_promotion_rechecks_current_source_and_complete_semantic_original(source, fault):
    current, record, original, retry, request = promotion_sources(source)
    now = current[2]
    lease, robot = current[0], RobotState(connected=True)
    if fault == "lease":
        lease = replace(lease, lease_id="new-lease")
    elif fault == "hard_stop":
        robot = RobotState(connected=True, estop_engaged=True)
    elif fault == "deadline":
        now = record.verification_state.deadline_at
    else:
        from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan

        original = freeze_original_visual_plan(
            **{**original.freeze_inputs(), "proposal_hash": "f" * 64}
        )
    changed = api().VisualBootstrapPromotionInput(
        record=record,
        original=original,
        event_key="promote-changed",
        current_lease=lease,
        robot_state=robot,
    )
    with pytest.raises(ValueError):
        api().promote_bootstrap(record, changed, record.verification_state, retry, now=now)


def test_promotion_record_rejects_coherently_rehashed_state_reset(source):
    current, record, _, retry, request = promotion_sources(source, spent=True)
    promoted = api().promote_bootstrap(
        record, request, record.verification_state, retry, now=current[2]
    )
    raw = promoted.to_payload()
    raw["state"]["remaining_reobservations"] = 2
    with pytest.raises(ValueError):
        api().VisualBootstrapRecord.from_payload(raw)


def complete_proposal(source, proposal):
    record, observation = captured(source)
    claim, _ = transition(source, record, "RESERVE_PLAN")
    draft = PlannerDraft(
        raw_text="SOFTWARE_ONLY semantic proposal",
        parsed_json=proposal,
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": source[1].model_snapshot_hash,
            "role_bundle_hash": source[1].role_bundle_hash,
        },
    )
    result, _ = transition(
        source,
        claim.record,
        "COMPLETE_PLAN",
        claim_id=claim.record.pending_claim_id,
        draft=draft,
    )
    return result.record


@pytest.mark.parametrize(
    "key,value",
    [
        ("plan_version", True),
        ("command_seq", "0"),
        ("task_id", ["placeholder"]),
        ("issued_at", "not-a-clock"),
        ("timestamp", False),
    ],
)
def test_identity_filling_cannot_hide_malformed_original_proposal(source, key, value):
    proposal = {
        **values()["original"].contract.model_dump(mode="json"),
        "user_instruction": source[1].user_instruction,
        key: value,
    }
    record = complete_proposal(source, proposal)
    assert not record.planning_source_usable
    assert record.proposal_hash is None


def test_bootstrap_preserves_home_and_original_safety_then_compiler_rejects(source):
    from cloud_edge_robot_arm.contracts import SkillName
    from cloud_edge_robot_arm.vision.worker_owner import REQUIRED_COMPILER_SOURCES

    definition = replace(
        source[1],
        source_hashes={
            path: "6" * 64 for path in (*REQUIRED_COMPILER_SOURCES, api().BOOTSTRAP_SOURCE_PATH)
        },
    )
    source = source[0], definition, source[2]
    contract = values()["original"].contract
    proposal = contract.model_dump(mode="json")
    proposal["user_instruction"] = definition.user_instruction
    home = contract.steps[-1].model_copy(update={"skill": SkillName.HOME, "step_id": "home"})
    proposal["steps"].append(home.model_dump(mode="json"))
    record = complete_proposal(source, proposal)
    preserved = api().bootstrap_contract(record, issued_at=source[2])
    assert preserved.steps[-1].skill == SkillName.HOME
    assert preserved.safety_constraints == contract.safety_constraints
    with pytest.raises(ValueError, match="unsupported visual skill"):
        api().compile_bootstrap_original_plan(
            record,
            current_lease=source[0],
            plan_id="plan",
            robot_id="robot",
            registered_at=source[2],
        )


def test_promotion_event_key_cannot_reuse_a_capture_or_planning_event(source):
    current, record, original, retry, _ = promotion_sources(source)
    request = api().VisualBootstrapPromotionInput(
        record=record,
        original=original,
        event_key=record.to_payload()["history"][0]["request"]["event_key"],
        current_lease=current[0],
        robot_state=RobotState(connected=True),
    )
    with pytest.raises(ValueError, match="event key"):
        api().promote_bootstrap(record, request, record.verification_state, retry, now=current[2])
