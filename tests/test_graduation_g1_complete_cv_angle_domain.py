import numpy as np
from scripts.graduation.g1_complete_cv_angle_domain import contact_opportunity

DOWN = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])


def sample(x=0.0, y=0.0, z=0.010, yaw=0.0, fingers=(0.039, 0.039), u=(0.00075, 0.00095, 0.00075)):
    c = np.array([0.45, 0, 0.035])
    a = np.radians(yaw)
    r = np.array([[np.cos(a), -np.sin(a), 0.0], [np.sin(a), np.cos(a), 0.0], [0.0, 0.0, 1.0]])
    return contact_opportunity(
        c,
        r,
        c + r @ np.array([x, y, z]),
        DOWN,
        fingers,
        u,
        yaw_error_deg=abs(yaw) + 0.30,
        yaw_uncertainty_deg=0.3,
        measured_rotation=r,
        support_height=0.0,
    )


def test_support_domain_releases_center_and_registered_joint_height_only():
    for z in (0.005, 0.010, 0.015, 0.020):
        assert sample(z=z)["passes"]
    assert sample(x=-0.0016, y=0.0011, z=0.0138, yaw=2.0)["passes"]
    assert not sample(x=0.008, y=0.002, z=0.021, yaw=2.5)["passes"]


def test_signed_finger_gaps_torque_and_overlap_controls():
    for fingers in ((0.030, 0.039), (0.039, 0.030)):
        assert not sample(fingers=fingers)["passes"]
    for key, args in (
        ("above_table", {"z": -0.016}),
        ("com_supported", {"z": 0.056}),
        ("enough_overlap", {"x": 0.056}),
        ("enough_moment", {"x": 0.060}),
    ):
        d = sample(**args)
        assert not d[key] and not d["passes"]
