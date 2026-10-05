"""Submit-time evidence checks; numerical expectations are hand calculated."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module, util

import pytest

NOW = datetime.now(UTC)


def api():
    name = "cloud_edge_robot_arm.edge.evidence.validator"
    assert util.find_spec(name) is not None, "missing production evidence validator"
    return import_module("cloud_edge_robot_arm.edge.evidence.models"), import_module(name)


def contract(**changes):
    models, _ = api()
    evidence = models.VisualEvidence(
        observation_id="frame-1",
        calibration_version="cal-1",
        captured_at=NOW - timedelta(seconds=0.1),
        geometric_error_bound_m=0.002,
        motion_bound_m_s=0.02,
        identity_status="CONFIRMED",
        sensor_status="VALID",
    )
    return models.ActionEvidenceContract(
        evidence=evidence,
        expected_duration_s=changes.get("duration", 0.2),
        allowed_error_m=0.01,
        sensor_requirements=("rgbd",),
        preconditions=changes.get("preconditions", ()),
        postconditions=(),
        plan_version=1,
        command_seq=1,
        context_hash="context-1",
    )


def verdict(value, **kwargs):
    _, validator = api()
    return validator.validate_evidence(
        value,
        now=NOW,
        current_context_hash="context-1",
        calibration_version="cal-1",
        **kwargs,
    )


def test_completion_time_bound_is_action_specific():
    # .002 + .02 * (.1 + .2) = .008; longer action gives .012.
    assert verdict(contract()).status == "VALID"
    assert verdict(contract()).bound_at_completion_m == pytest.approx(0.008)
    assert verdict(contract(duration=0.4)).status == "INVALID"
    assert verdict(contract(duration=0.4)).bound_at_completion_m == pytest.approx(0.012)


@pytest.mark.parametrize(
    "field,value",
    [
        ("motion_bound_m_s", None),
        ("geometric_error_bound_m", None),
        ("motion_bound_m_s", float("nan")),
        ("geometric_error_bound_m", -1.0),
        ("identity_status", "UNKNOWN"),
        ("sensor_status", "UNKNOWN"),
    ],
)
def test_missing_motion_identity_or_depth_is_unknown(field, value):
    from dataclasses import replace

    sample = contract()
    assert (
        verdict(replace(sample, evidence=replace(sample.evidence, **{field: value}))).status
        == "UNKNOWN"
    )


def test_calibration_mismatch_is_unknown():
    _, validator = api()
    assert (
        validator.validate_evidence(contract(), NOW, "context-1", "other-cal").status == "UNKNOWN"
    )


def test_cloud_return_and_commit_both_revalidate():
    _, validator = api()
    sample = contract()
    assert verdict(sample).status == "VALID"
    assert (
        validator.validate_evidence(sample, NOW + timedelta(seconds=1), "context-1", "cal-1").status
        == "INVALID"
    )
    assert validator.validate_evidence(sample, NOW, "new-context", "cal-1").status == "INVALID"


def test_missing_condition_evidence_is_unknown():
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    sample = contract(preconditions=(ConditionSpec("target_visible", target_id="object"),))
    assert verdict(sample).status == "UNKNOWN"


def test_precondition_verdict_is_bound_to_current_frame():
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    sample = contract(preconditions=(ConditionSpec("target_visible", target_id="object"),))
    online = online_evidence()
    assert verdict(sample, online_evidence=online).status == "VALID"
    wrong = replace(
        online,
        visual_facts={
            "target_visible": {**online.visual_facts["target_visible"], "target_id": "decoy"}
        },
    )
    assert verdict(sample, online_evidence=wrong).status == "UNKNOWN"
    assert verdict(sample, online_evidence=replace(online, command_seq=2)).status == "INVALID"


def test_b3_keeps_basic_sensor_context_and_condition_checks():
    from dataclasses import replace

    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    _, validator = api()
    sample = contract(preconditions=(ConditionSpec("target_reachable", target_id="object"),))
    online = online_evidence()
    online = replace(
        online,
        visual_facts={
            "target_reachable": {**online.visual_facts["target_visible"], "value": False}
        },
    )
    assert (
        validator.validate_b3(sample, NOW, "context-1", "cal-1", online_evidence=online).status
        == "INVALID"
    )
    sample = replace(sample, preconditions=())
    assert validator.validate_b3(sample, NOW, "context-1", "cal-1").status == "VALID"
    assert validator.validate_b3(sample, NOW, "changed", "cal-1").status == "INVALID"


def decisions():
    models, validator = api()
    data = dict(
        task_id="task",
        episode_id="episode",
        observation_id="frame-1",
        plan_version=1,
        command_seq=2,
        mode_version=3,
        context_hash="context",
        candidate_set_hash="candidates",
    )
    current = models.CommitContext(**data, cancelled=False)
    decision = models.DecisionEnvelope(
        **data,
        decision_id="decision",
        action="CONTINUE",
        policy_version="policy",
        provider_version="provider",
        created_at=NOW,
        valid_until=NOW + timedelta(seconds=1),
    )
    return decision, current, validator


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "other"),
        ("episode_id", "other"),
        ("observation_id", "other"),
        ("plan_version", 2),
        ("command_seq", 3),
        ("mode_version", 4),
        ("context_hash", "other"),
        ("candidate_set_hash", "other"),
    ],
)
def test_stale_decision_identity_blocks_commit(field, value):
    from dataclasses import replace

    decision, current, validator = decisions()
    assert validator.validate_decision_commit(decision, current, NOW).status == "VALID"
    assert (
        validator.validate_decision_commit(decision, replace(current, **{field: value}), NOW).status
        == "INVALID"
    )


def test_cancelled_or_expired_decision_cannot_commit():
    from dataclasses import replace

    decision, current, validator = decisions()
    assert (
        validator.validate_decision_commit(decision, replace(current, cancelled=True), NOW).status
        == "INVALID"
    )
    assert (
        validator.validate_decision_commit(decision, current, NOW + timedelta(seconds=1)).status
        == "INVALID"
    )
    assert (
        validator.validate_decision_commit(
            replace(decision, created_at=NOW + timedelta(seconds=0.1)), current, NOW
        ).status
        == "INVALID"
    )


def test_empty_episode_cannot_match_empty_episode():
    from dataclasses import replace

    decision, current, validator = decisions()
    assert (
        validator.validate_decision_commit(
            replace(decision, episode_id=""), replace(current, episode_id=""), NOW
        ).status
        == "INVALID"
    )


def online_evidence():
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    payload = observation_payload()
    payload.update(
        frame_id="frame-1",
        captured_at=NOW - timedelta(seconds=0.1),
        calibration_version="cal-1",
        episode_id="episode",
    )
    observation = RGBDObservation.model_validate(payload)
    return OnlineEvidenceSnapshot(
        observation,
        RobotState(connected=True),
        {
            "target_visible": {
                "source": "rgbd_estimate",
                "observation_id": "frame-1",
                "target_id": "object",
                "identity_confirmed": True,
                "value": True,
                "pixel": [0, 0],
            },
        },
        1,
        1,
        "context-1",
    )


def test_current_boolean_version_cannot_alias_integer_version():
    decision, current, validator = decisions()
    assert (
        validator.validate_decision_commit(
            decision, replace(current, plan_version=True), NOW
        ).status
        == "INVALID"
    )


def test_contract_copies_nested_condition_and_sensor_state():
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec

    nested = {"thresholds": {"minimum": 1}}
    requirements = ["rgbd"]
    value = contract(
        preconditions=(ConditionSpec("target_visible", "object", nested, requirements),)
    )
    nested["thresholds"]["minimum"] = 99
    requirements.append("unavailable")
    assert value.preconditions[0].tolerances["thresholds"]["minimum"] == 1
    assert value.preconditions[0].sensor_requirements == ("rgbd",)
    with pytest.raises(TypeError):
        value.preconditions[0].tolerances["thresholds"]["minimum"] = 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_duration_s", float("inf")),
        ("ordinary_ttl_s", 0),
        ("allowed_error_m", float("nan")),
        ("plan_version", True),
        ("command_seq", -1),
    ],
)
def test_invalid_contract_metadata_cannot_authorize(field, value):
    assert verdict(replace(contract(), **{field: value})).status != "VALID"
