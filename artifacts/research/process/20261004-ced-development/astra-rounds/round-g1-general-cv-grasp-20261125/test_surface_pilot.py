"""Analytic checks for the independent surface and aperture calculations."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
from surface_pilot import color_surface, width_check


def patches(positions, *, valid=True, color=(215, 23, 21)):
    frame = SimpleNamespace(camera_to_world=np.eye(4).ravel(), intrinsics=(200, 200, 30, 30))
    rgb = np.zeros((64, 64, 3), np.uint8)
    for x, y, width in positions:
        rgb[y : y + width, x : x + width] = color
    depth = np.ones(rgb.shape[:2])
    return color_surface(frame, rgb, depth, np.full(depth.shape, valid), [0.070, 0.070], 0.004)


def test_unique_surface_has_expected_metric_center():
    result = patches([(6, 7, 15)])
    assert result["status"] == "SUPPORTED"
    np.testing.assert_allclose(result["top_center_m"], [-0.085, -0.080, 1])


@pytest.mark.parametrize(
    ("positions", "settings", "reason"),
    [
        ([(6, 7, 15)], {"valid": False}, "insufficient_interior_depth"),
        ([(6, 7, 15)], {"color": (60, 60, 60)}, "no_qualifying_surface"),
        ([(6, 7, 15), (32, 35, 15)], {}, "multiple_qualifying_surfaces"),
        ([(6, 7, 6)], {}, "unsupported_extent"),
    ],
)
def test_missing_ambiguous_and_wrong_size_return_unknown(positions, settings, reason):
    result = patches(positions, **settings)
    assert result["top_center_m"] is None and result["status"] == "UNKNOWN"
    assert reason in [result["reason"], *(c.get("reason") for c in result["candidates"])]


def test_width_sweep_and_both_equalities():
    width = width_check(0.070, 0.070, 0.082)
    assert [v["angle_deg"] for v in width["sweep"]] == list(range(91))
    left, right = width["allowed_by_width_deg_inclusive"]
    assert left[0] == 0 and right[1] == 90
    for limit in (left[1], right[0]):
        theta = math.radians(limit)
        assert math.isclose(0.070 * (math.sin(theta) + math.cos(theta)), 0.082, abs_tol=1e-12)
    assert width["sweep"][0]["remaining_mm"] == pytest.approx(12.0)
    assert width["sweep"][45]["remaining_mm"] == pytest.approx(82 - 70 * math.sqrt(2))
