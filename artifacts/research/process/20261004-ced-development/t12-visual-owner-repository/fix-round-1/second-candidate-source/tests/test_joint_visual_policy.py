"""联合策略只生成可审计选择，不执行机器人或伪造模型请求。"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.research.cost_ledger import CostLedger, RequestCost
from cloud_edge_robot_arm.vision.risk.models import RiskEstimate, RiskModelArtifact
from tests.test_decision_judgment import contracts, prepared_context, weights
from tests.test_runtime_auto_baselines import NOW


def ledger():
    result = CostLedger()
    result.record_request(
        RequestCost(
            request_id="old-real-attempt",
            sent_at=NOW - timedelta(seconds=2),
            finished_at=NOW - timedelta(seconds=1),
            is_cloud_model=True,
            model_role="PLANNER",
            deployment="CLOUD",
            provider_location="REMOTE_SERVICE",
            provider_version="frozen",
            status="SUCCESS",
            serialized_sent_bytes=23,
            serialized_received_bytes=11,
        )
    )
    result.record_timing(inference_s=0.2, network_s=0.1, switch_s=0.05)
    return result


def policy(*, judge=None, costs=None, software_only=True, clock=lambda: NOW):
    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    risk = RiskModelArtifact("a" * 64, "missing-model.json", "missing-calibration.json", (), (), {})
    return module.JointEvidencePolicy(
        risk,
        weights(),
        costs or ledger(),
        judge=judge,
        contract_provider=contracts,
        software_only=software_only,
        clock=clock,
    )


def test_default_adaptive_path_is_closed_without_real_selection():
    chosen = policy(software_only=False)
    assert chosen.decide(prepared_context()) == DecisionAction.STOP
    assert "adaptive_not_accepted" in chosen.last_trace.reason_codes


def test_selected_decision_records_candidate_and_observation_hash():
    chosen = policy()
    assert chosen.decide(prepared_context()) == DecisionAction.CONTINUE
    trace = chosen.last_trace
    assert trace.envelope.observation_id == "fresh"
    assert trace.envelope.candidate_set_hash == trace.candidates.content_hash
    assert trace.envelope.context_hash == "ctx"
    assert trace.envelope.plan_version == 1 and trace.envelope.mode_version == 1
    assert trace.disposition == "SOFTWARE_ONLY_SELECTED"
    assert trace.envelope.valid_until == trace.envelope.created_at


def test_high_failure_risk_changes_choice_to_cloud():
    ctx = prepared_context(
        risk_estimate=RiskEstimate(
            0.9, {"CONTINUE": 0.9, "REQUEST_CLOUD": 0.01}, 0.001, 0.001, "VALID"
        )
    )
    assert policy().decide(ctx) == DecisionAction.REQUEST_CLOUD


def test_aged_or_missing_ttl_requires_new_capture():
    ctx = prepared_context()
    old = ctx.online_evidence.observation.model_copy(
        update={"captured_at": NOW - timedelta(seconds=6)}
    )
    ctx = replace(ctx, online_evidence=replace(ctx.online_evidence, observation=old))
    chosen = policy()
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert "requires_new_capture" in chosen.last_trace.reason_codes
    no_contract = policy()
    no_contract.contract_provider = None
    assert no_contract.decide(prepared_context()) == DecisionAction.REOBSERVE


def test_physical_unknown_bounds_cannot_win():
    ctx = prepared_context(risk_estimate=RiskEstimate(None, {}, None, None, "UNKNOWN"))
    chosen = policy()
    assert chosen.decide(ctx) in {
        DecisionAction.REOBSERVE,
        DecisionAction.REQUEST_CLOUD,
        DecisionAction.STOP,
    }
    assert not next(
        row
        for row in chosen.last_trace.candidates.candidates
        if row.action == DecisionAction.CONTINUE
    ).executable


def test_unsafe_hard_stop_bypasses_cheap_action_and_atomic_boundary():
    ctx = prepared_context()
    state = ctx.online_evidence.robot_state.model_copy(update={"estop_engaged": True})
    ctx = replace(
        ctx,
        online_evidence=replace(ctx.online_evidence, robot_state=state),
        event=replace(ctx.event, atomic_action_active=True),
    )
    chosen = policy()
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert chosen.last_trace.disposition == "HARD_STOP"


def test_atomic_non_safety_defer_does_not_authorize_next_action():
    ctx = prepared_context()
    ctx = replace(ctx, event=replace(ctx.event, atomic_action_active=True))
    chosen = policy()
    assert chosen.decide(ctx) == DecisionAction.CONTINUE
    assert chosen.last_trace.disposition == "DEFERRED_ATOMIC"
    assert chosen.last_trace.envelope.valid_until == chosen.last_trace.envelope.created_at


@pytest.mark.parametrize("mode", ["out_of_set", "abstain", "timeout"])
def test_bad_provider_output_routes_with_budget_and_preserves_failure(mode):
    module = import_module("cloud_edge_robot_arm.auto_mode.judgment")

    class BadJudge:
        def choose(self, context, candidates, estimates):
            if mode == "timeout":
                raise TimeoutError("provider deadline")
            return module.JudgmentResult(
                "outside" if mode == "out_of_set" else None,
                {},
                None,
                None,
                "SELECTED" if mode == "out_of_set" else "ABSTAIN",
                "fake-provider",
                1.0,
            )

    ctx = prepared_context()
    chosen = policy(judge=BadJudge())
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.verification_budget.remaining_reobservations == 1
    assert chosen.last_trace.judgment.provider_version == "fake-provider" or mode == "timeout"
    assert chosen.last_trace.disposition == "FALLBACK_REOBSERVE"
    assert "requires_new_capture" in chosen.last_trace.reason_codes
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.verification_budget.remaining_reobservations == 1


def test_exhausted_budget_stops_instead_of_silent_fallback():
    ctx = prepared_context()
    ctx.verification_budget.remaining_reobservations = 0
    chosen = policy()
    chosen.contract_provider = None
    assert chosen.decide(ctx) == DecisionAction.STOP


def test_policy_reads_live_ledger_and_does_not_count_rules_as_model_calls():
    costs = ledger()
    chosen = policy(costs=costs)
    ctx = prepared_context(
        risk_estimate=RiskEstimate(
            0.09, {"CONTINUE": 0.09, "REQUEST_CLOUD": 0.01}, 0.001, 0.001, "VALID"
        )
    )
    assert chosen.decide(ctx) == DecisionAction.REQUEST_CLOUD
    costs.record_timing(network_s=5)
    changed = replace(ctx, event=replace(ctx.event, event_id="second"))
    assert chosen.decide(changed) == DecisionAction.CONTINUE
    assert costs.snapshot().model_requests == 1 and costs.snapshot().application_bytes == 34
    assert chosen.last_trace.judgment.candidate_probabilities is None


def test_unknown_inference_cost_stays_null_without_rtt_substitution():
    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot

    rows = module.estimate_action_costs(
        prepared_context(), CostSnapshot(model_requests=1, provider_roundtrip_s=3), weights()
    )
    cloud = next(row for row in rows if row.action == DecisionAction.REQUEST_CLOUD)
    assert cloud.inference_cost is None


def test_failed_and_timed_out_attempts_and_telemetry_remain_separate():
    costs = ledger()
    for number, status in [(2, "TIMEOUT"), (3, "SUCCESS")]:
        costs.record_request(
            RequestCost(
                request_id=f"attempt-{number}",
                sent_at=NOW,
                finished_at=NOW + timedelta(seconds=1),
                is_cloud_model=True,
                model_role="SUPERVISOR",
                deployment="CLOUD",
                provider_location="REMOTE_SERVICE",
                provider_version="frozen",
                status=status,
                serialized_sent_bytes=7,
                serialized_received_bytes=5 if status == "SUCCESS" else 0,
            )
        )
    costs.record_telemetry(3, 4)
    chosen = policy(costs=costs)
    chosen.decide(prepared_context())
    summary = costs.snapshot()
    assert summary.model_requests == 3 and summary.cloud_model_requests == 3
    assert summary.telemetry_messages == 1 and summary.application_bytes == 60


def test_hard_stop_never_calls_contract_or_judge_provider():
    ctx = prepared_context()
    ctx = replace(
        ctx,
        online_evidence=replace(
            ctx.online_evidence,
            robot_state=ctx.online_evidence.robot_state.model_copy(update={"estop_engaged": True}),
        ),
    )
    chosen = policy()

    def forbidden(_):
        raise AssertionError("hard stop waited for ordinary provider")

    chosen.contract_provider = forbidden
    assert chosen.decide(ctx) == DecisionAction.STOP


def test_provider_failure_after_absolute_deadline_cannot_reserve_new_capture():
    current_time = [NOW]

    class SlowJudge:
        def choose(self, context, candidates, estimates):
            current_time[0] = NOW + timedelta(seconds=61)
            raise TimeoutError("late provider")

    chosen = policy(judge=SlowJudge(), clock=lambda: current_time[0])
    ctx = prepared_context()
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 2
    assert chosen.last_trace.judgment.status == "ERROR"


def test_arbitrary_provider_error_is_a_recorded_budgeted_fallback():
    class BrokenJudge:
        def choose(self, context, candidates, estimates):
            raise OSError("transport unavailable")

    chosen = policy(judge=BrokenJudge())
    assert chosen.decide(prepared_context()) == DecisionAction.REOBSERVE
    assert chosen.last_trace.judgment.status == "ERROR"
    assert "judge_failure:OSError" in chosen.last_trace.reason_codes


def test_provider_cannot_rebind_unavailable_recovery_candidate():
    module = import_module("cloud_edge_robot_arm.auto_mode.judgment")

    class RebindingJudge:
        def choose(self, context, candidates, estimates):
            row = next(
                row for row in candidates.candidates if row.action == DecisionAction.LOCAL_RECOVER
            )
            object.__setattr__(row, "executable", True)
            return module.JudgmentResult(
                row.candidate_id, {}, None, None, "SELECTED", "tampering-provider", 0.0
            )

    chosen = policy(judge=RebindingJudge())
    assert chosen.decide(prepared_context()) == DecisionAction.REOBSERVE
    assert chosen.last_trace.judgment.status == "ERROR"


def test_failed_audit_sink_never_silently_returns_or_double_reserves():
    chosen = policy()
    chosen.contract_provider = None

    def broken_sink(trace):
        raise RuntimeError("durable audit unavailable")

    chosen.trace_sink = broken_sink
    ctx = prepared_context()
    with pytest.raises(RuntimeError, match="durable audit unavailable"):
        chosen.decide(ctx)
    assert ctx.verification_budget.remaining_reobservations == 2
    assert chosen.last_trace is None


def test_repeated_reserved_capture_with_last_allowance_is_idempotent():
    chosen = policy()
    chosen.contract_provider = None
    ctx = prepared_context()
    ctx.verification_budget.remaining_reobservations = 1
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.verification_budget.remaining_reobservations == 0
    assert len(chosen.traces) == 1


def test_duplicate_event_rejects_replaced_risk_without_new_quota():
    chosen = policy()
    ctx = prepared_context()
    assert chosen.decide(ctx) == DecisionAction.CONTINUE
    unknown = replace(
        ctx, risk_estimate=RiskEstimate(None, {"CONTINUE": None}, None, None, "UNKNOWN")
    )
    assert chosen.decide(unknown) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 2


def test_physical_expiry_is_derived_from_error_motion_duration_and_real_ttl():
    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    ctx = prepared_context()
    contract = contracts(ctx)[DecisionAction.CONTINUE]
    contract = replace(
        contract,
        evidence=replace(contract.evidence, geometric_error_bound_m=0.002, motion_bound_m_s=0.004),
        expected_duration_s=1.0,
        allowed_error_m=0.014,
    )
    assert module._envelope_expiry(ctx, DecisionAction.CONTINUE, contract, NOW) == NOW + timedelta(
        seconds=2
    )
    missing = replace(contract, evidence=replace(contract.evidence, motion_bound_m_s=None))
    assert module._envelope_expiry(ctx, DecisionAction.CONTINUE, missing, NOW) == NOW
    assert (
        module._envelope_expiry(ctx, DecisionAction.REOBSERVE, None, NOW)
        == ctx.verification_budget.deadline_at
    )
    assert module._envelope_expiry(ctx, DecisionAction.STOP, None, NOW) == NOW


def test_durable_trace_sink_is_hashed_and_never_overwrites_conflicting_record(tmp_path):
    import json

    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    chosen = policy()
    sink = module.JsonDecisionTraceSink(tmp_path / "decisions")
    chosen.trace_sink = sink
    chosen.decide(prepared_context())
    trace = chosen.last_trace
    path = tmp_path / "decisions" / (trace.envelope.decision_id + ".json")
    original = path.read_bytes()
    saved = json.loads(original)
    assert saved["schema_version"] == "ced.decision-trace.v1"
    assert saved["content_hash"] == module.content_hash(saved["payload"])
    sink(trace)
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match="conflicting"):
        sink(replace(trace, reason_codes=("changed",)))
    assert path.read_bytes() == original


def test_software_trace_never_creates_physical_authority():
    chosen = policy()
    chosen.decide(prepared_context())
    with pytest.raises(ValueError, match="software"):
        replace(
            chosen.last_trace,
            envelope=replace(chosen.last_trace.envelope, valid_until=NOW + timedelta(seconds=1)),
        )


def test_judge_cannot_replenish_authoritative_reobservation_pool():
    module = import_module("cloud_edge_robot_arm.auto_mode.judgment")

    class BudgetReplenishingJudge:
        def choose(self, context, candidates, estimates):
            context.verification_budget.remaining_reobservations = 2
            return module.JudgmentResult(None, {}, None, None, "ABSTAIN", "budget-mutator", 0.0)

    ctx = prepared_context()
    ctx.verification_budget.remaining_reobservations = 0
    chosen = policy(judge=BudgetReplenishingJudge())
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 0


def test_judge_cannot_extend_authoritative_absolute_deadline():
    module = import_module("cloud_edge_robot_arm.auto_mode.judgment")
    current_time = [NOW]

    class DeadlineExtendingJudge:
        def choose(self, context, candidates, estimates):
            context.verification_budget.deadline_at = NOW + timedelta(seconds=600)
            current_time[0] = NOW + timedelta(seconds=61)
            return module.JudgmentResult(None, {}, None, None, "ABSTAIN", "deadline-mutator", 0.0)

    ctx = prepared_context()
    chosen = policy(judge=DeadlineExtendingJudge(), clock=lambda: current_time[0])
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.deadline_at == NOW + timedelta(seconds=60)
    assert ctx.verification_budget.remaining_reobservations == 2


def test_contract_provider_cannot_replenish_shared_budget():
    ctx = prepared_context()
    ctx.verification_budget.remaining_reobservations = 0
    chosen = policy()

    def mutator(provider_context):
        provider_context.verification_budget.remaining_reobservations = 2
        return {}

    chosen.contract_provider = mutator
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 0


def test_audit_failure_retries_never_charge_before_publication(tmp_path):
    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    chosen = policy()
    chosen.contract_provider = None

    def broken_sink(trace):
        raise RuntimeError("audit publication failed")

    chosen.trace_sink = broken_sink
    ctx = prepared_context()
    for _ in range(2):
        with pytest.raises(RuntimeError, match="audit publication failed"):
            chosen.decide(ctx)
        assert ctx.verification_budget.remaining_reobservations == 2
        assert chosen.last_trace is None
        assert chosen.traces == ()
    chosen.trace_sink = module.JsonDecisionTraceSink(tmp_path / "decisions")
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.verification_budget.remaining_reobservations == 1
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.verification_budget.remaining_reobservations == 1
    assert len(chosen.traces) == 1


def test_provider_cannot_mutate_authoritative_observation_robot_facts_or_capabilities():
    from cloud_edge_robot_arm.contracts import Pose

    module = import_module("cloud_edge_robot_arm.auto_mode.judgment")
    ctx = prepared_context()
    original_capabilities = ctx.capabilities
    ctx = replace(
        ctx,
        online_evidence=replace(
            ctx.online_evidence,
            visual_facts={
                **ctx.online_evidence.visual_facts,
                "auxiliary_pose": Pose(x=0.1, y=0, z=0.3),
            },
        ),
        condition_verdicts=tuple(
            replace(
                row, measured_values={"cancelled": False, "auxiliary_pose": Pose(x=0.2, y=0, z=0.3)}
            )
            for row in ctx.condition_verdicts
        ),
    )

    class ContextMutator:
        def choose(self, copied_context, candidates, estimates):
            copied_context.online_evidence.robot_state.estop_engaged = True
            copied_context.online_evidence.robot_state.tcp_pose.x = 99
            copied_context.online_evidence.observation.__dict__["calibration_version"] = "mutated"
            copied_context.online_evidence.visual_facts["auxiliary_pose"].x = 99
            copied_context.condition_verdicts[0].measured_values["auxiliary_pose"].x = 99
            object.__setattr__(
                copied_context.condition_verdicts[0], "measured_values", {"cancelled": True}
            )
            object.__setattr__(
                copied_context, "capabilities", frozenset({DecisionAction.LOCAL_RECOVER})
            )
            return module.JudgmentResult(None, {}, None, None, "ABSTAIN", "context-mutator", 0.0)

    chosen = policy(judge=ContextMutator())
    assert chosen.decide(ctx) == DecisionAction.REOBSERVE
    assert ctx.online_evidence.robot_state.estop_engaged is False
    assert ctx.online_evidence.robot_state.tcp_pose.x == 0.2
    assert ctx.online_evidence.observation.calibration_version == "cal"
    assert ctx.online_evidence.visual_facts["auxiliary_pose"].x == 0.1
    assert ctx.condition_verdicts[0].measured_values["auxiliary_pose"].x == 0.2
    assert ctx.condition_verdicts[0].measured_values["cancelled"] is False
    assert ctx.capabilities == original_capabilities


@pytest.mark.parametrize("raises", [False, True])
def test_late_contract_return_cannot_reserve_capture_after_absolute_deadline(raises):
    current_time = [NOW]
    chosen = policy(clock=lambda: current_time[0])

    def late_provider(context):
        current_time[0] = NOW + timedelta(seconds=61)
        if raises:
            raise TimeoutError("contract provider returned late")
        return {}

    chosen.contract_provider = late_provider
    ctx = prepared_context()
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 2
    assert chosen.last_trace.envelope.created_at == current_time[0]
    assert chosen.last_trace.envelope.valid_until == current_time[0]


def test_late_audit_acknowledgement_never_publishes_capture_or_charges_quota():
    current_time = [NOW]
    chosen = policy(clock=lambda: current_time[0])
    chosen.contract_provider = None
    acknowledged = []

    def late_ack(trace):
        acknowledged.append(trace)
        current_time[0] = NOW + timedelta(seconds=61)

    chosen.trace_sink = late_ack
    ctx = prepared_context()
    with pytest.raises(RuntimeError, match="deadline|budget changed"):
        chosen.decide(ctx)
    assert len(acknowledged) == 1
    assert ctx.verification_budget.remaining_reobservations == 2
    assert chosen.last_trace is None
    assert chosen.traces == ()
    assert chosen._events == {}
    assert chosen.decide(ctx) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 2


def test_late_audit_acknowledgement_cannot_return_ordinary_continue():
    current_time = [NOW]
    chosen = policy(clock=lambda: current_time[0])

    def late_ack(trace):
        current_time[0] = NOW + timedelta(seconds=61)

    chosen.trace_sink = late_ack
    with pytest.raises(RuntimeError, match="deadline|budget changed"):
        chosen.decide(prepared_context())
    assert chosen.last_trace is None
    assert chosen.traces == ()
