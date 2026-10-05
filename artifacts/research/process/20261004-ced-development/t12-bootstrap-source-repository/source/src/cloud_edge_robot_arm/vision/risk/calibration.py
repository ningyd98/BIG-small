"""Independent isotonic probabilities and grouped split-conformal error bounds."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.datasets.rgbd.models import SampleRecord, canonical_json, content_digest
from cloud_edge_robot_arm.vision.risk.fit import (
    action_outcomes,
    assert_disjoint,
    load_model,
    predict,
    provenance,
    sample_features,
    supervision,
)
from cloud_edge_robot_arm.vision.risk.models import (
    ACTIONS,
    RiskEstimate,
    RiskFeatures,
    RiskModelArtifact,
)


def isotonic_fit(scores: Sequence[float], labels: Sequence[bool]) -> list[list[float]]:
    if set(labels) != {False, True}:
        return []
    grouped: dict[float, list[bool]] = {}
    for score, label in zip(scores, labels, strict=True):
        grouped.setdefault(score, []).append(label)
    blocks: list[list[float]] = []
    for score, values in sorted(grouped.items()):
        blocks.append([score, score, float(sum(values)), float(len(values))])
        while len(blocks) > 1 and blocks[-2][2] / blocks[-2][3] > blocks[-1][2] / blocks[-1][3]:
            right = blocks.pop()
            left = blocks.pop()
            blocks.append([left[0], right[1], left[2] + right[2], left[3] + right[3]])
    return [[block[0], block[1], block[2] / block[3]] for block in blocks]


def isotonic_predict(blocks: Sequence[Sequence[float]], score: float) -> float | None:
    if not blocks:
        return None
    for _low, high, probability in blocks:
        if score <= high:
            return float(probability)
    return float(blocks[-1][2])


def grouped_bound(
    records: Sequence[SampleRecord], key: str, coverage: float
) -> tuple[float | None, list[float]]:
    groups: dict[str, float] = {}
    for record in records:
        value = supervision(record, "calibration").get(key)
        if value is None:
            continue
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise ValueError(f"offline {key} must be a finite nonnegative actual residual")
        groups[record.group_id] = max(groups.get(record.group_id, 0), value)
    residuals = sorted(groups.values())
    rank = math.ceil((len(residuals) + 1) * coverage)
    bound = residuals[rank - 1] if residuals and rank <= len(residuals) else None
    return bound, residuals


def calibrate_risk(
    model: RiskModelArtifact, calibration: Sequence[SampleRecord]
) -> RiskModelArtifact:
    data = load_model(model)
    if not calibration:
        raise ValueError("calibration records are required")
    calibration = sorted(calibration, key=lambda r: r.sample_id)
    if len({r.sample_id for r in calibration}) != len(calibration):
        raise ValueError("duplicate risk calibration sample identity")
    labels = [supervision(record, "calibration")["failure"] for record in calibration]
    assert_disjoint(data["fit_provenance"], provenance(calibration))
    features = [sample_features(record, calibration, "calibration") for record in calibration]
    scores = [predict(data, feature) for feature in features]
    support = {
        key: [
            min(data["feature_ranges"][key][0], min(f.values[key].value for f in features)),
            max(data["feature_ranges"][key][1], max(f.values[key].value for f in features)),
        ]
        for key in ("depth_median_m", "depth_dispersion_m", "calibration_residual_m")
    }
    coverage = data["settings"]["coverage"]
    geometry, geometry_residuals = grouped_bound(calibration, "geometric_error_m", coverage)
    # Motion residuals are meaningful only for actual fresh-frame pairs.
    motion_records = [
        record
        for record, feature in zip(calibration, features, strict=True)
        if feature.values["motion_pair_valid"].value == 1
    ]
    motion, motion_residuals = grouped_bound(motion_records, "motion_error_m_s", coverage)
    blocks = isotonic_fit(scores, labels)
    outcomes = [action_outcomes(record, "calibration") for record in calibration]
    action_blocks = {}
    for action, action_model in data["action_models"].items():
        indices = [i for i, outcome in enumerate(outcomes) if action in outcome]
        action_blocks[action] = isotonic_fit(
            [predict(action_model, features[i]) for i in indices],
            [outcomes[i][action] for i in indices],
        )
    payload = {
        "schema_version": "risk.calibration.v1",
        "model_hash": model.model_hash,
        "calibration_group_ids": sorted({record.group_id for record in calibration}),
        "calibration_provenance": provenance(calibration),
        "observable_support": support,
        "isotonic_blocks": blocks,
        "action_isotonic_blocks": action_blocks,
        "coverage": coverage,
        "geometric_error_bound_m": geometry,
        "motion_residual_bound_m_s": motion,
        "geometry_group_residuals_m": geometry_residuals,
        "motion_group_residuals_m_s": motion_residuals,
        "reliability": [
            {"score": score, "failure": label, "calibrated": isotonic_predict(blocks, score)}
            for score, label in zip(scores, labels, strict=True)
        ],
        "action_coverage": {
            action: {
                "calibration_outcomes": sum(action in row for row in outcomes),
                "calibrated": bool(action_blocks.get(action)),
            }
            for action in ACTIONS
        },
    }
    payload["content_hash"] = content_digest(payload)
    path = Path(model.model_path).with_name(f"calibration-{payload['content_hash']}.json")
    path.write_text(canonical_json(payload) + "\n")
    return replace(
        model,
        calibration_path=str(path),
        calibration_group_ids=tuple(payload["calibration_group_ids"]),
    )


def load_calibration(model: RiskModelArtifact) -> dict[str, Any] | None:
    if not model.calibration_path:
        return None
    payload: dict[str, Any] = json.loads(Path(model.calibration_path).read_text())
    digest = payload.pop("content_hash", None)
    if (
        digest != content_digest(payload)
        or payload.get("model_hash") != model.model_hash
        or Path(model.calibration_path).name != f"calibration-{digest}.json"
    ):
        raise ValueError("risk calibration hash/model binding mismatch")
    if tuple(payload["calibration_group_ids"]) != model.calibration_group_ids:
        raise ValueError("risk calibration group binding mismatch")
    return payload


def estimate_risk(model: RiskModelArtifact, features: RiskFeatures) -> RiskEstimate:
    data = load_model(model)
    calibrated = load_calibration(model)
    unknown = RiskEstimate(None, {action: None for action in ACTIONS}, None, None, "UNKNOWN")
    if set(features.values) != set(model.feature_schema) or calibrated is None:
        return unknown
    values = {key: feature.value for key, feature in features.values.items()}
    settings = data["settings"]
    if (
        values["invalid_depth_fraction"] > settings["max_invalid_depth_fraction"]
        or values["calibration_valid"] != 1
        or values["motion_pair_valid"] != 1
        or values["calibration_fingerprint"] not in data["calibration_fingerprints"]
        or values["frame_interval_s"] > settings["max_frame_interval_s"]
    ):
        return unknown
    # A software artifact cannot grant source acceptance or enable an online method.
    if not data.get("source_accepted", False):
        return unknown
    if any(
        not lower <= values[key] <= upper
        for key, (lower, upper) in calibrated["observable_support"].items()
    ):
        return unknown
    probability = isotonic_predict(calibrated["isotonic_blocks"], predict(data, features))
    geometry = calibrated["geometric_error_bound_m"]
    motion_residual = calibrated["motion_residual_bound_m_s"]
    if probability is None or geometry is None or motion_residual is None:
        return unknown
    by_action = {
        action: isotonic_predict(
            calibrated["action_isotonic_blocks"].get(action, []),
            predict(data["action_models"][action], features),
        )
        if action in data["action_models"]
        else None
        for action in ACTIONS
    }
    return RiskEstimate(
        probability, by_action, geometry, values["observed_motion_m_s"] + motion_residual, "VALID"
    )
