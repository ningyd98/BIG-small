from itertools import product

import pytest
from scripts.graduation.proposal_camera import STEPS, VIEWS, select_view


def observed(side=14.0):
    return {
        "status": "OBSERVED",
        "ids": [7],
        "min_side_px": side,
        "object_top_center_world_m": [0.45, 0.0, 0.07],
    }


def test_selection_retains_all_slots_and_ignores_hidden_and_unverified_images():
    rows = {(s, v): observed() for s, v in product(STEPS, VIEWS)}
    verified = dict.fromkeys(STEPS, True)
    assert select_view(rows, verified)[0] == "nominal"
    rows[(STEPS[-1], "nominal")] = {
        "status": "UNKNOWN",
        "ids": [],
        "min_side_px": None,
        "object_top_center_world_m": None,
    }
    assert select_view(rows, verified)[0] == "right"
    verified[STEPS[-1]] = False
    chosen, scores = select_view(rows, verified)
    assert chosen == "nominal"
    assert scores[chosen]["valid_steps"] == 7
    assert scores[chosen]["terminal_streak"] == 0
    with pytest.raises(ValueError):
        select_view({**rows, (120, "arm_hidden"): observed(1000)}, verified)
    del rows[120, "right"]
    with pytest.raises(ValueError):
        select_view(rows, verified)


def test_selection_prefers_coverage_then_terminal_streak_then_minimum_size():
    normal = {(s, v): observed(15.0) for s, v in product(STEPS, VIEWS)}
    verified = dict.fromkeys(STEPS, True)
    unknown = {
        "status": "UNKNOWN",
        "ids": [],
        "min_side_px": None,
        "object_top_center_world_m": None,
    }
    normal[STEPS[0], "nominal"] = unknown
    normal[STEPS[0], "left"] = unknown
    normal[STEPS[1], "right"] = unknown
    normal[STEPS[4], "nominal"] = observed(12)
    assert select_view(normal, verified)[0] == "left"
    normal[STEPS[-1], "left"] = unknown
    assert select_view(normal, verified)[0] == "nominal"
    normal[STEPS[1], "right"] = observed(11)
    assert select_view(normal, verified)[0] == "right"


def test_detection_requires_known_identity_metric_pose_and_measurable_side():
    from scripts.graduation.proposal_camera import valid

    assert valid(observed())
    for changed in ({"ids": [6]}, {"object_top_center_world_m": None}, {"min_side_px": None}):
        assert not valid({**observed(), **changed})
