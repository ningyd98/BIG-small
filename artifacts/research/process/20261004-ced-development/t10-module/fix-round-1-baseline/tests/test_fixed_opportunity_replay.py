"""Fixed offline opportunities preserve every label and policy-independent denominator."""

from dataclasses import replace
from importlib import import_module

import pytest

from tests.test_visual_evidence_contract import NOW, contract, online_evidence


def api():
    return import_module("cloud_edge_robot_arm.edge.evidence.opportunities")


def opportunities():
    observation = online_evidence().observation
    return [
        api().Opportunity("opp-safe", "episode-a", observation, contract(), "VALID"),
        api().Opportunity(
            "opp-unsafe",
            "episode-b",
            observation,
            replace(contract(), expected_duration_s=0.4),
            "INVALID",
        ),
        api().Opportunity(
            "opp-unknown",
            "episode-c",
            observation,
            replace(contract(), evidence=replace(contract().evidence, motion_bound_m_s=None)),
            "UNKNOWN",
        ),
    ]


def test_opportunity_denominators_do_not_depend_on_policy_actions():
    values = opportunities()
    gated = api().replay_opportunities(values, "JOINT", NOW, "cal-1")
    b3 = api().replay_opportunities(values, "B3", NOW, "cal-1")
    assert [value.opportunity_id for value in gated] == [value.opportunity_id for value in b3]
    assert len(gated) == len(b3) == 3
    summary = api().summarize_gate_replay(values, b3)
    assert summary["eligible_valid"] == summary["eligible_invalid"] == 1
    assert summary["oracle_unknown"] == 1
    assert summary["false_acceptance"] == 1
    assert summary["false_rejection"] == 0


def test_unknown_is_not_false_rejection_denominator():
    values = opportunities()
    values[0] = replace(
        values[0],
        action_contract=replace(
            contract(), evidence=replace(contract().evidence, motion_bound_m_s=None)
        ),
    )
    records = api().replay_opportunities(values, "JOINT", NOW, "cal-1")
    summary = api().summarize_gate_replay(values, records)
    assert summary["eligible_valid"] == 1
    assert summary["unknown_on_valid"] == 1
    assert summary["false_rejection"] == 0
    assert summary["false_rejection_rate"] == 0


def test_missing_duplicate_or_changed_snapshot_cannot_publish_replay():
    values = opportunities()
    records = api().replay_opportunities(values, "JOINT", NOW, "cal-1")
    with pytest.raises(ValueError, match="complete"):
        api().summarize_gate_replay(values, records[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        api().replay_opportunities([values[0], values[0]], "JOINT", NOW, "cal-1")
    with pytest.raises(ValueError, match="snapshot"):
        replace(
            values[0],
            action_contract=replace(
                contract(), evidence=replace(contract().evidence, observation_id="different-frame")
            ),
        )


def test_oracle_label_is_never_an_online_validation_input(monkeypatch):
    module = api()
    original = module.validate_evidence
    seen = []

    def observed(action_contract, *args, **kwargs):
        seen.append(action_contract)
        assert not hasattr(action_contract, "oracle_label")
        return original(action_contract, *args, **kwargs)

    monkeypatch.setattr(module, "validate_evidence", observed)
    values = opportunities()
    first = module.replay_opportunities(values, "JOINT", NOW, "cal-1")
    second = module.replay_opportunities(
        [replace(value, oracle_label="INVALID") for value in values], "JOINT", NOW, "cal-1"
    )
    assert [value.verdict for value in first] == [value.verdict for value in second]
    assert len(seen) == 6
