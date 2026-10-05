"""可空标定的离线 RGB-D 契约，明确保存能力缺口与上游证据。"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from PIL import Image


def decode_image(
    value: Any, *, kind: Literal["rgb", "depth"], raw_color_order: str = "RGB"
) -> np.ndarray:
    """编码帧由Pillow解码为RGB；只有原始BGR数组需要交换通道。"""
    if isinstance(value, np.ndarray) and value.ndim >= 2 and value.dtype != object:
        result = np.asarray(value)
        if kind == "rgb":
            if result.ndim != 3 or result.shape[2] != 3 or result.dtype != np.uint8:
                raise ValueError("raw RGB image must be HxWx3 uint8")
            if raw_color_order not in {"RGB", "BGR"}:
                raise ValueError("raw color order is unknown")
            return result[..., ::-1].copy() if raw_color_order == "BGR" else result.copy()
        if result.ndim != 2 or result.dtype.kind not in "uif":
            raise ValueError("raw depth must be a two-dimensional numeric array")
        return result.copy()
    if isinstance(value, np.ndarray):
        if value.dtype == object or value.dtype.kind not in "uSV":
            raise ValueError("encoded image must contain byte values")
        payload = value.tobytes()
    elif isinstance(value, (bytes, bytearray, memoryview, np.bytes_, np.void)):
        payload = bytes(value)
    else:
        raise ValueError("unsupported encoded image representation")
    if not payload:
        raise ValueError("encoded image is empty")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if kind == "rgb":
                return np.array(image.convert("RGB"), dtype=np.uint8)
            result = np.array(image)
    except (OSError, ValueError) as exc:
        raise ValueError("image frame cannot be decoded") from exc
    if result.ndim != 2 or result.dtype.kind not in "uif":
        raise ValueError("decoded depth must preserve a numeric two-dimensional image")
    # PNG I;16 is uint16 on current Pillow; older integer PNG decoders need lossless narrowing.
    if result.dtype == np.int32 and result.size and result.min() >= 0 and result.max() <= 65535:
        result = result.astype(np.uint16)
    return result


def metric_depth(
    raw: np.ndarray, scale_m: float | None, evidence: str | None
) -> tuple[np.ndarray | None, np.ndarray]:
    valid = np.isfinite(raw) & (raw > 0)
    if scale_m is None:
        return None, valid
    if not evidence:
        raise ValueError("depth scale requires source evidence")
    if not np.isfinite(scale_m) or scale_m <= 0:
        raise ValueError("depth scale must be finite and positive")
    depth = np.zeros(raw.shape, dtype=np.float32)
    depth[valid] = raw[valid].astype(np.float32) * scale_m
    valid &= np.isfinite(depth) & (depth > 0)
    depth[~valid] = 0
    return depth, valid


def validate_intrinsics(value: np.ndarray | None) -> np.ndarray | None:
    if value is None:
        return None
    matrix = np.asarray(value, dtype=np.float64)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or matrix[0, 0] <= 0
        or matrix[1, 1] <= 0
        or not np.allclose(matrix[2], [0, 0, 1])
    ):
        raise ValueError("camera intrinsics must be a finite 3x3 pinhole matrix")
    return matrix


def validate_transform(value: dict[str, Any]) -> dict[str, Any]:
    if not value.get("from_frame") or not value.get("to_frame"):
        raise ValueError("transform requires an explicit direction")
    if value.get("translation_unit") != "m":
        raise ValueError("transform translation unit must be metres")
    matrix = np.asarray(value.get("matrix"), dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("transform must be finite 4x4")
    rotation = matrix[:3, :3]
    if (
        not np.allclose(matrix[3], [0, 0, 0, 1])
        or not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-4)
        or not np.isclose(np.linalg.det(rotation), 1, atol=1e-4)
    ):
        raise ValueError("transform must have a right-handed rigid rotation")
    return {**value, "matrix": matrix.tolist()}


@dataclass
class DatasetSample:
    dataset_id: str
    source_revision: str
    sample_kind: Literal["trajectory_observation", "static_multiview_scene"]
    source_file: str
    relative_path: str
    source_sha256: str
    frame_index: int
    camera_id: str
    official_split: str | None
    rgb: np.ndarray = field(repr=False)
    depth_raw: np.ndarray = field(repr=False)
    task_id: str | None = None
    episode_id: str | None = None
    scene_id: str | None = None
    protocol: str | None = None
    timestamp: Any = None
    time_basis: str = "unknown"
    depth_scale_m: float | None = None
    depth_scale_evidence: str | None = None
    depth_excluded_values: list[float] = field(default_factory=list)
    depth_validity_evidence: str | None = None
    depth_semantics: str = "unknown"
    K_rgb: np.ndarray | None = field(default=None, repr=False)
    K_depth: np.ndarray | None = field(default=None, repr=False)
    distortion: dict[str, Any] = field(default_factory=dict)
    rgb_depth_aligned: bool | None = None
    alignment_evidence: str | None = None
    temporal_alignment: bool | None = None
    temporal_evidence: str | None = None
    transforms: dict[str, dict[str, Any]] = field(default_factory=dict)
    robot_state: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    annotations: dict[str, Any] = field(default_factory=dict, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)
    depth_m: np.ndarray | None = field(init=False, repr=False)
    depth_valid_mask: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            self.rgb.dtype != np.uint8
            or self.rgb.ndim != 3
            or self.rgb.shape[2] != 3
            or not self.rgb.size
        ):
            raise ValueError("rgb must be nonempty RGB uint8 HxWx3")
        if self.depth_raw.ndim != 2 or not self.depth_raw.size:
            raise ValueError("depth must be a nonempty numeric image")
        if self.depth_raw.dtype.kind not in "uif":
            raise ValueError("depth dtype must be numeric; pickle/object forbidden")
        self.depth_m, self.depth_valid_mask = metric_depth(
            self.depth_raw, self.depth_scale_m, self.depth_scale_evidence
        )
        if self.depth_excluded_values:
            if (
                not self.depth_validity_evidence
                or not np.isfinite(self.depth_excluded_values).all()
            ):
                raise ValueError("depth exclusion requires finite values and evidence")
            self.depth_valid_mask &= ~np.isin(self.depth_raw, self.depth_excluded_values)
            if self.depth_m is not None:
                self.depth_m[~self.depth_valid_mask] = 0
        self.K_rgb = validate_intrinsics(self.K_rgb)
        self.K_depth = validate_intrinsics(self.K_depth)
        self.transforms = {k: validate_transform(v) for k, v in self.transforms.items()}
        if self.rgb_depth_aligned is True:
            if not self.alignment_evidence or self.rgb.shape[:2] != self.depth_raw.shape:
                raise ValueError("RGB-Depth alignment requires evidence and equal dimensions")
        if self.temporal_alignment is True and not self.temporal_evidence:
            raise ValueError("temporal alignment requires source evidence")

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "rgbd_decodable": bool(self.depth_valid_mask.any()),
            "depth_metric": self.depth_m is not None,
            "rgb_depth_alignment": self.rgb_depth_aligned is True,
            "camera_geometry": (
                self.depth_m is not None
                and self.K_depth is not None
                and self.depth_semantics == "optical_z"
            ),
            "robot_base_geometry": (
                self.depth_m is not None
                and self.K_depth is not None
                and self.depth_semantics == "optical_z"
                and any(
                    t["from_frame"] in {"camera", "depth_camera"} and t["to_frame"] == "robot_base"
                    for t in self.transforms.values()
                )
            ),
            "temporal_alignment": self.temporal_alignment is True,
            "action_labels": self.action is not None and bool(self.action.get("semantics")),
            "task_annotations": bool(self.annotations),
        }

    def model_input(self) -> dict[str, Any]:
        """普通感知通道只含观察与来源；GT由annotations单独读取。"""
        return {
            "dataset_id": self.dataset_id,
            "source_revision": self.source_revision,
            "sample_kind": self.sample_kind,
            "frame_index": self.frame_index,
            "task_id": self.task_id,
            "episode_id": self.episode_id,
            "scene_id": self.scene_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "time_basis": self.time_basis,
            "source": "dataset_replay",
            "rgb": self.rgb,
            "depth_raw": self.depth_raw,
            "depth_m": self.depth_m,
            "depth_valid_mask": self.depth_valid_mask,
            "K_rgb": self.K_rgb,
            "K_depth": self.K_depth,
            "capabilities": self.capabilities,
        }


def backproject_depth(sample: DatasetSample, *, with_rgb: bool = False) -> np.ndarray:
    if sample.depth_m is None:
        raise ValueError("metric depth requires verified units")
    if sample.K_depth is None:
        raise ValueError("depth camera intrinsics are unavailable")
    if sample.depth_semantics != "optical_z":
        raise ValueError("depth optical-z semantics must be verified")
    if with_rgb and sample.rgb_depth_aligned is not True:
        raise ValueError("color projection requires RGB-Depth alignment evidence")
    v, u = np.nonzero(sample.depth_valid_mask)
    z = sample.depth_m[v, u]
    matrix = sample.K_depth
    points = np.column_stack(
        ((u - matrix[0, 2]) * z / matrix[0, 0], (v - matrix[1, 2]) * z / matrix[1, 1], z)
    ).astype(np.float32)
    return np.column_stack((points, sample.rgb[v, u])) if with_rgb else points
