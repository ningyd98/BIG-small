"""Versioned current-frame rigid-model derivation, with no execution authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np

from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY, marker_family
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.registered_objects import (
    RegisteredObjectGeometry,
    derive_registered_object_geometry,
)
from cloud_edge_robot_arm.vision.worker_owner import pin_worker_source_inventory

PREVIEW_SOURCE_PATHS = frozenset(
    {
        "src/cloud_edge_robot_arm/vision/registered_object_tracking.py",
        "src/cloud_edge_robot_arm/vision/registered_objects.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "src/cloud_edge_robot_arm/vision/native_calibration.py",
        "src/cloud_edge_robot_arm/vision/marker_families.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/vision/tracking.py",
        "src/cloud_edge_robot_arm/vision/worker_owner.py",
        "src/cloud_edge_robot_arm/vision/top_grasp.py",
        "src/cloud_edge_robot_arm/research/native_collection_grounding.py",
        "src/cloud_edge_robot_arm/vision/owner_registration.py",
    }
)
_CONTEXT_FIELDS = (
    "episode_id",
    "scene_id",
    "calibration_version",
    "source",
    "width",
    "height",
    "intrinsics",
    "camera_to_world",
)


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class RegisteredObjectTrackV1:
    """当前帧跟踪结果只保留注册模型推导，不宣称完整可见或校准精度。"""

    status: Literal["DERIVED", "UNKNOWN"]
    reason: str
    observation_id: str
    observation_checksum_sha256: str
    captured_at: datetime
    evaluated_at: datetime
    episode_id: str | None
    scene_id: str | None
    calibration_version: str | None
    source: str
    width: int
    height: int
    intrinsics: tuple[float, ...]
    camera_to_world: tuple[float, ...]
    registration_id: str
    registration_sha256: str
    marker_registration_hash: str
    marker_family_id: str
    asset_path: str
    asset_sha256: str
    source_sha256: str
    source_hashes: tuple[tuple[str, str], ...]
    is_new_frame: bool
    wrapper_freshness: Literal["CHECKED", "REJECTED"]
    geometry: RegisteredObjectGeometry | None
    schema_version: Literal["registered.object.track.v1"] = "registered.object.track.v1"
    wrapper_asset_validation: Literal["VERIFIED_LOCAL_BYTES"] = "VERIFIED_LOCAL_BYTES"
    source_validation: Literal["LOCAL_BYTE_CONSISTENCY_ONLY"] = "LOCAL_BYTE_CONSISTENCY_ONLY"
    native_authority: Literal["UNAVAILABLE"] = "UNAVAILABLE"

    def to_payload(self) -> dict:
        """返回独立的JSON值，调用方修改不能影响已冻结的结果。"""
        payload = asdict(self)
        payload["source_hashes"] = dict(self.source_hashes)
        return json.loads(
            json.dumps(payload, default=lambda value: value.isoformat(), allow_nan=False)
        )

    def digest(self) -> str:
        """绑定当前帧、注册几何、来源身份和未知量。"""
        return _digest(self.to_payload())


class RegisteredObjectTrackerV1:
    """只用当前注册标记生成模型姿态；失败帧不复用旧姿态。"""

    def __init__(
        self,
        reference: RGBDObservation,
        registration: NativeGeometryRegistration,
        *,
        source_root: Path,
        source_hashes: Mapping[str, str],
    ) -> None:
        if (
            type(reference) is not RGBDObservation
            or type(registration) is not NativeGeometryRegistration
        ):
            raise TypeError("exact RGBD observation and native geometry registration required")
        self._reference = RGBDObservation.model_validate(reference.model_dump())
        self._registration = NativeGeometryRegistration(registration.to_payload())
        self._source_root = Path(source_root)
        payload = self._registration.to_payload()
        asset = payload["asset_path"]
        # The 75mm validator also reads the original comparison asset and checks
        # its known hash; pin that dependency in the local source inventory too.
        self._required_paths = PREVIEW_SOURCE_PATHS | {
            asset,
            marker_family(LEGACY_FAMILY).asset_path,
        }
        self._source_hashes = dict(
            pin_worker_source_inventory(
                self._source_root, source_hashes, required_paths=self._required_paths
            )
        )
        if self._source_hashes[asset] != self._registration.pose_marker.marked_asset_sha256:
            raise ValueError("source inventory and registered asset hash differ")
        self._verify_sources()
        self._registration_sha256 = _digest(payload)
        self._source_sha256 = _digest(self._source_hashes)
        reason = self._binding_reason(self._reference, datetime.now(UTC))
        if reason:
            raise ValueError("initial registered observation unavailable: " + reason)
        geometry = derive_registered_object_geometry(self._reference, self._registration)
        self._verify_sources()
        reason = self._binding_reason(self._reference, datetime.now(UTC))
        if reason or geometry.status != "DERIVED":
            raise ValueError(
                "initial registered geometry unavailable: " + (reason or geometry.reason)
            )
        self._last_seen = self._reference
        self._seen = {self._reference.observation_id}
        self._last_successful_observation = self._reference
        self._last_successful_geometry = geometry

    def _verify_sources(self) -> None:
        pin_worker_source_inventory(
            self._source_root, self._source_hashes, required_paths=self._required_paths
        )
        self._registration.validate_asset(self._source_root)

    def _binding_reason(self, observation: RGBDObservation, evaluated_at: datetime) -> str | None:
        for field in _CONTEXT_FIELDS:
            if getattr(observation, field) != getattr(self._reference, field):
                return "observation_" + field + "_changed"
        for field in ("episode_id", "scene_id", "calibration_version"):
            value = getattr(observation, field)
            if not value or not value.strip():
                return "observation_" + field + "_missing"
        rotation = np.asarray(observation.camera_to_world).reshape(4, 4)[:3, :3]
        aligned_axis = np.isclose(np.abs(rotation[:2, :2]), 0.0, atol=1e-9) | np.isclose(
            np.abs(rotation[:2, :2]), 1.0, atol=1e-9
        )
        if not (
            np.allclose(rotation[:, 2], [0.0, 0.0, -1.0], atol=1e-9, rtol=0.0)
            and aligned_axis.all()
        ):
            return "camera_orientation_not_supported"
        age = (evaluated_at - observation.captured_at).total_seconds()
        return "capture_time_not_fresh" if age < -0.05 or age > 5.0 else None

    def _recheck_current(self, observation: RGBDObservation) -> tuple[str | None, datetime]:
        # Used after the collection's region stage as well as after marker work.
        current = RGBDObservation.model_validate(observation.model_dump())
        self._verify_sources()
        evaluated_at = datetime.now(UTC)
        return self._binding_reason(current, evaluated_at), evaluated_at

    def _result(
        self,
        observation: RGBDObservation,
        *,
        evaluated_at: datetime,
        is_new: bool,
        reason: str | None,
        geometry: RegisteredObjectGeometry | None = None,
    ) -> RegisteredObjectTrackV1:
        payload = self._registration.to_payload()
        return RegisteredObjectTrackV1(
            status="UNKNOWN" if reason else "DERIVED",
            reason=reason or "uncalibrated_registered_model_derivation",
            observation_id=observation.observation_id,
            observation_checksum_sha256=observation.checksum_sha256,
            captured_at=observation.captured_at,
            evaluated_at=evaluated_at,
            episode_id=observation.episode_id,
            scene_id=observation.scene_id,
            calibration_version=observation.calibration_version,
            source=observation.source,
            width=observation.width,
            height=observation.height,
            intrinsics=observation.intrinsics,
            camera_to_world=observation.camera_to_world,
            registration_id=payload["registration_id"],
            registration_sha256=self._registration_sha256,
            marker_registration_hash=self._registration.pose_marker.digest(),
            marker_family_id=self._registration.marker_family_id or LEGACY_FAMILY,
            asset_path=payload["asset_path"],
            asset_sha256=self._registration.pose_marker.marked_asset_sha256,
            source_sha256=self._source_sha256,
            source_hashes=tuple(sorted(self._source_hashes.items())),
            is_new_frame=is_new,
            wrapper_freshness="REJECTED" if reason else "CHECKED",
            geometry=None if reason else geometry,
        )

    def update(self, observation: RGBDObservation) -> RegisteredObjectTrackV1:
        """重新核对当前帧与源文件；记录失败身份但不改写成功姿态时间锚点。"""
        if type(observation) is not RGBDObservation:
            raise TypeError("exact RGBD observation required")
        current = RGBDObservation.model_validate(observation.model_dump())
        self._verify_sources()
        evaluated_at = datetime.now(UTC)
        reason = self._binding_reason(current, evaluated_at)
        repeat = current.observation_id == self._last_seen.observation_id
        is_new = not repeat
        if reason is None:
            if repeat and current.checksum_sha256 != self._last_seen.checksum_sha256:
                reason = "reused_frame_with_changed_payload"
            elif not repeat:
                if current.observation_id in self._seen:
                    reason = "observation_replay"
                elif (
                    current.captured_at <= self._last_seen.captured_at
                    or current.sim_time_s <= self._last_seen.sim_time_s
                ):
                    reason = "capture_not_new_and_monotonic"
                else:
                    self._seen.add(current.observation_id)
                    self._last_seen = current
        if reason:
            return self._result(current, evaluated_at=evaluated_at, is_new=is_new, reason=reason)
        geometry = derive_registered_object_geometry(current, self._registration)
        reason, evaluated_at = self._recheck_current(current)
        if reason is None and geometry.status != "DERIVED":
            reason = geometry.reason
        if (
            reason is None
            and current.observation_id != self._last_successful_observation.observation_id
        ):
            previous = self._last_successful_observation
            elapsed = (
                current.sim_time_s - previous.sim_time_s
                if current.source in {"mujoco_camera", "isaac_camera"}
                else (current.captured_at - previous.captured_at).total_seconds()
            )
            displacement = float(
                np.linalg.norm(
                    np.asarray(geometry.object_center_world_m)
                    - np.asarray(self._last_successful_geometry.object_center_world_m)
                )
            )
            if elapsed <= 0 or displacement > 1.5 * elapsed + 0.012:
                reason = "target_identity_temporal_jump"
        if reason is None:
            self._last_successful_observation = current
            self._last_successful_geometry = geometry
        return self._result(
            current, evaluated_at=evaluated_at, is_new=is_new, reason=reason, geometry=geometry
        )
