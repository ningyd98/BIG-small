from datetime import UTC, datetime, timedelta

import pytest
from scripts.graduation import proposal_fixed_opportunities as study


def test_issued_opportunity_ids_and_pairs_are_unique_despite_reused_scene():
    rows = study.cases()
    assert [r["waiting_steps"] for r in rows] == [0, 96, 96, 0]
    assert [r["pair"] for r in rows] == [1, 1, 2, 2]
    assert len({r["id"] for r in rows}) == 4


def test_shared_gate_requires_the_same_candidate_skill():
    candidate = {"action_type": "MOVE_TCP", "timeout_s": 8, "target_position_m": [0.35, 0, 0.16]}
    support = study.skill_support(candidate)
    assert support["task_step_valid"] is False
    assert support["production_motion_skill"] is False
    assert support["production_target_pose_checks"] is False
    assert support["rejection_type"] == "enum"


def test_sim_and_wall_clocks_are_independent_and_wrong_dispatch_is_rejected():
    utc = datetime.now(UTC)
    args = (120, 216, 96, 0.5, 0.9, utc.isoformat(), (utc + timedelta(seconds=2)).isoformat())
    ages = study.ages(*args)
    assert ages["sim_s"] == 0.4 and ages["wall_s"] == 2.0
    with pytest.raises(ValueError):
        study.ages(120, 215, *args[2:])
    with pytest.raises(ValueError):
        study.ages(120, 216, 96, 0.5, 0.4, utc.isoformat(), utc.isoformat())


def test_online_protocol_rejects_truth_and_changed_candidate():
    candidate = {"action_type": "MOVE_TCP", "target_position_m": [0.35, 0, 0.16]}
    simple = {"opportunity_id": "x", "candidate": candidate, "sha256": "p"}
    study.check_online_index(simple, "x", candidate)
    with pytest.raises(ValueError):
        study.check_online_index({**simple, "physics_state": {}}, "x", candidate)
    with pytest.raises(ValueError):
        study.check_online_index(simple, "x", {**candidate, "target_position_m": [0, 0, 0]})
