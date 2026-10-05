"""有限候选选择的非法输出、不可变hash及规则来源测试。"""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module

import pytest

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, VisualEvidence
from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot
from tests.test_runtime_auto_baselines import context


def modules():
    candidates = import_module("cloud_edge_robot_arm.auto_mode.candidates")
    judgment = import_module("cloud_edge_robot_arm.auto_mode.judgment")
    policy = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    return candidates, judgment, policy


def prepared_context(**changes):
    ctx = context(**changes)
    fact = {
        "source": "rgbd_estimate",
        "target_id": "cube",
        "identity_confirmed": True,
        "observation_id": "fresh",
        "pixel": [0, 0],
        "value": True,
    }
    return replace(
        ctx, online_evidence=replace(ctx.online_evidence, visual_facts={"target_visible": fact})
    )


def contracts(ctx):
    obs = ctx.online_evidence.observation
    evidence = VisualEvidence(
        obs.observation_id,
        obs.calibration_version,
        obs.captured_at,
        ctx.risk_estimate.geometric_error_bound_m,
        ctx.risk_estimate.motion_bound_m_s,
        "CONFIRMED",
        "VALID",
    )
    contract = ActionEvidenceContract(
        evidence,
        0.5,
        0.01,
        ("rgbd",),
        (ConditionSpec("target_visible", "cube"),),
        (),
        ctx.plan_version,
        ctx.command_seq,
        ctx.online_evidence.context_hash,
        ordinary_ttl_s=5,
    )
    return {DecisionAction.CONTINUE: contract, DecisionAction.REQUEST_CLOUD: contract}


def weights():
    return dict(
        failure_loss=10.0,
        stop_failure_loss=20.0,
        inference_weight=1.0,
        network_weight=1.0,
        switch_weight=1.0,
    )


def estimates(ctx):
    module = import_module("cloud_edge_robot_arm.auto_mode.joint_policy")
    return module.estimate_action_costs(
        ctx,
        CostSnapshot(model_requests=1, inference_s=0.2, network_s=0.1, switch_s=0.05),
        weights(),
    )


def test_unsafe_low_cost_action_cannot_win():
    c, j, p = modules()
    ctx = prepared_context()
    supplied = contracts(ctx)
    supplied[DecisionAction.CONTINUE] = replace(
        supplied[DecisionAction.CONTINUE], context_hash="stale"
    )
    candidates = c.build_candidates(ctx, action_contracts=supplied)
    assert not next(
        row for row in candidates.candidates if row.action == DecisionAction.CONTINUE
    ).executable
    result = j.CostDecisionJudge().choose(ctx, candidates, estimates(ctx))
    assert result.selected_candidate_id != next(
        row.candidate_id for row in candidates.candidates if row.action == DecisionAction.CONTINUE
    )


def test_missing_action_contract_and_unaccepted_recovery_are_masked():
    c, j, p = modules()
    ctx = prepared_context()
    candidates = c.build_candidates(ctx)
    assert not next(
        row for row in candidates.candidates if row.action == DecisionAction.CONTINUE
    ).executable
    assert not next(
        row for row in candidates.candidates if row.action == DecisionAction.LOCAL_RECOVER
    ).executable
    assert next(
        row for row in candidates.candidates if row.action == DecisionAction.STOP
    ).executable


def test_atomic_ordinary_candidates_are_deferred_but_stop_remains():
    c, j, p = modules()
    ctx = prepared_context()
    ctx = replace(ctx, event=replace(ctx.event, atomic_action_active=True))
    candidates = c.build_candidates(ctx, action_contracts=contracts(ctx))
    assert all(
        not row.executable for row in candidates.candidates if row.action != DecisionAction.STOP
    )


def test_candidate_hash_rejects_mutation_and_duplicate_options():
    c, j, p = modules()
    ctx = prepared_context()
    built = c.build_candidates(ctx, action_contracts=contracts(ctx))
    wrong = replace(
        built.candidates[0],
        executable=not built.candidates[0].executable,
        unavailable_reasons=("tampered",),
    )
    with pytest.raises(ValueError, match="hash"):
        c.CandidateSet((wrong, *built.candidates[1:]), built.content_hash)
    with pytest.raises(ValueError, match="duplicate"):
        c.CandidateSet((built.candidates[0], built.candidates[0]), "")


def test_rule_scores_have_no_fabricated_probabilities():
    c, j, p = modules()
    ctx = prepared_context()
    built = c.build_candidates(ctx, action_contracts=contracts(ctx))
    result = j.CostDecisionJudge().choose(ctx, built, estimates(ctx))
    assert result.status == "SELECTED" and result.rule_scores
    assert result.candidate_probabilities is None and result.reported_confidence is None
    with pytest.raises(TypeError):
        result.rule_scores["forged"] = 0


def test_equal_scores_have_deterministic_tie_break():
    c, j, p = modules()
    ctx = prepared_context()
    built = c.build_candidates(ctx, action_contracts=contracts(ctx))
    values = [p.ActionCostEstimate(row.action, 0.0, 0.0, 0.0, 0.0, 0.0) for row in built.candidates]
    expected = min(row.candidate_id for row in built.candidates if row.executable)
    result = j.CostDecisionJudge().choose(ctx, built, values)
    reversed_set = c.CandidateSet(tuple(reversed(built.candidates)), "")
    assert result.selected_candidate_id == expected
    assert j.CostDecisionJudge().choose(ctx, reversed_set, values).selected_candidate_id == expected


def test_independent_answers_with_conflicting_actions_are_rejected():
    c, j, p = modules()
    with pytest.raises(ValueError):
        j.JudgmentResult(
            "a", {"a": 1, "b": 2}, {"a": 0.8, "b": 0.7}, 0.9, "SELECTED", "provider", 1.0
        )
    with pytest.raises(ValueError):
        j.JudgmentResult("a", {}, None, None, "ABSTAIN", "provider", 1.0)


def test_candidate_identity_changes_with_observation_and_versions():
    c, j, p = modules()
    ctx = prepared_context()
    first = c.build_candidates(ctx, action_contracts=contracts(ctx))
    fresh = ctx.online_evidence.observation.model_copy(
        update={"frame_id": "next", "observation_id": "next"}
    )
    from cloud_edge_robot_arm.vision.risk.models import RiskFeatures

    newer = replace(
        ctx,
        online_evidence=replace(ctx.online_evidence, observation=fresh),
        event=replace(ctx.event, observation_id="next"),
        risk_features=RiskFeatures({}, "next"),
        condition_verdicts=tuple(replace(v, observation_id="next") for v in ctx.condition_verdicts),
    )
    assert c.build_candidates(newer).content_hash != first.content_hash


def test_unknown_cloud_identity_cannot_replace_new_capture():
    c, j, p = modules()
    ctx = prepared_context()
    supplied = contracts(ctx)
    supplied = {
        action: replace(value, evidence=replace(value.evidence, identity_status="UNKNOWN"))
        for action, value in supplied.items()
    }
    choices = c.build_candidates(ctx, action_contracts=supplied)
    assert not next(
        row for row in choices.candidates if row.action == DecisionAction.REQUEST_CLOUD
    ).executable


def test_final_verification_failure_cannot_continue_even_with_old_pass_conditions():
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus

    c, j, p = modules()
    ctx = prepared_context()
    ctx = replace(ctx, event=replace(ctx.event, verification_status=ConditionStatus.FAIL))
    choices = c.build_candidates(ctx, action_contracts=contracts(ctx))
    assert not next(
        row for row in choices.candidates if row.action == DecisionAction.CONTINUE
    ).executable
