import math

import pytest
from development_plan import (
    PLACE_CONTROL_SEED,
    assert_no_conflicts,
    make_assignments,
    score_outcomes,
    wilson95,
)


def test_assignment_groups_have_separate_replicate_denominator():
    main, repeats = make_assignments()
    assert len(main) == len({slot["pose_seed"] for slot in main}) == 20
    assert len({slot["assignment_id"] for slot in main + repeats}) == 22
    assert sum(slot["scene"]["condition"] == "ARM_OCCLUSION_STRESS" for slot in main) == 5
    assert all(slot["pose_seed"] == PLACE_CONTROL_SEED for slot in repeats)
    assert repeats[0]["scene"] == repeats[1]["scene"]
    assert len({slot["run_instance_id"] for slot in main + repeats}) == 22
    assert conflicts_are_empty(main)


def conflicts_are_empty(main):
    assert_no_conflicts(main, {"history": ({PLACE_CONTROL_SEED}, set())})
    return True


def test_existing_seed_and_existing_pose_fail_closed():
    rows, _ = make_assignments()
    row = rows[0]
    pose = tuple(row["scene"]["object_position_m"])
    with pytest.raises(ValueError, match="prior pool.*seed"):
        assert_no_conflicts(rows, {"prior pool": ({row["pose_seed"]}, set())})
    with pytest.raises(ValueError, match="teacher.*position"):
        assert_no_conflicts(rows, {"teacher": (set(), {pose})})


@pytest.mark.parametrize(
    ("n", "total", "expected"),
    [
        (1, 4, (0.04558726080970055, 0.6993581574175981)),
        (0, 20, (0, 0.1611251580528194)),
        (20, 20, (0.8388748419471806, 1)),
    ],
)
def test_wilson_matches_known_values(n, total, expected):
    interval = wilson95(n, total)
    assert math.isclose(interval[0], expected[0], abs_tol=1e-12)
    assert math.isclose(interval[1], expected[1], abs_tol=1e-12)


def test_empty_or_invalid_wilson_does_not_fabricate_a_result():
    assert wilson95(0, 0) is None
    with pytest.raises(ValueError, match="binomial counts"):
        wilson95(1, 0)


def test_new_denominator_is_never_inflated_by_repeats_or_missing_results():
    main, repeats = make_assignments()
    base = {"development": main, "repeats_1802": repeats}
    empty = score_outcomes(base, [], closed=False)
    assert empty["development"]["component_complete"]["wilson95"] is None
    assert empty["development"]["observed_audited"] == 0
    assert len(empty["repeats_1802"]) == 2
    events = [
        row_result(main[0], True, False),
        row_result(repeats[0], True, True),
    ]
    result = score_outcomes(base, events, closed=False)
    assert result["development"]["observed_audited"] == 1
    assert result["development"]["component_complete"]["successes"] == 1
    assert result["development"]["physical_success"]["successes"] == 0
    assert result["development"]["component_complete"]["wilson95"] is None
    with pytest.raises(ValueError, match="missing assignments"):
        score_outcomes(base, events, closed=True)
    with pytest.raises(ValueError, match="not a unique registered"):
        score_outcomes(base, events + [events[0]], closed=False)


def row_result(slot, complete, physical):
    return {
        "assignment_id": slot["assignment_id"],
        "run_instance_id": slot["run_instance_id"],
        "pose_seed": slot["pose_seed"],
        "status": "AUDITED",
        "component_completed": complete,
        "independent_physical_success": physical,
        "audit_sha256": "c" * 64,
    }
