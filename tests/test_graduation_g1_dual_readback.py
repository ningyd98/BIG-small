import pytest
from scripts.graduation import g1_dual_cross_readback as cross


def test_matching_original_feedback_excludes_separately_acquired_terminal():
    feedback = {
        "physics_step": 8,
        "frame_id": "servo",
        "checksum_sha256": "a",
        "label": "MOVE_ABOVE/feedback",
    }
    cross.require_feedback(feedback, dict(feedback))
    for replacement in ({"frame_id": "terminal"}, {"label": "terminal"}, {"physics_step": 0}):
        with pytest.raises(ValueError, match="feedback"):
            cross.require_feedback(feedback, {**feedback, **replacement})


def test_distinct_step_roles_and_verified_uniquely_visible_sides_are_needed():
    assert cross.classify_pose({"X": True, "Y": False}, True) == "X_only"
    assert cross.classify_pose({"X": False, "Y": True}, True) == "Y_only"
    assert cross.classify_pose({"X": False, "Y": True}, False) == "unverified"
    with pytest.raises(ValueError):
        cross.classify_pose({"X": True}, True)
