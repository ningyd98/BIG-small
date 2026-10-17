"""Registered original calibration readers, with a fixed application source anchor.

Public registrations are offline data, not publishers or execution authority. Only
an application's frozen index can construct NativeCalibrationSource. Consumers
must still supply their actual owned observation/owner originals, not route JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

import numpy as np

from cloud_edge_robot_arm.vision.native_references import (
    NativeActionReference,
    resolve_native_reference,
    validate_native_reference,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

APPLICATION_INDEX_PATH = "configs/research/native_calibration_sources.json"
_ASSET = "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"
_CAMERA_KEYS = {"calibration_version", "intrinsics", "camera_to_world", "width", "height", "source"}
_REGISTRY_KEYS = {
    "schema_version",
    "calibration_id",
    "source_scope",
    "recipe",
    "coverage",
    "preregistered_at",
    "geometry",
    "supported_actions",
    "support",
    "source_hashes",
    "groups",
    "original_file_hashes",
}
_GROUP_KEYS = {
    "group_id",
    "directory",
    "envelope_path",
    "records_path",
    "owner_inputs_paths",
    "split",
    "prior_usage",
    "ancestor_ids",
    "clock_reference_path",
}


def required_native_source_paths() -> tuple[str, ...]:
    return (
        "src/cloud_edge_robot_arm/vision/native_calibration.py",
        "src/cloud_edge_robot_arm/research/native_geometry_calibration.py",
        "src/cloud_edge_robot_arm/vision/native_references.py",
        "src/cloud_edge_robot_arm/research/raw_episode_v3.py",
        "src/cloud_edge_robot_arm/vision/raw_recorder_v3.py",
        "src/cloud_edge_robot_arm/vision/capture.py",
        "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py",
        "src/cloud_edge_robot_arm/vision/owner_registration.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/vision/runtime_binding.py",
        "src/cloud_edge_robot_arm/vision/execution.py",
        "src/cloud_edge_robot_arm/edge/runtime/skill_registry.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
        _ASSET,
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise ValueError("string JSON keys required")
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def _json(value: Any) -> str:
    try:
        return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("detached finite JSON required") from error


def _load(stored: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate original JSON key")
            result[key] = value
        return result

    return json.loads(
        stored,
        object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)),
    )


def _sha(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("complete SHA256 required")
    return value


def _relative(value: Any) -> Path:
    if type(value) is not str or not value:
        raise ValueError("canonical relative original path required")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("original path escapes registered root")
    if any(
        p.startswith(".env") or p in {".aws", ".ssh", "credentials", "secrets"} for p in path.parts
    ):
        raise ValueError("private configuration is not calibration input")
    return path


def _safe(root: Path, name: str) -> Path:
    path = root / _relative(name)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("original/source absent or symlinked")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("original/source escaped registered root")
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: Any, minimum: float | None = None) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("strict finite numeric quantity required")
    if minimum is not None and value < minimum:
        raise ValueError("numeric quantity outside registered support")
    return float(value)


def _vector(value: Any, length: int) -> np.ndarray:
    if type(value) not in {list, tuple} or len(value) != length:
        raise ValueError("complete registered vector required")
    return np.asarray([_number(v) for v in value])


def _rigid(value: Any) -> np.ndarray:
    matrix = _vector(value, 16).reshape(4, 4)
    if (
        not np.array_equal(matrix[3], [0, 0, 0, 1])
        or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-9, rtol=0)
        or not math.isclose(float(np.linalg.det(matrix[:3, :3])), 1, abs_tol=1e-9)
    ):
        raise ValueError("complete right-handed rigid frame required")
    return matrix


@dataclass(frozen=True, init=False)
class NativeGeometryRegistration:
    _payload_json: str

    def __init__(self, payload: Mapping[str, Any]) -> None:
        data = _load(_json(payload))
        keys = {
            "registration_id",
            "object_id",
            "object_class",
            "target_region_id",
            "asset_path",
            "pose_marker",
            "marker_to_object",
            "object_half_extent_m",
            "contact_points_m",
            "object_to_tcp",
            "tool_to_tcp",
            "camera",
            "region_world_m",
            "support_height_m",
        }
        if set(data) != keys or (
            data["object_id"],
            data["object_class"],
            data["target_region_id"],
        ) != ("object", "cube", "target_region"):
            raise ValueError("complete supported object/tool/region geometry required")
        _relative(data["asset_path"])
        if not data["registration_id"] or set(data["camera"]) != _CAMERA_KEYS:
            raise ValueError("registered identity and full camera descriptor required")
        PoseMarkerRegistration(**data["pose_marker"])
        for name in ("marker_to_object", "object_to_tcp", "tool_to_tcp"):
            _rigid(data[name])
        if any(v <= 0 for v in _vector(data["object_half_extent_m"], 3)):
            raise ValueError("complete positive rigid-object dimensions required")
        if not isinstance(data["contact_points_m"], dict) or len(data["contact_points_m"]) < 2:
            raise ValueError("complete registered contact geometry required")
        for point in data["contact_points_m"].values():
            _vector(point, 3)
        _vector(data["region_world_m"], 3)
        _number(data["support_height_m"])
        object.__setattr__(self, "_payload_json", _json(data))

    def to_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], _load(self._payload_json))

    @property
    def pose_marker(self) -> PoseMarkerRegistration:
        return PoseMarkerRegistration(**self.to_payload()["pose_marker"])

    def validate_asset(self, root: Path) -> None:
        data = self.to_payload()
        path = _safe(root, data["asset_path"])
        if _hash(path) != self.pose_marker.marked_asset_sha256:
            raise ValueError("registered asset bytes differ")
        tree = ET.fromstring(path.read_bytes())
        geom = tree.find("./worldbody/body[@name='object']/geom[@name='object_geom']")
        site = tree.find(".//site[@name='tcp']")
        region = tree.find("./worldbody/body[@name='target_region']")
        if geom is None or site is None or region is None or geom.get("type") != "box":
            raise ValueError("registered full rigid asset geometry unavailable")
        if not np.array_equal(
            [float(v) for v in geom.attrib["size"].split()], data["object_half_extent_m"]
        ):
            raise ValueError("complete object dimensions differ from asset")
        cells = [
            g
            for g in tree.findall("./worldbody/body[@name='object']/geom")
            if re.fullmatch(r"pose_marker_outboard_v3_r[0-5]c[0-5]", g.get("name", ""))
        ]
        if len(cells) != 36:
            raise ValueError("complete ordered marker surface unavailable")
        centers = np.array([[float(v) for v in g.attrib["pos"].split()] for g in cells])
        z = centers[0, 2] + float(cells[0].attrib["size"].split()[2])
        attached = np.eye(4)
        attached[:3, 3] = [centers[:, 0].mean(), centers[:, 1].mean(), z]
        if not np.allclose(attached, _rigid(data["marker_to_object"]), atol=1e-12, rtol=0):
            raise ValueError("marker offset/orientation differs from original rigid attachment")
        tool = np.eye(4)
        tool[:3, 3] = [float(v) for v in site.attrib["pos"].split()]
        if not np.array_equal(tool, _rigid(data["tool_to_tcp"])):
            raise ValueError("registered TCP frame differs from original tool")
        if region.findall("joint") or region.findall("freejoint"):
            raise ValueError("region is not attached to the fixed registered world")
        region_geom = region.find("geom")
        if region_geom is None:
            raise ValueError("registered support region geometry missing")
        location = np.array([float(v) for v in region.attrib["pos"].split()])
        location[2] += float(region_geom.attrib["size"].split()[2])
        if not np.array_equal(location, data["region_world_m"]):
            raise ValueError("registered world region/support differs from source asset")


@dataclass(frozen=True)
class NativeCalibrationRegistration:
    artifact_root: Path
    source_root: Path
    registry_path: str
    registry_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).absolute())
        object.__setattr__(self, "source_root", Path(self.source_root).absolute())
        _sha(self.registry_sha256)
        self.read_registry()

    def read_registry(self) -> dict[str, Any]:
        path = _safe(self.artifact_root, self.registry_path)
        if _hash(path) != self.registry_sha256:
            raise ValueError("pinned original registry changed")
        data = _load(path.read_text())
        if (
            set(data) != _REGISTRY_KEYS
            or data["schema_version"] != "native.calibration.registry.v1"
            or data["recipe"] != "FULL_RIGID_GEOMETRY_AND_TERMINAL_JOINT_V1"
            or data["source_scope"] not in {"SOFTWARE_ONLY", "REGISTERED_SIMULATION_CALIBRATION"}
            or type(data["coverage"]) not in {int, float}
            or data["coverage"] != 0.9
        ):
            raise ValueError("exact registered original recipe/schema required")
        if not data["groups"] or len({g["group_id"] for g in data["groups"]}) != len(
            data["groups"]
        ):
            raise ValueError("complete distinct group allocations required")
        for group in data["groups"]:
            if (
                set(group) != _GROUP_KEYS
                or group["split"] != "calibration"
                or group["prior_usage"] != ["UNVIEWED"]
                or not group["ancestor_ids"]
            ):
                raise ValueError("viewed/unknown/leaking group cannot be relabelled calibration")
            for name in ("directory", "envelope_path", "records_path"):
                _relative(group[name])
            for name in group["owner_inputs_paths"].values():
                _relative(name)
            if group["clock_reference_path"] is not None:
                _relative(group["clock_reference_path"])
        if not set(required_native_source_paths()) <= set(data["source_hashes"]):
            raise ValueError("registered native producer/consumer source inventory incomplete")
        for inventory in (data["source_hashes"], data["original_file_hashes"]):
            if not isinstance(inventory, dict) or not inventory:
                raise ValueError("complete original/current source inventory required")
            for name, digest in inventory.items():
                _relative(name)
                _sha(digest)
        geometry = NativeGeometryRegistration(data["geometry"])
        geometry.validate_asset(self.source_root)
        for skill, horizon in data["supported_actions"].items():
            if skill not in {
                "MOVE_ABOVE",
                "APPROACH",
                "GRASP",
                "LIFT",
                "RETREAT",
                "MOVE_TO_REGION",
                "PLACE",
            }:
                raise ValueError("unsupported native calibration action")
            if _number(horizon, 0) == 0:
                raise ValueError("complete positive registered horizon required")
        if set(data["support"]) != {
            "object_center_min_m",
            "object_center_max_m",
            "endpoint_min_m",
            "endpoint_max_m",
            "min_marker_side_px",
        }:
            raise ValueError("full registered geometry/endpoint support required")
        for prefix in ("object_center", "endpoint"):
            if np.any(
                _vector(data["support"][prefix + "_min_m"], 3)
                >= _vector(data["support"][prefix + "_max_m"], 3)
            ):
                raise ValueError("registered support box is empty")
        _number(data["support"]["min_marker_side_px"], 8)
        preregistered = datetime.fromisoformat(data["preregistered_at"])
        if preregistered.tzinfo is None or preregistered.utcoffset() is None:
            raise ValueError("aware original preregistration timestamp required")
        return cast(dict[str, Any], data)

    def revalidate(self) -> dict[str, Any]:
        data = self.read_registry()
        actual_paths = set()
        for path in self.artifact_root.rglob("*"):
            if path.is_symlink():
                raise ValueError("original inventory contains a symlink")
            if path.is_file():
                name = str(path.relative_to(self.artifact_root))
                if name != self.registry_path:
                    actual_paths.add(name)
        if actual_paths != set(data["original_file_hashes"]):
            raise ValueError("original inventory has missing/extra assigned files")
        for name, expected in data["original_file_hashes"].items():
            if _hash(_safe(self.artifact_root, name)) != expected:
                raise ValueError("registered original bytes changed")
        executing_root = Path(__file__).resolve().parents[3]
        for name, expected in data["source_hashes"].items():
            if _hash(_safe(self.source_root, name)) != expected:
                raise ValueError("registered native source drift")
            if (
                name in required_native_source_paths()
                and _hash(_safe(executing_root, name)) != expected
            ):
                raise ValueError("rehashed copy differs from current native implementation")
        return data


@dataclass(frozen=True)
class NativeCalibrationEstimate:
    geometric_error_bound_m: float | None
    reference_motion_bound_m_s: float | None
    reference_digest: str
    registration_sha256: str
    full_horizon_s: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, init=False)
class NativeCalibrationSource:
    """App-created source object; a public registration alone cannot construct it."""

    _registration: NativeCalibrationRegistration
    _role_digest: str
    _index_sha: str
    _catalog_sha: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("native source requires the frozen application source index")

    @classmethod
    def from_application(cls, role_binding: RoleRuntimeBinding) -> NativeCalibrationSource:
        if cls is not NativeCalibrationSource or type(role_binding) is not RoleRuntimeBinding:
            raise ValueError("application-owned exact role binding required")
        root = Path(__file__).resolve().parents[3]
        if (
            role_binding.root.resolve() != root
            or APPLICATION_INDEX_PATH not in role_binding.device_source_hashes
        ):
            raise ValueError("native source is not anchored by the actual application")
        role_binding._validate_sources(role_binding.device_source_hashes)
        index_path = _safe(root, APPLICATION_INDEX_PATH)
        index = _load(index_path.read_text())
        if (
            set(index)
            != {
                "schema_version",
                "registry_path",
                "registry_sha256",
                "capture_catalog_path",
                "capture_catalog_sha256",
            }
            or index["schema_version"] != "native.calibration.application.v1"
        ):
            raise ValueError("exact application source anchor required")
        registry_path = _relative(index["registry_path"])
        registration = NativeCalibrationRegistration(
            root / registry_path.parent, root, registry_path.name, index["registry_sha256"]
        )
        catalog_path = _safe(root, index["capture_catalog_path"])
        if _hash(catalog_path) != index["capture_catalog_sha256"]:
            raise ValueError("independent acquisition catalog changed")
        data = registration.revalidate()
        catalog = _load(catalog_path.read_text())
        if (
            set(catalog)
            != {
                "schema_version",
                "publisher",
                "preregistered_at",
                "groups",
                "original_file_hashes",
                "source_hashes",
            }
            or catalog["schema_version"] != "native.calibration.capture-catalog.v1"
            or catalog["publisher"] != "APP_OWNED_RAW_V3_CALIBRATION"
            or data["source_scope"] != "REGISTERED_SIMULATION_CALIBRATION"
            or any(
                catalog[k] != data[k]
                for k in ("preregistered_at", "groups", "original_file_hashes", "source_hashes")
            )
        ):
            raise ValueError(
                "registry differs from independently anchored complete acquisition catalog"
            )
        from cloud_edge_robot_arm.research.native_geometry_calibration import (
            reconstruct_registered_calibration,
        )

        reconstruct_registered_calibration(registration)
        source = object.__new__(cls)
        object.__setattr__(source, "_registration", registration)
        object.__setattr__(source, "_role_digest", role_binding.bundle.digest())
        object.__setattr__(source, "_index_sha", _hash(index_path))
        object.__setattr__(source, "_catalog_sha", _hash(catalog_path))
        return source

    def revalidate(self, role_binding: RoleRuntimeBinding) -> Any:
        if (
            type(self) is not NativeCalibrationSource
            or type(role_binding) is not RoleRuntimeBinding
            or role_binding.bundle.digest() != self._role_digest
        ):
            raise ValueError("native application role changed")
        rebuilt = type(self).from_application(role_binding)
        if (rebuilt._index_sha, rebuilt._catalog_sha, rebuilt._registration.registry_sha256) != (
            self._index_sha,
            self._catalog_sha,
            self._registration.registry_sha256,
        ):
            raise ValueError("native application source anchor changed")
        from cloud_edge_robot_arm.research.native_geometry_calibration import (
            reconstruct_registered_calibration,
        )

        return reconstruct_registered_calibration(self._registration)

    def estimate(
        self,
        online: Any,
        contract: Any,
        step: Any,
        *,
        owner_inputs: Mapping[str, Any],
        reference: NativeActionReference,
        role_binding: RoleRuntimeBinding,
        now: datetime,
    ) -> NativeCalibrationEstimate:
        """Recompute owned receipt/reference; no caller residual/status is an input.

        Task3 must supply owner_inputs from the actual repository owner, not JSON.
        This source object is selected at app construction, never from a request.
        """
        from cloud_edge_robot_arm.research.native_geometry_calibration import (
            calibration_policy_digest,
            rebuild_owner_binding,
        )

        diagnostics = self.revalidate(role_binding)
        data = self._registration.read_registry()
        binding = rebuild_owner_binding(owner_inputs, online, now=now)
        if binding.original_requirements.original_step.model_dump(mode="json") != step.model_dump(
            mode="json"
        ):
            raise ValueError("native current original action differs from owner receipt")
        grounding = {
            "resolved_top_grasp_tcp": owner_inputs["grounding_inputs"]["grasp_tcp"],
            "grounded_destination": owner_inputs["grounding_inputs"]["destination"],
            "top_grasp_support_height_m": owner_inputs["grounding_inputs"]["support_height_m"],
        }
        current = resolve_native_reference(
            online,
            contract,
            step,
            resolved=binding.grounded_step,
            grounding=grounding,
            role_binding=role_binding,
            effective_duration_s=binding.expected_duration_s,
        )
        validate_native_reference(
            reference,
            online,
            contract,
            step,
            resolved=binding.grounded_step,
            grounding=grounding,
            role_binding=role_binding,
            effective_duration_s=binding.expected_duration_s,
        )
        scope = NativeGeometryRegistration(data["geometry"])
        observation = RGBDObservation.model_validate(online.observation.model_dump())
        estimate = detect_pose_marker(observation, scope.pose_marker)
        camera = {k: observation.model_dump(mode="json")[k] for k in _CAMERA_KEYS}
        reasons = []
        bound = None
        motion = None
        if camera != data["geometry"]["camera"] or estimate.status != "OBSERVED":
            reasons.append("current_camera_or_full_geometry_unavailable")
        else:
            transform = _rigid(data["geometry"]["marker_to_object"])
            rotation = (
                np.array(estimate.rotation_marker_to_world).reshape(3, 3) @ transform[:3, :3].T
            )
            center = np.array(estimate.marker_center_world_m) - rotation @ transform[:3, 3]
            grasp = center + rotation @ _rigid(data["geometry"]["object_to_tcp"])[:3, 3]
            if (
                not np.allclose(
                    grasp,
                    [grounding["resolved_top_grasp_tcp"][k] for k in "xyz"],
                    atol=1e-9,
                    rtol=0,
                )
                or [grounding["grounded_destination"][k] for k in "xyz"]
                != data["geometry"]["region_world_m"]
                or grounding["top_grasp_support_height_m"] != data["geometry"]["support_height_m"]
            ):
                reasons.append("owner_geometry_recipe_differs_from_registered_estimator")
            elif np.any(center < data["support"]["object_center_min_m"]) or np.any(
                center > data["support"]["object_center_max_m"]
            ):
                reasons.append("current_geometry_outside_registered_support")
            elif (
                estimate.measured_min_side_px is None
                or estimate.measured_min_side_px < data["support"]["min_marker_side_px"]
                or current.endpoint_xyz is not None
                and (
                    np.any(np.array(current.endpoint_xyz) < data["support"]["endpoint_min_m"])
                    or np.any(np.array(current.endpoint_xyz) > data["support"]["endpoint_max_m"])
                )
            ):
                reasons.append("current_marker_or_endpoint_outside_registered_support")
            elif current.full_horizon_s != data["supported_actions"].get(step.skill.value, 0):
                reasons.append("full_owner_horizon_not_supported")
            elif (
                calibration_policy_digest(self._registration, step.skill.value)
                != binding.grounding_policy_hash
            ):
                reasons.append("owner_policy_not_supported_by_registered_originals")
            else:
                quantile = diagnostics.action_quantiles.get(step.skill.value)
                if quantile is None or quantile.bound_m is None:
                    reasons.append("full_geometry_terminal_clock_horizon_groups_unavailable")
                else:
                    bound = quantile.bound_m
                    if current.fixed_goal_coordinate_invariant:
                        # Fixed command coordinate speed; not physical body/TCP speed.
                        motion = 0.0
                    else:
                        reasons.append("mutable_contact_future_motion_source_unavailable")
        return NativeCalibrationEstimate(
            bound,
            motion,
            current.reference_digest,
            self._registration.registry_sha256,
            current.full_horizon_s,
            tuple(reasons),
        )
