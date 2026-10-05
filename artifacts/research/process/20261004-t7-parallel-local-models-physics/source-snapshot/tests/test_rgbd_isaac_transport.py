"""Registered Isaac camera arrays survive the JSONL transport without detections."""
import base64
from datetime import UTC, datetime

import numpy as np

from cloud_edge_robot_arm.simulation.isaac.backend import IsaacSimBackend
from tests.test_rgbd_observations import observation_payload


def test_isaac_backend_preserves_pixels_depth_and_calibration() -> None:
    p = observation_payload()
    sensor = {"frame_id": "actual-camera", "width": 2, "height": 2, "object_detections": [], "latency_ms": 1,
              "rgb_base64": base64.b64encode(bytes([255, 0, 0] * 4)).decode(),
              "depth_float32_base64": p["depth_float32_base64"], "intrinsics": p["intrinsics"],
              "camera_to_world": p["camera_to_world"], "captured_at": datetime.now(UTC).isoformat()}
    frame = IsaacSimBackend()._parse_sensor_frame({"sim_time_s": 0, "sensor_frame": sensor})
    assert frame.rgb == bytes([255, 0, 0] * 4)
    assert frame.depth == (2, 2, 2, 0)
    assert len(frame.intrinsics) == 4 and len(frame.camera_to_world) == 16


def test_standalone_sensor_payload_uses_actual_arrays() -> None:
    from scripts.phase9.isaac_standalone_app import encode_rgbd_sensor_frame

    class Camera:
        def get_intrinsics_matrix(self):
            return np.array([[2, 0, 0], [0, 2, 0], [0, 0, 1]])

        def get_world_pose(self, camera_axes):
            assert camera_axes == "ros"
            return np.array([1, 2, 3]), np.array([1, 0, 0, 0])

    payload = encode_rgbd_sensor_frame(Camera(), np.full((2, 2, 4), 255, dtype=np.uint8), np.array([[2, 2], [2, np.inf]]))
    assert len(base64.b64decode(payload["rgb_base64"])) == 12
    frame = IsaacSimBackend()._parse_sensor_frame({"sim_time_s": 0, "sensor_frame": {
        "frame_id": "camera", "width": 2, "height": 2, "object_detections": [], "latency_ms": 1, **payload}})
    assert frame.depth[-1] == 0
