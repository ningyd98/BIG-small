"""Payload-backed validation and conservative local RGB-D duplicate screening."""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    QualityReport,
    SampleRecord,
    SplitManifest,
    canonical_json,
    content_digest,
    safe_relative_path,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def source_identity(record: SampleRecord) -> str:
    """Full canonical physical/asset hash; never trust a user-supplied group ID."""
    physical = {
        key: value
        for key, value in record.scene.scene_parameters.items()
        if key not in {"camera", "light_intensity", "depth_noise_m", "invalid_depth_fraction"}
    }
    return content_digest(
        {"parameters": physical, "asset_family_hash": record.scene.asset_family_hash}
    )


def perceptual_signature(observation: RGBDObservation) -> str:
    """Return v1 RGB 64x48 + metric depth 32x24 thumbnails, with no labels.

    Local channel-centered colors remove uniform lighting offsets. Comparison
    requires matching chromatic support and local colors, then metric depth.
    Unlike a global average/dHash, the fixed background cannot drown out a moved
    colored object. This conservative test detects small photometric changes;
    source grouping additionally covers viewpoint and corruption derivatives.
    """
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        rgb = np.asarray(image.resize((64, 48), Image.Resampling.BOX), dtype=np.uint8)
    depth = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4")
    depth = depth.reshape((observation.height, observation.width))
    small_depth = np.asarray(
        Image.fromarray(depth).resize((32, 24), Image.Resampling.NEAREST), dtype="<f4"
    )
    return canonical_json(
        {
            "version": "local-rgbd-v1",
            "shape": [observation.width, observation.height],
            "rgb": base64.b64encode(rgb.tobytes()).decode(),
            "depth": base64.b64encode(small_depth.tobytes()).decode(),
        }
    )


@lru_cache(maxsize=4096)
def _decode_signature(
    signature: str,
) -> tuple[tuple[int, ...], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    try:
        payload = json.loads(signature)
        if (
            set(payload) != {"version", "shape", "rgb", "depth"}
            or payload["version"] != "local-rgbd-v1"
        ):
            raise ValueError("unknown signature version")
        shape = payload["shape"]
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or any(type(n) is not int or n < 1 for n in shape)
            or shape[0] > 1280
            or shape[1] > 720
        ):
            raise ValueError("invalid signature dimensions")
        rgb = (
            np.frombuffer(base64.b64decode(payload["rgb"], validate=True), dtype=np.uint8)
            .reshape(48, 64, 3)
            .astype(np.float32)
            / 255
        )
        depth = np.frombuffer(
            base64.b64decode(payload["depth"], validate=True), dtype="<f4"
        ).reshape(24, 32)
        if not np.isfinite(depth).all() or (depth < 0).any():
            raise ValueError("invalid signature depth")
        chroma = rgb - rgb.mean(axis=2, keepdims=True)
        support = rgb.max(axis=2) - rgb.min(axis=2) > 0.15
        coarse = chroma.reshape(12, 4, 16, 4, 3).mean(axis=(1, 3))
        gray = rgb.mean(axis=2)
        return tuple(shape), chroma, support, depth, coarse, gray - np.median(gray)
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise ValueError("invalid perceptual signature") from exc


def _near_duplicate(first: str, second: str) -> bool:
    left, right = _decode_signature(first), _decode_signature(second)
    if left[0] != right[0] or np.max(np.abs(left[4] - right[4])) > 0.035:
        return False
    union = left[2] | right[2]
    if union.any():
        intersection = left[2] & right[2]
        if intersection.sum() / union.sum() < 0.95:
            return False
        changed = np.max(np.abs(left[1] - right[1]), axis=2) > 0.06
        if (changed & union).sum() / union.sum() > 0.02:
            return False
    elif np.max(np.abs(left[5] - right[5])) > 0.04:
        return False
    valid = (left[3] > 0) & (right[3] > 0)
    if np.mean((left[3] > 0) != (right[3] > 0)) > 0.02:
        return False
    return bool(not valid.any() or np.max(np.abs(left[3][valid] - right[3][valid])) <= 0.015)


def duplicate_reason(candidate: SampleRecord, existing: SampleRecord) -> str | None:
    for record in (candidate, existing):
        if record.perceptual_hash:
            _decode_signature(record.perceptual_hash)
    if candidate.group_id == existing.group_id:
        return "source_group"
    if candidate.episode_id == existing.episode_id:
        return "episode"
    if source_identity(candidate) == source_identity(existing):
        return "canonical_source"
    if candidate.scene.scene_hash == existing.scene.scene_hash:
        return "scene_content"
    if candidate.content_hash and candidate.content_hash == existing.content_hash:
        return "content_hash"
    if (
        candidate.perceptual_hash
        and existing.perceptual_hash
        and _near_duplicate(candidate.perceptual_hash, existing.perceptual_hash)
    ):
        return "near_duplicate"
    return None


def find_duplicate(candidate: SampleRecord, existing: Sequence[SampleRecord]) -> str | None:
    """Return a matching existing sample ID, or None; persist the signature first."""
    if candidate.perceptual_hash:
        _decode_signature(candidate.perceptual_hash)
    for record in sorted(existing, key=lambda item: item.sample_id):
        if duplicate_reason(candidate, record):
            return record.sample_id
    return None


