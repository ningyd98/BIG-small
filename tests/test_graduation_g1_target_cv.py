import numpy as np
from scripts.graduation import g1_target_cv as cv


def test_only_incompatible_depths_and_missing_print_rim_can_disprove_an_island():
    z = np.ones(36)
    z[:15] -= 0.30
    rim = np.zeros((4, 7))
    assert cv.incompatible_print(z, rim, marker_size_m=0.075, edge_contrast=32)
    assert not cv.incompatible_print(np.ones(36), rim, marker_size_m=0.075, edge_contrast=32)
    z[3] = 0
    assert not cv.incompatible_print(z, rim, marker_size_m=0.075, edge_contrast=32)
    z[3] = 0.7
    rim[1] = 80
    assert not cv.incompatible_print(z, rim, marker_size_m=0.075, edge_contrast=32)


def test_green_support_requires_measured_plane_color_and_reference():
    colors = np.array([[80, 160, 100], [90, 90, 90], [120, 70, 70], [80, 160, 100]])
    expected = np.array([0.1, 0.6, 0.2])
    support = cv.current_shaded_green(colors, expected, np.array([0.0, 0.0, 0.0, 0.032]), 0.008)
    assert support.tolist() == [True, False, False, False]


def test_complete_region_must_match_original_world_bounds_including_height():
    original = dict(min=[0.1, 0.2, 0.0], max=[0.3, 0.4, 0.0], uncertainty_m=[0.003, 0.003, 0.002])
    assert cv.same_region(original, dict(original))
    assert not cv.same_region(
        original, {**original, "min": [0.14, 0.2, 0.0], "max": [0.34, 0.4, 0.0]}
    )
    assert not cv.same_region(
        original, {**original, "min": [0.1, 0.2, 0.03], "max": [0.3, 0.4, 0.03]}
    )
