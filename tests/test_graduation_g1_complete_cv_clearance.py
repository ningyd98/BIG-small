"""The live checker must explain returns on a visible surface and protect both fingers."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def _geometry():
    name = "scripts.graduation.g1_complete_cv_geometry"
    assert importlib.util.find_spec(name), "single-target registered-surface checker unavailable"
    return __import__(name, fromlist=["Model"])


def test_an_occluded_box_never_explains_arbitrary_front_or_back_returns():
    mod = _geometry()
    box = mod.Box("carrier", np.array([0.0, 0.0, 0.35]), np.array([0.05, 0.05, 0.01]), np.eye(3))
    points = np.array([[0, 0, 0.36], [0, 0, 0.41], [0, 0, 0.34], [0.15, 0, 0.36]])
    assert mod.visible_box(points, np.array([0, 0, 1.4]), box, 0.004).tolist() == [
        True,
        False,
        False,
        False,
    ]


def test_side_surface_remains_visible_from_oblique_camera():
    mod = _geometry()
    box = mod.Box("hand", np.zeros(3), np.full(3, 0.035), np.eye(3))
    points = np.array([[0.035, 0, 0], [-0.035, 0, 0], [0, 0.035, 0], [0, 0, 0]])
    assert mod.visible_box(points, np.array([0.5, 0, 1.4]), box, 0.004).tolist() == [
        True,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("assembly", "part"),
    [
        ("scene_g1_development_dual_id7_y115_id8_x115_low_bracket_v3.xml", "crossbar"),
        ("scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml", "crossbar"),
        ("scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml", None),
    ],
)
def test_center_approach_distinguishes_real_carrier_layouts(assembly, part):
    mod = _geometry()
    source = Path(__file__).resolve().parents[1] / "assets/robots/franka_panda" / assembly
    model = mod.Model(source)
    route = model.approach(np.array([0.45, 0, 0.035]), np.eye(3), [0.45, 0, 0.045], 0.039)
    assert route["pair"][1].endswith(part) if part else route["gap_m"] > 0.004
    if part:
        assert route["gap_m"] < 0


def test_actual_between_sample_thin_obstacle_is_in_swept_gripper_volume():
    mod = _geometry()
    a = mod.Box("gripper", np.array([0.0, 0.0, 0.20]), np.array([0.03, 0.008, 0.01]), np.eye(3))
    b = mod.Box("gripper", np.array([0.0, 0.0, 0.04]), a.h, a.r)
    beam = mod.Box(
        "thin_beam", np.array([0.0, 0.0, 0.115]), np.array([0.02, 0.012, 0.001]), np.eye(3)
    )
    assert mod.box_gap(a, beam) > 0.01 and mod.box_gap(b, beam) > 0.01
    assert mod.box_gap(mod.translation_envelope(a, b), beam) < 0


def test_only_independently_measured_empty_table_rays_can_carry_self_occlusion():
    name = "scripts.graduation.g1_complete_cv_clearance"
    assert importlib.util.find_spec(name), "registered RGB-D difference check unavailable"
    mod = __import__(name, fromlist=["depth_changes"])
    old = np.array([[1.4, 1.4, 0.0, 1.4, 1.4]], np.float32)
    now = np.array([[1.396, 1.2, 1.3, 0.0, 1.55]], np.float32)
    new, lost = mod.depth_changes(now, old, 0.004)
    assert new.tolist() == [[False, True, True, False, False]]
    assert lost.tolist() == [[False, False, False, True, True]]


def test_empty_map_requires_original_calibration_and_a_real_axial_return():
    name = "scripts.graduation.g1_complete_cv_calibrate"
    assert importlib.util.find_spec(name), "empty-workspace registration unavailable"
    mod = __import__(name, fromlist=["checked_background"])
    images = [np.array([[1.400, 1.400, 0.0, 0.0]]) for _ in range(3)]
    model = np.array([[1.400, 1.350, 1.400, 0.0]])
    actual, counts = mod.checked_background(images, model, 0.004)
    assert actual.tolist() == [[1.4, 0.0, 0.0, 0.0]]
    assert counts["mismatched"] == 1 and counts["missing"] == 1


def test_native_raster_silhouette_explains_only_its_own_axial_return():
    from scripts.graduation import g1_complete_cv_clearance as mod

    assert hasattr(mod, "robot_raster_matches"), "measured arm contour raster reference unavailable"
    # A near single pixel on the arm edge is a separate physical return. A
    # nearby registered table pixel is never re-labelled as a robot component.
    depth = np.array([0.966, 0.941, 1.40, 0.997])
    predicted_arm = np.array([0.9655, 0.9655, 1.4, 0.0])
    empty_table = np.array([1.4, 1.4, 1.4, 0.0])
    assert mod.robot_raster_matches(depth, predicted_arm, empty_table, 0.004).tolist() == [
        True,
        False,
        False,
        False,
    ]


def test_short_rotating_sweep_contains_each_vertex_and_physical_stop_displacement():
    name = "scripts.graduation.g1_complete_cv_motion"
    assert importlib.util.find_spec(name), "measured eight-tick-and-stop envelope unavailable"
    mod = __import__(name, fromlist=["enclose"])
    geom = _geometry()
    box = geom.Box("finger", np.zeros(3), np.array([0.04, 0.01, 0.005]), np.eye(3))
    end = geom.Box(
        "finger", np.array([0.03, 0.004, 0]), box.h, np.array([[0.0, -1, 0], [1, 0, 0], [0, 0, 1]])
    )
    pad = np.array([0.003, 0.004, 0.002])
    outer = mod.enclose(box, [box.corners(), end.corners()], pad)
    for sample in (box, end):
        assert np.max(np.abs((sample.corners() - outer.c) @ outer.r) + pad - outer.h) <= 1e-12


def test_partial_board_must_have_opposite_depth_and_print_edges():
    name = "scripts.graduation.g1_complete_cv_angle"
    assert importlib.util.find_spec(name), (
        "current single-ID opposing-board pose support unavailable"
    )
    mod = __import__(name, fromlist=["board_center_row"])
    z = np.full((45, 55), 1.4)
    rgb = np.full(z.shape, 100.0)
    z[13:33, 12:43], rgb[13:33, 12:43] = 1.33, 210.0
    z[19:27, 9:48], rgb[19:27, 9:48] = 1.20, 22.0
    edge = mod.board_center_row(z, rgb, [27.0, 22.6], -0.01, 10.0, 1.33, np.arange(18, 38))
    assert edge and abs(edge["center_row"] - 22.5) < 0.1
    z[10:16, 9:46] = 1.20
    assert mod.board_center_row(z, rgb, [27.0, 22.6], -0.01, 10.0, 1.33, np.arange(18, 38)) is None


def test_signed_sweep_proves_separation_and_protects_a_real_midpath_intruder():
    from scripts.graduation import g1_complete_cv_motion as motion

    axes = np.array([[1, 0, 0], [-1, 0, 0], [1, 0, -1], [-1, 0, 1]], float)
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    signs = _geometry().SIGNS
    half = np.array([0.002, 0.002, 0.002])
    centers = np.linspace([0.02, 0, 0.02], [0, 0, 0], 9)
    arm = centers[:, None, :] + signs * half
    # A real stop carries a little farther along the same diagonal.
    measured = np.array([[0, 0, 0], [-0.006, 0, -0.006]])
    residual = (measured @ axes.T).max(axis=0)
    upper = motion.upper_support(arm, axes, residual)
    reflected = np.array([1, 0, 3, 2])
    for center, separated in (([0.017, 0, 0.003], True), ([0.010, 0, 0.010], False)):
        pin = np.array(center) + signs * half
        pin_support = (pin @ axes.T).max(axis=0)
        gap = max(-pin_support[reflected] - upper)
        assert (gap > 0) == separated


def test_directional_refinement_requires_observed_open_phase_pose_and_signed_motion():
    name = "scripts.graduation.g1_complete_cv_support_domain"
    assert importlib.util.find_spec(name), (
        "current 8+240 motion has no measured applicability check"
    )
    mod = __import__(name, fromlist=["domain_row", "locate"])
    q = np.zeros(7)
    dq = np.array([0, 0.30, 0, 0, 0, 0, 0])
    fingers = np.array([0.039, 0.039])
    fvel = np.zeros(2)
    offset = np.array([0.02, 0, 0.08])
    v = np.array([-0.10, 0, -0.15])
    point = np.concatenate((q, dq, fingers, fvel, offset, v))
    assert mod.locate(point, point[None]) == 0
    for change in (
        np.r_[q, -dq, fingers, fvel, offset, -v],
        np.r_[q, dq, [0.020, 0.020], fvel, offset, v],
        np.r_[q, dq * 4, fingers, fvel, offset, v],
        np.r_[q, dq, fingers, fvel, offset + [0, 0.1, 0], v],
    ):
        assert mod.locate(change, point[None]) is None


def test_arbitrary_signed_face_is_a_positive_combination_of_registered_axes():
    from scripts.graduation.g1_complete_cv_motion import DirectionCone, support_axes

    axes = support_axes()
    queried = np.array(
        [[0.01, 0.999, 0.006], [-0.021, -0.996, 0.004], [0.68, 0.44, -0.6], [0.0, 0.0, 1.0]]
    )
    queried /= np.linalg.norm(queried, axis=1, keepdims=True)
    face, weights = DirectionCone(axes).mix(queried)
    assert np.all(weights >= 0.0)
    np.testing.assert_allclose((axes[face] * weights[:, :, None]).sum(1), queried, atol=1e-10)
    points = np.array([[0.02, -0.002, 0.003], [0.001, -0.003, 0.01], [-0.002, 0.04, 0.005]])
    measured = (points @ axes.T).max(0)
    assert np.all((measured[face] * weights).sum(1) >= (points @ queried.T).max(0) - 1e-12)


def test_controlled_cubic_sweep_accounts_for_between_tick_reversal():
    from scripts.graduation import g1_complete_cv_motion as motion

    # With identical endpoints a centrally directed mid-step speed can still
    # travel outside their shared point. The certified cubic derivative is a
    # convex combination of the two measured endpoint velocities and this third.
    start = np.array([[[[0.0, 0.0, 0.0]]], [[[0.0, 0.0, 0.0]]]])
    velocity = np.array([[[[0.24, 0.0, 0.0]]], [[[-0.24, 0.0, 0.0]]]])
    bound = motion.hermite_rate_limits(start, velocity, np.eye(3))
    assert bound[0, 0] >= 0.24
