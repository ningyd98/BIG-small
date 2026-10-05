"""synthetic_fixture：第三方离线观察的单位、标定与真值边界。"""

import io

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.external.models import (
    DatasetSample,
    backproject_depth,
    decode_image,
    metric_depth,
    validate_transform,
)


def sample(**kwargs):
    return DatasetSample(
        dataset_id="synthetic_fixture",
        source_revision="a" * 40,
        sample_kind="trajectory_observation",
        source_file="fixture.h5",
        relative_path="fixture.h5",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split="train",
        rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        depth_raw=np.ones((2, 3), dtype=np.uint16),
        **kwargs,
    )


def test_encoded_rgb_is_not_swapped_twice():
    rgb = np.array([[[255, 0, 0], [0, 0, 255]]], dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    decoded = decode_image(np.frombuffer(buffer.getvalue(), dtype=np.uint8), kind="rgb")
    np.testing.assert_array_equal(decoded, rgb)


def test_raw_bgr_swapped_once():
    bgr = np.array([[[0, 0, 255]]], dtype=np.uint8)
    np.testing.assert_array_equal(
        decode_image(bgr, kind="rgb", raw_color_order="BGR"),
        np.array([[[255, 0, 0]]], dtype=np.uint8),
    )


def test_encoded_depth_keeps_sixteen_bits():
    raw = np.array([[0, 1200, 65000]], dtype=np.uint16)
    buffer = io.BytesIO()
    Image.fromarray(raw).save(buffer, format="PNG")
    decoded = decode_image(buffer.getvalue(), kind="depth")
    assert decoded.dtype == np.uint16
    np.testing.assert_array_equal(decoded, raw)


def test_metric_depth_needs_evidence_and_masks_invalid():
    raw = np.array([[0, 1500, np.nan, np.inf, -1]], dtype=np.float32)
    missing, mask = metric_depth(raw, None, None)
    assert missing is None
    assert mask.tolist() == [[False, True, False, False, False]]
    metres, _ = metric_depth(raw, 0.001, "official BOP depth_scale=1")
    assert metres.dtype == np.float32
    np.testing.assert_allclose(metres, [[0, 1.5, 0, 0, 0]], rtol=1e-6)
    with pytest.raises(ValueError, match="evidence"):
        metric_depth(raw, 0.001, None)


def test_no_fabricated_calibration_or_timestamp_and_gt_separate():
    item = sample(annotations={"object_pose": [1, 2, 3]})
    assert item.timestamp is None and item.K_depth is None
    assert not item.capabilities["camera_geometry"]
    assert "annotations" not in item.model_input()
    assert "object_pose" not in item.model_input()
    assert item.depth_m is None


def test_backprojection_requires_corresponding_intrinsics():
    item = sample(depth_scale_m=0.001, depth_scale_evidence="fixture explicit mm")
    with pytest.raises(ValueError, match="intrinsics"):
        backproject_depth(item)
    calibrated = sample(
        depth_scale_m=0.001,
        depth_scale_evidence="fixture explicit mm",
        depth_semantics="optical_z",
        K_depth=np.array([[2, 0, 1], [0, 2, 1], [0, 0, 1]], dtype=float),
    )
    assert backproject_depth(calibrated).shape == (6, 3)
    with pytest.raises(ValueError, match="alignment"):
        backproject_depth(calibrated, with_rgb=True)


def test_transform_requires_named_direction_and_metric_translation():
    with pytest.raises(ValueError, match="direction"):
        validate_transform({"matrix": np.eye(4).tolist()})
    with pytest.raises(ValueError, match="unit"):
        validate_transform(
            {
                "matrix": np.eye(4).tolist(),
                "from_frame": "camera",
                "to_frame": "base",
                "translation_unit": "unknown",
            }
        )


def test_empty_depth_cannot_be_valid_rgbd():
    with pytest.raises(ValueError):
        sample(depth_scale_m=0, depth_scale_evidence="bad scale")


def test_empty_rgb_is_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        DatasetSample(
            dataset_id="synthetic_fixture",
            source_revision="a" * 40,
            sample_kind="trajectory_observation",
            source_file="test.h5",
            relative_path="test.h5",
            source_sha256="b" * 64,
            frame_index=0,
            camera_id="top",
            official_split="train",
            rgb=np.zeros((0, 3, 3), dtype=np.uint8),
            depth_raw=np.ones((2, 3), dtype=np.uint16),
        )


def test_robot_base_requires_depth_geometry_and_camera_transform():
    transform = {
        "matrix": np.eye(4).tolist(),
        "from_frame": "object_model",
        "to_frame": "robot_base",
        "translation_unit": "m",
    }
    assert not sample(transforms={"object_to_base": transform}).capabilities["robot_base_geometry"]
