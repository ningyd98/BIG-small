"""Dataset boundaries and real filesystem recovery without a renderer."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError


def models():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.rgbd.models")
    except ModuleNotFoundError:
        pytest.fail("shared RGB-D dataset models are not implemented")


def test_scene_identity_ignores_seed_and_group_identity_ignores_camera():
    model = models().SceneSpec
    parameters = {"target": {"position": [0.3, 0.1, 0.04]}, "camera": {"fovy": 45}}
    first = model.from_parameters(parameters, "asset-a", 1)
    second = model.from_parameters(parameters, "asset-a", 99)
    variant = model.from_parameters({**parameters, "camera": {"fovy": 55}}, "asset-a", 1)
    assert first.group_id == second.group_id == variant.group_id
    assert first.scene_hash == second.scene_hash
    assert first.scene_hash != variant.scene_hash


@pytest.mark.parametrize(
    "change",
    [
        {"dataset_id": "../escape"},
        {"target_x": (0.5, 0.1)},
        {"camera_height": (float("nan"), 2.0)},
        {"max_attempt_multiplier": 6},
        {"distractor_count": (0, 4)},
        {"invalid_depth_fractions": (1.1,)},
    ],
)
def test_config_rejects_unsafe_or_unbounded_values(change):
    with pytest.raises(ValidationError):
        models().DatasetConfig(**{"dataset_id": "ds", **change})


def test_config_hash_covers_generation_parameters():
    config = models().DatasetConfig(dataset_id="ds")
    clone = models().DatasetConfig.model_validate_json(config.model_dump_json())
    assert config.config_hash == clone.config_hash
    assert config.config_hash != models().DatasetConfig(dataset_id="ds", seed=1).config_hash


def sample_record(*, raw=False):
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    stream = io.BytesIO()
    Image.new("RGB", (4, 3), (90, 30, 10)).save(stream, format="PNG")
    depth = np.array([[0.0, 0.1, 1.234567, 2.0]] * 3, dtype="<f4")
    observation = RGBDObservation(
        frame_id="frame-7",
        captured_at=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        sim_time_s=0.125,
        width=4,
        height=3,
        source="mujoco_camera",
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        intrinsics=(10.0, 10.0, 2.0, 1.5),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1.4, 0, 0, 0, 1),
        episode_id="original-episode",
        calibration_version="camera-v1",
    )
    frame = CapturedFrame(
        observation,
        (-1, 10, 11, 12) * 3,
        {10: "target", 11: "distractor", 12: "destination"},
        "state-hash",
        ("state-hash",) * 3,
    )
    scene = models().SceneSpec.from_parameters(
        {"target": {"position": [0.3, 0.1, 0.04]}}, "asset-a", 1
    )
    labels = {
        "positive": False,
        "negative_reasons": ["TARGET_TOO_SMALL"],
        "instances": [
            {"semantic_id": 1, "geom_ids": [10]},
            {"semantic_id": 2, "geom_ids": [11]},
            {"semantic_id": 5, "geom_ids": [12]},
        ],
    }
    return models().SampleRecord.from_capture(
        scene, frame, labels, raw_captured_frame=frame if raw else None
    )


def storage():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.rgbd.writer")
    except ModuleNotFoundError:
        pytest.fail("atomic RGB-D dataset storage is not implemented")


def write_fixture(tmp_path, *, raw=False):
    config = models().DatasetConfig(dataset_id="ds", groups=1, width=4, height=3, min_free_bytes=0)
    record = sample_record(raw=raw)
    writer = storage().DatasetWriter(tmp_path, config)
    writer.write_episode([record])
    return writer, record, config


def test_offline_reader_preserves_timestamp(tmp_path):
    writer, original, _ = write_fixture(tmp_path)
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    stored = storage().load_records(tmp_path)[0]
    replayed = load_offline_observation(stored)
    assert replayed == original.captured_frame.observation
    assert replayed.captured_at.isoformat() == "2025-01-02T03:04:05+00:00"
    assert stored.root == tmp_path.resolve()
    assert "base64" not in (tmp_path / "samples.jsonl").read_text()
    assert "captured_frame" not in stored.model_dump()
    assert np.load(tmp_path / stored.paths["depth"], allow_pickle=False).dtype == np.dtype("<f4")
    assert np.load(tmp_path / stored.paths["instance"], allow_pickle=False).tolist() == [
        [0, 1, 2, 5],
        [0, 1, 2, 5],
        [0, 1, 2, 5],
    ]
    assert writer.total_bytes > 48


def test_raw_evidence_is_preserved_with_separate_hashes(tmp_path):
    writer, original, _ = write_fixture(tmp_path, raw=True)
    stored = writer.records[0]
    assert {"raw_rgb", "raw_depth", "raw_valid_mask", "raw_camera"} <= stored.paths.keys()
    metadata = json.loads((tmp_path / stored.paths["raw_camera"]).read_text())
    assert metadata["checksum_sha256"] == original.raw_captured_frame.observation.checksum_sha256
    assert "base64" not in json.dumps(metadata)


def test_atomic_publish_survives_disk_failure(tmp_path, monkeypatch):
    config = models().DatasetConfig(dataset_id="ds", groups=1, min_free_bytes=0)
    writer = storage().DatasetWriter(tmp_path, config)
    original = os.replace

    def disk_full(source, destination):
        if Path(destination).parent.name == "episodes":
            raise OSError(28, "No space left on device")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", disk_full)
    with pytest.raises(OSError):
        writer.write_episode([sample_record()])
    assert storage().load_records(tmp_path) == []
    monkeypatch.setattr(os, "replace", original)
    resumed = storage().DatasetWriter(tmp_path, config)
    resumed.write_episode([sample_record()])
    resumed.write_episode([sample_record()])
    assert len(storage().load_records(tmp_path)) == 1


def test_recovery_rebuilds_index_after_publish_before_index_crash(tmp_path, monkeypatch):
    config = models().DatasetConfig(dataset_id="ds", groups=1, min_free_bytes=0)
    writer = storage().DatasetWriter(tmp_path, config)
    original = os.replace

    def crash(source, destination):
        if Path(destination) == tmp_path / "samples.jsonl":
            raise OSError("index publication interrupted")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        writer.write_episode([sample_record()])
    monkeypatch.setattr(os, "replace", original)
    resumed = storage().DatasetWriter(tmp_path, config)
    assert len(resumed.records) == 1
    assert len((tmp_path / "samples.jsonl").read_text().splitlines()) == 1


def test_same_episode_with_changed_labels_is_rejected(tmp_path):
    writer, record, _ = write_fixture(tmp_path)
    altered = record.model_copy(
        update={"labels": {**record.labels, "negative_reasons": ["changed"]}}
    )
    with pytest.raises(ValueError, match="(?i)(different|conflict|identical)"):
        writer.write_episode([altered])


@pytest.mark.parametrize("key", ["rgb", "depth", "camera", "labels", "instance"])
def test_altered_payload_blocks_reader_and_resume(tmp_path, key):
    writer, _, config = write_fixture(tmp_path)
    record = writer.records[0]
    payload = tmp_path / record.paths[key]
    payload.write_bytes(payload.read_bytes() + b"tampered")
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="(?i)(hash|checksum)"):
        load_offline_observation(record)
    with pytest.raises(ValueError, match="(?i)(hash|checksum)"):
        storage().DatasetWriter(tmp_path, config)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.npy",
        "/tmp/escape.npy",
        "episodes/../escape.npy",
        "episodes\\escape.npy",
        "./episode.npy",
    ],
)
def test_record_rejects_path_traversal(path):
    record = sample_record()
    with pytest.raises(ValidationError):
        models().SampleRecord.model_validate({**record.model_dump(), "paths": {"depth": path}})


def test_reader_rejects_symlink_payload(tmp_path):
    writer, _, _ = write_fixture(tmp_path)
    record = writer.records[0]
    payload = tmp_path / record.paths["depth"]
    external = tmp_path.parent / "external-depth.npy"
    external.write_bytes(payload.read_bytes())
    payload.unlink()
    payload.symlink_to(external)
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="(?i)(symlink|outside|path)"):
        load_offline_observation(record)


@pytest.mark.parametrize("dtype", [object, np.float64, np.int32])
def test_reader_rejects_unsafe_depth_dtype_even_with_matching_file_hash(tmp_path, dtype):
    writer, _, _ = write_fixture(tmp_path)
    record = writer.records[0]
    payload = tmp_path / record.paths["depth"]
    np.save(payload, np.ones((3, 4), dtype=dtype))
    record.file_hashes["depth"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="(?i)(pickle|dtype|float32)"):
        load_offline_observation(record)


def test_config_resume_and_manifest_conflicts_are_not_overwritten(tmp_path):
    _, _, config = write_fixture(tmp_path)
    with pytest.raises(ValueError, match="(?i)config"):
        storage().DatasetWriter(tmp_path, config.model_copy(update={"seed": 2}))
    manifest = models().DatasetManifest(
        dataset_id="ds",
        config=config,
        config_hash=config.config_hash,
        status="RUNNING",
        requested_groups=1,
    )
    storage().save_manifest(tmp_path, manifest)
    assert storage().load_manifest(tmp_path) == manifest
    other = models().DatasetConfig(dataset_id="other", groups=1)
    conflict = models().DatasetManifest(
        dataset_id="other",
        config=other,
        config_hash=other.config_hash,
        status="COMPLETE",
        requested_groups=1,
    )
    with pytest.raises(ValueError, match="(?i)config"):
        storage().save_manifest(tmp_path, conflict)
    assert storage().load_manifest(tmp_path) == manifest


def test_numpy_header_shape_is_checked_before_loading_payload(tmp_path, monkeypatch):
    writer, _, _ = write_fixture(tmp_path)
    record = writer.records[0]
    payload = tmp_path / record.paths["depth"]
    with payload.open("wb") as stream:
        np.lib.format.write_array_header_1_0(
            stream, {"descr": "<f4", "fortran_order": False, "shape": (999999999, 999999999)}
        )
    record.file_hashes["depth"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    original = np.load

    def reject_dangerous_allocation(*args, **kwargs):
        pytest.fail("unsafe ndarray dimensions reached the allocating NumPy loader")

    monkeypatch.setattr(np, "load", reject_dangerous_allocation)
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="(?i)(shape|dimensions)"):
        load_offline_observation(record)
    monkeypatch.setattr(np, "load", original)


def test_writer_rejects_inconsistent_positive_status(tmp_path):
    config = models().DatasetConfig(dataset_id="ds", groups=1, min_free_bytes=0)
    writer = storage().DatasetWriter(tmp_path, config)
    inconsistent = sample_record().model_copy(update={"status": "POSITIVE"})
    with pytest.raises(ValueError, match="(?i)(positive|status)"):
        writer.write_episode([inconsistent])
    assert writer.records == []


def test_content_hash_ignores_acquisition_identity_and_time(tmp_path):
    from dataclasses import replace

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    record = sample_record()
    writer, _, _ = write_fixture(tmp_path / "first")
    original = record.captured_frame.observation
    changed = RGBDObservation.model_validate(
        {
            **original.model_dump(),
            "frame_id": "different-frame",
            "observation_id": "different-frame",
            "episode_id": "different-episode",
            "captured_at": "2026-06-01T12:00:00+00:00",
            "checksum_sha256": "",
        }
    )
    frame = replace(record.captured_frame, observation=changed)
    derivative = models().SampleRecord.from_capture(record.scene, frame, record.labels)
    second = storage().DatasetWriter(tmp_path / "second", writer.config)
    second.write_episode([derivative])
    assert second.records[0].content_hash == writer.records[0].content_hash
    assert second.records[0].file_hashes["camera"] != writer.records[0].file_hashes["camera"]


@pytest.mark.parametrize("limits", [{"max_bytes": 1024}, {"min_free_bytes": 10**20}])
def test_byte_and_free_space_budget_prevents_episode_publication(tmp_path, limits):
    config = models().DatasetConfig(**{"dataset_id": "ds", "min_free_bytes": 0, **limits})
    writer = storage().DatasetWriter(tmp_path, config)
    with pytest.raises(OSError, match="(?i)(budget|space)"):
        writer.write_episode([sample_record()])
    assert storage().load_records(tmp_path) == []
    assert list((tmp_path / "episodes").iterdir()) == []


@pytest.mark.parametrize("changed", ["timestamp", "episode", "calibration", "rgb", "physics"])
def test_raw_evidence_from_different_acquisition_is_rejected(tmp_path, changed):
    from dataclasses import replace

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    record = sample_record(raw=True)
    raw = record.raw_captured_frame
    payload = raw.observation.model_dump()
    if changed == "timestamp":
        payload["captured_at"] = "2026-01-01T00:00:00+00:00"
    elif changed == "episode":
        payload["episode_id"] = "another-episode"
    elif changed == "calibration":
        payload["intrinsics"] = (11.0, 10.0, 2.0, 1.5)
    elif changed == "rgb":
        stream = io.BytesIO()
        Image.new("RGB", (4, 3), (0, 0, 200)).save(stream, format="PNG")
        payload["rgb_png_base64"] = base64.b64encode(stream.getvalue()).decode()
    payload["checksum_sha256"] = ""
    raw = replace(raw, observation=RGBDObservation.model_validate(payload))
    if changed == "physics":
        raw = replace(raw, physics_state_hash="other-state", pass_state_hashes=("other-state",) * 3)
    record = record.model_copy(update={"raw_captured_frame": raw})
    writer = storage().DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="ds"))
    with pytest.raises(ValueError, match="(?i)raw"):
        writer.write_episode([record])
    assert writer.records == []


@pytest.mark.parametrize("corruption", [{"depth_noise_m": 0.002}, {"invalid_depth_fraction": 0.1}])
def test_corrupted_observation_requires_raw_evidence(tmp_path, corruption):
    record = sample_record()
    scene = models().SceneSpec.from_parameters(
        {**record.scene.scene_parameters, **corruption}, "asset-a", 1
    )
    record = record.model_copy(update={"scene": scene})
    writer = storage().DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="ds"))
    with pytest.raises(ValueError, match="(?i)raw"):
        writer.write_episode([record])


def test_reader_verifies_raw_physics_linkage(tmp_path):
    writer, _, _ = write_fixture(tmp_path, raw=True)
    record = writer.records[0]
    assert "raw_state" in record.paths
    path = tmp_path / record.paths["raw_state"]
    payload = json.loads(path.read_text())
    payload["physics_state_hash"] = "other-state"
    path.write_text(json.dumps(payload))
    record.file_hashes["raw_state"] = hashlib.sha256(path.read_bytes()).hexdigest()
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="(?i)raw"):
        load_offline_observation(record)


@pytest.mark.parametrize("passes", [(), ("state-hash",), ("state-hash",) * 2,
                                    ("state-hash",) * 4])
def test_writer_requires_three_synchronized_passes(tmp_path, passes):
    from dataclasses import replace

    from cloud_edge_robot_arm.datasets.rgbd.writer import DatasetWriter

    record = sample_record()
    record.captured_frame = replace(record.captured_frame, pass_state_hashes=passes)
    writer = DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="passes"))
    with pytest.raises(ValueError, match="render passes"):
        writer.write_episode([record])


@pytest.mark.parametrize("passes", [(), ("state-hash",), ("state-hash",) * 2,
                                    ("state-hash",) * 4])
def test_writer_requires_three_raw_passes(tmp_path, passes):
    from dataclasses import replace

    record = sample_record(raw=True)
    record.raw_captured_frame = replace(record.raw_captured_frame, pass_state_hashes=passes)
    writer = storage().DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="raw-passes"))
    with pytest.raises(ValueError, match="raw"):
        writer.write_episode([record])


@pytest.mark.parametrize("empty_hash", ["", "   "])
def test_empty_physics_hash_is_not_sync_evidence(tmp_path, empty_hash):
    from dataclasses import replace

    record = sample_record()
    record.physics_state_hash = empty_hash
    record.captured_frame = replace(record.captured_frame, physics_state_hash=empty_hash,
                                    pass_state_hashes=(empty_hash,) * 3)
    writer = storage().DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="empty-hash"))
    with pytest.raises(ValueError, match="render passes"):
        writer.write_episode([record])


def test_main_state_file_is_persisted_and_verified_on_replay(tmp_path):
    writer, _, _ = write_fixture(tmp_path)
    record = writer.records[0]
    assert "state" in record.paths
    state_path = tmp_path / record.paths["state"]
    state = json.loads(state_path.read_text())
    assert state["physics_state_hash"] == "state-hash"
    assert state["pass_state_hashes"] == ["state-hash"] * 3
    state["pass_state_hashes"] = []
    state_path.write_text(json.dumps(state))
    record.file_hashes["state"] = hashlib.sha256(state_path.read_bytes()).hexdigest()
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="render passes"):
        load_offline_observation(record)


@pytest.mark.parametrize("mode,value", [("L", 255), ("RGB", (255, 0, 255))])
def test_wrong_depth_visualization_rejected_even_with_matching_hash(tmp_path, mode, value):
    writer, _, _ = write_fixture(tmp_path)
    record = writer.records[0]
    path = tmp_path / record.paths["depth_vis"]
    Image.new(mode, (4, 3), value).save(path, format="PNG")
    record.file_hashes["depth_vis"] = hashlib.sha256(path.read_bytes()).hexdigest()
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    with pytest.raises(ValueError, match="depth visualization"):
        load_offline_observation(record)


def test_all_invalid_depth_keeps_black_visualization_and_replays(tmp_path):
    from dataclasses import replace

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.offline_reader import load_offline_observation

    record = sample_record()
    frame = record.captured_frame
    observation = RGBDObservation.model_validate({
        **frame.observation.model_dump(),
        "depth_float32_base64": base64.b64encode(np.zeros((3, 4), dtype="<f4").tobytes()).decode(),
        "valid_mask_base64": None, "checksum_sha256": "",
    })
    record = models().SampleRecord.from_capture(
        record.scene, replace(frame, observation=observation), record.labels)
    writer = storage().DatasetWriter(tmp_path, models().DatasetConfig(dataset_id="invalid"))
    writer.write_episode([record])
    saved = writer.records[0]
    assert load_offline_observation(saved) == observation
    with Image.open(tmp_path / saved.paths["depth_vis"]) as image:
        assert image.mode == "L" and image.getextrema() == (0, 0)
