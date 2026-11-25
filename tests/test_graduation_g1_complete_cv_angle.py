import numpy as np
import pytest
from scripts.graduation import g1_complete_cv_angle as angle


def test_closure_checks_both_pads_and_locked_mechanical_offsets():
    basis = np.eye(3)
    x = [0.001, -0.0005, 0.010]
    good = angle.grasp_patch(np.zeros(3), basis, x, basis, [0.039, 0.039], xy_uncertainty_m=0.0004)
    assert good["passes"] and good["minimum_inside_gap_m"] > 0
    assert not angle.grasp_patch(
        np.zeros(3), basis, [0.017, 0, 0.010], basis, [0.039, 0.039], xy_uncertainty_m=0.0004
    )["passes"]
    assert not angle.grasp_patch(
        np.zeros(3), basis, [0, 0.006, 0.010], basis, [0.039, 0.039], xy_uncertainty_m=0.0004
    )["passes"]
    assert not angle.grasp_patch(
        np.zeros(3), basis, x, basis, [0.033, 0.033], xy_uncertainty_m=0.0004
    )["passes"]


def test_angle_bound_uses_measured_wrist_yaw_and_original_equality():
    ang = angle.angle_error_deg(1.75, 0.25, np.eye(3), closure=True)
    assert ang == pytest.approx(2.0)
    wrist = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert angle.angle_error_deg(90.0, 0.25, wrist, closure=True) == pytest.approx(0.25)
    assert angle.angle_error_deg(2.25, 0.25, np.eye(3), closure=True) == pytest.approx(2.5)
