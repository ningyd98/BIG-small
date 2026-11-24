import numpy as np
import pytest
from scripts.graduation import g1_dual_batch_score as score
from scripts.graduation.g1_dual_pixel_readback import rigid_points


def test_two_attachments_map_to_one_cube_and_tcp_under_yaw():
    rot = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    for marker, delta in ((7, [-0.1, 0, 0.03505]), (8, [0, 0.1, 0.03505])):
        center, top, tcp = rigid_points(np.add([0.45, 0, 0.035], delta), rot, marker)
        assert np.allclose(center, [0.45, 0, 0.035])
        assert np.allclose(top, [0.45, 0, 0.070])
        assert np.allclose(tcp, [0.45, 0, 0.045])
    with pytest.raises(ValueError):
        rigid_points([0, 0, 0], rot, 49)


def test_bracket_contact_never_satisfies_cube_pinch():
    records = [
        {
            "contact_pairs": [
                ["left_finger_geom", "test_bracket"],
                ["test_plate", "right_finger_geom"],
            ]
        },
        {
            "contact_pairs": [
                ["object_geom", "left_finger_geom"],
                ["right_finger_geom", "object_geom"],
            ]
        },
    ]
    summary = score.contact_counts(records, {"test_plate", "test_bracket"})
    assert summary["bilateral_cube_steps"] == 1 and summary["any_finger_support_steps"] == 1
    assert summary["support_contact_without_bilateral_cube_steps"] == 1


def test_unobserved_and_all_rejected_are_separate():
    assert score.coverage([])["fraction"] is None
    assert (
        score.coverage(
            [
                {
                    "usable": False,
                    "selected_id": None,
                    "usable_ids": [],
                    "observed_ids": [],
                    "reason": "absent",
                    "per_id": {},
                    "top_error_mm": None,
                }
            ]
        )["fraction"]
        == 0
    )
