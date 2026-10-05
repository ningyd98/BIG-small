"""The composition seam never turns software or missing admission into dispatch."""

from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.auto_mode.judgment import JudgmentResult
from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction, DecisionEvent
from cloud_edge_robot_arm.contracts import AutoModeStatus, ControlMode
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec, ConditionStatus
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.research.network import NetworkCostSnapshot
from tests.test_joint_visual_policy import policy
from tests.test_visual_repair_builder import NOW, fixture


def api():
    return import_module("cloud_edge_robot_arm.auto_mode.runtime_composition")


def snapshot(**changes):
    from cloud_edge_robot_arm.vision.action_evidence import native_action_contract

    _, repair, _, _ = fixture()
    online, contract = repair.online_evidence, repair.active_contract
    action = native_action_contract(online, contract, contract.steps[1])
    values = dict(
        active_contract=contract,
        checkpoint=repair.checkpoint.model_copy(
            update={
                "pending_step_ids": ["grasp", "telemetry"],
                "current_step_index": 1,
                "current_step_id": "grasp",
            },
            deep=True,
        ),
        mode_status=AutoModeStatus(
            task_id=contract.task_id,
            current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
            mode_version=1,
        ),
        online_evidence=online,
        verification_budget=VerificationBudgetState.start(VerificationBudget(2, 2, 5, 60), now=NOW),
        capabilities=set(DecisionAction),
        network_cost=NetworkCostSnapshot(
            observed_rtt_s=None,
            observed_loss_rate=None,
            observed_bandwidth_bytes_s=None,
            sampled_at=NOW,
        ),
        condition_specs=(ConditionSpec("target_visible", contract.task_target.object_id),),
        action_contracts={DecisionAction.CONTINUE: action, DecisionAction.REQUEST_CLOUD: action},
    )
    return api().RuntimeCompositionSnapshot(**{**values, **changes})


def event(snap):
    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionEventKind

    return DecisionEvent(
        "composition-event",
        DecisionEventKind.SKILL_BOUNDARY,
        NOW + timedelta(seconds=0.2),
        snap.online_evidence.observation.observation_id,
        snap.atomic_action_active,
        ConditionStatus.PASS,
    )


def software_adapter(snap, *, clock=lambda: NOW + timedelta(seconds=0.2), source_validator=None):
    class AbstainingSoftwareJudge:
        is_model = False

        def choose(self, context, candidates, estimates):
            return JudgmentResult(None, {}, None, None, "ABSTAIN", "software-abstain", 0.0)

    selected = policy(clock=clock, judge=AbstainingSoftwareJudge())
    selected.contract_provider = lambda ctx: snap.action_contracts
    adapter = api().RuntimeCompositionAdapter(
        lambda: snap,
        policy=selected,
        clock=clock,
        source_validator=source_validator,
        software_only=True,
    )
    return adapter, selected


def test_default_actual_composition_cannot_enable_from_source_validation():
    snap = snapshot()
    selected = policy(software_only=False, clock=lambda: NOW + timedelta(seconds=0.2))
    adapter = api().RuntimeCompositionAdapter(
        lambda: snap,
        policy=selected,
        source_validator=lambda: None,
        clock=lambda: NOW + timedelta(seconds=0.2),
    )
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert result.scope == "NOT_ADMITTED"
    assert "actual_admission_verifier_unavailable" in result.reasons
    assert result.context.risk_estimate.status == "UNKNOWN"
    assert result.context.risk_estimate.failure_probability is None
    assert snap.verification_budget.remaining_reobservations == 2


def test_current_native_unknown_bounds_mask_continue_and_recovery():
    snap = snapshot()
    result = (
        api()
        .RuntimeCompositionAdapter(lambda: snap, clock=lambda: NOW + timedelta(seconds=0.2))
        .evaluate(event(snap))
    )
    rows = {row.action: row for row in result.candidates.candidates}
    assert rows[DecisionAction.STOP].executable
    assert not rows[DecisionAction.CONTINUE].executable
    assert not rows[DecisionAction.LOCAL_RECOVER].executable
    assert result.context.evidence_verdict.status == "UNKNOWN"


