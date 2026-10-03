# T2 acceptance review package

Review scope: existing T2 implementation plus continuation fixes. No commits; unrelated dirty tree excluded. Initial copies retained in before/.

## Continuation diff: src/cloud_edge_robot_arm/vision/observations.py
```diff
--- before/src/cloud_edge_robot_arm/vision/observations.py
+++ src/cloud_edge_robot_arm/vision/observations.py
@@ -215,13 +215,27 @@
 def observation_from_sensor_frame(frame: SensorFrame, *, source: str) -> RGBDObservation:
     if not frame.rgb or not frame.depth or not frame.intrinsics or not frame.camera_to_world:
         raise ValueError("RGBD_CAMERA_DATA_MISSING")
+    if frame.captured_at is None:
+        raise ValueError("captured_at must record sensor acquisition time")
+    if (
+        type(frame.width) is not int
+        or type(frame.height) is not int
+        or not 1 <= frame.width <= 1280
+        or not 1 <= frame.height <= 720
+    ):
+        raise ValueError("RGB-D dimensions must be integers within 1280 x 720")
+    pixel_count = frame.width * frame.height
+    if len(frame.rgb) != pixel_count * 3:
+        raise ValueError("RGB size must equal width * height * 3")
+    if len(frame.depth) != pixel_count:
+        raise ValueError("depth size must equal width * height")
     image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
     output = io.BytesIO()
     image.save(output, format="PNG")
     return RGBDObservation.model_validate(
         {
             "frame_id": frame.frame_id,
-            "captured_at": frame.captured_at or datetime.now(UTC),
+            "captured_at": frame.captured_at,
             "sim_time_s": frame.sim_time_s,
             "width": frame.width,
             "height": frame.height,
```

## Current source: src/cloud_edge_robot_arm/vision/observations.py
```python
"""Bounded RGB-D transport; metric depth is never replaced by a text summary."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import struct
from datetime import UTC, datetime
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.models import SensorFrame


class RGBDObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str = Field(min_length=1, max_length=160)
    observation_id: str = ""
    captured_at: datetime
    sim_time_s: float = Field(ge=0, allow_inf_nan=False)
    width: int = Field(ge=1, le=1280)
    height: int = Field(ge=1, le=720)
    rgb_png_base64: str = Field(min_length=1, max_length=5_000_000, repr=False)
    depth_float32_base64: str = Field(min_length=1, max_length=5_000_000, repr=False)
    intrinsics: tuple[float, float, float, float]
    camera_to_world: tuple[float, ...] = Field(min_length=16, max_length=16)
    depth_convention: Literal["optical_z_m"] = "optical_z_m"
    source: Literal["mujoco_camera", "isaac_camera", "rgbd_camera"]
    scene_id: str | None = None
    episode_id: str | None = None
    calibration_version: str | None = None
    valid_mask_base64: str | None = Field(default=None, repr=False)
    checksum_sha256: str = ""

    @model_validator(mode="after")
    def validate_pair(self) -> RGBDObservation:
        if self.observation_id and self.observation_id != self.frame_id:
            raise ValueError("observation_id must match frame_id")
        object.__setattr__(self, "observation_id", self.frame_id)
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include timezone")
        try:
            rgb = base64.b64decode(self.rgb_png_base64, validate=True)
            depth = base64.b64decode(self.depth_float32_base64, validate=True)
            with Image.open(io.BytesIO(rgb)) as image:
                if image.format != "PNG" or image.size != (self.width, self.height):
                    raise ValueError("RGB PNG dimensions do not match registered depth")
                if image.mode != "RGB":
                    raise ValueError("RGB PNG must use RGB color encoding")
                image.verify()
        except (OSError, ValueError) as exc:
            raise ValueError("invalid RGB-D image encoding") from exc
        if len(depth) != self.width * self.height * 4:
            raise ValueError("depth size must equal width * height * float32")
        depths = tuple(v[0] for v in struct.iter_unpack("<f", depth))
        if any(not math.isfinite(value) or value < 0 for value in depths):
            raise ValueError("depth must be finite nonnegative metres (zero = invalid)")
        expected_mask = bytes(int(value > 0) for value in depths)
        if self.valid_mask_base64 is None:
            object.__setattr__(
                self, "valid_mask_base64", base64.b64encode(expected_mask).decode("ascii")
            )
        else:
            try:
                supplied_mask = base64.b64decode(self.valid_mask_base64, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("invalid depth mask encoding") from exc
            if supplied_mask != expected_mask:
                raise ValueError("valid mask must match positive finite depth")
        fx, fy, cx, cy = self.intrinsics
        if not all(math.isfinite(v) for v in self.intrinsics + self.camera_to_world):
            raise ValueError("camera calibration must be finite")
        if fx <= 0 or fy <= 0:
            raise ValueError("invalid camera intrinsics")
        matrix = self.camera_to_world
        if matrix[12:] != (0, 0, 0, 1):
            raise ValueError("camera transform must be homogeneous")
        rows = [matrix[i : i + 3] for i in (0, 4, 8)]
        for i in range(3):
            for j in range(3):
                dot = sum(a * b for a, b in zip(rows[i], rows[j], strict=True))
                if abs(dot - float(i == j)) > 1e-4:
                    raise ValueError("camera rotation must be orthonormal")
        a, b, c = rows
        determinant = (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )
        if abs(determinant - 1) > 1e-4:
            raise ValueError("camera rotation must be right-handed")
        checksum_fields = {
            "frame_id": self.frame_id,
            "captured_at": self.captured_at.astimezone(UTC).isoformat(),
            "sim_time_s": self.sim_time_s,
            "source": self.source,
            "depth_convention": self.depth_convention,
            "scene_id": self.scene_id,
            "episode_id": self.episode_id,
            "calibration_version": self.calibration_version,
            "width": self.width,
            "height": self.height,
            "intrinsics": self.intrinsics,
            "camera_to_world": self.camera_to_world,
            "rgb_sha256": hashlib.sha256(rgb).hexdigest(),
            "depth_sha256": hashlib.sha256(depth).hexdigest(),
            "mask_sha256": hashlib.sha256(expected_mask).hexdigest(),
        }
        checksum = hashlib.sha256(json.dumps(checksum_fields, sort_keys=True).encode()).hexdigest()
        if self.checksum_sha256 and self.checksum_sha256 != checksum:
            raise ValueError("RGB-D checksum mismatch")
        object.__setattr__(self, "checksum_sha256", checksum)
        return self

    def valid_mask_bytes(self) -> bytes:
        assert self.valid_mask_base64 is not None
        return base64.b64decode(self.valid_mask_base64, validate=True)

    def crop(self, box: tuple[int, int, int, int]) -> RGBDObservation:
        left, top, right, bottom = box
        if not (0 <= left < right <= self.width and 0 <= top < bottom <= self.height):
            raise ValueError("crop is outside camera image")
        with Image.open(io.BytesIO(base64.b64decode(self.rgb_png_base64))) as image:
            output = io.BytesIO()
            image.crop(box).save(output, format="PNG")
        depths = self.depth_values()
        selected = [
            depths[y * self.width + x] for y in range(top, bottom) for x in range(left, right)
        ]
        fx, fy, cx, cy = self.intrinsics
        return RGBDObservation.model_validate(
            {
                **self.model_dump(),
                "width": right - left,
                "height": bottom - top,
                "rgb_png_base64": base64.b64encode(output.getvalue()).decode("ascii"),
                "depth_float32_base64": base64.b64encode(
                    struct.pack(f"<{len(selected)}f", *selected)
                ).decode("ascii"),
                "intrinsics": (fx, fy, cx - left, cy - top),
                "valid_mask_base64": None,
                "checksum_sha256": "",
            }
        )

    def depth_values(self) -> tuple[float, ...]:
        raw = base64.b64decode(self.depth_float32_base64, validate=True)
        return struct.unpack(f"<{self.width * self.height}f", raw)

    def world_point(self, pixel: tuple[int, int]) -> Pose:
        u, v = pixel
        if not 0 <= u < self.width or not 0 <= v < self.height:
            raise ValueError("selected pixel is outside camera image")
        depth = self.depth_values()[v * self.width + u]
        if depth <= 0:
            raise ValueError("selected pixel has invalid depth")
        fx, fy, cx, cy = self.intrinsics
        camera = ((u - cx) * depth / fx, (v - cy) * depth / fy, depth)
        matrix = self.camera_to_world
        world = [
            sum(matrix[i + j] * camera[j] for j in range(3)) + matrix[i + 3] for i in (0, 4, 8)
        ]
        return Pose(x=world[0], y=world[1], z=world[2])

    def depth_range(self) -> tuple[float, float]:
        valid = [value for value in self.depth_values() if value > 0]
        if not valid:
            raise ValueError("depth frame has no valid measurements")
        return min(valid), max(valid)

    def depth_png_base64(self) -> str:
        near, far = self.depth_range()
        span = max(far - near, 1e-6)
        pixels = bytes(
            0 if value <= 0 else 1 + round(254 * (far - value) / span)
            for value in self.depth_values()
        )
        image = Image.frombytes("L", (self.width, self.height), pixels)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return base64.b64encode(output.getvalue()).decode("ascii")

    def evidence(self) -> dict[str, object]:
        return {
            "input_mode": "RGBD",
            "frame_id": self.frame_id,
            "observation_id": self.observation_id,
            "scene_id": self.scene_id,
            "episode_id": self.episode_id,
            "calibration_version": self.calibration_version,
            "checksum_sha256": self.checksum_sha256,
            "source": self.source,
            "captured_at": self.captured_at.isoformat(),
            "sim_time_s": self.sim_time_s,
            "width": self.width,
            "height": self.height,
            "intrinsics": list(self.intrinsics),
            "camera_to_world": list(self.camera_to_world),
            "depth_convention": self.depth_convention,
            "rgb_sha256": hashlib.sha256(base64.b64decode(self.rgb_png_base64)).hexdigest(),
            "depth_sha256": hashlib.sha256(base64.b64decode(self.depth_float32_base64)).hexdigest(),
            "model_image_count": 2,
            "ground_truth_used_for_control": False,
        }


def observation_from_sensor_frame(frame: SensorFrame, *, source: str) -> RGBDObservation:
    if not frame.rgb or not frame.depth or not frame.intrinsics or not frame.camera_to_world:
        raise ValueError("RGBD_CAMERA_DATA_MISSING")
    if frame.captured_at is None:
        raise ValueError("captured_at must record sensor acquisition time")
    if (
        type(frame.width) is not int
        or type(frame.height) is not int
        or not 1 <= frame.width <= 1280
        or not 1 <= frame.height <= 720
    ):
        raise ValueError("RGB-D dimensions must be integers within 1280 x 720")
    pixel_count = frame.width * frame.height
    if len(frame.rgb) != pixel_count * 3:
        raise ValueError("RGB size must equal width * height * 3")
    if len(frame.depth) != pixel_count:
        raise ValueError("depth size must equal width * height")
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return RGBDObservation.model_validate(
        {
            "frame_id": frame.frame_id,
            "captured_at": frame.captured_at,
            "sim_time_s": frame.sim_time_s,
            "width": frame.width,
            "height": frame.height,
            "rgb_png_base64": base64.b64encode(output.getvalue()).decode("ascii"),
            "depth_float32_base64": base64.b64encode(
                struct.pack(f"<{len(frame.depth)}f", *frame.depth)
            ).decode("ascii"),
            "intrinsics": frame.intrinsics,
            "camera_to_world": frame.camera_to_world,
            "source": source,
            "scene_id": frame.scene_id,
            "episode_id": frame.episode_id,
            "calibration_version": frame.calibration_version,
            "valid_mask_base64": base64.b64encode(frame.valid_mask).decode("ascii")
            if frame.valid_mask is not None
            else None,
        }
    )

```

