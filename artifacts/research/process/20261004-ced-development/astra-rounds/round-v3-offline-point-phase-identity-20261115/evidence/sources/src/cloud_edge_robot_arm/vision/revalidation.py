"""Paused MuJoCo scene-consistency guards; no physical identity/stability certificate."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation

POLICY_ID = "paused_mujoco_rgb_depth_v1"


def validate_post_cloud_observation(
    reference: RGBDObservation, candidate: RGBDObservation, *, not_before: datetime
) -> dict[str, Any]:
    """Check payload/session consistency; the caller separately enforces fresh age.

    A trusted acquisition callback must perform the exposure. Payload metadata alone
    cannot distinguish that from maliciously relabelled bytes. These residual limits
    are engineering anomaly guards for the scoped paused simulator, not error bounds.
    """
    if not isinstance(reference, RGBDObservation) or not isinstance(candidate, RGBDObservation):
        raise ValueError("post_cloud_payload_invalid_type")
    try:
        RGBDObservation.model_validate(reference.model_dump())
        RGBDObservation.model_validate(candidate.model_dump())
    except ValueError:
        raise ValueError("post_cloud_payload_invalid") from None
    if not isinstance(not_before, datetime) or not_before.tzinfo is None:
        raise ValueError("post_cloud_boundary_invalid")
    for field in ("scene_id", "episode_id", "calibration_version"):
        value = getattr(reference, field)
        if not value or not value.strip():
            raise ValueError(f"post_cloud_binding_missing:{field}")
    if reference.source != "mujoco_camera":
        raise ValueError("post_cloud_source_unsupported")
    for field in (
        "source",
        "scene_id",
        "episode_id",
        "calibration_version",
        "width",
        "height",
        "intrinsics",
        "camera_to_world",
        "depth_convention",
        "sim_time_s",
    ):
        if getattr(reference, field) != getattr(candidate, field):
            raise ValueError(f"post_cloud_binding_changed:{field}")
    if (
        candidate.observation_id == reference.observation_id
        or candidate.frame_id == reference.frame_id
        or candidate.checksum_sha256 == reference.checksum_sha256
    ):
        raise ValueError("post_cloud_frame_not_new")
    if candidate.captured_at <= reference.captured_at:
        raise ValueError("post_cloud_capture_not_new")
    if candidate.captured_at < not_before:
        raise ValueError("post_cloud_capture_before_supplier")
    if reference.evidence()["rgb_sha256"] != candidate.evidence()["rgb_sha256"]:
        raise ValueError("post_cloud_rgb_changed")
    mask = reference.valid_mask_bytes()
    if mask != candidate.valid_mask_bytes():
        raise ValueError("post_cloud_valid_mask_changed")
    valid = np.frombuffer(mask, dtype=np.uint8) != 0
    count = int(valid.sum())
    if count == 0:
        raise ValueError("post_cloud_no_valid_depth")
    old = np.frombuffer(base64.b64decode(reference.depth_float32_base64), dtype="<f4")
    new = np.frombuffer(base64.b64decode(candidate.depth_float32_base64), dtype="<f4")
    delta = new[valid].astype(np.float64) - old[valid].astype(np.float64)
    maximum = float(np.max(np.abs(delta)))
    rms = float(np.sqrt(np.mean(delta**2)))
    mean = float(np.mean(delta))
    if maximum > 0.010:
        raise ValueError("post_cloud_depth_max_delta_exceeded")
    if rms > 0.002:
        raise ValueError("post_cloud_depth_rms_delta_exceeded")
    if abs(mean) > 0.00025:
        raise ValueError("post_cloud_depth_mean_delta_exceeded")
    return {
        "policy_id": POLICY_ID,
        "reference_checksum": reference.checksum_sha256,
        "fresh_checksum": candidate.checksum_sha256,
        "not_before": not_before.isoformat(),
        "sim_time_s": candidate.sim_time_s,
        "rgb_sha256": candidate.evidence()["rgb_sha256"],
        "valid_pixels": count,
        "depth_max_abs_delta_m": maximum,
        "depth_rms_delta_m": rms,
        "depth_mean_delta_m": mean,
        "limits_m": {"maximum": 0.010, "rms": 0.002, "absolute_mean": 0.00025},
        "physical_identity_or_stability_certified": False,
    }