@pytest.mark.parametrize(
    "field",
    ["contract_version", "checkpoint_version", "online_sequence", "mode_task", "frame", "atomic"],
)
def test_incoherent_authoritative_snapshot_fails_closed(field):
    snap = snapshot()
    supplied_event = event(snap)
    if field == "contract_version":
        snap = replace(
            snap, active_contract=snap.active_contract.model_copy(update={"plan_version": 2})
        )
    elif field == "checkpoint_version":
        snap = replace(snap, checkpoint=snap.checkpoint.model_copy(update={"command_seq": 2}))
    elif field == "online_sequence":
        snap = replace(snap, online_evidence=replace(snap.online_evidence, command_seq=2))
    elif field == "mode_task":
        snap = replace(snap, mode_status=snap.mode_status.model_copy(update={"task_id": "other"}))
    elif field == "frame":
        supplied_event = replace(supplied_event, observation_id="other")
    else:
        snap = replace(snap, atomic_action_active=True)
    result = (
        api()
        .RuntimeCompositionAdapter(lambda: snap, clock=lambda: NOW + timedelta(seconds=0.2))
        .evaluate(supplied_event)
    )
    assert result.action == DecisionAction.STOP
    assert "snapshot_identity_invalid" in result.reasons


def test_canonical_unknown_overrides_event_caller_pass():
    snap = snapshot()
    online = replace(snap.online_evidence, visual_facts={})
    snap = replace(snap, online_evidence=online)
    ctx = api().compose_decision_context(snap, event(snap), NOW + timedelta(seconds=0.2))
    assert ctx.event.verification_status == ConditionStatus.UNKNOWN
    assert ctx.condition_verdicts[0].status == ConditionStatus.UNKNOWN


@pytest.mark.parametrize(
    "field,value", [("estop_engaged", True), ("collision_detected", True), ("connected", False)]
)
def test_hard_state_skips_policy_and_source_callbacks(field, value):
    snap = snapshot()
    snap = replace(
        snap,
        online_evidence=replace(
            snap.online_evidence,
            robot_state=snap.online_evidence.robot_state.model_copy(update={field: value}),
        ),
    )

    def forbidden():
        raise AssertionError("hard stop must precede source/provider callbacks")

    adapter, selected = software_adapter(snap, source_validator=forbidden)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert selected.last_trace is None
    assert snap.verification_budget.remaining_reobservations == 2


def test_software_math_is_explicit_and_never_submittable():
    snap = snapshot()
    selected = policy()
    with pytest.raises(ValueError):
        api().RuntimeCompositionAdapter(lambda: snap, policy=selected)
    adapter, _ = software_adapter(snap)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.REOBSERVE
    assert result.scope == "SOFTWARE_ONLY"
    assert result.trace.envelope.valid_until == result.trace.envelope.created_at
    assert snap.verification_budget.remaining_reobservations == 2
    verdict = adapter.validate_for_existing_submission(result)
    assert verdict.status != "VALID"
    assert "software_diagnostic_never_submit" in verdict.reasons


def test_duplicate_event_returns_one_software_trace_without_second_reservation():
    snap = snapshot()
    adapter, selected = software_adapter(snap)
    first = adapter.evaluate(event(snap))
    first.context.verification_budget.remaining_reobservations = 0
    again = adapter.evaluate(event(snap))
    assert again.action == DecisionAction.REOBSERVE
    assert len(selected.traces) == 1
    assert again.context.verification_budget.remaining_reobservations == 2
    assert snap.verification_budget.remaining_reobservations == 2


def test_snapshot_values_are_isolated_from_result_and_provider():
    snap = snapshot()
    adapter, selected = software_adapter(snap)

    def mutating(ctx):
        ctx.verification_budget.remaining_reobservations = 99
        ctx.online_evidence.robot_state.estop_engaged = True
        ctx.online_evidence.observation.__dict__["calibration_version"] = "provider-mutated"
        return DecisionAction.REOBSERVE

    selected.decide = mutating
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "policy_mutated_bound_context" in result.reasons
    assert snap.verification_budget.remaining_reobservations == 2
    assert not snap.online_evidence.robot_state.estop_engaged
    assert snap.online_evidence.observation.calibration_version == "cal-1"