## Current source: src/cloud_edge_robot_arm/vision/capture.py
```python
"""Capture paired simulator images and retain auditable metric depth."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cloud_edge_robot_arm.simulation.backend import SimulatorBackend
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame


@dataclass(frozen=True)
class CapturedFrame:
    observation: RGBDObservation
    # Flattened row-major MuJoCo geom IDs; -1 is background. Names map IDs to MJCF geoms.
    instance_ids: tuple[int, ...]
    instance_labels: dict[int, str]
    physics_state_hash: str
    pass_state_hashes: tuple[str, ...]


class MuJoCoCaptureSession:
    """Reuse one renderer while explicitly capturing fresh frames from one episode."""

    def __init__(self, config: SimulatorConfig) -> None:
        self._config = config.model_copy(update={"render_rgb": True, "render_depth": True})
        self._backend = MuJoCoPhysicsBackend()
        self._open = False

    def __enter__(self) -> MuJoCoCaptureSession:
        try:
            self._backend.initialize(self._config)
            self._backend.reset(
                PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=self._config.seed)
            )
        except BaseException:
            self._backend.shutdown()
            raise
        self._open = True
        return self

    def __exit__(self, *_exc: object) -> None:
        self._open = False
        self._backend.shutdown()

    def capture(self) -> RGBDObservation:
        return self.capture_with_instances().observation

    def capture_with_instances(self) -> CapturedFrame:
        if not self._open:
            raise RuntimeError("MuJoCo capture session is closed")
        frame, ids, labels, pass_hashes = self._backend.capture_sensor_frame_with_instances()
        if len(set(pass_hashes)) != 1:
            raise RuntimeError("render passes observed different physics states")
        return CapturedFrame(
            observation=observation_from_sensor_frame(frame, source="mujoco_camera"),
            instance_ids=ids,
            instance_labels=labels,
            physics_state_hash=pass_hashes[0],
            pass_state_hashes=pass_hashes,
        )


def capture_simulated_observation(
    *,
    backend: Literal["MUJOCO", "ISAAC_SIM"] = "MUJOCO",
    scenario_id: str = "S01_NORMAL_STATIC",
    seed: int = 0,
) -> RGBDObservation:
    simulator: SimulatorBackend
    if backend == "MUJOCO":
        from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

        simulator = MuJoCoPhysicsBackend()
        source = "mujoco_camera"
    elif backend == "ISAAC_SIM":
        from cloud_edge_robot_arm.simulation.isaac.backend import IsaacSimBackend

        simulator = IsaacSimBackend()
        source = "isaac_camera"
    else:
        raise ValueError("RGBD_CAMERA_REQUIRED: Mock cannot provide real RGB-D observations")
    try:
        simulator.initialize(SimulatorConfig(render_rgb=True, render_depth=True))
        simulator.reset(PhysicalScenarioConfig.scenario(scenario_id, seed=seed))
        return observation_from_sensor_frame(simulator.get_sensor_frame(), source=source)
    finally:
        simulator.shutdown()


def save_observation(observation: RGBDObservation, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "rgb": directory / "rgb.png",
        "depth": directory / "depth.f32",
        "depth_visualization": directory / "depth.png",
        "observation": directory / "observation.json",
    }
    paths["rgb"].write_bytes(base64.b64decode(observation.rgb_png_base64))
    paths["depth"].write_bytes(base64.b64decode(observation.depth_float32_base64))
    paths["depth_visualization"].write_bytes(base64.b64decode(observation.depth_png_base64()))
    metadata = {
        **observation.evidence(),
        "model_image_count": 0,
        "files": {name: path.name for name, path in paths.items() if name != "observation"},
    }
    paths["observation"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def save_captured_frame(frame: CapturedFrame, directory: Path) -> dict[str, Path]:
    """Persist raw registered inputs and offline-only geom IDs for audit."""
    paths = save_observation(frame.observation, directory)
    paths["mask"] = directory / "valid_mask.u8"
    paths["instances"] = directory / "instance_geom_ids.i32"
    paths["mask"].write_bytes(frame.observation.valid_mask_bytes())
    paths["instances"].write_bytes(struct.pack(f"<{len(frame.instance_ids)}i", *frame.instance_ids))
    metadata = json.loads(paths["observation"].read_text(encoding="utf-8"))
    metadata.update(
        {
            "physics_state_hash": frame.physics_state_hash,
            "pass_state_hashes": list(frame.pass_state_hashes),
            "instance_id_convention": "MuJoCo geom ID, -1 background; row-major int32",
            "instance_labels": {str(key): value for key, value in frame.instance_labels.items()},
        }
    )
    metadata["files"].update(
        {
            "mask": paths["mask"].name,
            "instances": paths["instances"].name,
        }
    )
    paths["observation"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths

```

