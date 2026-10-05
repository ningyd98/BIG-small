"""Deterministic CPU logistic regression on explicitly isolated offline supervision."""

from __future__ import annotations

import hashlib
import json
import math
import random
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.datasets.rgbd.models import (
    SampleRecord,
    TrajectoryFrame,
    canonical_json,
    content_digest,
)
from cloud_edge_robot_arm.datasets.rgbd.quality import source_identity
from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation, resolve_payload
from cloud_edge_robot_arm.vision.risk.features import extract_risk_features
from cloud_edge_robot_arm.vision.risk.models import (
    ACTIONS,
    FEATURE_SOURCES,
    RiskFeatures,
    RiskModelArtifact,
)

REGRESSORS = tuple(
    key
    for key in FEATURE_SOURCES
    if key not in {"calibration_fingerprint", "calibration_valid", "motion_pair_valid"}
)
SETTINGS = {
    "coverage": 0.9,
    "iterations": 400,
    "learning_rate": 0.1,
    "l2": 0.01,
    "max_invalid_depth_fraction": 0.3,
    "max_frame_interval_s": 2.0,
}


def supervision(record: SampleRecord, split: str) -> dict[str, Any]:
    value = record.labels.get("risk_supervision")
    if not isinstance(value, dict):
        raise ValueError(
            "dedicated risk supervision is required; perception labels are insufficient"
        )
    if value.get("split") != split:
        raise ValueError(f"risk records must belong to {split}")
    if type(value.get("failure")) is not bool:
        raise ValueError("risk supervision failure must be a verified offline boolean label")
    residuals = value.get("calibration_residuals_m")
    if not isinstance(residuals, list) or not residuals:
        raise ValueError("measured calibration residuals are required")
    return value


def provenance(records: Sequence[SampleRecord]) -> dict[str, list[str]]:
    return {
        name: sorted({value for record in records if (value := getter(record))})
        for name, getter in {
            "group": lambda r: r.group_id,
            "source": source_identity,
            "episode": lambda r: r.episode_id,
            "physics_state": lambda r: r.physics_state_hash,
            "content": lambda r: r.content_hash,
            "perceptual": lambda r: r.perceptual_hash,
        }.items()
    }


def assert_disjoint(left: Mapping[str, Sequence[str]], right: Mapping[str, Sequence[str]]) -> None:
    for kind in left:
        if set(left[kind]) & set(right.get(kind, ())):
            raise ValueError(f"risk source overlap across partitions: {kind}")


def sample_features(
    record: SampleRecord, records: Sequence[SampleRecord], split: str
) -> RiskFeatures:
    labels = supervision(record, split)
    observation = (
        load_offline_observation(record)
        if record.root is not None
        else record.captured_frame.observation
        if record.captured_frame
        else None
    )
    if observation is None:
        raise ValueError("risk fit requires actual RGB-D camera input")
    previous = None
    previous_id = labels.get("previous_sample_id")
    if previous_id is not None:
        candidates = [item for item in records if item.sample_id == previous_id]
        if len(candidates) != 1 or candidates[0].group_id != record.group_id:
            raise ValueError(
                "previous frame must be uniquely bound to the same isolated source group"
            )
        item = candidates[0]
        supervision(item, split)
        previous = (
            load_offline_observation(item)
            if item.root is not None
            else item.captured_frame.observation
            if item.captured_frame
            else None
        )
        if previous is None:
            raise ValueError("previous frame payload is missing")
    return extract_risk_features(observation, previous, labels["calibration_residuals_m"])


def action_outcomes(record: SampleRecord, split: str) -> dict[str, bool]:
    """An action label requires hash-verified executed feedback, never perception status."""
    raw = supervision(record, split).get("action_outcomes", {})
    if not isinstance(raw, dict):
        raise ValueError("action outcomes must be a mapping of executed feedback references")
    result = {}
    for action, reference in raw.items():
        if action not in ACTIONS or not isinstance(reference, dict) or record.root is None:
            raise ValueError("action outcome requires an actual executed feedback source")
        key = reference.get("evidence_key")
        if key not in record.paths or key not in record.file_hashes:
            raise ValueError("action outcome must reference a committed checksummed payload")
        payload = resolve_payload(record.root, record.paths[key]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.file_hashes[key]:
            raise ValueError("executed feedback hash mismatch")
        feedback = json.loads(payload)
        if (
            feedback.get("executed") is not True
            or type(feedback.get("failure")) is not bool
            or feedback.get("action") != action
            or feedback.get("sample_id") != record.sample_id
            or feedback.get("observation_id") != record.frame_id
            or feedback.get("split") != split
            or not feedback.get("trajectory_hash")
            or not feedback.get("independent_result_ref")
        ):
            raise ValueError("executed feedback lacks independent trajectory/result evidence")
        try:
            trajectory_payload = resolve_payload(
                record.root, feedback["trajectory_ref"]
            ).read_bytes()
            result_payload = resolve_payload(
                record.root, feedback["independent_result_ref"]
            ).read_bytes()
            if (
                hashlib.sha256(trajectory_payload).hexdigest() != feedback["trajectory_hash"]
                or hashlib.sha256(result_payload).hexdigest()
                != feedback["independent_result_sha256"]
            ):
                raise ValueError("executed feedback trajectory/result hash mismatch")
            trajectory = TrajectoryFrame.model_validate_json(trajectory_payload)
            independent = json.loads(result_payload)
            if (
                trajectory.observation.frame_id != record.frame_id
                or trajectory.observation.checksum_sha256
                != record.observation_metadata.get("checksum_sha256")
                or trajectory.action.finished_at <= trajectory.action.started_at
                or trajectory.action.started_at < trajectory.observation.captured_at
                or trajectory.action.finished_at > trajectory.next_observation.captured_at
                or independent.get("source") != "INDEPENDENT_EVALUATOR"
                or independent.get("action_id") != trajectory.action.action_id
                or independent.get("action") != action
                or independent.get("next_observation_checksum")
                != trajectory.next_observation.checksum_sha256
                or independent.get("failure") != feedback["failure"]
            ):
                raise ValueError("executed feedback trajectory/result identity mismatch")
        except (KeyError, OSError, TypeError) as exc:
            raise ValueError(
                "executed feedback needs actual trajectory and independent result"
            ) from exc
        result[action] = feedback["failure"]
    return result


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-40, min(40, value))))


