import numpy as np
import pytest
from scripts.graduation import g1_visibility_radial_screen as screen


def test_contact_on_left_id7_plate_is_hazard_but_finger_on_cube_and_cube_on_table_are_recognized():
    assert screen.contact_category("left_finger_geom", "g1_dual_id7_plate") == "unauthorized"
    assert screen.contact_category("object_geom", "left_finger_geom") == "finger_object"
    assert screen.contact_category("table", "object_geom") == "object_on_table"
    assert screen.contact_category("g1_dual_id8_crossbar", "table") == "unauthorized"


def test_dual_conflict_anchor_demands_both_prints_and_independent_metric_errors():
    base = {
        "usable": True,
        "observed_ids": [7],
        "usable_ids": [7],
        "selected_id": 7,
        "target_disagreement_m": None,
    }
    truth = {
        "correct_registered_id": True,
        "per_id": {"7": {"tcp_error_mm": 0.3, "top_error_mm": 0.4}},
    }
    assert screen.visual_qualified(base, truth, False)
    assert not screen.visual_qualified(base, truth, True)
    both = {**base, "observed_ids": [7, 8], "usable_ids": [7, 8], "target_disagreement_m": 0.009}
    truth["per_id"]["8"] = {"tcp_error_mm": 3.4, "top_error_mm": 2.4}
    assert screen.visual_qualified(both, truth, True)
    assert not screen.visual_qualified({**both, "target_disagreement_m": 0.01001}, truth, True)
    truth["per_id"]["8"]["tcp_error_mm"] = 11.2
    assert not screen.visual_qualified(both, truth, True)


def test_oriented_boxes_with_overlapping_world_bounds_can_have_certified_positive_gap():
    rot = np.array(
        [
            [0.7071067811865476, -0.7071067811865476, 0],
            [0.7071067811865476, 0.7071067811865476, 0],
            [0, 0, 1],
        ]
    )
    half = np.array([1, 0.05, 0.1])
    # Short-axis displacement 0.2, twice the local half width is 0.1.
    assert screen.box_separation(
        np.zeros(3), rot, half, rot[:, 1] * 0.2, rot, half
    ) == pytest.approx(0.1)
    assert screen.box_separation(
        np.zeros(3), rot, half, rot[:, 1] * 0.05, rot, half
    ) == pytest.approx(-0.05)