## Continuation diff: src/cloud_edge_robot_arm/simulation/mujoco/camera.py
```diff
--- before/src/cloud_edge_robot_arm/simulation/mujoco/camera.py
+++ src/cloud_edge_robot_arm/simulation/mujoco/camera.py
@@ -80,23 +80,39 @@
         episode_id: str | None,
         include_instances: bool,
     ) -> tuple[SensorFrame, tuple[int, ...], dict[int, str], tuple[str, ...]]:
+        captured_at = datetime.now(UTC)
         started = perf_counter()
         initial_hash = self._physics_state_hash(data)
+        camera_position = np.asarray(data.cam_xpos[self._camera_id]).copy()
+        camera_rotation = np.asarray(data.cam_xmat[self._camera_id]).copy()
+        camera_fovy = float(self._model.cam_fovy[self._camera_id])
+
+        def check_calibration() -> None:
+            if (
+                not np.array_equal(data.cam_xpos[self._camera_id], camera_position)
+                or not np.array_equal(data.cam_xmat[self._camera_id], camera_rotation)
+                or float(self._model.cam_fovy[self._camera_id]) != camera_fovy
+            ):
+                raise RuntimeError("camera calibration changed during capture")
+
         self._renderer.disable_depth_rendering()
         self._renderer.disable_segmentation_rendering()
         self._renderer.update_scene(data, camera=self._camera_id)
         if self._physics_state_hash(data) != initial_hash:
             raise RuntimeError("physics state changed while preparing camera scene")
+        check_calibration()
         pass_hashes: list[str] = []
         rgb = self._renderer.render().copy()
         pass_hashes.append(self._physics_state_hash(data))
         if pass_hashes[-1] != initial_hash:
             raise RuntimeError("physics state changed during RGB render")
+        check_calibration()
         self._renderer.enable_depth_rendering()
         depth = self._renderer.render().copy()
         pass_hashes.append(self._physics_state_hash(data))
         if pass_hashes[-1] != initial_hash:
             raise RuntimeError("physics state changed during depth render")
+        check_calibration()
         self._renderer.disable_depth_rendering()
         instance_ids: tuple[int, ...] = ()
         instance_labels: dict[int, str] = {}
@@ -107,6 +123,7 @@
             pass_hashes.append(self._physics_state_hash(data))
             if pass_hashes[-1] != initial_hash:
                 raise RuntimeError("physics state changed during instance render")
+            check_calibration()
             geom_pixels = np.where(
                 segmentation[:, :, 1] == int(self._mujoco.mjtObj.mjOBJ_GEOM),
                 segmentation[:, :, 0],
@@ -126,20 +143,17 @@
         depth[~valid | (depth <= 0)] = 0
         valid = np.isfinite(depth) & (depth > 0)
         # MuJoCo camera: +X right, +Y up, -Z forward; optical: +Y down, +Z forward.
-        optical_to_world = np.asarray(data.cam_xmat[self._camera_id]).reshape(3, 3) @ np.diag(
-            [1, -1, -1]
-        )
+        optical_to_world = camera_rotation.reshape(3, 3) @ np.diag([1, -1, -1])
         transform = np.eye(4)
         transform[:3, :3] = optical_to_world
-        transform[:3, 3] = data.cam_xpos[self._camera_id]
-        focal = (self._height / 2) / math.tan(
-            math.radians(float(self._model.cam_fovy[self._camera_id])) / 2
-        )
+        transform[:3, 3] = camera_position
+        focal = (self._height / 2) / math.tan(math.radians(camera_fovy) / 2)
         intrinsics = (focal, focal, (self._width - 1) / 2, (self._height - 1) / 2)
         calibration_values = np.asarray((*intrinsics, *transform.ravel()), dtype="<f8")
         calibration = hashlib.sha256(calibration_values.tobytes()).hexdigest()[:16]
         if self._physics_state_hash(data) != initial_hash:
             raise RuntimeError("physics state changed while finalizing camera calibration")
+        check_calibration()
         frame = SensorFrame(
             frame_id=f"rgbd-{uuid4().hex}",
             sim_time_s=float(data.time),
@@ -149,7 +163,7 @@
             depth=tuple(float(value) for value in depth.ravel()),
             intrinsics=intrinsics,
             camera_to_world=tuple(float(value) for value in transform.ravel()),
-            captured_at=datetime.now(UTC),
+            captured_at=captured_at,
             latency_ms=(perf_counter() - started) * 1000,
             scene_id=scene_id,
             episode_id=episode_id,
```

## Current source: src/cloud_edge_robot_arm/simulation/mujoco/camera.py
```python
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

        def check_calibration() -> None:
            if (
                not np.array_equal(data.cam_xpos[self._camera_id], camera_position)
                or not np.array_equal(data.cam_xmat[self._camera_id], camera_rotation)
                or float(self._model.cam_fovy[self._camera_id]) != camera_fovy
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

```

