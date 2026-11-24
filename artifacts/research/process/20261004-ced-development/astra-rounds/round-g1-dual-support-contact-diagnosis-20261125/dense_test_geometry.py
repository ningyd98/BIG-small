import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dense_geometry as geom


def test_only_actual_intersection_in_observed_box_is_forbidden():
    box = (np.zeros(3), np.eye(3), np.array([2.0, 1.0, 1.0]))
    cut = geom.intersect(box, np.array([1.5, -0.5, -0.5]), np.array([3.0, 0.5, 0.5]))
    assert cut["positive_3d_volume"]
    assert np.allclose(cut["min_m"], [1.5, -0.5, -0.5])
    assert np.allclose(cut["max_m"], [2.0, 0.5, 0.5])
    assert np.isclose(cut["volume_m3"], 0.5)


def test_touching_face_is_not_positive_intersection_volume():
    box = (np.zeros(3), np.eye(3), np.ones(3))
    cut = geom.intersect(box, np.array([1.0, -0.5, -0.5]), np.array([1.0, 0.5, 0.5]))
    assert not cut["positive_3d_volume"] and len(cut["vertices_m"]) == 4
    assert abs(geom.axes(box[1])[0] @ np.ones(3)).max() >= 1
