"""RGB-D must come from rendered cameras and preserve metric geometry."""

from __future__ import annotations

import base64
import io
import struct
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from PIL import Image
from pydantic import ValidationError

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig, SensorFrame
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def observation_payload() -> dict[str, object]:
    image = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 0, 0)).save(image, format="PNG")
    return {
        "frame_id": "test-camera",
        "captured_at": datetime.now(UTC).isoformat(),
        "sim_time_s": 0.0,
        "width": 2,
        "height": 2,
        "rgb_png_base64": base64.b64encode(image.getvalue()).decode(),
        "depth_float32_base64": base64.b64encode(struct.pack("<4f", 2, 2, 2, 0)).decode(),
        "intrinsics": [2, 2, 0, 0],
        "camera_to_world": [1, 0, 0, 1, 0, 1, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1],
        "source": "mujoco_camera",
    }


@pytest.fixture
def sensor_frame() -> SensorFrame:
    return SensorFrame(
        frame_id="historical-camera-frame",
        captured_at=datetime(2020, 1, 1, tzinfo=UTC),
        sim_time_s=0.0,
        width=2,
        height=2,
        rgb=bytes((255, 0, 0)) * 4,
        depth=(2.0, 2.0, 2.0, 0.0),
        intrinsics=(2.0, 2.0, 0.0, 0.0),
        camera_to_world=(1, 0, 0, 1, 0, 1, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1),
    )


def test_sensor_frame_requires_acquisition_timestamp(sensor_frame: SensorFrame) -> None:
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

    with pytest.raises(ValueError, match="captured_at"):
        observation_from_sensor_frame(
            replace(sensor_frame, captured_at=None), source="mujoco_camera"
        )


def test_historical_sensor_frame_preserves_acquisition_timestamp(sensor_frame: SensorFrame) -> None:
    from cloud_edge_robot_arm.vision.observations import (
        RGBDObservation,
        observation_from_sensor_frame,
    )

    observation = observation_from_sensor_frame(sensor_frame, source="mujoco_camera")
    restored = RGBDObservation.model_validate_json(observation.model_dump_json())
    assert restored.captured_at == datetime(2020, 1, 1, tzinfo=UTC)
    assert restored.crop((0, 0, 1, 1)).captured_at == restored.captured_at


@pytest.mark.parametrize("length", [11, 13])
def test_sensor_frame_rejects_wrong_rgb_payload_length(
    sensor_frame: SensorFrame, length: int
) -> None:
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

    with pytest.raises(ValueError):
        observation_from_sensor_frame(
            replace(sensor_frame, rgb=bytes(length)), source="mujoco_camera"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"width": 0},
        {"width": -1},
        {"width": 1281},
        {"height": 0},
        {"height": 721},
        {"width": 1.5},
        {"rgb": bytes(11)},
        {"rgb": bytes(13)},
        {"depth": (2.0,) * 3},
        {"depth": (2.0,) * 5},
    ],
)
def test_sensor_frame_validates_bounds_and_payloads_before_encoding(
    sensor_frame: SensorFrame, changes: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

    def unexpected_encoding(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid raw RGB-D reached image encoding")

    monkeypatch.setattr(Image, "frombytes", unexpected_encoding)
    with pytest.raises(ValueError):
        observation_from_sensor_frame(replace(sensor_frame, **changes), source="mujoco_camera")


def test_mujoco_camera_produces_registered_rgb_and_metric_depth() -> None:
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        frame = backend.get_sensor_frame()
        assert frame.rgb is not None
        assert frame.width == 320 and frame.height == 240
        assert len(frame.rgb) == frame.width * frame.height * 3
        assert len(frame.depth) == frame.width * frame.height
        assert min(d for d in frame.depth if d > 0) > 0.01
        assert frame.object_detections == []
        assert len(frame.camera_to_world) == 16
    finally:
        backend.shutdown()


def test_metric_depth_backprojects_with_calibration() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    observation = RGBDObservation.model_validate(observation_payload())
    point = observation.world_point((1, 0))
    assert (point.x, point.y, point.z) == pytest.approx((2, 2, 5))
    with pytest.raises(ValueError, match="depth"):
        observation.world_point((1, 1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("depth_float32_base64", "AAAA"),
        ("rgb_png_base64", "not-base64"),
        ("width", 1281),
        ("intrinsics", [0, 2, 0, 0]),
        ("camera_to_world", [0] * 16),
    ],
)
def test_invalid_rgbd_is_rejected(field: str, value: object) -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    payload = observation_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        RGBDObservation.model_validate(payload)


def test_depth_visualization_has_same_resolution_as_rgb() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    observation = RGBDObservation.model_validate(observation_payload())
    image = Image.open(io.BytesIO(base64.b64decode(observation.depth_png_base64())))
    assert image.size == (2, 2)
    assert image.getpixel((0, 0)) != image.getpixel((1, 1))


def test_default_camera_has_visible_target_surface() -> None:
    from cloud_edge_robot_arm.vision.capture import capture_simulated_observation

    observation = capture_simulated_observation()
    image = Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64)))
    red_pixels = sum(1 for r, g, b in image.get_flattened_data() if r - g > 50 and r - b > 50)
    assert red_pixels > 100, "the initial arm pose must not hide the cube from the visual planner"


def test_legacy_observation_stays_unbound_and_crop_preserves_identity() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    observation = RGBDObservation.model_validate(observation_payload())
    assert observation.observation_id == observation.frame_id
    assert observation.model_dump()["observation_id"] == "test-camera"
    assert observation.scene_id is None and observation.episode_id is None
    assert observation.calibration_version is None
    assert observation.valid_mask_bytes() == bytes((1, 1, 1, 0))
    assert observation.crop((0, 0, 1, 1)).observation_id == observation.observation_id


def test_invalid_depth_and_calibration_rejected() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    for value in (float("nan"), -1.0):
        payload = observation_payload()
        payload["depth_float32_base64"] = base64.b64encode(
            struct.pack("<4f", 2, 2, 2, value)
        ).decode()
        with pytest.raises(ValidationError):
            RGBDObservation.model_validate(payload)
    payload = observation_payload()
    payload["camera_to_world"] = [0] * 16
    with pytest.raises(ValidationError):
        RGBDObservation.model_validate(payload)
    payload = observation_payload()
    payload["valid_mask_base64"] = base64.b64encode(bytes((1, 1, 1, 1))).decode()
    with pytest.raises(ValidationError):
        RGBDObservation.model_validate(payload)
    observation = RGBDObservation.model_validate(observation_payload())
    with pytest.raises(ValueError, match="invalid depth"):
        observation.world_point((1, 1))
    payload = observation.model_dump()
    payload["scene_id"] = "altered"
    with pytest.raises(ValidationError, match="checksum"):
        RGBDObservation.model_validate(payload)
    for field, altered in (
        ("captured_at", datetime(2020, 1, 1, tzinfo=UTC)),
        ("sim_time_s", 3.0),
        ("source", "isaac_camera"),
    ):
        payload = observation.model_dump()
        payload[field] = altered
        with pytest.raises(ValidationError, match="checksum"):
            RGBDObservation.model_validate(payload)