## Current source: src/cloud_edge_robot_arm/simulation/mujoco/backend.py
```python
"""仿真后端抽象或具体实现，区分 Mock、MuJoCo、Isaac 和 dry-run。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    ContactSnapshot,
    GripperCommand,
    JointCommand,
    JointStateSnapshot,
    PhysicalFault,
    PhysicalFaultType,
    PhysicalScenarioConfig,
    SensorFrame,
    SimulationStepResult,
)
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.spec_randomization import (
    compile_randomized_mjspec_model,
)


class MuJoCoPhysicsBackend:
    """MuJoCo-backed deterministic physics backend for Phase 9 core validation."""

    def __init__(self) -> None:
        self._mujoco: Any | None = None
        self._model: Any | None = None
        self._data: Any | None = None
        self._config: SimulatorConfig | None = None
        self._scenario: PhysicalScenarioConfig | None = None
        self._joint_names = [f"joint{i}" for i in range(1, 8)]
        self._target_positions = np.zeros(7, dtype=float)
        self._gripper_open = True
        self._estop_engaged = False
        self._total_physics_steps = 0
        self._last_contacts: list[ContactSnapshot] = []
        self._sensor_frame = SensorFrame(frame_id="camera", sim_time_s=0.0, width=0, height=0)
        self._rng = np.random.default_rng(0)
        self._command_records: list[dict[str, object]] = []
        self._model_parameters: dict[str, float] = {}
        self._model_parameter_evidence: list[dict[str, object]] = []
        self._mjspec_xml_sha256 = ""
        self._sensor_noise_std_m = 0.001
        self._actuator_delay_steps = 0
        self._pending_joint_targets: list[tuple[int, np.ndarray[Any, Any]]] = []
        self._camera: MuJoCoRGBDCamera | None = None
        self._episode_id: str | None = None

    @property
    def total_physics_steps(self) -> int:
        return self._total_physics_steps

    @property
    def estop_engaged(self) -> bool:
        return self._estop_engaged

    @property
    def command_records(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._command_records]

    @property
    def model_parameter_evidence(self) -> dict[str, object]:
        physics_dt_s = self._config.physics_dt_s if self._config is not None else 0.0
        return {
            "compiler": "MuJoCo.MjSpec" if self._mjspec_xml_sha256 else "MjModel.from_xml_path",
            "spec_xml_sha256": self._mjspec_xml_sha256,
            "parameters": [dict(item) for item in self._model_parameter_evidence],
            "runtime": {
                "sensor_noise_std_m": self._sensor_noise_std_m,
                "actuator_delay_requested_ms": self._model_parameters.get("actuator_delay_ms", 0.0),
                "actuator_delay_steps": self._actuator_delay_steps,
                "actuator_delay_applied_ms": self._actuator_delay_steps * physics_dt_s * 1_000.0,
            },
        }

    def initialize(
        self,
        config: SimulatorConfig,
        *,
        model_parameters: Mapping[str, float] | None = None,
    ) -> None:
        if find_spec("mujoco") is None:
            raise RuntimeError(
                "MuJoCo is not installed. Install with python -m pip install -e '.[sim-mujoco]'"
            )
        import mujoco

        model_path = Path(config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        self._mujoco = mujoco
        self._model_parameters = {
            str(name): float(value) for name, value in (model_parameters or {}).items()
        }
        if self._model_parameters:
            build = compile_randomized_mjspec_model(
                mujoco,
                model_path=model_path,
                parameters=self._model_parameters,
            )
            self._model = build.model
            self._mjspec_xml_sha256 = build.spec_xml_sha256
            self._model_parameter_evidence = [item.to_jsonable() for item in build.evidence]
        else:
            self._model = mujoco.MjModel.from_xml_path(str(model_path))
            self._mjspec_xml_sha256 = ""
            self._model_parameter_evidence = []
        self._model.opt.timestep = config.physics_dt_s
        self._data = mujoco.MjData(self._model)
        self._config = config
        self._sensor_noise_std_m = max(
            0.0, self._model_parameters.get("camera_depth_noise_m", 0.001)
        )
        delay_ms = max(0.0, self._model_parameters.get("actuator_delay_ms", 0.0))
        self._actuator_delay_steps = int(round(delay_ms / 1000.0 / config.physics_dt_s))

    def reset(self, scenario: PhysicalScenarioConfig) -> None:
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        self._scenario = scenario
        self._episode_id = uuid4().hex
        self._rng = np.random.default_rng(scenario.seed)
        self._mujoco.mj_resetData(self._model, self._data)
        self._target_positions = np.zeros(7, dtype=float)
        assert self._config is not None
        if self._config.render_rgb or self._config.render_depth:
            # Initial observation pose keeps the workspace visible to the overhead camera.
            joint = self._model.joint("joint1")
            self._data.qpos[joint.qposadr[0]] = -0.8
            self._target_positions[0] = -0.8
        self._estop_engaged = False
        self._gripper_open = True
        self._total_physics_steps = 0
        self._last_contacts = []
        self._command_records = []
        self._pending_joint_targets = []
        self._set_free_body_pose("object", scenario.object_pose)
        self._set_body_mass("object", scenario.object_mass_kg)
        self._set_geom_friction("object_geom", scenario.friction_coefficient)
        self._mujoco.mj_forward(self._model, self._data)
        self._update_sensor_frame()

    def step(self, steps: int = 1) -> SimulationStepResult:
        self._require_loaded()
        assert self._mujoco is not None and self._model is not None and self._data is not None
        if steps < 1:
            raise ValueError("steps must be positive")
        executed = 0
        for _ in range(steps):
            if not self._estop_engaged:
                self._apply_control()
            else:
                self._data.ctrl[:] = 0.0
            self._mujoco.mj_step(self._model, self._data)
            executed += 1
            self._total_physics_steps += 1
        self._last_contacts = self._read_contacts()
        self._update_sensor_frame()
        return SimulationStepResult(
            sim_time_s=self.get_sim_time(),
            physics_steps=executed,
            contacts=list(self._last_contacts),
            sensor_frame=self._sensor_frame,
        )

    def shutdown(self) -> None:
        if self._camera is not None:
            self._camera.close()
            self._camera = None
        self._data = None
        self._model = None
        self._mujoco = None
        self._episode_id = None

    def get_sim_time(self) -> float:
        self._require_loaded()
        assert self._data is not None
        return float(self._data.time)

    def get_joint_state(self) -> JointStateSnapshot:
        self._require_loaded()
        assert self._data is not None
        positions = [float(value) for value in self._data.qpos[:7]]
        velocities = [float(value) for value in self._data.qvel[:7]]
        efforts = [float(value) for value in self._data.ctrl[:7]]
        return JointStateSnapshot(
            names=list(self._joint_names),
            positions=positions,
            velocities=velocities,
            efforts=efforts,
            sim_time_s=self.get_sim_time(),
        )

    def get_tcp_pose(self) -> Pose:
        self._require_loaded()
        assert self._model is not None and self._data is not None
        site_id = self._model.site("tcp").id
        pos = self._data.site_xpos[site_id]
        return Pose(x=float(pos[0]), y=float(pos[1]), z=float(pos[2]))

    def get_contacts(self) -> list[ContactSnapshot]:
        return list(self._last_contacts)

    def get_sensor_frame(self) -> SensorFrame:
        return self._sensor_frame

    def capture_sensor_frame_with_instances(
        self,
    ) -> tuple[SensorFrame, tuple[int, ...], dict[int, str], tuple[str, ...]]:
        """Render a new frame without advancing physics or replacing the cached step frame."""
        self._require_loaded()
        if self._scenario is None or self._config is None:
            raise RuntimeError("MuJoCo scenario is not reset")
        if not (self._config.render_rgb and self._config.render_depth):
            raise RuntimeError("RGB-D rendering is not enabled")
        if self._camera is None:
            self._camera = MuJoCoRGBDCamera(
                self._mujoco, self._model,
                width=self._config.camera_width, height=self._config.camera_height,
            )
        return self._camera.capture_with_instances(
            self._data, rng=self._rng, noise_std_m=self._sensor_noise_std_m,
            scene_id=self._scenario.scenario_id, episode_id=self._episode_id,
        )

    def apply_joint_targets(self, targets: JointCommand) -> None:
        if self._estop_engaged:
            self._record_command("joint_target", accepted=False, reason="emergency_stop")
            return
        if len(targets.positions) != 7:
            raise ValueError("Franka Panda profile requires exactly 7 joint targets")
        clipped = np.clip(np.array(targets.positions, dtype=float), -2.8, 2.8)
        if self._actuator_delay_steps:
            available_step = self._total_physics_steps + self._actuator_delay_steps
            self._pending_joint_targets.append((available_step, clipped))
            self._record_command(
                "joint_target",
                accepted=True,
                reason=f"queued_until_physics_step={available_step}",
            )
        else:
            self._target_positions = clipped
            self._record_command("joint_target", accepted=True, reason="")

    def apply_gripper_command(self, command: GripperCommand) -> None:
        if self._estop_engaged:
            self._record_command("gripper", accepted=False, reason="emergency_stop")
            return
        self._gripper_open = command.open
        assert self._data is not None
        target = 0.04 if command.open else 0.0
        if self._data.ctrl.shape[0] >= 9:
            self._data.ctrl[7] = target
            self._data.ctrl[8] = target
        self._record_command("gripper", accepted=True, reason="")

    def emergency_stop(self) -> None:
        self._estop_engaged = True
        self._record_command("emergency_stop", accepted=True, reason="")
        if self._data is not None:
            self._data.ctrl[:] = 0.0

    def inject_fault(self, fault: PhysicalFault) -> None:
        if fault.fault_type == PhysicalFaultType.EMERGENCY_STOP:
            self.emergency_stop()
        elif fault.fault_type == PhysicalFaultType.OBJECT_SLIP:
            self._set_geom_friction("object_geom", 0.05)
        elif fault.fault_type == PhysicalFaultType.PAYLOAD_MASS_VARIATION:
            mass = float(fault.parameters.get("object_mass_kg", 0.25))
            self._set_body_mass("object", mass)
        elif fault.fault_type == PhysicalFaultType.FRICTION_VARIATION:
            friction = float(fault.parameters.get("friction_coefficient", 0.2))
            self._set_geom_friction("object_geom", friction)

    def _require_loaded(self) -> None:
        if self._model is None or self._data is None:
            raise RuntimeError("MuJoCo backend is not initialized")

    def _apply_control(self) -> None:
        assert self._data is not None
        while (
            self._pending_joint_targets
            and self._pending_joint_targets[0][0] <= self._total_physics_steps
        ):
            _, self._target_positions = self._pending_joint_targets.pop(0)
        current = np.array(self._data.qpos[:7], dtype=float)
        error = self._target_positions - current
        control = current + np.clip(error, -0.035, 0.035)
        self._data.ctrl[:7] = control

    def _set_free_body_pose(self, body_name: str, pose: Pose) -> None:
        assert self._model is not None and self._data is not None
        joint_id = self._model.joint(f"{body_name}_free").id
        qpos_addr = self._model.jnt_qposadr[joint_id]
        self._data.qpos[qpos_addr : qpos_addr + 3] = [pose.x, pose.y, pose.z]
        self._data.qpos[qpos_addr + 3 : qpos_addr + 7] = [1.0, 0.0, 0.0, 0.0]

    def _set_body_mass(self, body_name: str, mass_kg: float) -> None:
        assert self._model is not None
        body_id = self._model.body(body_name).id
        self._model.body_mass[body_id] = max(0.001, mass_kg)

    def _set_geom_friction(self, geom_name: str, friction: float) -> None:
        assert self._model is not None
        geom_id = self._model.geom(geom_name).id
        self._model.geom_friction[geom_id][0] = max(0.01, friction)

    def _read_contacts(self) -> list[ContactSnapshot]:
        assert self._mujoco is not None and self._model is not None and self._data is not None
        contacts: list[ContactSnapshot] = []
        for index in range(int(self._data.ncon)):
            contact = self._data.contact[index]
            geom1 = self._mujoco.mj_id2name(
                self._model, self._mujoco.mjtObj.mjOBJ_GEOM, contact.geom1
            )
            geom2 = self._mujoco.mj_id2name(
                self._model, self._mujoco.mjtObj.mjOBJ_GEOM, contact.geom2
            )
            g1 = str(geom1 or f"geom_{contact.geom1}")
            g2 = str(geom2 or f"geom_{contact.geom2}")
            expected = "finger" in g1 and "object" in g2 or "finger" in g2 and "object" in g1
            illegal = not expected and not ({"table", "object_geom"} <= {g1, g2})
            impulse = float(np.linalg.norm(contact.frame[:3])) if contact.frame.size else 0.0
            contacts.append(
                ContactSnapshot(
                    geom1=g1,
                    geom2=g2,
                    impulse=impulse,
                    position=Pose(
                        x=float(contact.pos[0]),
                        y=float(contact.pos[1]),
                        z=float(contact.pos[2]),
                    ),
                    sim_time_s=self.get_sim_time(),
                    expected=expected,
                    illegal=illegal,
                )
            )
        return contacts

    def _update_sensor_frame(self) -> None:
        if self._config is not None and (self._config.render_rgb or self._config.render_depth):
            if self._camera is None:
                self._camera = MuJoCoRGBDCamera(
                    self._mujoco, self._model,
                    width=self._config.camera_width, height=self._config.camera_height,
                )
            self._sensor_frame = self._camera.capture(
                self._data, rng=self._rng, noise_std_m=self._sensor_noise_std_m,
                scene_id=self._scenario.scenario_id if self._scenario else None,
                episode_id=self._episode_id,
            )
            return
        tcp = self.get_tcp_pose()
        noise = float(self._rng.normal(0.0, self._sensor_noise_std_m))
        self._sensor_frame = SensorFrame(
            frame_id="camera",
            sim_time_s=self.get_sim_time(),
            width=0,
            height=0,
            depth=(max(0.0, tcp.z + noise),),
            object_detections=[
                {
                    "object_id": "object",
                    "confidence": max(0.0, min(1.0, 0.98 - abs(noise) * 10.0)),
                    "pose": {"x": tcp.x + noise, "y": tcp.y - noise, "z": tcp.z},
                }
            ],
            latency_ms=abs(noise) * 1000.0,
            ground_truth_used_for_control=False,
        )

    def _record_command(self, command_type: str, *, accepted: bool, reason: str) -> None:
        self._command_records.append(
            {
                "type": command_type,
                "accepted": accepted,
                "reason": reason,
                "after_emergency_stop": self._estop_engaged and command_type != "emergency_stop",
                "sim_time_s": self.get_sim_time() if self._data is not None else 0.0,
            }
        )


def joint_targets_for_pose(pose: Pose) -> list[float]:
    """Small deterministic IK surrogate for the local MJCF arm.

    The command is still executed through MuJoCo actuators and physics steps; this
    maps task-space intent to reachable joint targets for the simple reference arm.
    """

    base = math.atan2(pose.y, max(0.05, pose.x))
    reach = min(0.6, math.hypot(pose.x, pose.y))
    shoulder = np.clip((0.45 - pose.z) * 1.6, -1.2, 1.2)
    elbow = np.clip((reach - 0.25) * 2.2, -1.0, 1.0)
    wrist = np.clip((pose.z - 0.25) * 1.5, -0.8, 0.8)
    return [
        float(base),
        float(shoulder),
        float(elbow),
        float(-shoulder / 2),
        float(wrist),
        0.2,
        0.0,
    ]

```

