"""Single-frame registered rigid-model geometry, without admission authority.

Only the marker surface is observed. Object geometry comes from the declared
rigid registration; its asset bytes, measurement error and freshness are not
certified here. Existing consumers retain their asset/source and admission gates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerEstimate, detect_pose_marker

if TYPE_CHECKING:
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration


@dataclass(frozen=True, slots=True)
class RegisteredObjectGeometry:
    """分开记录单帧标记测量与注册刚体推导，不能作为动作准入凭据。"""

    status: Literal["DERIVED", "UNKNOWN"]
    reason: str
    observation_id: str
    observation_checksum_sha256: str
    captured_at: datetime
    episode_id: str | None
    calibration_version: str | None
    observation_source: str
    geometry_sha256: str
    registration_id: str
    object_id: str
    asset_path: str
    asset_sha256: str
    marker_registration_hash: str
    marker_estimate: PoseMarkerEstimate | None = None
    object_center_world_m: tuple[float, float, float] | None = None
    rotation_object_to_world: tuple[float, ...] | None = None
    grasp_tcp_world_m: tuple[float, float, float] | None = None
    geometric_error_bound_m: None = None
    object_surface_visibility: Literal["UNKNOWN"] = "UNKNOWN"
    freshness: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    native_authority: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    asset_validation: Literal["NOT_PERFORMED"] = "NOT_PERFORMED"
    geometry_basis: Literal["REGISTERED_RIGID_MODEL"] = "REGISTERED_RIGID_MODEL"


def derive_registered_object_geometry(
    observation: RGBDObservation, registration: NativeGeometryRegistration
) -> RegisteredObjectGeometry:
    """从同帧原始深度标记与注册变换推导物体中心及抓取点，保留未知量。"""
    # Local import avoids a cycle with the calibration consumer of this helper.
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

    if (
        type(observation) is not RGBDObservation
        or type(registration) is not NativeGeometryRegistration
    ):
        raise TypeError("exact RGBD observation and native geometry registration required")
    current = RGBDObservation.model_validate(observation.model_dump())
    scope = NativeGeometryRegistration(registration.to_payload())
    payload = scope.to_payload()
    if type(payload["registration_id"]) is not str:
        raise ValueError("string registered geometry identity required")
    marker_registration = scope.pose_marker
    provenance = dict(
        observation_id=current.observation_id,
        observation_checksum_sha256=current.checksum_sha256,
        captured_at=current.captured_at,
        episode_id=current.episode_id,
        calibration_version=current.calibration_version,
        observation_source=current.source,
        geometry_sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
        registration_id=payload["registration_id"],
        object_id=payload["object_id"],
        asset_path=payload["asset_path"],
        asset_sha256=marker_registration.marked_asset_sha256,
        marker_registration_hash=marker_registration.digest(),
    )
    camera = current.model_dump(mode="json")
    if any(camera[key] != value for key, value in payload["camera"].items()):
        return RegisteredObjectGeometry("UNKNOWN", "registered_camera_mismatch", **provenance)

    marker = detect_pose_marker(current, marker_registration)
    if type(marker) is not PoseMarkerEstimate:
        return RegisteredObjectGeometry("UNKNOWN", "invalid_marker_result", **provenance)
    if (
        marker.registration_hash != marker_registration.digest()
        or marker.observation_id != current.observation_id
        or marker.observation_checksum_sha256 != current.checksum_sha256
        or marker.captured_at != current.captured_at
    ):
        return RegisteredObjectGeometry("UNKNOWN", "marker_binding_mismatch", **provenance)
    if marker.status != "OBSERVED":
        return RegisteredObjectGeometry(
            "UNKNOWN", marker.reason, marker_estimate=marker, **provenance
        )
    if marker.observed_marker_ids != (marker_registration.marker_id,):
        return RegisteredObjectGeometry("UNKNOWN", "marker_identity_mismatch", **provenance)
    try:
        marker_center = np.asarray(marker.marker_center_world_m, dtype=float)
        marker_rotation = np.asarray(marker.rotation_marker_to_world, dtype=float).reshape(3, 3)
    except (TypeError, ValueError):
        return RegisteredObjectGeometry("UNKNOWN", "marker_geometry_unavailable", **provenance)
    if (
        marker_center.shape != (3,)
        or not np.isfinite(marker_center).all()
        or not np.isfinite(marker_rotation).all()
    ):
        return RegisteredObjectGeometry("UNKNOWN", "marker_geometry_unavailable", **provenance)

    # A_T_B maps B coordinates to A. The observed marker pose and the registered
    # marker attachment determine the model pose; no second tool offset is added.
    attached = np.asarray(payload["marker_to_object"]).reshape(4, 4)
    rotation = marker_rotation @ attached[:3, :3].T
    center = marker_center - rotation @ attached[:3, 3]
    grasp = center + rotation @ np.asarray(payload["object_to_tcp"]).reshape(4, 4)[:3, 3]
    if not np.isfinite(center).all() or not np.isfinite(grasp).all():
        return RegisteredObjectGeometry("UNKNOWN", "derived_geometry_nonfinite", **provenance)
    return RegisteredObjectGeometry(
        "DERIVED",
        "uncalibrated_registered_model_derivation",
        marker_estimate=marker,
        object_center_world_m=tuple(float(v) for v in center),
        rotation_object_to_world=tuple(float(v) for v in rotation.ravel()),
        grasp_tcp_world_m=tuple(float(v) for v in grasp),
        **provenance,
    )
