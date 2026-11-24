from dataclasses import replace

import pytest
from scripts.graduation.dynamic_physics import CRITERIA
from scripts.graduation.proposal_scoring import (
    check_batch,
    registered_windows,
    score_admissions,
    summarize_view,
)

from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import sample_physical_observation
from tests.test_graduation_dynamic_physics import obs


def test_window_requires_entire_registered_hold_and_uses_reset_height():
    samples = [sample_physical_observation(obs(step), CRITERIA) for step in range(124)]
    samples[0] = replace(samples[0], object_position_m=(0.2, 0.25, 0.035))
    stages = {
        "LIFT": {"dispatch_step": 1, "dwell_start_step": 3, "end_step": 123},
        "RELEASE": {},
    }
    lift, release = registered_windows(samples, stages).values()
    assert (lift["actual_samples"], lift["qualified"]) == (121, True)
    assert release["status"] == "NOT_REACHED"
    incomplete = registered_windows(samples[:-1], stages)["lift"]
    assert incomplete["status"] == "INCOMPLETE" and not incomplete["qualified"]
    samples[50] = replace(samples[50], right_finger_contact=False)
    assert not registered_windows(samples, stages)["lift"]["qualified"]


def test_empty_or_uncertain_conditions_cannot_certify_a_stage():
    decision = {
        "frame_id": "f",
        "checksum_sha256": "h",
        "conditions": [{"status": "PASS", "name": "gripper_open"}],
        "shield": {"allowed": True, "unmodified": True},
    }
    stage = {
        "skill": "RELEASE",
        "status": "PASS",
        "pre": decision,
        "post": decision,
        "executor_entered": True,
        "return_evidence": {
            "success": True,
            "action_result_present": True,
            "original_window_error": None,
        },
    }
    assert score_admissions([stage], {"f": "h"}) == 1
    for conditions in ([], [{"status": "UNKNOWN", "name": "object_in_region"}]):
        assert (
            score_admissions(
                [{**stage, "post": {**decision, "conditions": conditions}}], {"f": "h"}
            )
            == 0
        )
    with pytest.raises(ValueError, match="frame"):
        score_admissions([stage], {"f": "other"})


def test_denominator_includes_stops_and_distinguishes_unacquired_cases():
    observed = {
        "acquired": True,
        "joint_success": False,
        "physical_success": False,
        "online_success": False,
        "coverage": {"acquired": 5, "valid": 3},
    }
    result = summarize_view([observed, {"acquired": False}], [0.001, 0.002, 0.003])
    assert (result["allocated"], result["acquired"], result["unacquired"]) == (2, 1, 1)
    assert result["joint_successes"] == 0
    assert result["joint_wilson95_by_placement"] is None
    assert result["valid_frames"] == 3 and result["acquired_frames"] == 5
    assert result["conditional_top_center_p90_mm"] == pytest.approx(2.8)


def test_allocations_cannot_drop_a_placement_or_reuse_an_evidence_directory():
    from scripts.graduation.proposal_closed_loop import allocated_cases

    rows = [
        {**r, "allocation_file": r["id"] + "/allocation.json"} for r in allocated_cases("nominal")
    ]
    batch = {"schema": "proposal.heldout.development.allocation.v1", "selected_view": "nominal"}
    check_batch({**batch, "cases": rows})
    with pytest.raises(ValueError, match="allocation"):
        check_batch({**batch, "cases": rows[:-1]})
    with pytest.raises(ValueError, match="directory"):
        check_batch(
            {
                **batch,
                "cases": [*rows[:-1], {**rows[-1], "allocation_file": rows[0]["allocation_file"]}],
            }
        )