## Current source: src/cloud_edge_robot_arm/simulation/config.py
```python
"""仿真运行配置模型。

该模块集中约束 MuJoCo/Isaac 等仿真后端的时间步长、随机化强度、输出目录和
场景模型路径，确保实验入口读取配置后仍会经过统一校验。
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RandomizationLevel(StrEnum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class SimulatorConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    backend: str = "mujoco"
    headless: bool = True
    robot_profile: str = "franka_panda"
    scene_profile: str = "desktop_pick_place"
    seed: int = 0
    physics_dt_s: float = Field(default=0.0041666667, gt=0)
    control_dt_s: float = Field(default=0.02, gt=0)
    sensor_dt_s: float = Field(default=0.0333333333, gt=0)
    realtime_factor: float = Field(default=0.0, ge=0)
    max_episode_s: float = Field(default=60.0, gt=0)
    domain_randomization: bool = True
    randomization_level: RandomizationLevel = RandomizationLevel.NONE
    render_rgb: bool = False
    render_depth: bool = False
    camera_width: int = Field(default=320, ge=1, le=1280)
    camera_height: int = Field(default=240, ge=1, le=720)
    record_video: bool = False
    artifact_dir: Path = Path("experiments/results/phase9")
    model_path: str = "assets/robots/franka_panda/scene.xml"

    @model_validator(mode="after")
    def validate_time_grid(self) -> SimulatorConfig:
        if self.control_dt_s < self.physics_dt_s:
            raise ValueError("control_dt_s must be greater than or equal to physics_dt_s")
        if self.sensor_dt_s < self.physics_dt_s:
            raise ValueError("sensor_dt_s must be greater than or equal to physics_dt_s")
        return self


def load_simulator_config(path: Path) -> SimulatorConfig:
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SimulatorConfig.model_validate(payload)

```

