"""Source-bound DEVELOPMENT_ONLY marker/color diagnostics; never admission.

Measured support masks remain separate from registered image-region hypotheses.
No simulator/instance inputs, color filling, calibration or interval certificate.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import cv2
import numpy as np
import yaml
from PIL import Image

from cloud_edge_robot_arm.contracts.models import TaskTarget
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.online_intent import _INSTRUCTIONS, _matches
from cloud_edge_robot_arm.vision.pose_markers import (
    PoseMarkerEstimate,
    PoseMarkerRegistration,
    detect_pose_marker,
)


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value


def _freeze(value: object) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(v) for v in value)
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _has_symlink(path: Path) -> bool:
    # Inspect lexical ancestors before resolve() can erase their source identity.
    absolute = path.absolute()
    return any(parent.is_symlink() for parent in (absolute, *absolute.parents))


def _regular_file_under_root(path: Path, root: Path) -> bool:
    return not _has_symlink(path) and path.is_file() and path.resolve().is_relative_to(root)


@dataclass(frozen=True)
class MarkerObjectRegistration:
    registration_id: str
    pose_marker: PoseMarkerRegistration
    object_id: str
    object_class: str
    expected_color: str
    target_region_id: str
    object_half_extent_m: tuple[float, float, float]
    marker_to_object: tuple[float, ...]
    appearance_layout: Mapping[str, object]
    registration_source_hashes: Mapping[str, str]
    admission_scope: Literal["DEVELOPMENT_ONLY"] = "DEVELOPMENT_ONLY"
    root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[3], kw_only=True, repr=False
    )

    def __post_init__(self) -> None:
        if self.admission_scope != "DEVELOPMENT_ONLY":
            raise ValueError("only DEVELOPMENT_ONLY registration is implemented")

        def square(half: float) -> list[list[float]]:
            return [[-half, half], [half, half], [half, -half], [-half, -half]]

        fixed_layout = {
            "tag_polygon_m": square(0.0225),
            "quiet_polygon_m": square(0.030),
            "face_polygon_m": square(0.035),
        }
        fixed_transform = [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.03505,
            0.0,
            0.0,
            0.0,
            1.0,
        ]
        if (
            (self.object_id, self.object_class, self.expected_color, self.target_region_id)
            != ("object", "cube", "red", "target_region")
            or (
                self.pose_marker.marker_id,
                self.pose_marker.marker_size_m,
                self.pose_marker.marked_asset_sha256,
            )
            != (7, 0.045, "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4")
            or list(self.object_half_extent_m) != [0.035] * 3
            or (
                list(self.marker_to_object) != fixed_transform
                or _plain(self.appearance_layout) != fixed_layout
            )
        ):
            raise ValueError("only exact frozen colored-v2 development object/layout supported")
        if not all(
            isinstance(v, str) and v.strip()
            for v in (
                self.registration_id,
                self.object_id,
                self.object_class,
                self.target_region_id,
            )
        ) or self.expected_color not in set(_INSTRUCTIONS.values()):
            raise ValueError("complete known object/color/target registration required")
        if len(self.object_half_extent_m) != 3 or any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0
            for v in self.object_half_extent_m
        ):
            raise ValueError("known positive object dimensions required")
        flat_matrix = np.asarray(self.marker_to_object, dtype=float)
        if flat_matrix.shape != (16,) or not np.isfinite(flat_matrix).all():
            raise ValueError("complete finite marker attachment transform required")
        matrix = flat_matrix.reshape(4, 4)
        if (
            not np.array_equal(matrix[3], [0, 0, 0, 1])
            or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-9, rtol=0)
            or not math.isclose(float(np.linalg.det(matrix[:3, :3])), 1, abs_tol=1e-9)
        ):
            raise ValueError("marker attachment must be right-handed rigid transform")
        layout = _plain(self.appearance_layout)
        if set(layout) != {"tag_polygon_m", "quiet_polygon_m", "face_polygon_m"}:
            raise ValueError("exact registered tag/quiet/face layout required")
        for name in layout:
            polygon = np.asarray(layout[name], dtype=float)
            if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
                raise ValueError("complete finite four-corner layout required")
        half = self.pose_marker.marker_size_m / 2
        expected_tag = [[-half, half], [half, half], [half, -half], [-half, -half]]
        if not np.allclose(layout["tag_polygon_m"], expected_tag, atol=1e-12, rtol=0):
            raise ValueError("layout differs from registered ordered marker size")
        required = {
            "src/cloud_edge_robot_arm/vision/pose_markers.py",
            "src/cloud_edge_robot_arm/vision/observations.py",
            "src/cloud_edge_robot_arm/vision/online_intent.py",
            "src/cloud_edge_robot_arm/vision/pose_marker_assets.py",
            "src/cloud_edge_robot_arm/vision/marker_association.py",
        }
        sources = dict(self.registration_source_hashes)
        if not required <= sources.keys() or not all(_sha(v) for v in sources.values()):
            raise ValueError("actual association/detector/observation/intent sources required")
        object.__setattr__(self, "appearance_layout", _freeze(layout))
        object.__setattr__(self, "registration_source_hashes", MappingProxyType(sources))
        object.__setattr__(self, "object_half_extent_m", tuple(self.object_half_extent_m))
        object.__setattr__(self, "marker_to_object", tuple(self.marker_to_object))
        object.__setattr__(self, "root", Path(self.root))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, root: Path) -> MarkerObjectRegistration:
        data = dict(payload)
        if data.pop("schema_version", None) != "marker.object.registration.v1":
            raise ValueError("unsupported registration schema")
        data["pose_marker"] = PoseMarkerRegistration(**data["pose_marker"])
        return cls(**data, root=root)

    def digest(self) -> str:
        return _digest(
            {
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name not in {"root", "pose_marker"}
            }
            | {"pose_marker": self.pose_marker.digest()}
        )

    def sources_valid(self) -> bool:
        if _has_symlink(self.root) or not self.root.is_dir():
            return False
        root = self.root.resolve()
        asset_matched = False
        for name, expected in self.registration_source_hashes.items():
            relative = Path(name)
            path = root / relative
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not _regular_file_under_root(path, root)
            ):
                return False
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return False
            if relative.suffix == ".xml" and expected == self.pose_marker.marked_asset_sha256:
                asset_matched = True
        return asset_matched


def load_marker_registration(
    path: Path,
    *,
    expected_registry_sha256: str,
    root: Path,
) -> MarkerObjectRegistration:
    if _has_symlink(root) or not root.is_dir():
        raise ValueError("registration source root unavailable")
    if (
        not _sha(expected_registry_sha256)
        or not _regular_file_under_root(path, root.resolve())
        or (hashlib.sha256(path.read_bytes()).hexdigest() != expected_registry_sha256)
    ):
        raise ValueError("registry bytes differ from expected frozen registry")
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("registry must be an exact mapping")
    registration = MarkerObjectRegistration.from_payload(payload, root=root)
    if not registration.sources_valid():
        raise ValueError("registration source/asset binding unavailable")
    return registration


def camera_profile_hash(observation: RGBDObservation) -> str:
    return _digest(
        {
            name: getattr(observation, name)
            for name in (
                "source",
                "width",
                "height",
                "intrinsics",
                "camera_to_world",
                "depth_convention",
                "calibration_version",
            )
        }
    )


@dataclass(frozen=True)
class MarkerFrameContext:
    task_id: str
    object_id: str
    object_class: str
    target_region_id: str
    instruction: str
    task_target_payload: Mapping[str, object]
    context_hash: str
    role_bundle_hash: str
    registration_sha256: str
    active_asset_sha256: str
    observation_id: str
    observation_sha256: str
    episode_id: str
    scene_id: str
    camera_profile_sha256: str
    calibration_version: str
    plan_version: int
    command_seq: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_target_payload", _freeze(_plain(self.task_target_payload)))

    def digest(self) -> str:
        return _digest({name: getattr(self, name) for name in self.__dataclass_fields__})


def marker_frame_context(
    observation: RGBDObservation,
    registration: MarkerObjectRegistration,
    *,
    task_id: str,
    task_target: TaskTarget,
    instruction: str,
    context_hash: str,
    role_bundle_hash: str,
    active_asset_sha256: str,
    plan_version: int,
    command_seq: int,
) -> MarkerFrameContext:
    return MarkerFrameContext(
        task_id,
        task_target.object_id,
        task_target.object_class,
        task_target.target_region_id,
        instruction,
        task_target.model_dump(mode="json"),
        context_hash,
        role_bundle_hash,
        registration.digest(),
        active_asset_sha256,
        observation.observation_id,
        observation.checksum_sha256,
        observation.episode_id or "",
        observation.scene_id or "",
        camera_profile_hash(observation),
        observation.calibration_version or "",
        plan_version,
        command_seq,
    )


@dataclass(frozen=True)
class MarkerTargetAssociation:
    status: Literal["OBSERVED_CANDIDATE", "UNKNOWN", "INVALID"]
    reasons: tuple[str, ...]
    observation_sha256: str
    context_sha256: str
    registration_sha256: str
    replay_mode: Literal["LIVE_DIAGNOSTIC", "DEVELOPMENT_REPLAY"]
    pose_estimate: PoseMarkerEstimate | None = None
    support_masks: Mapping[str, bytes] = field(default_factory=dict)
    region_hypotheses: Mapping[str, bytes] = field(default_factory=dict)
    coverage: Mapping[str, object] = field(default_factory=dict)
    boundary_support: Mapping[str, object] = field(default_factory=dict)
    admission_status: Literal["NOT_ADMITTED"] = field(default="NOT_ADMITTED", init=False)
    whole_target_identity_status: Literal["UNKNOWN"] = field(default="UNKNOWN", init=False)
    extent_complete: Literal[False] = field(default=False, init=False)
    geometric_error_bound_m: None = field(default=None, init=False)
    motion_bound_m_s: None = field(default=None, init=False)
    angular_velocity_bound_rad_s: None = field(default=None, init=False)
    stability_status: Literal["UNKNOWN"] = field(default="UNKNOWN", init=False)

    def __post_init__(self) -> None:
        if self.status not in {"OBSERVED_CANDIDATE", "UNKNOWN", "INVALID"} or (
            self.replay_mode not in {"LIVE_DIAGNOSTIC", "DEVELOPMENT_REPLAY"}
        ):
            raise ValueError("diagnostic status/mode required")
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(
            self,
            "support_masks",
            MappingProxyType({name: bytes(value) for name, value in self.support_masks.items()}),
        )
        object.__setattr__(self, "coverage", _freeze(_plain(self.coverage)))
        object.__setattr__(self, "boundary_support", _freeze(_plain(self.boundary_support)))
        object.__setattr__(
            self,
            "region_hypotheses",
            MappingProxyType(
                {name: bytes(value) for name, value in self.region_hypotheses.items()}
            ),
        )


def _associate(
    observation: RGBDObservation,
    registration: MarkerObjectRegistration,
    context: MarkerFrameContext,
    now: datetime,
    replay: bool,
) -> MarkerTargetAssociation:
    def result(
        status: Literal["OBSERVED_CANDIDATE", "UNKNOWN", "INVALID"], *reasons: str, **details: Any
    ) -> MarkerTargetAssociation:
        return MarkerTargetAssociation(
            status,
            tuple(reasons),
            observation.checksum_sha256,
            context.digest(),
            registration.digest(),
            "DEVELOPMENT_REPLAY" if replay else "LIVE_DIAGNOSTIC",
            **details,
        )

    if registration.admission_scope != "DEVELOPMENT_ONLY" or not registration.sources_valid():
        return result("INVALID", "registration_source_changed")
    try:
        observation = RGBDObservation.model_validate(observation.model_dump())
    except ValueError:
        return result("INVALID", "invalid_registered_rgbd")
    if not all(_sha(v) for v in (context.context_hash, context.role_bundle_hash)) or (
        not context.task_id
        or type(context.plan_version) is not int
        or type(context.command_seq) is not int
        or context.plan_version < 0
        or context.command_seq < 0
    ):
        return result("INVALID", "current_context_missing")
    expected_target = {
        "object_id": context.object_id,
        "object_class": context.object_class,
        "target_region_id": context.target_region_id,
    }
    if _plain(context.task_target_payload) != expected_target or (
        (context.object_id, context.object_class, context.target_region_id)
        != (registration.object_id, registration.object_class, registration.target_region_id)
    ):
        return result("INVALID", "full_task_target_mismatch")
    color = _INSTRUCTIONS.get(context.instruction.strip())
    if color is None:
        return result("UNKNOWN", "instruction_outside_supported_whole_sentence")
    if color != registration.expected_color:
        return result("INVALID", "requested_color_registration_mismatch")
    if context.active_asset_sha256 != registration.pose_marker.marked_asset_sha256 or (
        context.registration_sha256 != registration.digest()
    ):
        return result("INVALID", "registration_asset_mismatch")
    if (
        context.observation_id,
        context.observation_sha256,
        context.episode_id,
        context.scene_id,
        context.calibration_version,
    ) != (
        observation.observation_id,
        observation.checksum_sha256,
        observation.episode_id,
        observation.scene_id,
        observation.calibration_version,
    ) or (not context.episode_id or not context.scene_id or not context.calibration_version):
        return result("INVALID", "frame_identity_mismatch")
    if context.camera_profile_sha256 != camera_profile_hash(observation):
        return result("INVALID", "camera_profile_changed")
    if now.tzinfo is None or not 0 <= (now - observation.captured_at).total_seconds() <= 5:
        return result("UNKNOWN", "capture_not_fresh")
    pose = detect_pose_marker(observation, registration.pose_marker)
    if pose.status != "OBSERVED" or pose.ordered_corners_px is None:
        return result("UNKNOWN", pose.reason, pose_estimate=pose)
    rgb = np.asarray(
        Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))).convert("RGB")
    )
    colors, inverse = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    matching = np.asarray([_matches(color, sample / 255) for sample in colors], dtype=np.uint8)
    raw_color = matching[inverse].reshape(rgb.shape[:2])
    contours, hierarchy = cv2.findContours(raw_color, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or len(contours) != 2 or tuple(hierarchy[0, :, 3]) != (-1, 0):
        return result(
            "UNKNOWN", "requested_color_ring_missing_ambiguous_or_broken", pose_estimate=pose
        )
    outer = contours[0]
    left, top, width, height = cv2.boundingRect(outer)
    if (
        left == 0
        or top == 0
        or left + width == observation.width
        or top + height == observation.height
    ):
        return result("UNKNOWN", "color_outer_boundary_clipped", pose_estimate=pose)
    corners = np.asarray(pose.ordered_corners_px, dtype=np.float32)
    # A single central observed hole is a topology candidate only. Layout projection
    # below is kept as a hypothesis; no red mask or object silhouette is filled.
    if any(
        cv2.pointPolygonTest(contours[1], tuple(float(v) for v in point), False) < 0
        for point in corners
    ):
        return result("UNKNOWN", "color_hole_does_not_contain_registered_tag", pose_estimate=pose)
    half = registration.pose_marker.marker_size_m / 2
    source = np.asarray([[-half, half], [half, half], [half, -half], [-half, -half]], np.float32)
    homography = cv2.getPerspectiveTransform(source, corners)
    masks = {"requested_color": raw_color.tobytes()}
    hypotheses: dict[str, bytes] = {}
    coverage: dict[str, object] = {
        "requested_color_pixels": int(raw_color.sum()),
        "color_hole_count": 1,
        "color_hole_filling": False,
        "coverage_is_diagnostic_not_acceptance_threshold": True,
        "requested_color": color,
        "object_id": context.object_id,
        "object_class": context.object_class,
        "target_region_id": context.target_region_id,
        "destination_observed": False,
        "outer_boundary_verified": False,
        "depth_error_bound_m": None,
    }
    valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(rgb.shape[:2])
    for name, polygon in registration.appearance_layout.items():
        projected = cv2.perspectiveTransform(np.asarray([polygon], np.float32), homography)[0]
        if (
            not np.isfinite(projected).all()
            or np.any(projected < 1)
            or (
                np.any(projected[:, 0] >= observation.width - 1)
                or np.any(projected[:, 1] >= observation.height - 1)
            )
        ):
            return result("UNKNOWN", "layout_region_clipped", pose_estimate=pose)
        region = np.zeros(rgb.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(region, np.round(projected).astype(np.int32), 1)
        hypotheses[name.replace("polygon_m", "region")] = region.tobytes()
        coverage[name + "_hypothesis_pixels"] = int(region.sum())
        if np.any((region > 0) & (valid == 0)):
            return result("UNKNOWN", "layout_depth_unavailable", pose_estimate=pose)
    neutral = (np.ptp(rgb.astype(int), axis=2) <= 30).astype(np.uint8)
    quiet = np.frombuffer(hypotheses["quiet_region"], dtype=np.uint8).reshape(rgb.shape[:2])
    tag = np.frombuffer(hypotheses["tag_region"], dtype=np.uint8).reshape(rgb.shape[:2])
    # Match immutable detector's 2mm plane sanity, not a calibrated error bound.
    # Median3x3 interior patches avoid assigning antialiased outer border/table
    # samples to the quiet face. The outer boundary remains explicitly unverified.
    interior = cv2.erode(quiet, np.ones((3, 3), np.uint8)) > 0
    ys, xs = np.nonzero(interior & (tag == 0))
    depth = np.asarray(observation.depth_values(), dtype=np.float32).reshape(rgb.shape[:2])
    medians = cv2.medianBlur(depth, 3)[ys, xs]
    fx, fy, cx, cy = observation.intrinsics
    points = np.column_stack(((xs - cx) * medians / fx, (ys - cy) * medians / fy, medians))
    transform = np.asarray(observation.camera_to_world).reshape(4, 4)
    world = points @ transform[:3, :3].T + transform[:3, 3]
    assert pose.rotation_marker_to_world is not None and pose.marker_center_world_m is not None
    normal = np.asarray(pose.rotation_marker_to_world).reshape(3, 3)[:, 2]
    residuals = np.abs((world - np.asarray(pose.marker_center_world_m)) @ normal)
    if len(residuals) == 0 or np.any(residuals > 0.002):
        return result("UNKNOWN", "quiet_plane_sanity_failed", pose_estimate=pose)
    coverage["quiet_plane_sanity_limit_m"] = 0.002
    coverage["quiet_plane_sanity_is_calibrated_bound"] = False
    coverage["quiet_patch_max_observed_residual_m"] = float(residuals.max())
    masks["observed_neutral_quiet"] = (quiet & (1 - tag) & neutral & valid).tobytes()
    masks["observed_tag_depth_support"] = (tag & valid).tobytes()
    coverage["observed_neutral_quiet_pixels"] = int(
        np.frombuffer(masks["observed_neutral_quiet"], dtype=np.uint8).sum()
    )
    # Select measured exterior support from the actual color contour, not the
    # homography's face region. No interior color/quiet/tag hole is filled.
    boundary = np.zeros(rgb.shape[:2], dtype=np.uint8)
    cv2.drawContours(boundary, contours, 0, 1, thickness=1)
    boundary &= raw_color
    neighborhood = np.zeros_like(boundary)
    ny, nx = np.nonzero((cv2.dilate(boundary, np.ones((3, 3), np.uint8)) > 0) & (raw_color == 0))
    for y, x in zip(ny, nx, strict=True):
        if cv2.pointPolygonTest(outer, (float(x), float(y)), False) < 0:
            neighborhood[y, x] = 1
    if (
        not boundary.any()
        or not neighborhood.any()
        or np.any(((boundary | neighborhood) > 0) & (valid == 0))
    ):
        return result("UNKNOWN", "outer_boundary_depth_unavailable", pose_estimate=pose)

    def samples(mask: np.ndarray) -> dict[str, object]:
        sy, sx = np.nonzero(mask)
        measured_depth = depth[sy, sx]
        camera = np.column_stack(
            ((sx - cx) * measured_depth / fx, (sy - cy) * measured_depth / fy, measured_depth)
        )
        measured_world = camera @ transform[:3, :3].T + transform[:3, 3]
        signed_residual = (measured_world - np.asarray(pose.marker_center_world_m)) @ normal
        return {
            "pixels": np.column_stack((sx, sy)).tolist(),
            "rgb": rgb[sy, sx].tolist(),
            "depth_m": measured_depth.tolist(),
            "points_world_m": measured_world.tolist(),
            "marker_plane_signed_residual_m": signed_residual.tolist(),
            "observed_world_aabb_min_m": measured_world.min(axis=0).tolist(),
            "observed_world_aabb_max_m": measured_world.max(axis=0).tolist(),
            "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
        }

    masks["observed_color_outer_boundary"] = boundary.tobytes()
    masks["observed_outer_boundary_neighbor_depth"] = neighborhood.tobytes()
    boundary_support = {
        "source": "observed_requested_color_outer_contour_and_exterior_neighbors",
        "depth_convention": observation.depth_convention,
        "pixel_coordinates": "integer_uv_centers",
        "metric_coordinates": "uncalibrated_rgbd_world_estimates",
        "calibrated_error_bound_m": None,
        "measured_color_contour_is_body_extent": False,
        "outer_boundary": samples(boundary),
        "outer_neighborhood": samples(neighborhood),
    }
    # Strict raw depth ordering is exposed for later calibration. Antialias and
    # coplanar samples are retained, not discarded using an invented tolerance.
    # Even positive separation is not a calibrated complete-body certificate.
    rim_depth_max = float(depth[raw_color > 0].max())
    neighbor_gap = depth[neighborhood > 0].astype(float) - rim_depth_max
    coverage["observed_color_contour_bbox_px"] = [left, top, width, height]
    coverage["observed_outer_boundary_pixels"] = int(boundary.sum())
    coverage["observed_outer_neighborhood_pixels"] = int(neighborhood.sum())
    coverage["outer_boundary_depth_support_status"] = "OBSERVED_ALL_VALID"
    coverage["outer_boundary_depth_separation_status"] = "UNKNOWN_UNCALIBRATED"
    coverage["outer_neighbor_strictly_farther_than_rim_pixels"] = int((neighbor_gap > 0).sum())
    coverage["outer_neighbor_depth_minus_rim_max_m"] = neighbor_gap.tolist()
    return result(
        "OBSERVED_CANDIDATE",
        "registered_tag_and_color_ring_diagnostic_only",
        pose_estimate=pose,
        support_masks=masks,
        region_hypotheses=hypotheses,
        coverage=coverage,
        boundary_support=boundary_support,
    )


def associate_marker_target(
    observation: RGBDObservation,
    registration: MarkerObjectRegistration,
    context: MarkerFrameContext,
    *,
    now: datetime,
) -> MarkerTargetAssociation:
    return _associate(observation, registration, context, now, False)


def replay_marker_target_development(
    observation: RGBDObservation,
    registration: MarkerObjectRegistration,
    context: MarkerFrameContext,
) -> MarkerTargetAssociation:
    """Original capture-time replay only; cannot produce native/fresh admission."""
    return _associate(observation, registration, context, observation.captured_at, True)