@pytest.mark.parametrize("return_value", [True, False, "VALID"])
def test_flag_source_callback_cannot_be_treated_as_verified_binding(return_value):
    snap = snapshot()
    adapter, selected = software_adapter(snap, source_validator=lambda: return_value)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert result.source_verdict.status != "VALID"
    assert selected.last_trace is None


def test_source_drift_stops_without_calling_policy_or_charging():
    snap = snapshot()

    def drift():
        raise ValueError("actual source bytes changed")

    adapter, selected = software_adapter(snap, source_validator=drift)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "source_binding_unavailable" in result.reasons
    assert selected.last_trace is None
    assert snap.verification_budget.remaining_reobservations == 2


def test_late_source_ack_cannot_publish_capture_request():
    snap = snapshot()
    clock = [NOW + timedelta(seconds=0.2)]

    def delayed():
        clock[0] = NOW + timedelta(seconds=61)

    adapter, selected = software_adapter(snap, source_validator=delayed, clock=lambda: clock[0])
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "absolute_verification_deadline_expired" in result.reasons
    assert selected.last_trace is None
    assert snap.verification_budget.remaining_reobservations == 2


def test_fresh_authoritative_state_after_callback_rejects_new_cancel():
    initial = snapshot()
    current = [initial]
    selected = policy(clock=lambda: NOW + timedelta(seconds=0.2))
    selected.contract_provider = lambda ctx: initial.action_contracts

    def changed():
        current[0] = replace(initial, cancelled=True)

    adapter = api().RuntimeCompositionAdapter(
        lambda: current[0],
        policy=selected,
        source_validator=changed,
        clock=lambda: NOW + timedelta(seconds=0.2),
        software_only=True,
    )
    result = adapter.evaluate(event(initial))
    assert result.action == DecisionAction.STOP
    assert selected.last_trace is None
    assert initial.verification_budget.remaining_reobservations == 2


def test_forged_future_envelope_and_policy_identity_never_grant_admission():
    snap = snapshot()
    adapter, _ = software_adapter(snap)
    result = adapter.evaluate(event(snap))
    changed_envelope = replace(
        result.trace.envelope,
        valid_until=NOW + timedelta(seconds=50),
        policy_version="accepted-looking-hash",
    )
    forged = replace(
        result,
        scope="NOT_ADMITTED",
        trace=replace(result.trace, envelope=changed_envelope, software_only=False),
    )
    assert adapter.validate_for_existing_submission(forged).status != "VALID"


def actual_guard_and_forged_result(snap):
    software, _ = software_adapter(snap)
    result = software.evaluate(event(snap))
    envelope = replace(result.trace.envelope, valid_until=NOW + timedelta(seconds=50))
    forged = replace(
        result,
        scope="NOT_ADMITTED",
        trace=replace(result.trace, envelope=envelope, software_only=False),
    )
    guard = api().RuntimeCompositionAdapter(
        lambda: snap, source_validator=lambda: None, clock=lambda: NOW + timedelta(seconds=0.2)
    )
    return guard, forged


def test_actual_guard_cannot_admit_forged_scope_hash_or_future_expiry():
    guard, forged = actual_guard_and_forged_result(snapshot())
    verdict = guard.validate_for_existing_submission(forged)
    assert verdict.status == "UNKNOWN"
    assert "actual_admission_verifier_unavailable" in verdict.reasons


def test_submission_guard_reads_current_mode_and_cancel_instead_of_saved_result():
    initial = snapshot()
    guard, forged = actual_guard_and_forged_result(initial)
    current = [
        replace(initial, mode_status=initial.mode_status.model_copy(update={"mode_version": 2}))
    ]
    guard.snapshot_reader = lambda: current[0]
    assert guard.validate_for_existing_submission(forged).status == "INVALID"
    current[0] = replace(initial, cancelled=True)
    assert "episode_cancelled" in guard.validate_for_existing_submission(forged).reasons