## Current source: src/cloud_edge_robot_arm/simulation/models.py
```python
"""结构化数据模型，作为 API、测试和服务之间的稳定契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cloud_edge_robot_arm.contracts import Pose


@dataclass(frozen=True)
class JointStateSnapshot:
    names: list[str]
    positions: list[float]
    velocities: list[float]
    efforts: list[float]
    sim_time_s: float


@dataclass(frozen=True)
class ContactSnapshot:
    geom1: str
    geom2: str
    impulse: float
    position: Pose
    sim_time_s: float
    expected: bool = False
    illegal: bool = False


@dataclass(frozen=True)
class SensorFrame:
    frame_id: str
    sim_time_s: float
    width: int
    height: int
    rgb: bytes | None = None
    depth: tuple[float, ...] = ()
    object_detections: list[dict[str, object]] = field(default_factory=list)
    latency_ms: float = 0.0
    ground_truth_used_for_control: bool = False
    intrinsics: tuple[float, ...] = ()
    camera_to_world: tuple[float, ...] = ()
    captured_at: datetime | None = None
    scene_id: str | None = None
    episode_id: str | None = None
    calibration_version: str | None = None
    valid_mask: bytes | None = None


@dataclass(frozen=True)
class JointCommand:
    positions: list[float]
    max_velocity: float = 1.0
    timeout_s: float = 5.0


@dataclass(frozen=True)
class GripperCommand:
    open: bool
    force_n: float = 30.0
    timeout_s: float = 1.0


class PhysicalFaultType(StrEnum):
    PAYLOAD_MASS_VARIATION = "PAYLOAD_MASS_VARIATION"
    FRICTION_VARIATION = "FRICTION_VARIATION"
    ACTUATOR_DELAY = "ACTUATOR_DELAY"
    CAMERA_NOISE = "CAMERA_NOISE"
    OBJECT_SLIP = "OBJECT_SLIP"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class PhysicalFault:
    fault_type: PhysicalFaultType
    parameters: dict[str, float | int | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalScenarioConfig:
    scenario_id: str
    seed: int
    object_mass_kg: float = 0.08
    friction_coefficient: float = 0.8
    table_height_m: float = 0.0
    object_pose: Pose = field(default_factory=lambda: Pose(x=0.45, y=0.0, z=0.035))
    target_region_pose: Pose = field(default_factory=lambda: Pose(x=0.2, y=0.25, z=0.035))
    max_episode_s: float = 60.0

    @classmethod
    def scenario(cls, scenario_id: str, *, seed: int) -> PhysicalScenarioConfig:
        if scenario_id == "S21_OBJECT_SLIP_AFTER_LIFT":
            return cls(scenario_id=scenario_id, seed=seed, friction_coefficient=0.12)
        if scenario_id == "S16_PAYLOAD_MASS_VARIATION":
            return cls(scenario_id=scenario_id, seed=seed, object_mass_kg=0.22)
        return cls(scenario_id=scenario_id, seed=seed)


@dataclass(frozen=True)
class SimulationStepResult:
    sim_time_s: float
    physics_steps: int
    contacts: list[ContactSnapshot]
    sensor_frame: SensorFrame


@dataclass(frozen=True)
class PhysicalTrialResult:
    scenario_id: str
    seed: int
    randomization_level: str
    result_hash: str
    metrics: dict[str, float | int | str | bool]
    randomization_sample: dict[str, object] = field(default_factory=dict)
    backend_parameter_evidence: dict[str, object] = field(default_factory=dict)
    trajectory: list[dict[str, object]] = field(default_factory=list)
    sensor_stream: list[dict[str, object]] = field(default_factory=list)
    timebase: dict[str, object] = field(
        default_factory=lambda: {
            "timeline": "elapsed_s",
            "clock": "simulation_time",
            "frame": "world",
        }
    )

```

