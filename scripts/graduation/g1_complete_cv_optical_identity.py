"""Bind the current RGB-D read to a verified development allocation and an independent reset."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction


def camera_hash(value):
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(blob).hexdigest()


def _hash(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("missing or invalid verified SHA256")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing registered optical identity")
    return value


@dataclass(frozen=True, slots=True)
class OpticalIdentity:
    allocation_sha256: str
    generation_sha256: str
    calibration_sha256: str
    asset_sha256: str
    geometry_sha256: str
    registration_id: str
    marker_family: str
    design_scene_id: str
    case_id: str
    scene_id: str
    episode_id: str
    source: str
    calibration_version: str
    width: int
    height: int
    intrinsics: tuple
    camera_to_world: tuple
    physics_dt: Fraction

    def matches(self, frame, marker, geometry, physics_step):
        if (
            type(physics_step) is not int
            or physics_step < 0
            or camera_hash(geometry) != self.geometry_sha256
        ):
            return False
        expected_time = float(physics_step * self.physics_dt)
        return bool(
            frame.scene_id == self.scene_id == marker.get("scene_id")
            and frame.episode_id == self.episode_id == marker.get("episode_id")
            and frame.source == self.source
            and frame.calibration_version == self.calibration_version
            and (frame.width, frame.height) == (self.width, self.height)
            and tuple(frame.intrinsics) == self.intrinsics
            and tuple(frame.camera_to_world) == self.camera_to_world
            and frame.frame_id == marker.get("frame_id")
            and frame.checksum_sha256 == marker.get("checksum")
            and frame.observation_id == marker.get("observation_id")
            and frame.captured_at.isoformat() == marker.get("captured_at")
            and frame.sim_time_s == marker.get("sim_time_s")
            and math.isclose(frame.sim_time_s, expected_time, abs_tol=1e-8, rel_tol=0.0)
            and self.asset_sha256 == marker.get("asset_sha256")
            and self.registration_id == marker.get("registration_id")
        )


def bind_allocation(
    allocation_bytes,
    *,
    allocation_sha256,
    generation_sha256,
    calibration_sha256,
    asset_sha256,
    reset_scene_id,
    reset_episode_id,
):
    """Call after the allocation verifier and native reset each supply their separate provenance."""
    if type(allocation_bytes) is not bytes or hashlib.sha256(allocation_bytes).hexdigest() != _hash(
        allocation_sha256
    ):
        raise ValueError("verified allocation byte digest mismatch")
    try:
        allocation = json.loads(allocation_bytes)
        case = allocation["case"]
        geometry = allocation["geometry"]
        rig = geometry["development_dual"]
        camera = geometry["camera"]
        if (
            allocation["runtime_build_sha256"] != _hash(generation_sha256)
            or allocation["calibration_sha256"] != _hash(calibration_sha256)
            or not _hash(asset_sha256)
            == allocation["asset_sha256"]
            == case["asset_sha256"]
            == rig["scene_asset_sha256"]
            == geometry["pose_marker"]["marked_asset_sha256"]
            or camera_hash(camera) != rig["camera_sha256"]
            or case["scene_id"] != _name(reset_scene_id)
        ):
            raise ValueError("allocation, calibrated rig, source or reset identity differs")
        source = _name(camera["source"])
        if (
            source != "mujoco_camera"
            or len(camera["intrinsics"]) != 4
            or len(camera["camera_to_world"]) != 16
        ):
            raise ValueError("invalid registered camera")
        dt = Fraction(case["physics_dt_s"])
        if dt != Fraction(1, 240):
            raise ValueError("unregistered physics clock")
        return OpticalIdentity(
            allocation_sha256,
            generation_sha256,
            calibration_sha256,
            asset_sha256,
            camera_hash(geometry),
            _name(geometry["registration_id"]),
            _name(geometry["marker_family"]),
            _name(rig["scene_id"]),
            _name(case["id"]),
            _name(case["scene_id"]),
            _name(reset_episode_id),
            source,
            _name(camera["calibration_version"]),
            int(camera["width"]),
            int(camera["height"]),
            tuple(camera["intrinsics"]),
            tuple(camera["camera_to_world"]),
            dt,
        )
    except (KeyError, TypeError, ZeroDivisionError) as exc:
        raise ValueError("incomplete verified optical allocation") from exc
