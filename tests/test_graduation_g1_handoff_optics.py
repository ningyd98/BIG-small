from types import SimpleNamespace

import numpy as np
import pytest
from scripts.graduation.g1_complete_cv_handoff_optics import directional_error, rigid_pose


def test_error_uses_local_lever_and_actual_world_direction():
    pose = dict(
        anchor_object_m=[0.13, 0, 0],
        anchor_error_object_m=[0.0005, 0.001, 0.0002],
        basis_error_object=[[0, 0, 0], [0.01, 0, 0], [0.003, 0, 0]],
        rotation_object_to_world=[[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    )
    points = [[0.13, 0, 0], [-0.13, 0, 0]]
    assert np.allclose(directional_error(pose, points, [1, 0, 0]), [0.001, 0.0036])
    assert np.allclose(directional_error(pose, points, [0, 1, 0]), [0.0005, 0.0005])
    with pytest.raises(ValueError):
        directional_error(pose, points, [0, 0, 2])


def test_pose_declines_wrong_camera_and_unknown_current_marker():
    asset = {"development_dual": {"scene_id": "s"}}
    assert rigid_pose(SimpleNamespace(source="rgbd_camera"), {}, asset) is None
    assert rigid_pose(SimpleNamespace(source="mujoco_camera", scene_id="bad"), {}, asset) is None
    assert (
        rigid_pose(SimpleNamespace(source="mujoco_camera", scene_id="s"), {"usable": False}, asset)
        is None
    )