## Continuation diff: tests/test_rgbd_observations.py
```diff
--- before/tests/test_rgbd_observations.py
+++ tests/test_rgbd_observations.py
@@ -5,6 +5,7 @@
 import base64
 import io
 import struct
+from dataclasses import replace
 from datetime import UTC, datetime
 
 import pytest
@@ -12,7 +13,7 @@
 from pydantic import ValidationError
 
 from cloud_edge_robot_arm.simulation.config import SimulatorConfig
-from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
+from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig, SensorFrame
 from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
 
 
@@ -33,6 +34,82 @@
     }
 
 
+@pytest.fixture
+def sensor_frame() -> SensorFrame:
+    return SensorFrame(
+        frame_id="historical-camera-frame",
+        captured_at=datetime(2020, 1, 1, tzinfo=UTC),
+        sim_time_s=0.0,
+        width=2,
+        height=2,
+        rgb=bytes((255, 0, 0)) * 4,
+        depth=(2.0, 2.0, 2.0, 0.0),
+        intrinsics=(2.0, 2.0, 0.0, 0.0),
+        camera_to_world=(1, 0, 0, 1, 0, 1, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1),
+    )
+
+
+def test_sensor_frame_requires_acquisition_timestamp(sensor_frame: SensorFrame) -> None:
+    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
+
+    with pytest.raises(ValueError, match="captured_at"):
+        observation_from_sensor_frame(
+            replace(sensor_frame, captured_at=None), source="mujoco_camera"
+        )
+
+
+def test_historical_sensor_frame_preserves_acquisition_timestamp(sensor_frame: SensorFrame) -> None:
+    from cloud_edge_robot_arm.vision.observations import (
+        RGBDObservation,
+        observation_from_sensor_frame,
+    )
+
+    observation = observation_from_sensor_frame(sensor_frame, source="mujoco_camera")
+    restored = RGBDObservation.model_validate_json(observation.model_dump_json())
+    assert restored.captured_at == datetime(2020, 1, 1, tzinfo=UTC)
+    assert restored.crop((0, 0, 1, 1)).captured_at == restored.captured_at
+
+
+@pytest.mark.parametrize("length", [11, 13])
+def test_sensor_frame_rejects_wrong_rgb_payload_length(
+    sensor_frame: SensorFrame, length: int
+) -> None:
+    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
+
+    with pytest.raises(ValueError):
+        observation_from_sensor_frame(
+            replace(sensor_frame, rgb=bytes(length)), source="mujoco_camera"
+        )
+
+
+@pytest.mark.parametrize(
+    "changes",
+    [
+        {"width": 0},
+        {"width": -1},
+        {"width": 1281},
+        {"height": 0},
+        {"height": 721},
+        {"width": 1.5},
+        {"rgb": bytes(11)},
+        {"rgb": bytes(13)},
+        {"depth": (2.0,) * 3},
+        {"depth": (2.0,) * 5},
+    ],
+)
+def test_sensor_frame_validates_bounds_and_payloads_before_encoding(
+    sensor_frame: SensorFrame, changes: dict[str, object], monkeypatch: pytest.MonkeyPatch
+) -> None:
+    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
+
+    def unexpected_encoding(*args: object, **kwargs: object) -> None:
+        pytest.fail("invalid raw RGB-D reached image encoding")
+
+    monkeypatch.setattr(Image, "frombytes", unexpected_encoding)
+    with pytest.raises(ValueError):
+        observation_from_sensor_frame(replace(sensor_frame, **changes), source="mujoco_camera")
+
+
 def test_mujoco_camera_produces_registered_rgb_and_metric_depth() -> None:
     backend = MuJoCoPhysicsBackend()
     try:
```

## Current source: tests/test_rgbd_observations.py
```python
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

```

## Continuation diff: tests/test_rgbd_capture_session.py
```diff
--- before/tests/test_rgbd_capture_session.py
+++ tests/test_rgbd_capture_session.py
@@ -5,6 +5,7 @@
 import json
 import math
 import struct
+from datetime import UTC, datetime, timedelta
 
 import mujoco
 import pytest
@@ -112,3 +113,67 @@
             monkeypatch.setattr(renderer_type, "render", moved_render)
             session.capture_with_instances()
     assert backend._camera is None
+
+
+def test_capture_timestamp_includes_render_latency(monkeypatch: pytest.MonkeyPatch) -> None:
+    from cloud_edge_robot_arm.simulation.mujoco import camera
+    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
+
+    started_at = datetime(2026, 10, 3, tzinfo=UTC)
+    current_time = started_at
+
+    class CaptureClock:
+        @staticmethod
+        def now(tz):
+            return current_time.astimezone(tz)
+
+    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
+        renderer_type = type(session._backend._camera._renderer)
+        original_render = renderer_type.render
+
+        def delayed_render(renderer, *args, **kwargs):
+            nonlocal current_time
+            image = original_render(renderer, *args, **kwargs)
+            current_time += timedelta(seconds=2)
+            return image
+
+        monkeypatch.setattr(camera, "datetime", CaptureClock)
+        monkeypatch.setattr(renderer_type, "render", delayed_render)
+        captured = session.capture_with_instances()
+
+    assert captured.observation.captured_at == started_at
+    assert (current_time - captured.observation.captured_at).total_seconds() == 6
+
+
+@pytest.mark.parametrize("field", ["cam_xpos", "cam_xmat", "cam_fovy"])
+def test_concurrent_calibration_change_rejects_mixed_frame(
+    monkeypatch: pytest.MonkeyPatch, field: str
+) -> None:
+    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
+
+    with pytest.raises(RuntimeError, match="camera calibration changed"):
+        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
+            backend = session._backend
+            assert backend._camera is not None and backend._data is not None
+            renderer_type = type(backend._camera._renderer)
+            original_render = renderer_type.render
+            count = 0
+
+            def changed_calibration_render(renderer, *args, **kwargs):
+                nonlocal count
+                image = original_render(renderer, *args, **kwargs)
+                count += 1
+                if count == 1:
+                    camera_id = backend._camera._camera_id
+                    if field == "cam_fovy":
+                        backend._model.cam_fovy[camera_id] += 1.0
+                    elif field == "cam_xpos":
+                        backend._data.cam_xpos[camera_id, 0] += 0.1
+                    else:
+                        # A 180-degree rotation remains a valid right-handed calibration.
+                        backend._data.cam_xmat[camera_id, :6] *= -1
+                return image
+
+            monkeypatch.setattr(renderer_type, "render", changed_calibration_render)
+            session.capture_with_instances()
+    assert backend._camera is None
```

