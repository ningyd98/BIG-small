"""Registered RGB/depth rendering in optical camera coordinates."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import numpy as np

from cloud_edge_robot_arm.simulation.models import SensorFrame


class MuJoCoRGBDCamera:
    def __init__(self, mujoco: Any, model: Any, *, width: int, height: int) -> None:
        self._mujoco = mujoco
        self._model = model
        self._width = width
        self._height = height
        self._camera_id = model.camera("rgbd").id
        self._renderer = mujoco.Renderer(model, height=height, width=width)

    def capture(self, data: Any, *, rng: Any, noise_std_m: float) -> SensorFrame:
        started = perf_counter()
        self._renderer.disable_depth_rendering()
        self._renderer.update_scene(data, camera=self._camera_id)
        rgb = self._renderer.render().copy()
        self._renderer.enable_depth_rendering()
        depth = self._renderer.render().copy()
        self._renderer.disable_depth_rendering()
        valid = np.isfinite(depth) & (depth > 0) & (depth < 10.0)
        if noise_std_m:
            depth[valid] += rng.normal(0, noise_std_m, size=int(valid.sum()))
        depth[~valid | (depth <= 0)] = 0
        # MuJoCo camera: +X right, +Y up, -Z forward; optical: +Y down, +Z forward.
        optical_to_world = np.asarray(data.cam_xmat[self._camera_id]).reshape(3, 3) @ np.diag([1, -1, -1])
        transform = np.eye(4)
        transform[:3, :3] = optical_to_world
        transform[:3, 3] = data.cam_xpos[self._camera_id]
        focal = (self._height / 2) / math.tan(math.radians(float(self._model.cam_fovy[self._camera_id])) / 2)
        return SensorFrame(
            frame_id="rgbd", sim_time_s=float(data.time), width=self._width, height=self._height,
            rgb=rgb.tobytes(), depth=tuple(float(value) for value in depth.ravel()),
            intrinsics=(focal, focal, (self._width - 1) / 2, (self._height - 1) / 2),
            camera_to_world=tuple(float(value) for value in transform.ravel()),
            captured_at=datetime.now(UTC), latency_ms=(perf_counter() - started) * 1000,
        )

    def close(self) -> None:
        self._renderer.close()
