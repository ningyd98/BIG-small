"""Focused CPU tests for the preregistered outboard bearing."""

import numpy as np
import pytest
from probe_current_views import proposal_basis


def attachment():
    transform = np.eye(4)
    transform[:3, 3] = [0, 0.14, 0.03505]
    return transform


def test_registered_outboard_bearing_rotates_with_world_yaw():
    yaw90 = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    bearing, object_rotation, offset, horizontal = proposal_basis(yaw90, attachment())
    assert bearing.tolist() == [-1.0, 0.0]
    assert object_rotation.tolist() == yaw90.tolist()
    assert offset.tolist() == [-0.14, 0.0, 0.03505]
    assert horizontal == 0.14


def test_registered_vertical_component_contributes_after_world_rotation():
    pitch90 = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
    bearing, _, offset, horizontal = proposal_basis(pitch90, attachment())
    assert offset.tolist() == [0.03505, 0.14, 0.0]
    assert bearing.tolist() == pytest.approx([0.2428616822, 0.9700609276], abs=1e-6)
    assert horizontal == pytest.approx(0.14432083945, abs=1e-8)


@pytest.mark.parametrize("invalid", ["reflected", "nonfinite", "offset_zero", "tilted"])
def test_invalid_or_degenerate_outboard_bearing_stops(invalid):
    rotation = np.eye(3)
    registered = attachment()
    reason = "proper rotations"
    if invalid == "reflected":
        rotation[0, 0] = -1.0
    elif invalid == "nonfinite":
        rotation[0, 0] = float("nan")
    elif invalid == "offset_zero":
        registered[1, 3] = 0.0
        reason = "nonzero registered horizontal offset"
    else:
        rotation = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
        reason = "degenerate"
    with pytest.raises(ValueError, match=reason):
        proposal_basis(rotation, registered)