def _validate_labels(record: SampleRecord, observation: RGBDObservation) -> None:
    from cloud_edge_robot_arm.vision.offline_reader import load_numeric, resolve_payload

    labels = record.labels
    required = {
        "instruction",
        "instruction_en",
        "target_instance_id",
        "destination_instance_id",
        "instances",
        "target_pixel",
        "destination_pixel",
        "surface_point",
        "object_center",
        "positive",
        "negative_reasons",
        "suggested_action",
        "label_source",
        "execution_verified",
    }
    if not required <= labels.keys() or any(
        not isinstance(labels[key], str) or not labels[key].strip()
        for key in ("instruction", "instruction_en")
    ):
        raise ValueError("incomplete grounding labels")
    if not isinstance(labels["negative_reasons"], list) or any(
        not isinstance(reason, str) or not reason for reason in labels["negative_reasons"]
    ):
        raise ValueError("negative reasons must be a list of nonempty strings")
    if (
        labels["label_source"] != "SIMULATOR_GROUND_TRUTH"
        or labels["execution_verified"] is not False
    ):
        raise ValueError("labels cannot claim verified physical execution")
    if labels["target_instance_id"] != 1 or labels["destination_instance_id"] != 5:
        raise ValueError("invalid target/destination semantic IDs")
    assert record.root is not None
    instances = load_numeric(
        resolve_payload(record.root, record.paths["instance"]).read_bytes(),
        "<i4",
        (observation.height, observation.width),
        "instance",
    )
    depth_valid = np.frombuffer(observation.valid_mask_bytes(), dtype="u1").reshape(instances.shape)
    by_id = {}
    for item in labels["instances"]:
        semantic_id = item["semantic_id"]
        if type(semantic_id) is not int or semantic_id in by_id or not 1 <= semantic_id <= 5:
            raise ValueError("duplicate/invalid label semantic ID")
        by_id[semantic_id] = item
        ys, xs = np.where(instances == semantic_id)
        count = len(xs)
        box = (
            [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if count else None
        )
        valid_fraction = float(depth_valid[ys, xs].mean()) if count else 0.0
        if item["visible_pixels"] != count or item["bbox_xyxy"] != box:
            raise ValueError("label visibility/bbox disagrees with semantic payload")
        if not np.isclose(item["valid_depth_fraction"], valid_fraction, atol=1e-7):
            raise ValueError("label depth fraction disagrees with restored depth")
    if 1 not in by_id or 5 not in by_id:
        raise ValueError("missing target/destination instance labels")
    target = by_id[1]
    destination = by_id[5]
    threshold_positive = all(
        item["visible_pixels"] >= 100 and item["valid_depth_fraction"] >= 0.95
        for item in (target, destination)
    )
    if labels["object_center"] != target["position"]:
        raise ValueError("object center differs from the target position")
    if type(labels["positive"]) is not bool or labels["positive"] != (record.status == "POSITIVE"):
        raise ValueError("record/label positive status disagrees")
    if labels["positive"] and not threshold_positive:
        raise ValueError("research negative incorrectly marked positive")
    if labels["positive"]:
        if labels["surface_point"] is None:
            raise ValueError("positive sample missing metric surface grounding")
        if labels["negative_reasons"] or labels["suggested_action"] != "GROUND_TARGET":
            raise ValueError("positive label has inconsistent action/reasons")
    elif not labels["negative_reasons"] or labels["suggested_action"] != "REQUEST_MORE_OBSERVATION":
        raise ValueError("negative sample must retain reasons and request observation")
    for name, semantic_id in (("target_pixel", 1), ("destination_pixel", 5)):
        pixel = labels[name]
        if pixel is None:
            if labels["positive"]:
                raise ValueError("positive sample missing grounding pixel")
            continue
        if (
            not isinstance(pixel, list)
            or len(pixel) != 2
            or any(type(v) is not int for v in pixel)
            or not 0 <= pixel[0] < observation.width
            or not 0 <= pixel[1] < observation.height
            or instances[pixel[1], pixel[0]] != semantic_id
            or not depth_valid[pixel[1], pixel[0]]
        ):
            raise ValueError("grounding pixel does not belong to its semantic instance")
    if labels["surface_point"] is not None:
        pixel = labels["target_pixel"]
        if pixel is None:
            raise ValueError("surface point requires a selected target pixel")
        point = observation.world_point(tuple(pixel))
        if not np.allclose(labels["surface_point"], [point.x, point.y, point.z], atol=1e-6):
            raise ValueError("surface grounding disagrees with metric depth/calibration")


def validate_dataset(root: Path) -> QualityReport:
    """Verify complete durable evidence, schemas, labels, counts and holdout audit.

    A fully populated RUNNING manifest can pass the generator's completion gate
    with a warning; partial/cancelled/failed datasets never report valid=True.
    Validation is read-only and does not repair/rewrite the original data.
    """
    from cloud_edge_robot_arm.datasets.rgbd.splitter import ROLES, assign_splits
    from cloud_edge_robot_arm.datasets.rgbd.writer import load_manifest, load_records
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation, resolve_payload

    root = Path(root).resolve()
    errors, warnings = [], []
    records, manifest, split = [], None, None
    try:
        config = DatasetConfig.model_validate_json(
            resolve_payload(root, "config.json").read_bytes()
        )
        manifest = load_manifest(root)
        if manifest is None:
            raise ValueError("missing dataset manifest")
        if manifest.config_hash != config.config_hash:
            raise ValueError("config hash mismatch")
        source = json.loads(resolve_payload(root, "source.json").read_bytes())
        if source != manifest.source:
            raise ValueError("source evidence differs from manifest")
        for kind in ("source", "asset"):
            hashes = source.get(f"{kind}_files")
            if not isinstance(hashes, dict) or not hashes:
                raise ValueError(f"missing {kind} file evidence")
            for name, digest in hashes.items():
                safe_relative_path(name)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError(f"invalid {kind} file checksum")
            if source.get(f"{kind}_hash") != content_digest(hashes):
                raise ValueError(f"{kind} evidence hash mismatch")
        records = load_records(root)
        indexed = [
            SampleRecord.model_validate_json(line)
            for line in resolve_payload(root, "samples.jsonl").read_bytes().splitlines()
            if line.strip()
        ]
        if {r.sample_id for r in indexed} != {r.sample_id for r in records} or len(indexed) != len(
            records
        ):
            raise ValueError("dataset index does not completely cover committed samples")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        errors.append(f"dataset evidence: {exc}")
    for record in records:
        try:
            observation = load_offline_observation(record)
            if manifest and (
                observation.width != manifest.config.width
                or observation.height != manifest.config.height
            ):
                raise ValueError("observation dimensions differ from dataset config")
            if not record.perceptual_hash or record.perceptual_hash != perceptual_signature(
                observation
            ):
                raise ValueError("perceptual signature does not match restored observation")
            _validate_labels(record, observation)
        except (ValueError, OSError, TypeError, KeyError, IndexError) as exc:
            errors.append(f"sample {record.sample_id}: {exc}")
    positive_count = sum(record.status == "POSITIVE" for record in records)
    negative_count = len(records) - positive_count
    expected_split = None
    try:
        split = SplitManifest.model_validate_json(
            resolve_payload(root, "reports/split_audit.json").read_bytes()
        )
        if manifest and split.seed != manifest.config.seed:
            raise ValueError("split seed differs from dataset config")
        expected_split = assign_splits(records, split.seed)
        if split != expected_split:
            raise ValueError("split audit differs from verified source/content assignments")
        seen = set()
        canonical_records = {r.sample_id: r.model_dump(mode="json") for r in records}
        for role in ROLES:
            role_records = [
                SampleRecord.model_validate_json(line)
                for line in resolve_payload(root, f"splits/{role}.jsonl").read_bytes().splitlines()
                if line.strip()
            ]
            actual = set()
            for record in role_records:
                if record.sample_id in seen or canonical_records.get(
                    record.sample_id
                ) != record.model_dump(mode="json"):
                    raise ValueError("overlapping holdouts or altered split record")
                seen.add(record.sample_id)
                actual.add(record.sample_id)
            expected = {
                sample_id
                for sample_id, assigned in split.sample_assignments.items()
                if assigned == role
            }
            if actual != expected:
                raise ValueError(f"{role} split coverage/assignment mismatch")
        if seen != set(canonical_records):
            raise ValueError("split files do not cover all retained samples")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        errors.append(f"holdout integrity: {exc}")
    group_count = (
        sum(expected_split.counts.values())
        if expected_split
        else len({source_identity(r) for r in records})
    )
    if manifest:
        if manifest.status not in {"COMPLETE", "RUNNING"}:
            reason = manifest.reason or "generation did not complete"
            errors.append(f"dataset status is {manifest.status}: {reason}")
        elif manifest.status == "RUNNING":
            warnings.append("complete payload checked before final COMPLETE manifest publication")
        if manifest.completed_groups != group_count or group_count != manifest.requested_groups:
            errors.append("manifest/requested/independent group counts disagree")
        if (
            manifest.sample_count != len(records)
            or manifest.positive_count != positive_count
            or manifest.negative_count != negative_count
        ):
            errors.append("manifest sample/positive/negative counts disagree")
        if (
            not len(records)
            or manifest.attempts < group_count
            or manifest.attempts
            > manifest.requested_groups * manifest.config.max_attempt_multiplier
        ):
            errors.append("empty dataset or inconsistent bounded attempt count")
        if manifest.content_hash != content_digest(sorted(r.content_hash for r in records)):
            errors.append("manifest content hash mismatch")
    return QualityReport(
        valid=not errors,
        sample_count=len(records),
        group_count=group_count,
        positive_count=positive_count,
        negative_count=negative_count,
        errors=errors,
        warnings=warnings,
        split_counts=expected_split.counts if expected_split else {},
        duplicate_count=len(expected_split.duplicates) if expected_split else 0,
    )
