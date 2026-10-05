"""Extract only registered camera measurements, calibration and frame timing."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import statistics
from collections.abc import Sequence

from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.risk.models import FEATURE_SOURCES, FeatureValue, RiskFeatures


def calibration_fingerprint(observation: RGBDObservation) -> float:
    # A 48-bit digest is exactly representable in a float; it is a guard, never a regressor.
    fields = (
        observation.calibration_version,
        observation.intrinsics,
        observation.camera_to_world,
        observation.width,
        observation.height,
        observation.source,
    )
    return float(int(hashlib.sha256(json.dumps(fields).encode()).hexdigest()[:12], 16))


def extract_risk_features(
    observation: RGBDObservation,
    previous: RGBDObservation | None,
    calibration_residuals: Sequence[float],
) -> RiskFeatures:
    # model_copy bypasses pydantic validation; revalidate to reject injected truth fields.
    for frame in (observation, previous):
        if frame is not None and set(vars(frame)) - set(RGBDObservation.model_fields):
            raise ValueError("unapproved fields in online RGB-D observation")
    observation = RGBDObservation.model_validate(observation.model_dump())
    if previous is not None:
        previous = RGBDObservation.model_validate(previous.model_dump())
    if any(not math.isfinite(v) or v < 0 for v in calibration_residuals):
        raise ValueError("calibration residuals must be finite nonnegative metres")
    depth = observation.depth_values()
    valid = [v for v in depth if v > 0]
    median = statistics.median(valid) if valid else 0.0
    fingerprint = calibration_fingerprint(observation)
    matching = previous is None or calibration_fingerprint(previous) == fingerprint
    interval = (observation.captured_at - previous.captured_at).total_seconds() if previous else 0
    pair_valid = bool(
        previous is not None
        and matching
        and interval > 0
        and observation.sim_time_s > previous.sim_time_s
        and observation.frame_id != previous.frame_id
        and observation.episode_id
        and observation.episode_id == previous.episode_id
        and observation.scene_id == previous.scene_id
        and (observation.width, observation.height) == (previous.width, previous.height)
    )
    motion = 0.0
    consistency = 0.0
    if pair_valid and previous is not None:
        speeds = []
        fx, fy, cx, cy = observation.intrinsics
        for index, (current, before) in enumerate(zip(depth, previous.depth_values(), strict=True)):
            if current > 0 and before > 0:
                u, v = index % observation.width, index // observation.width
                ray_length = math.sqrt(((u - cx) / fx) ** 2 + ((v - cy) / fy) ** 2 + 1)
                speeds.append(abs(current - before) * ray_length / interval)
        motion = max(speeds, default=0.0)
        pair_valid = bool(speeds)
        with (
            Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as current_rgb,
            Image.open(io.BytesIO(base64.b64decode(previous.rgb_png_base64))) as before_rgb,
        ):
            differences = sum(
                abs(a - b) for a, b in zip(current_rgb.tobytes(), before_rgb.tobytes(), strict=True)
            )
            consistency = 1 - differences / (observation.width * observation.height * 3 * 255)
    values = {
        "invalid_depth_fraction": 1 - len(valid) / len(depth),
        "depth_median_m": median,
        "depth_dispersion_m": statistics.median(abs(v - median) for v in valid) if valid else 0,
        "pixel_consistency": consistency,
        "calibration_residual_m": max(calibration_residuals, default=0),
        "calibration_valid": float(
            bool(observation.calibration_version) and bool(calibration_residuals) and matching
        ),
        "calibration_fingerprint": fingerprint,
        "motion_pair_valid": float(pair_valid),
        "observed_motion_m_s": motion,
        "frame_interval_s": max(interval, 0),
    }
    return RiskFeatures(
        {key: FeatureValue(float(value), FEATURE_SOURCES[key]) for key, value in values.items()},
        observation.observation_id,
    )
