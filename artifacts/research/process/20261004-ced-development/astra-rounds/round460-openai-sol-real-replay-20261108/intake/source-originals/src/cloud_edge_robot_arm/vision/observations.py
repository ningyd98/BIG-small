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