def logistic_fit(
    rows: Sequence[Sequence[float]], labels: Sequence[bool], seed: int
) -> dict[str, Any]:
    if set(labels) != {False, True}:
        raise ValueError("logistic fit requires both failure classes")
    width = len(rows[0])
    means = [sum(row[j] for row in rows) / len(rows) for j in range(width)]
    scales = [
        max(math.sqrt(sum((row[j] - means[j]) ** 2 for row in rows) / len(rows)), 1e-9)
        for j in range(width)
    ]
    normalized = [[(row[j] - means[j]) / scales[j] for j in range(width)] for row in rows]
    weights = [0.0] * width
    intercept = 0.0
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    for _ in range(int(SETTINGS["iterations"])):
        errors = [
            sigmoid(intercept + sum(w * x for w, x in zip(weights, normalized[i], strict=True)))
            - labels[i]
            for i in order
        ]
        intercept -= SETTINGS["learning_rate"] * sum(errors) / len(rows)
        weights = [
            w
            - SETTINGS["learning_rate"]
            * (
                sum(error * normalized[i][j] for error, i in zip(errors, order, strict=True))
                / len(rows)
                + SETTINGS["l2"] * w
            )
            for j, w in enumerate(weights)
        ]
    return {"means": means, "scales": scales, "weights": weights, "intercept": intercept}


def predict(data: Mapping[str, Any], features: RiskFeatures) -> float:
    row = [features.values[key].value for key in REGRESSORS]
    return sigmoid(
        data["intercept"]
        + sum(
            weight * (value - mean) / scale
            for value, mean, scale, weight in zip(
                row, data["means"], data["scales"], data["weights"], strict=True
            )
        )
    )


def load_model(model: RiskModelArtifact) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(Path(model.model_path).read_text())
    if content_digest(data) != model.model_hash:
        raise ValueError("risk model hash mismatch")
    if tuple(data["fit_group_ids"]) != model.fit_group_ids or data["feature_schema"] != dict(
        model.feature_schema
    ):
        raise ValueError("risk artifact provenance/schema mismatch")
    return data


def fit_risk_model(train: Sequence[SampleRecord], seed: int) -> RiskModelArtifact:
    if not train:
        raise ValueError("train records are required")
    if len({record.sample_id for record in train}) != len(train):
        raise ValueError("duplicate risk training sample identity")
    train = sorted(train, key=lambda r: r.sample_id)
    labels = [supervision(record, "train")["failure"] for record in train]
    features = [sample_features(record, train, "train") for record in train]
    rows = [[feature.values[key].value for key in REGRESSORS] for feature in features]
    data = logistic_fit(rows, labels, seed)
    data.update(
        {
            "schema_version": "risk.model.v1",
            "seed": seed,
            "settings": SETTINGS,
            "feature_schema": dict(FEATURE_SOURCES),
            "regressors": REGRESSORS,
            "fit_group_ids": sorted({record.group_id for record in train}),
            "fit_provenance": provenance(train),
            "calibration_fingerprints": sorted(
                {f.values["calibration_fingerprint"].value for f in features}
            ),
            "feature_ranges": {
                key: [
                    min(f.values[key].value for f in features),
                    max(f.values[key].value for f in features),
                ]
                for key in REGRESSORS
            },
            "action_models": {},
            "source_accepted": False,  # API preparation never grants research acceptance.
        }
    )
    outcomes = [action_outcomes(record, "train") for record in train]
    for action in ACTIONS:
        indices = [i for i, outcome in enumerate(outcomes) if action in outcome]
        action_labels = [outcomes[i][action] for i in indices]
        if set(action_labels) == {False, True}:
            data["action_models"][action] = logistic_fit(
                [rows[i] for i in indices], action_labels, seed
            )
    path = Path(tempfile.mkdtemp(prefix="bigsmall-risk-")) / "model.json"
    path.write_text(canonical_json(data) + "\n")
    return RiskModelArtifact(
        content_digest(data), str(path), "", tuple(data["fit_group_ids"]), (), FEATURE_SOURCES
    )