## Current source: tests/test_rgbd_capture_session.py
```python
"""A continuous camera session must produce synchronized, identifiable real frames."""

from __future__ import annotations

import json
import math
import struct
from datetime import UTC, datetime, timedelta

import mujoco
import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig


def test_render_passes_share_frozen_state() -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        first = session.capture_with_instances()
        second = session.capture_with_instances()
        assert len(first.pass_state_hashes) == 3
        assert len(set(first.pass_state_hashes)) == 1
        assert first.physics_state_hash == first.pass_state_hashes[0]
        assert first.observation.sim_time_s == second.observation.sim_time_s == 0.0
        assert first.observation.observation_id != second.observation.observation_id
        assert first.observation.scene_id == "S01_NORMAL_STATIC"
        assert first.observation.episode_id == second.observation.episode_id
        assert first.observation.calibration_version
        assert len(first.instance_ids) == 320 * 240


def test_plane_back_projection_within_5mm() -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        captured = session.capture_with_instances()
        table_ids = [key for key, value in captured.instance_labels.items() if value == "table"]
        assert len(table_ids) == 1
        width = captured.observation.width
        pixels = [
            (index % width, index // width)
            for index, geom_id in enumerate(captured.instance_ids)
            if geom_id == table_ids[0]
        ]
        assert len(pixels) > 1000
        samples = pixels[:: max(1, len(pixels) // 20)][:20]
        errors = [abs(captured.observation.world_point(pixel).z) for pixel in samples]
        assert max(errors) <= 0.005, f"table plane z=0 errors: {errors}"


def test_capture_session_reuses_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    renderer = mujoco.Renderer
    created = []

    def counted_renderer(*args: object, **kwargs: object) -> mujoco.Renderer:
        result = renderer(*args, **kwargs)
        created.append(result)
        return result

    monkeypatch.setattr(mujoco, "Renderer", counted_renderer)
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        first = session.capture()
        second = session.capture()
        assert first.observation_id != second.observation_id
        assert len(created) == 1
    assert len(created) == 1
    with pytest.raises(RuntimeError):
        created[0].render()


def test_capture_artifacts_include_raw_depth_mask_instances_and_calibration(tmp_path) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        frame = session.capture_with_instances()
        assert math.isfinite(frame.observation.depth_range()[0])
        assert frame.observation.checksum_sha256
        paths = save_captured_frame(frame, tmp_path)
    depth = struct.unpack(
        f"<{frame.observation.width * frame.observation.height}f", paths["depth"].read_bytes()
    )
    assert max(depth) > 0
    assert paths["mask"].read_bytes() == frame.observation.valid_mask_bytes()
    assert len(paths["instances"].read_bytes()) == len(depth) * 4
    metadata = json.loads(paths["observation"].read_text())
    assert metadata["physics_state_hash"] == frame.physics_state_hash
    assert metadata["pass_state_hashes"] == list(frame.pass_state_hashes)
    assert "instance_ids" not in frame.observation.model_dump()


def test_concurrent_physics_change_rejects_mixed_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with pytest.raises(RuntimeError, match="physics state changed"):
        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
            backend = session._backend
            assert backend._camera is not None and backend._data is not None
            renderer_type = type(backend._camera._renderer)
            original_render = renderer_type.render
            count = 0

            def moved_render(renderer, *args, **kwargs):
                nonlocal count
                image = original_render(renderer, *args, **kwargs)
                count += 1
                if count == 1:
                    backend._data.qpos[0] += 0.01
                return image

            monkeypatch.setattr(renderer_type, "render", moved_render)
            session.capture_with_instances()
    assert backend._camera is None


def test_capture_timestamp_includes_render_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.simulation.mujoco import camera
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    started_at = datetime(2026, 10, 3, tzinfo=UTC)
    current_time = started_at

    class CaptureClock:
        @staticmethod
        def now(tz):
            return current_time.astimezone(tz)

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        renderer_type = type(session._backend._camera._renderer)
        original_render = renderer_type.render

        def delayed_render(renderer, *args, **kwargs):
            nonlocal current_time
            image = original_render(renderer, *args, **kwargs)
            current_time += timedelta(seconds=2)
            return image

        monkeypatch.setattr(camera, "datetime", CaptureClock)
        monkeypatch.setattr(renderer_type, "render", delayed_render)
        captured = session.capture_with_instances()

    assert captured.observation.captured_at == started_at
    assert (current_time - captured.observation.captured_at).total_seconds() == 6


@pytest.mark.parametrize("field", ["cam_xpos", "cam_xmat", "cam_fovy"])
def test_concurrent_calibration_change_rejects_mixed_frame(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with pytest.raises(RuntimeError, match="camera calibration changed"):
        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
            backend = session._backend
            assert backend._camera is not None and backend._data is not None
            renderer_type = type(backend._camera._renderer)
            original_render = renderer_type.render
            count = 0

            def changed_calibration_render(renderer, *args, **kwargs):
                nonlocal count
                image = original_render(renderer, *args, **kwargs)
                count += 1
                if count == 1:
                    camera_id = backend._camera._camera_id
                    if field == "cam_fovy":
                        backend._model.cam_fovy[camera_id] += 1.0
                    elif field == "cam_xpos":
                        backend._data.cam_xpos[camera_id, 0] += 0.1
                    else:
                        # A 180-degree rotation remains a valid right-handed calibration.
                        backend._data.cam_xmat[camera_id, :6] *= -1
                return image

            monkeypatch.setattr(renderer_type, "render", changed_calibration_render)
            session.capture_with_instances()
    assert backend._camera is None

```

## Current source: scripts/verify_rgbd_capture.py
```python
"""Save one real MuJoCo RGB-D capture and an independent table-plane measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/research/process/20261003-phase1/capture"),
    )
    args = parser.parse_args()
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        captured = session.capture_with_instances()
        paths = save_captured_frame(captured, args.output)
    table_ids = [key for key, label in captured.instance_labels.items() if label == "table"]
    if len(table_ids) != 1:
        raise RuntimeError("expected one rendered table geom")
    width = captured.observation.width
    table_pixels = [
        (index % width, index // width)
        for index, geom_id in enumerate(captured.instance_ids)
        if geom_id == table_ids[0]
    ]
    valid_mask = captured.observation.valid_mask_bytes()
    valid_pixels = [
        pixel
        for pixel in table_pixels
        if valid_mask[pixel[1] * width + pixel[0]]
    ]
    if len(valid_pixels) < 1000:
        raise RuntimeError("too few valid rendered table pixels")
    sampled = valid_pixels[:: max(1, len(valid_pixels) // 100)][:100]
    # scene.xml: table centre z=-0.025 m, half-height=0.025 m, top plane z=0.
    plane_z_m = 0.0
    errors = [abs(captured.observation.world_point(pixel).z - plane_z_m) for pixel in sampled]
    if max(errors) > 0.005:
        raise RuntimeError(f"table-plane back-projection exceeds 5 mm: {max(errors):.6f} m")
    measurement = {
        "reference": "assets/robots/franka_panda/scene.xml table top plane z=0 m",
        "sample_count": len(sampled),
        "table_visible_valid_pixel_count": len(valid_pixels),
        "max_abs_z_error_m": max(errors),
        "mean_abs_z_error_m": sum(errors) / len(errors),
        "threshold_m": 0.005,
        "physics_state_hash": captured.physics_state_hash,
        "pass_state_hashes": list(captured.pass_state_hashes),
        "observation_id": captured.observation.observation_id,
        "episode_id": captured.observation.episode_id,
        "scene_id": captured.observation.scene_id,
        "calibration_version": captured.observation.calibration_version,
        "renderer_closed_after_session": session._backend._camera is None,
        "file_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
        },
    }
    measurement_path = args.output / "measurement.json"
    measurement_path.write_text(
        json.dumps(measurement, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"measurement": str(measurement_path), **measurement}, ensure_ascii=False))


if __name__ == "__main__":
    main()

```
