"""SFT exports only verified trainable evidence and preserve research negatives."""

from __future__ import annotations

import base64
import importlib
import io
import json
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    DatasetManifest,
    SampleRecord,
    SceneSpec,
    content_digest,
)
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def module(name):
    try:
        return importlib.import_module(f"cloud_edge_robot_arm.datasets.rgbd.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"RGB-D {name} is not implemented")


@pytest.fixture
def dataset(tmp_path):
    quality, splitter, storage = module("quality"), module("splitter"), module("writer")
    root = tmp_path / "dataset"
    config = DatasetConfig(
        dataset_id="test-dataset", groups=20, width=96, height=64, min_free_bytes=0
    )
    writer = storage.DatasetWriter(root, config)
    for i in range(20):
        positive = i % 2 == 0
        side = 10 if positive else 8
        x, y = 2 + 11 * (i % 5), 1 + 11 * (i // 5)
        rgb = np.full((64, 96, 3), 80, dtype=np.uint8)
        rgb[y : y + side, x : x + side] = [220, 20, 20]
        ids = np.full((64, 96), -1, dtype=np.int32)
        ids[y : y + side, x : x + side] = 11
        ids[52:62, 84:94] = 22
        rgb[52:62, 84:94] = [20, 180, 20]
        depth = np.full((64, 96), 2, dtype="<f4")
        depth[y : y + side, x : x + side] = 1
        png = io.BytesIO()
        Image.fromarray(rgb).save(png, format="PNG")
        observation = RGBDObservation(
            frame_id=f"f-{i}",
            captured_at=datetime(2020, 1, 1, tzinfo=UTC),
            sim_time_s=float(i),
            width=96,
            height=64,
            rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            intrinsics=(60, 60, 32, 24),
            camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
            source="mujoco_camera",
        )
        frame = CapturedFrame(
            observation,
            tuple(map(int, ids.flat)),
            {11: "target", 22: "destination"},
            "a" * 64,
            ("a" * 64,) * 3,
        )
        scene = SceneSpec.from_parameters(
            {"target": {"position": [i / 100, 0, 0.04]}}, "assets-test", i
        )
        labels = {
            "instruction": "将红色方块移至绿色区域",
            "instruction_en": "Move the red block to the green area",
            "target_instance_id": 1,
            "destination_instance_id": 5,
            "instances": [
                {
                    "semantic_id": 1,
                    "role": "target",
                    "geom_ids": [11],
                    "bbox_xyxy": [x, y, x + side, y + side],
                    "visible_pixels": side * side,
                    "valid_depth_fraction": 1.0,
                    "position": [i / 100, 0, 0.04],
                    "half_size": [0.03, 0.03, 0.03],
                },
                {
                    "semantic_id": 5,
                    "role": "destination",
                    "geom_ids": [22],
                    "bbox_xyxy": [84, 52, 94, 62],
                    "visible_pixels": 100,
                    "valid_depth_fraction": 1.0,
                    "position": [0.4, 0.2, 0.002],
                    "half_size": [0.07, 0.07, 0.002],
                },
            ],
            "target_pixel": [x + side // 2, y + side // 2],
            "destination_pixel": [89, 57],
            "surface_point": list(
                observation.world_point((x + side // 2, y + side // 2)).model_dump().values()
            ),
            "object_center": [i / 100, 0, 0.04],
            "positive": positive,
            "negative_reasons": [] if positive else ["TARGET_TOO_SMALL"],
            "suggested_action": "GROUND_TARGET" if positive else "REQUEST_MORE_OBSERVATION",
            "label_source": "SIMULATOR_GROUND_TRUTH",
            "execution_verified": False,
        }
        record = SampleRecord.from_capture(scene, frame, labels)
        record.perceptual_hash = quality.perceptual_signature(observation)
        writer.write_episode([record])
    records = storage.load_records(root)
    split = splitter.assign_splits(records, config.seed)
    splitter.write_splits(root, split, records)
    source = {"source_files": {"fixture.py": "a" * 64}, "asset_files": {"scene.xml": "b" * 64}}
    source.update(
        source_hash=content_digest(source["source_files"]),
        asset_hash=content_digest(source["asset_files"]),
    )
    (root / "source.json").write_text(json.dumps(source))
    manifest = DatasetManifest(
        dataset_id=config.dataset_id,
        config=config,
        config_hash=config.config_hash,
        status="COMPLETE",
        requested_groups=20,
        completed_groups=20,
        sample_count=20,
        positive_count=10,
        negative_count=10,
        attempts=20,
        source=source,
        content_hash=content_digest(sorted(record.content_hash for record in records)),
    )
    storage.save_manifest(root, manifest)
    return root, records, split


def test_test_split_export_is_denied(tmp_path):
    with pytest.raises(ValueError, match="test"):
        module("exporters").export_grounding_sft(
            tmp_path / "missing", "test", tmp_path / "leaked.jsonl"
        )
    assert not (tmp_path / "leaked.jsonl").exists()


def test_negative_conditions_are_retained(dataset, tmp_path):
    root, records, split = dataset
    output = tmp_path / "training.jsonl"
    count = module("exporters").export_grounding_sft(root, "train", output)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    expected = [
        record for record in records if split.sample_assignments[record.sample_id] == "train"
    ]
    assert count == len(rows) == len(expected) == 16
    actions = [json.loads(row["messages"][1]["content"])["action"] for row in rows]
    assert actions.count("REQUEST_MORE_OBSERVATION") == sum(
        r.status == "NEGATIVE" for r in expected
    )
    assert "GROUND_TARGET" in actions and "REQUEST_MORE_OBSERVATION" in actions


def test_sft_user_has_only_instruction_and_opaque_image_paths(dataset, tmp_path):
    root, _, _ = dataset
    output = tmp_path / "training.jsonl"
    module("exporters").export_grounding_sft(root, "train", output)
    for row in map(json.loads, output.read_text().splitlines()):
        user, assistant = row["messages"]
        assert user["role"] == "user" and assistant["role"] == "assistant"
        assert set(user["content"]) == {"instruction", "images"}
        assert len(user["content"]["images"]) == 2
        for path in user["content"]["images"]:
            assert not any(
                word in path.lower() for word in ("red", "target", "negative", "positive", "pose")
            )
            assert (root / path).is_file()
        assert "object_center" not in json.dumps(user)


def test_valid_dataset_verifies_restored_evidence_and_counts(dataset):
    root, _, _ = dataset
    report = module("quality").validate_dataset(root)
    assert report.valid, report.errors
    assert (
        report.sample_count,
        report.group_count,
        report.positive_count,
        report.negative_count,
    ) == (20, 20, 10, 10)
    assert report.split_counts == {"train": 16, "calibration": 1, "selection": 1, "test": 2}


@pytest.mark.parametrize(
    "damage", ["depth", "labels", "manifest", "split", "missing_split", "signature"]
)
def test_dataset_damage_blocks_validation_and_export(dataset, tmp_path, damage):
    root, records, split = dataset
    if damage in {"depth", "labels"}:
        path = root / records[0].paths[damage]
        path.write_bytes(path.read_bytes() + b"tamper")
    elif damage == "manifest":
        path = root / "manifest.json"
        payload = json.loads(path.read_text())
        payload["negative_count"] = 0
        path.write_text(json.dumps(payload))
    elif damage == "split":
        train = root / "splits/train.jsonl"
        (root / "splits/test.jsonl").write_text(train.read_text())
    elif damage == "missing_split":
        (root / "splits/test.jsonl").unlink()
    else:
        path = root / "reports/split_audit.json"
        payload = json.loads(path.read_text())
        payload["schema_version"] = "unknown.v999"
        path.write_text(json.dumps(payload))
    report = module("quality").validate_dataset(root)
    assert not report.valid and report.errors
    output = tmp_path / "must-not-exist.jsonl"
    with pytest.raises(ValueError):
        module("exporters").export_grounding_sft(root, "train", output)
    assert not output.exists()


def test_empty_directory_is_not_valid(tmp_path):
    report = module("quality").validate_dataset(tmp_path)
    assert not report.valid and report.errors


def test_export_cannot_overwrite_dataset_directory(dataset):
    root, _, _ = dataset
    with pytest.raises(ValueError, match="file"):
        module("exporters").export_grounding_sft(root, "train", root)


@pytest.mark.parametrize(
    "change",
    [
        {"surface_point": None},
        {"object_center": [999, 999, 999]},
        {"negative_reasons": ""},
        {"instruction_en": ""},
    ],
)
def test_inconsistent_grounding_labels_are_invalid(dataset, change):
    root, records, _ = dataset
    record = next(r for r in records if r.status == "POSITIVE")
    observation = importlib.import_module(
        "cloud_edge_robot_arm.vision.offline_reader"
    ).load_offline_observation(record)
    altered = record.model_copy(update={"labels": {**record.labels, **change}})
    with pytest.raises(ValueError):
        module("quality")._validate_labels(altered, observation)


@pytest.mark.parametrize("damage", ["small_destination", "invalid_destination_pixel"])
def test_positive_grounding_requires_observable_destination(dataset, damage):
    root, records, _ = dataset
    record = next(r for r in records if r.status == "POSITIVE")
    observation = importlib.import_module(
        "cloud_edge_robot_arm.vision.offline_reader"
    ).load_offline_observation(record)
    labels = json.loads(json.dumps(record.labels))
    instance_path = root / record.paths["instance"]
    semantics = np.load(instance_path, allow_pickle=False)
    if damage == "small_destination":
        semantics[52:62, 84] = 0
        np.save(instance_path, semantics, allow_pickle=False)
        destination = next(item for item in labels["instances"] if item["semantic_id"] == 5)
        destination.update(visible_pixels=90, bbox_xyxy=[85, 52, 94, 62])
    else:
        depth = (
            np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4")
            .copy()
            .reshape(64, 96)
        )
        depth[57, 89] = 0
        observation = RGBDObservation.model_validate(
            {
                **observation.model_dump(),
                "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
                "valid_mask_base64": None,
                "checksum_sha256": "",
            }
        )
        next(item for item in labels["instances"] if item["semantic_id"] == 5)[
            "valid_depth_fraction"
        ] = 0.99
    altered = record.model_copy(update={"labels": labels})
    with pytest.raises(ValueError):
        module("quality")._validate_labels(altered, observation)


@pytest.mark.parametrize(
    "damage", ["missing_source", "source_mismatch", "source_digest", "empty_content_hash"]
)
def test_source_and_dataset_digests_are_required(dataset, damage):
    root, _, _ = dataset
    source_path, manifest_path = root / "source.json", root / "manifest.json"
    if damage == "missing_source":
        source_path.unlink()
    elif damage == "source_mismatch":
        source_path.write_text("{}")
    else:
        manifest = json.loads(manifest_path.read_text())
        if damage == "source_digest":
            manifest["source"]["source_hash"] = "c" * 64
            source_path.write_text(json.dumps(manifest["source"]))
        else:
            manifest["content_hash"] = ""
        manifest_path.write_text(json.dumps(manifest))
    report = module("quality").validate_dataset(root)
    assert not report.valid, report
