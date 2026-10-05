"""Vision prompts carry aligned images without offline labels or scene truth."""

from __future__ import annotations

import base64
import io
import json
import struct
from datetime import UTC, datetime

import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _observation() -> RGBDObservation:
    rgb = Image.new("RGB", (8, 4), (240, 10, 10))
    for y in range(4):
        for x in range(4, 8):
            rgb.putpixel((x, y), (10, 240, 10))
    encoded_rgb = io.BytesIO()
    rgb.save(encoded_rgb, format="PNG")
    depths = [2.0 if x < 4 else 4.0 for _ in range(4) for x in range(8)]
    return RGBDObservation.model_validate(
        {
            "frame_id": "oracle-target-secret",
            "scene_id": "oracle-scene-secret",
            "episode_id": "oracle-episode-secret",
            "calibration_version": "oracle-calibration-secret",
            "captured_at": datetime.now(UTC),
            "sim_time_s": 0.0,
            "width": 8,
            "height": 4,
            "rgb_png_base64": base64.b64encode(encoded_rgb.getvalue()).decode(),
            "depth_float32_base64": base64.b64encode(struct.pack("<32f", *depths)).decode(),
            "intrinsics": (8.0, 4.0, 0.0, 0.0),
            "camera_to_world": (1, 0, 0, 1, 0, 1, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1),
            "source": "mujoco_camera",
        }
    )


def test_wire_payload_contains_two_images_no_truth() -> None:
    """Catches image omission, misregistration and leakage of observation sidecars."""
    from cloud_edge_robot_arm.vision.messages import build_visual_messages

    messages = build_visual_messages("pick the cube", _observation(), image_size=(4, 4))
    wire = json.dumps({"model": "qwen3.5:4b", "messages": messages})
    assert all(secret not in wire for secret in (
        "oracle-target-secret", "oracle-scene-secret", "oracle-episode-secret",
        "oracle-calibration-secret",
    ))
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "pick the cube" in messages[1]["content"]
    images = messages[1]["images"]
    assert isinstance(images, list) and len(images) == 2
    assert images[0] != images[1]
    with Image.open(io.BytesIO(base64.b64decode(images[0]))) as rgb:
        assert rgb.format == "PNG" and rgb.mode == "RGB" and rgb.size == (4, 2)
        assert rgb.getpixel((0, 0)) == (240, 10, 10)
        assert rgb.getpixel((3, 0)) == (10, 240, 10)
    with Image.open(io.BytesIO(base64.b64decode(images[1]))) as depth:
        assert depth.format == "PNG" and depth.mode == "L" and depth.size == (4, 2)
        assert depth.getpixel((0, 0)) == 255
        assert depth.getpixel((3, 0)) == 1
    assert "4x2" in wire
    assert "8x4" in wire


def test_scaled_pixels_map_to_original_depth() -> None:
    """Catches using model pixels directly as original metric-depth indices."""
    from cloud_edge_robot_arm.vision.messages import (
        build_visual_messages,
        display_to_observation_pixel,
    )

    observation = _observation()
    build_visual_messages("pick the cube", observation, image_size=(4, 4))
    original_pixel = display_to_observation_pixel((2, 0), observation, image_size=(4, 4))
    assert original_pixel == (5, 1)
    point = observation.world_point(original_pixel)
    assert (point.x, point.y, point.z) == pytest.approx((3.5, 3.0, 7.0))
    assert display_to_observation_pixel((0, 0), observation, image_size=(4, 4)) == (1, 1)
    assert display_to_observation_pixel((3, 1), observation, image_size=(4, 4)) == (7, 3)
    assert display_to_observation_pixel((7, 3), observation) == (7, 3)


def test_display_pixel_outside_transmitted_image_is_rejected() -> None:
    """Catches invalid model coordinates wrapping into a different depth pixel."""
    from cloud_edge_robot_arm.vision.messages import display_to_observation_pixel

    observation = _observation()
    for pixel in ((-1, 0), (4, 0), (0, 2), (1.5, 0), (True, 0)):
        with pytest.raises(ValueError, match="outside|integer"):
            display_to_observation_pixel(pixel, observation, image_size=(4, 4))
