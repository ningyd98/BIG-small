"""Strict offline replay; acquisition timestamps and checksums remain unchanged."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation

if TYPE_CHECKING:
    from cloud_edge_robot_arm.datasets.rgbd.models import SampleRecord


def resolve_payload(root: Path, relative: str) -> Path:
    from cloud_edge_robot_arm.datasets.rgbd.models import safe_relative_path

    safe_relative_path(relative)
    root = root.resolve()
    path = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink payload path is forbidden")
    if not path.resolve().is_relative_to(root):
        raise ValueError("payload path lies outside dataset root")
    if not path.is_file():
        raise ValueError(f"missing payload path: {relative}")
    return path


def verified_payloads(record: SampleRecord) -> dict[str, bytes]:
    if record.root is None:
        raise ValueError("offline record must be bound to its dataset root")
    required = {
        "rgb", "depth", "depth_vis", "valid_mask", "instance", "camera", "scene", "labels", "state"
    }
    if not required <= record.paths.keys() or record.paths.keys() != record.file_hashes.keys():
        raise ValueError("payload paths and checksums must cover every required file")
    prefix = f"episodes/{record.episode_id}/{record.sample_id}/"
    result = {}
    for key, relative in record.paths.items():
        if not relative.startswith(prefix):
            raise ValueError("payload path does not belong to the indexed episode/sample")
        payload = resolve_payload(record.root, relative).read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.file_hashes[key]:
            raise ValueError(f"payload checksum mismatch: {relative}")
        result[key] = payload
    return result


def load_numeric(payload: bytes, dtype: str, shape: tuple[int, int], name: str) -> np.ndarray:
    stream = io.BytesIO(payload)
    try:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            stored_shape, _, stored_dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            stored_shape, _, stored_dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise ValueError("unsupported numeric array version")
    except (ValueError, OSError, EOFError) as exc:
        raise ValueError(f"invalid {name} array (pickle forbidden)") from exc
    if stored_dtype.hasobject or stored_dtype != np.dtype(dtype):
        raise ValueError(f"{name} dtype must be {dtype}; float32 depth is required")
    if stored_shape != shape:
        raise ValueError(f"{name} shape does not match camera dimensions")
    if len(payload) - stream.tell() != shape[0] * shape[1] * stored_dtype.itemsize:
        raise ValueError(f"{name} payload length does not match array dimensions")
    stream.seek(0)
    array = np.load(stream, allow_pickle=False)
    if not isinstance(array, np.ndarray):
        raise ValueError(f"{name} must contain one numeric ndarray")
    return array


def _decode_observation(
    payloads: dict[str, bytes], metadata: dict[str, Any], prefix: str = ""
) -> RGBDObservation:
    if type(metadata.get("width")) is not int or type(metadata.get("height")) is not int:
        raise ValueError("camera dimensions must be integers")
    shape = (metadata["height"], metadata["width"])
    if not 1 <= shape[0] <= 720 or not 1 <= shape[1] <= 1280:
        raise ValueError("camera dimensions exceed RGB-D bounds")
    depth = load_numeric(payloads[prefix + "depth"], "<f4", shape, "depth")
    mask = load_numeric(payloads[prefix + "valid_mask"], "u1", shape, "valid_mask")
    return RGBDObservation.model_validate(
        {
            **metadata,
            "rgb_png_base64": base64.b64encode(payloads[prefix + "rgb"]).decode("ascii"),
            "depth_float32_base64": base64.b64encode(depth.tobytes(order="C")).decode("ascii"),
            "valid_mask_base64": base64.b64encode(mask.tobytes(order="C")).decode("ascii"),
        }
    )


def _validate_state(payload: bytes, expected_hash: str, name: str) -> None:
    state = json.loads(payload)
    if not isinstance(state, dict):
        raise ValueError(f"{name} render passes need a physics state object")
    passes = state.get("pass_state_hashes")
    if (
        not expected_hash.strip()
        or state.get("physics_state_hash") != expected_hash
        or not isinstance(passes, list)
        or len(passes) != 3
        or any(value != expected_hash for value in passes)
    ):
        raise ValueError(
            f"{name} three render passes must share the nonempty indexed physics state"
        )


def load_offline_observation(record: SampleRecord) -> RGBDObservation:
    """Reconstruct verified camera input without any simulator truth or clock update."""
    payloads = verified_payloads(record)
    metadata = json.loads(payloads["camera"])
    if metadata != record.observation_metadata:
        raise ValueError("camera metadata does not match sample record")
    if not metadata.get("checksum_sha256"):
        raise ValueError("original observation checksum is required")
    if json.loads(payloads["scene"]) != record.scene.model_dump(mode="json"):
        raise ValueError("scene metadata does not match sample record")
    if json.loads(payloads["labels"]) != record.labels:
        raise ValueError("label metadata does not match sample record")
    if (record.labels.get("positive") is True) != (record.status == "POSITIVE"):
        raise ValueError("positive label and sample status disagree")
    observation = _decode_observation(payloads, metadata)
    if observation.frame_id != record.frame_id or observation.source != record.source:
        raise ValueError("observation identity/source does not match sample record")
    _validate_state(payloads["state"], record.physics_state_hash, "main")
    instance = load_numeric(
        payloads["instance"], "<i4", (observation.height, observation.width), "instance"
    )
    semantics = {0, *(item["semantic_id"] for item in record.labels.get("instances", []))}
    if not set(np.unique(instance)).issubset(semantics):
        raise ValueError("instance mask contains unknown semantic IDs")
    try:
        expected_depth = base64.b64decode(observation.depth_png_base64())
        with Image.open(io.BytesIO(expected_depth)) as expected:
            expected_pixels = expected.tobytes()
    except ValueError:
        expected_pixels = bytes(observation.width * observation.height)
    try:
        with Image.open(io.BytesIO(payloads["depth_vis"])) as image:
            if image.format != "PNG" or image.size != (observation.width, observation.height):
                raise ValueError("depth visualization dimensions do not match camera")
            if image.mode != "L" or image.tobytes() != expected_pixels:
                raise ValueError("depth visualization does not match metric depth")
    except OSError as exc:
        raise ValueError("invalid depth visualization PNG") from exc
    raw_keys = {"raw_rgb", "raw_depth", "raw_valid_mask", "raw_camera", "raw_state"}
    corrupted = any(
        float(record.scene.scene_parameters.get(key, 0)) > 0
        for key in ("depth_noise_m", "invalid_depth_fraction")
    )
    if corrupted and not raw_keys <= payloads.keys():
        raise ValueError("depth-corrupted observation requires raw RGB-D evidence")
    if raw_keys & payloads.keys():
        if not raw_keys <= payloads.keys():
            raise ValueError("raw RGB-D evidence is incomplete")
        raw_metadata = json.loads(payloads["raw_camera"])
        if not raw_metadata.get("checksum_sha256"):
            raise ValueError("raw observation checksum is required")
        raw_observation = _decode_observation(payloads, raw_metadata, "raw_")
        allowed_changes = {"depth_float32_base64", "valid_mask_base64", "checksum_sha256"}
        if raw_observation.model_dump(exclude=allowed_changes) != observation.model_dump(
            exclude=allowed_changes
        ):
            raise ValueError("raw evidence must share the same acquisition, RGB and calibration")
        _validate_state(payloads["raw_state"], record.physics_state_hash, "raw")
    return observation
