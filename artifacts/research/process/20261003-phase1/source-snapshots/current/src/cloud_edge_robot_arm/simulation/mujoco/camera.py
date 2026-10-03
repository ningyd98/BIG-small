"""Registered RGB/depth rendering in optical camera coordinates."""

from __future__ import annotations

import hashlib
import math
import struct
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import numpy as np

from cloud_edge_robot_arm.simulation.models import SensorFrame


class MuJoCoRGBDCamera:
    def __init__(self, mujoco: Any, model: Any, *, width: int, height: int) -> None:
        self._mujoco = mujoco
        self._model = model
        self._width = width
        self._height = height
        self._camera_id = model.camera("rgbd").id
        model.vis.global_.offwidth = max(model.vis.global_.offwidth, width)
        model.vis.global_.offheight = max(model.vis.global_.offheight, height)
        self._renderer = mujoco.Renderer(model, height=height, width=width)

    def capture(
        self,
        data: Any,
        *,
        rng: Any,
        noise_std_m: float,
        scene_id: str | None = None,
        episode_id: str | None = None,
    ) -> SensorFrame:
        frame, _, _, _ = self._capture(
            data,
            rng=rng,
            noise_std_m=noise_std_m,
            scene_id=scene_id,
            episode_id=episode_id,
            include_instances=False,
        )
        return frame

    def capture_with_instances(
        self,
        data: Any,
        *,
        rng: Any,
        noise_std_m: float,
        scene_id: str | None = None,
        episode_id: str | None = None,
    ) -> tuple[SensorFrame, tuple[int, ...], dict[int, str], tuple[str, ...]]:
        return self._capture(
            data,
            rng=rng,
            noise_std_m=noise_std_m,
            scene_id=scene_id,
            episode_id=episode_id,
            include_instances=True,
        )

    @staticmethod
    def _physics_state_hash(data: Any) -> str:
        digest = hashlib.sha256(struct.pack("<d", float(data.time)))
        for name in ("qpos", "qvel", "act", "ctrl"):
            values = np.asarray(getattr(data, name), dtype="<f8")
            digest.update(struct.pack("<I", values.size))
            digest.update(values.tobytes())
        return digest.hexdigest()

    def _capture(
        self,
        data: Any,
        *,
        rng: Any,
        noise_std_m: float,
        scene_id: str | None,
        episode_id: str | None,
        include_instances: bool,
    ) -> tuple[SensorFrame, tuple[int, ...], dict[int, str], tuple[str, ...]]:
        captured_at = datetime.now(UTC)
        started = perf_counter()
        initial_hash = self._physics_state_hash(data)
        camera_position = np.asarray(data.cam_xpos[self._camera_id]).copy()
        camera_rotation = np.asarray(data.cam_xmat[self._camera_id]).copy()
        camera_fovy = float(self._model.cam_fovy[self._camera_id])
        depth_znear = float(self._model.vis.map.znear)
        depth_zfar = float(self._model.vis.map.zfar)
        depth_extent = float(self._model.stat.extent)

        def check_calibration() -> None:
            if (
                not np.array_equal(data.cam_xpos[self._camera_id], camera_position)
                or not np.array_equal(data.cam_xmat[self._camera_id], camera_rotation)
                or float(self._model.cam_fovy[self._camera_id]) != camera_fovy
                or float(self._model.vis.map.znear) != depth_znear
                or float(self._model.vis.map.zfar) != depth_zfar
                or float(self._model.stat.extent) != depth_extent
            ):
                raise RuntimeError("camera calibration changed during capture")

        self._renderer.disable_depth_rendering()
        self._renderer.disable_segmentation_rendering()
        self._renderer.update_scene(data, camera=self._camera_id)
        if self._physics_state_hash(data) != initial_hash:
            raise RuntimeError("physics state changed while preparing camera scene")
        check_calibration()
        pass_hashes: list[str] = []
        rgb = self._renderer.render().copy()
        pass_hashes.append(self._physics_state_hash(data))
        if pass_hashes[-1] != initial_hash:
            raise RuntimeError("physics state changed during RGB render")
        check_calibration()
        self._renderer.enable_depth_rendering()
        depth = self._renderer.render().copy()
        pass_hashes.append(self._physics_state_hash(data))
        if pass_hashes[-1] != initial_hash:
            raise RuntimeError("physics state changed during depth render")
        check_calibration()
        self._renderer.disable_depth_rendering()
        instance_ids: tuple[int, ...] = ()
        instance_labels: dict[int, str] = {}
        if include_instances:
            self._renderer.enable_segmentation_rendering()
            segmentation = self._renderer.render().copy()
            self._renderer.disable_segmentation_rendering()
            pass_hashes.append(self._physics_state_hash(data))
            if pass_hashes[-1] != initial_hash:
                raise RuntimeError("physics state changed during instance render")
            check_calibration()
            geom_pixels = np.where(
                segmentation[:, :, 1] == int(self._mujoco.mjtObj.mjOBJ_GEOM),
                segmentation[:, :, 0],
                -1,
            )
            instance_ids = tuple(int(value) for value in geom_pixels.ravel())
            for geom_id in set(instance_ids) - {-1}:
                name = self._mujoco.mj_id2name(
                    self._model,
                    self._mujoco.mjtObj.mjOBJ_GEOM,
                    geom_id,
                )
                instance_labels[geom_id] = str(name or f"geom_{geom_id}")
        valid = np.isfinite(depth) & (depth > 0) & (depth < 10.0)
        if noise_std_m:
            depth[valid] += rng.normal(0, noise_std_m, size=int(valid.sum()))
        depth[~valid | (depth <= 0)] = 0
        valid = np.isfinite(depth) & (depth > 0)
        # MuJoCo camera: +X right, +Y up, -Z forward; optical: +Y down, +Z forward.
        optical_to_world = camera_rotation.reshape(3, 3) @ np.diag([1, -1, -1])
        transform = np.eye(4)
        transform[:3, :3] = optical_to_world
        transform[:3, 3] = camera_position
        focal = (self._height / 2) / math.tan(math.radians(camera_fovy) / 2)
        intrinsics = (focal, focal, (self._width - 1) / 2, (self._height - 1) / 2)
        calibration_values = np.asarray((*intrinsics, *transform.ravel()), dtype="<f8")
        calibration = hashlib.sha256(calibration_values.tobytes()).hexdigest()[:16]
        if self._physics_state_hash(data) != initial_hash:
            raise RuntimeError("physics state changed while finalizing camera calibration")
        check_calibration()
        frame = SensorFrame(
            frame_id=f"rgbd-{uuid4().hex}",
            sim_time_s=float(data.time),
            width=self._width,
            height=self._height,
            rgb=rgb.tobytes(),
            depth=tuple(float(value) for value in depth.ravel()),
            intrinsics=intrinsics,
            camera_to_world=tuple(float(value) for value in transform.ravel()),
            captured_at=captured_at,
            latency_ms=(perf_counter() - started) * 1000,
            scene_id=scene_id,
            episode_id=episode_id,
            calibration_version=calibration,
            valid_mask=valid.astype(np.uint8).tobytes(),
        )
        return (
            frame,
            instance_ids,
            instance_labels,
            tuple(pass_hashes),
        )

    def close(self) -> None:
        self._renderer.close()