def test_late_exception_reports_fresh_absolute_deadline_without_quota_charge():
    snap = snapshot()
    clock = [NOW + timedelta(seconds=0.2)]
    adapter, selected = software_adapter(snap, clock=lambda: clock[0])

    def late_failure(ctx):
        clock[0] = NOW + timedelta(seconds=61)
        raise TimeoutError("late software callback")

    selected.decide = late_failure
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert result.evaluated_at == NOW + timedelta(seconds=61)
    assert "absolute_verification_deadline_expired" in result.reasons
    assert snap.verification_budget.remaining_reobservations == 2


def test_late_snapshot_exception_does_not_report_the_old_callback_timestamp():
    snap = snapshot()
    clock = [NOW + timedelta(seconds=0.2)]

    def late_read():
        clock[0] = NOW + timedelta(seconds=61)
        raise OSError("late reader unavailable")

    result = (
        api().RuntimeCompositionAdapter(late_read, clock=lambda: clock[0]).evaluate(event(snap))
    )
    assert result.action == DecisionAction.STOP and result.context is None
    assert result.evaluated_at == NOW + timedelta(seconds=61)


def test_late_source_error_observes_deadline_and_never_calls_policy():
    snap = snapshot()
    clock = [NOW + timedelta(seconds=0.2)]

    def late_source():
        clock[0] = NOW + timedelta(seconds=61)
        raise ValueError("late source drift")

    adapter, selected = software_adapter(snap, clock=lambda: clock[0], source_validator=late_source)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert result.evaluated_at == NOW + timedelta(seconds=61)
    assert selected.last_trace is None


def test_expired_task_contract_stops_even_when_verification_deadline_is_later():
    snap = snapshot()
    snap = replace(
        snap,
        active_contract=snap.active_contract.model_copy(
            update={"valid_until": NOW + timedelta(seconds=0.15)}
        ),
    )
    adapter, selected = software_adapter(snap)
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "active_contract_expired" in result.reasons
    assert selected.last_trace is None
    assert snap.verification_budget.remaining_reobservations == 2


@pytest.mark.parametrize("field", ["timestamp", "valid_until"])
def test_naive_contract_time_fails_closed_without_ordinary_choice(field):
    snap = snapshot()
    snap.active_contract.__dict__[field] = getattr(snap.active_contract, field).replace(tzinfo=None)
    result = (
        api()
        .RuntimeCompositionAdapter(lambda: snap, clock=lambda: NOW + timedelta(seconds=0.2))
        .evaluate(event(snap))
    )
    assert result.action == DecisionAction.STOP
    assert "snapshot_identity_invalid" in result.reasons


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan_version", 9),
        ("command_seq", 9),
        ("mode_version", 9),
        ("observation_id", "stale"),
        ("context_hash", "another-context"),
    ],
)
def test_policy_trace_must_bind_every_current_envelope_field(field, value):
    snap = snapshot()
    adapter, selected = software_adapter(snap)
    actual_decide = selected.decide

    def changed(ctx):
        action = actual_decide(ctx)
        selected.last_trace = replace(
            selected.last_trace, envelope=replace(selected.last_trace.envelope, **{field: value})
        )
        return action

    selected.decide = changed
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "policy_trace_binding_invalid" in result.reasons


def test_trace_source_and_frame_metadata_cannot_be_substituted():
    snap = snapshot()
    adapter, selected = software_adapter(snap)
    actual_decide = selected.decide

    def changed(ctx):
        action = actual_decide(ctx)
        selected.last_trace = replace(
            selected.last_trace,
            observation_checksum="f" * 64,
            source_hashes={"different-source": "a" * 64},
        )
        return action

    selected.decide = changed
    result = adapter.evaluate(event(snap))
    assert result.action == DecisionAction.STOP
    assert "policy_trace_binding_invalid" in result.reasons


def test_reader_failure_returns_stop_without_invented_context():
    def missing():
        raise OSError("no active repository record")

    result = (
        api()
        .RuntimeCompositionAdapter(missing, clock=lambda: NOW + timedelta(seconds=0.2))
        .evaluate(event(snapshot()))
    )
    assert result.action == DecisionAction.STOP
    assert result.context is None
