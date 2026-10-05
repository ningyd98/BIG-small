"""A periodic response must actually govern its matching action boundary."""

from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.vision.supervision import (
    SupervisionContext,
    SupervisionDecision,
    decide_supervision,
)


def context(version=3):
    return SupervisionContext(episode_id="ep", plan_version=1, state_version=version,
        next_step_id="approach", next_skill="APPROACH", observation_id="obs",
        captured_at=datetime.now(UTC), proprioception={"gripper_open": True})


@pytest.mark.parametrize("recommendation,expected", [
    ("CONTINUE", "CONTINUE"), ("REOBSERVE", "REOBSERVE"),
    ("REPLAN", "STOP"), ("STOP", "STOP"),
])
def test_response_content_changes_boundary_decision(recommendation, expected):
    current = context()
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=3,
        observation_id="obs", next_step_id="approach", recommendation=recommendation,
        reason="unit fixture")
    assert decide_supervision(reply, current, current, maximum_age_s=5) == expected


def test_old_state_or_mismatched_step_can_never_authorize_motion():
    captured = context(2)
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=2,
        observation_id="obs", next_step_id="approach", recommendation="CONTINUE", reason="")
    assert decide_supervision(reply, captured, context(3), maximum_age_s=5) == "DISCARD"
    wrong_step = reply.model_copy(update={"next_step_id": "place"})
    assert decide_supervision(wrong_step, captured, captured, maximum_age_s=5) == "REJECT"


def test_supervisor_input_schema_rejects_oracle_fields():
    with pytest.raises(ValueError):
        SupervisionContext.model_validate({**context().model_dump(), "physical_success": True})


def test_matching_stop_response_terminates_the_real_episode_boundary():
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode

    captured = context()
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=3,
        observation_id="obs", next_step_id="approach", recommendation="STOP", reason="unsafe")
    response = {"episode_id": "ep", "captured_at": captured.captured_at,
                "context": captured.model_dump(), "decision": reply.model_dump()}
    run = _VisualEpisode.__new__(_VisualEpisode)
    run.supervision = SimpleNamespace(poll=lambda **_: [response])
    run.observation = SimpleNamespace(episode_id="ep")
    run.supervision_context = lambda _: captured
    run.records = []
    run._state_version = 3
    with pytest.raises(_EpisodeStopped, match="SUPERVISION_STOPPED_SEQUENCE"):
        run.apply_supervision()
    assert run.records[-1]["action"] == "STOP"
