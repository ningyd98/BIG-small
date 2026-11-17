"""Camera translation improves marker sampling while keeping all known features visible."""

import numpy as np
import pytest


def test_camera_framing_keeps_current_and_final_features_inside_image():
    from cloud_edge_robot_arm.vision.camera_positioning import position_camera_for_features

    points = np.array([
        [0.41, -0.04, 0.18], [0.49, 0.04, 0.18],
        [0.12, 0.17, 0.004], [0.28, 0.33, 0.004],
        [0.1625, 0.3525, 0.07], [0.2375, 0.4275, 0.07],
        [0.4125, 0.1025, 0.18], [0.4875, 0.1775, 0.18],
    ])
    intrinsics = (257.34, 257.34, 159.5, 119.5)
    position = position_camera_for_features(
        points, current_position_m=(0.35, 0, 1.35), intrinsics=intrinsics,
        image_size=(320, 240), marker_size_m=0.075, lowest_marker_z_m=0.07,
    )
    assert position is not None and 0.6 <= position[2] < 1.35
    camera = (points - position) * np.array([1, -1, -1])
    pixels = camera[:, :2] / camera[:, 2, None] * intrinsics[:2] + intrinsics[2:]
    assert (pixels >= 16).all() and (pixels <= np.array([303, 223])).all()
    old_side = intrinsics[1] * 0.075 / (1.35 - 0.07)
    assert intrinsics[1] * 0.075 / (position[2] - 0.07) > 1.8 * old_side


def test_framing_never_returns_a_camera_outside_development_workspace():
    from cloud_edge_robot_arm.vision.camera_positioning import position_camera_for_features

    assert position_camera_for_features(
        np.array([[-2, -2, 0], [2, 2, 0.2]]),
        current_position_m=(0.35, 0, 1.35), intrinsics=(257, 257, 159.5, 119.5),
        image_size=(320, 240), marker_size_m=0.075, lowest_marker_z_m=0.07,
    ) is None


def test_oblique_framing_aims_at_measured_features_and_keeps_marker_sampled():
    from cloud_edge_robot_arm.vision.camera_positioning import oblique_camera_for_features

    points = np.array([[x, y, z] for x, y, z in (
        (0.45, 0.14, 0.18), (0.20, 0.39, 0.07),
    ) for x, y in ((x - 0.0375, y - 0.0375), (x + 0.0375, y - 0.0375),
                   (x + 0.0375, y + 0.0375), (x - 0.0375, y + 0.0375))])
    features = np.vstack((points, [[0.12, 0.17, 0.004], [0.28, 0.33, 0.004]]))
    result = oblique_camera_for_features(
        features, marker_corners_m=points, intrinsics=(257, 257, 159.5, 119.5),
        image_size=(320, 240), current_height_m=1.35,
    )
    assert result is not None
    position, aim = result
    backward = np.array(position) - aim
    assert np.linalg.norm(backward[:2]) / backward[2] > 0.35
    backward /= np.linalg.norm(backward)
    right = np.cross([0, 1, 0], backward)
    right /= np.linalg.norm(right)
    up = np.cross(backward, right)
    optical = np.column_stack((right, -up, -backward))
    camera = (features - position) @ optical
    pixels = camera[:, :2] / camera[:, 2, None] * 257 + [159.5, 119.5]
    assert np.all(pixels >= 16) and np.all(pixels <= [303, 223])
    assert np.linalg.norm(np.roll(pixels[:4], -1, axis=0) - pixels[:4], axis=1).min() > 18


@pytest.mark.parametrize("direction", [(-1, 0), (1, 0)])
def test_side_view_can_frame_registered_marker_and_region_without_hidden_body_extent(direction):
    from cloud_edge_robot_arm.vision.camera_positioning import oblique_camera_for_features

    corners = np.array([[x + dx, y + dy, z] for x, y, z in (
        (0.45, 0.14, 0.18), (0.20, 0.39, 0.07),
    ) for dx, dy in ((-0.0375, -0.0375), (0.0375, -0.0375),
                     (0.0375, 0.0375), (-0.0375, 0.0375))])
    features = np.vstack((corners, [[0.12, 0.17, 0.004], [0.28, 0.33, 0.004]]))
    view = oblique_camera_for_features(
        features, marker_corners_m=corners, intrinsics=(257, 257, 159.5, 119.5),
        image_size=(320, 240), current_height_m=1.35, view_direction_xy=direction,
        angles_deg=(35,), image_margin_px=8,
        look_at_m=(0.303, 0.196, 0.09),
    )
    assert view is not None and view[0][2] == pytest.approx(0.6)
    assert view[1] == (0.303, 0.196, 0.09)
