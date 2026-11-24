"""The independent plane-to-image readback must respect perspective and marker yaw."""

import importlib.util
from types import SimpleNamespace

import numpy as np
import pytest


def test_inverse_projection_respects_ordered_grid_axes_and_optical_depth():
    module = "scripts.graduation.g1_mount_screen_verify"
    assert importlib.util.find_spec(module), "missing independent screen readback"
    from scripts.graduation.g1_mount_screen_verify import local_points

    # Camera x points right, camera y points backwards on the table, camera z points down.
    f = SimpleNamespace(
        camera_to_world=[1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 2, 0, 0, 0, 1],
        intrinsics=[100, 100, 5, 5],
        width=11,
        height=11,
    )
    world = np.array([[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 1], [0, 0, 0, 1]])
    x, y, z = local_points(f, world)
    assert [x[5, 5], y[5, 5], z[5, 5]] == pytest.approx([0, 0, 1])
    assert [x[7, 8], y[7, 8], z[7, 8]] == pytest.approx([-0.02, -0.03, 1])
    world[2, 3] = 0
    x, y, z = local_points(f, world)
    assert [x[7, 8], y[7, 8], z[7, 8]] == pytest.approx([-0.04, -0.06, 2])
