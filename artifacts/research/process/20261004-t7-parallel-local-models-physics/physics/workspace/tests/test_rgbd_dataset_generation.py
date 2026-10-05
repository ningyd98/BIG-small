"""CPU-only orchestration fixtures exercise real storage, recovery, and CLI boundaries."""

from __future__ import annotations

import base64
import errno
import importlib
import io
import json
import subprocess
import sys
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image


def generator():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.rgbd.generator")
    except ModuleNotFoundError:
        pytest.fail("RGB-D dataset generator is not implemented")


@pytest.fixture
def cpu_factory(monkeypatch):
    """Only capture is replaced: samples, payload checks, splits and disk writes stay real."""
    module = generator()
    from cloud_edge_robot_arm.datasets.rgbd.models import (
        DatasetConfig,
        SceneSpec,
        content_digest,
    )
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    class Session:
        captures = 0
        fail_enter = False

        def __init__(self, config):
            self.scene = None

        def __enter__(self):
            if self.fail_enter:
                raise RuntimeError("EGL fixture unavailable")
            return self

        def __exit__(self, *_):
            pass

        def apply_scene(self, scene):
            self.scene = scene

    class Adapter:
        def __init__(self, session, *, settle_steps):
            self.session = session

        def capture(self):
            scene = self.session.scene
            seed = scene.seed
            Session.captures += 1
            rgb = np.random.default_rng(seed).integers(0, 256, (24, 32, 3), dtype=np.uint8)
            png = io.BytesIO()
            Image.fromarray(rgb).save(png, format="PNG")
            depth = np.full((24, 32), 1 + seed * 0.01, dtype="<f4")
            observation = RGBDObservation(
                frame_id=f"fixture-{seed}",
                captured_at=datetime(2020, 1, 1, tzinfo=UTC),
                sim_time_s=0,
                width=32,
                height=24,
                rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
                depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
                intrinsics=(30, 30, 15.5, 11.5),
                camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
                source="mujoco_camera",
                scene_id=scene.group_id,
                episode_id=f"episode-{seed}",
                calibration_version="fixture-v1",
            )
            ids = tuple(1 if i % 32 < 16 else 2 for i in range(32 * 24))
            raw_frame = CapturedFrame(
                observation,
                ids,
                {1: "target", 2: "destination"},
                "fixture-state",
                ("fixture-state",) * 3,
            )
            if seed % 2:
                indices = [index for index, geom in enumerate(ids) if geom == 1][:40]
                depth.reshape(-1)[indices] = 0
                observation = RGBDObservation.model_validate(
                    {
                        **observation.model_dump(),
                        "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
                        "valid_mask_base64": None,
                        "checksum_sha256": "",
                    }
                )
            frame = CapturedFrame(
                observation,
                ids,
                {1: "target", 2: "destination"},
                "fixture-state",
                ("fixture-state",) * 3,
            )
            return frame, {"_raw_captured_frame": raw_frame, "seed": seed}

    def scene(config, seed):
        return SceneSpec.from_parameters(
            {"target": {"position": [seed, 0, 0.04]}}, "fixture-asset", seed
        )

    def labels(frame, truth):
        negative = truth["seed"] % 2 == 1
        depth = float(np.float32(1 + truth["seed"] * 0.01))
        return {
            "instruction": "Locate the red block",
            "instruction_en": "Locate the red block",
            "target_instance_id": 1,
            "destination_instance_id": 5,
            "instances": [
                {
                    "semantic_id": 1,
                    "role": "target",
                    "geom_ids": [1],
                    "bbox_xyxy": [0, 0, 16, 24],
                    "visible_pixels": 384,
                    "valid_depth_fraction": 344 / 384 if negative else 1.0,
                    "position": [0, 0, 0.04],
                    "half_size": [0.03] * 3,
                },
                {
                    "semantic_id": 5,
                    "role": "destination",
                    "geom_ids": [2],
                    "bbox_xyxy": [16, 0, 32, 24],
                    "visible_pixels": 384,
                    "valid_depth_fraction": 1.0,
                    "position": [0.3, 0, 0.002],
                    "half_size": [0.07, 0.07, 0.002],
                },
            ],
            "target_pixel": None if negative else [8, 12],
            "destination_pixel": [24, 12],
            "surface_point": None if negative else [-0.25 * depth, depth / 60, depth],
            "object_center": [0, 0, 0.04],
            "positive": not negative,
            "negative_reasons": ["INVALID_DEPTH"] if negative else [],
            "suggested_action": "REQUEST_MORE_OBSERVATION" if negative else "GROUND_TARGET",
            "label_source": "SIMULATOR_GROUND_TRUTH",
            "execution_verified": False,
        }

    monkeypatch.setattr(module, "_capture_dependencies", lambda: (Session, Adapter, scene, labels))
    fixture_sources = {"fixture.py": "a" * 64}
    fixture_assets = {"fixture.xml": "b" * 64}
    monkeypatch.setattr(
        module,
        "_source_evidence",
        lambda config: {
            "source_hash": content_digest(fixture_sources),
            "source_files": fixture_sources,
            "asset_hash": content_digest(fixture_assets),
            "asset_files": fixture_assets,
            "evidence_kind": "SOFTWARE_FIXTURE",
        },
    )
    config = DatasetConfig(
        dataset_id="cpu-fixture", groups=3, width=32, height=24, min_free_bytes=0, settle_steps=0
    )
    return module, config, Session, scene, labels


def test_generator_without_model(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    import urllib.request

    def forbidden(*args, **kwargs):
        raise AssertionError("offline generation must not call model or network services")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "COMPLETE"
    assert (result.completed_groups, result.sample_count, result.attempts) == (3, 3, 3)
    assert (result.positive_count, result.negative_count) == (2, 1)
    assert result.resources["bytes_per_sample"] > 0
    assert result.resources["gpu_peak_memory_bytes"] == "NOT_MEASURED"
    assert (tmp_path / "reports" / "split_audit.json").exists()


def test_sampling_stops_at_five_times_budget_across_resume(cpu_factory, tmp_path, monkeypatch):
    module, config, session, scene, labels = cpu_factory
    config = config.model_copy(update={"groups": 2})
    session_type, adapter, _, _ = module._capture_dependencies()
    monkeypatch.setattr(
        module,
        "_capture_dependencies",
        lambda: (session_type, adapter, lambda cfg, seed: scene(cfg, 0), labels),
    )
    first = module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    assert first.status == "CANCELLED" and first.attempts == 1
    second = module.generate_dataset(config, tmp_path, lambda: False)
    assert second.status == "INCOMPLETE"
    assert (second.attempts, second.completed_groups, second.rejected_count) == (10, 1, 9)
    third = module.generate_dataset(config, tmp_path, lambda: False)
    assert third.attempts == 10
    assert third.completed_groups == 1


def test_cancel_preserves_committed_episode_and_resume_finishes(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    first = module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    records_before = module.load_records(tmp_path)
    assert first.status == "CANCELLED" and len(records_before) == 1
    second = module.generate_dataset(config, tmp_path, lambda: False)
    records_after = module.load_records(tmp_path)
    assert second.status == "COMPLETE" and second.attempts == 3
    assert len({record.sample_id for record in records_after}) == 3
    retained = next(
        record for record in records_after if record.sample_id == records_before[0].sample_id
    )
    assert records_before[0].file_hashes == retained.file_hashes


def test_disk_failure_keeps_published_episodes_and_attempts(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    original = module.DatasetWriter.write_episode

    def disk_full(writer, records):
        if len(writer.records) == 1:
            raise OSError(errno.ENOSPC, "disk full fixture")
        return original(writer, records)

    with monkeypatch.context() as patch:
        patch.setattr(module.DatasetWriter, "write_episode", disk_full)
        first = module.generate_dataset(config, tmp_path, lambda: False)
    assert first.status == "INCOMPLETE"
    assert (first.completed_groups, first.attempts) == (1, 2)
    assert len(module.load_records(tmp_path)) == 1
    second = module.generate_dataset(config, tmp_path, lambda: False)
    assert second.status == "COMPLETE" and second.attempts == 4


def test_disk_budget_prevents_first_capture(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    config = config.model_copy(update={"min_free_bytes": 10**30})
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "INCOMPLETE"
    assert result.attempts == result.sample_count == session.captures == 0
    assert "disk" in result.reason.lower()


def test_unavailable_renderer_is_blocked(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    session.fail_enter = True
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "BLOCKED"
    assert result.completed_groups == 0 and result.attempts == 0
    assert "EGL fixture unavailable" in result.reason


def test_resume_rejects_changed_source_or_config(cpu_factory, tmp_path, monkeypatch):
    module, config, session, _, _ = cpu_factory
    module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    before = (tmp_path / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="config"):
        module.generate_dataset(config.model_copy(update={"seed": 5}), tmp_path, lambda: False)
    monkeypatch.setattr(module, "_source_evidence", lambda cfg: {"source_hash": "changed"})
    with pytest.raises(ValueError, match="source"):
        module.generate_dataset(config, tmp_path, lambda: False)
    assert (tmp_path / "manifest.json").read_bytes() == before


def test_attempt_journal_recovers_counter_ahead_of_manifest(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    with (tmp_path / "attempts.jsonl").open("a") as stream:
        stream.write(json.dumps({"event": "started", "attempt": 2, "seed": 1}) + "\n")
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "COMPLETE"
    assert result.attempts == 4


def test_missing_attempt_history_never_resets_budget(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    (tmp_path / "attempts.jsonl").unlink()
    with pytest.raises(ValueError, match="attempt"):
        module.generate_dataset(config, tmp_path, lambda: False)


def test_interrupted_last_journal_line_is_recovered(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    module.generate_dataset(config, tmp_path, lambda: session.captures >= 1)
    with (tmp_path / "attempts.jsonl").open("ab") as stream:
        stream.write(b'{"event":"started","attempt":')
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "COMPLETE" and result.attempts == 3
    assert (tmp_path / "attempt-journal-recovery.json").exists()


def test_post_publish_disk_failure_recovers_commit(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    original = module.DatasetWriter.write_episode

    def interrupted(writer, records):
        original(writer, records)
        raise OSError(errno.ENOSPC, "post-publish failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.DatasetWriter, "write_episode", interrupted)
        first = module.generate_dataset(config, tmp_path, lambda: False)
    assert first.status == "INCOMPLETE" and first.completed_groups == 1
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "COMPLETE" and result.attempts == 3


def test_complete_dataset_is_revalidated_without_capture(cpu_factory, tmp_path):
    module, config, session, _, _ = cpu_factory
    assert module.generate_dataset(config, tmp_path, lambda: False).status == "COMPLETE"
    session.fail_enter = True
    assert module.generate_dataset(config, tmp_path, lambda: False).status == "COMPLETE"
    record = module.load_records(tmp_path)[0]
    (tmp_path / record.paths["rgb"]).write_bytes(b"corrupted")
    with pytest.raises(ValueError):
        module.generate_dataset(config, tmp_path, lambda: False)


def test_validation_failure_cannot_be_marked_complete(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    from cloud_edge_robot_arm.datasets.rgbd.models import QualityReport

    monkeypatch.setattr(
        module,
        "validate_dataset",
        lambda root: QualityReport(
            valid=False, sample_count=3, group_count=3, errors=["injected quality failure"]
        ),
    )
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "FAILED" and "quality failure" in result.reason


def test_generation_duration_includes_final_validation(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    clock = [0.0]
    original = module.validate_dataset
    monkeypatch.setattr(module, "perf_counter", lambda: clock[0])

    def delayed_validation(root):
        result = original(root)
        clock[0] = 7.0
        return result

    monkeypatch.setattr(module, "validate_dataset", delayed_validation)
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "COMPLETE"
    assert result.resources["generation_wall_time_s"] == 7.0


@pytest.mark.parametrize(
    "script",
    [
        "generate_rgbd_dataset",
        "validate_rgbd_dataset",
        "export_rgbd_training",
        "replay_rgbd_sample",
    ],
)
def test_dataset_clis_expose_help(script):
    result = subprocess.run(
        [sys.executable, f"scripts/{script}.py", "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_validate_export_and_replay_clis_use_persisted_samples(cpu_factory, tmp_path):
    module, config, _, _, _ = cpu_factory
    dataset = tmp_path / "dataset"
    assert module.generate_dataset(config, dataset, lambda: False).status == "COMPLETE"
    record = module.load_records(dataset)[0]
    commands = [
        ["validate_rgbd_dataset", "--dataset", str(dataset)],
        [
            "export_rgbd_training",
            "--dataset",
            str(dataset),
            "--split",
            "train",
            "--output",
            str(tmp_path / "train.jsonl"),
        ],
        [
            "replay_rgbd_sample",
            "--dataset",
            str(dataset),
            "--sample-id",
            record.sample_id,
            "--output",
            str(tmp_path / "replay"),
        ],
    ]
    for name, *arguments in commands:
        result = subprocess.run(
            [sys.executable, f"scripts/{name}.py", *arguments],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)
    replay = json.loads((tmp_path / "replay" / "observation.json").read_text())
    assert replay["captured_at"].startswith("2020-01-01")
    denied = subprocess.run(
        [
            sys.executable,
            "scripts/export_rgbd_training.py",
            "--dataset",
            str(dataset),
            "--split",
            "test",
            "--output",
            str(tmp_path / "test.jsonl"),
        ],
        capture_output=True,
        timeout=20,
    )
    assert denied.returncode == 2 and not (tmp_path / "test.jsonl").exists()


def test_finalization_cannot_exceed_persistent_disk_budget(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    config = config.model_copy(update={"groups": 20})
    pre_finalize = []
    original = module.write_splits

    def measure(root, split, records):
        pre_finalize.append(sum(p.stat().st_size for p in root.rglob("*") if p.is_file()))
        return original(root, split, records)

    monkeypatch.setattr(module, "write_splits", measure)
    assert (
        module.generate_dataset(config, tmp_path / "baseline", lambda: False).status == "COMPLETE"
    )
    capped = config.model_copy(update={"max_bytes": pre_finalize[0] + 150_000})
    root = tmp_path / "capped"
    result = module.generate_dataset(capped, root, lambda: False)
    assert result.status == "INCOMPLETE"
    assert "disk" in result.reason.lower()
    assert result.completed_groups == 20
    assert len(module.load_records(root)) == 20
    assert sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) <= capped.max_bytes
    assert not (root / "splits" / "train.jsonl").exists()


def test_finalization_reserves_atomic_write_free_space(cpu_factory, tmp_path, monkeypatch):
    module, config, _, _, _ = cpu_factory
    original = module.assign_splits
    real_disk_usage = module.shutil.disk_usage
    phase = {"finalizing": False}

    def mark_finalization(records, seed):
        phase["finalizing"] = True
        return original(records, seed)

    def available(path):
        actual = real_disk_usage(path)
        return actual._replace(free=12_000) if phase["finalizing"] else actual

    monkeypatch.setattr(module, "assign_splits", mark_finalization)
    monkeypatch.setattr(module.shutil, "disk_usage", available)
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "INCOMPLETE"
    assert result.completed_groups == 3
    assert len(module.load_records(tmp_path)) == 3
    assert "free-space" in result.reason
    assert not (tmp_path / "splits" / "train.jsonl").exists()


@pytest.mark.parametrize(
    "relative",
    [
        "contracts/models.py",
        "contracts/__init__.py",
        "errors.py",
        "simulation/backend.py",
        "simulation/mujoco/spec_randomization.py",
        "__init__.py",
        "datasets/__init__.py",
        "vision/__init__.py",
        "simulation/__init__.py",
        "simulation/mujoco/__init__.py",
    ],
)
def test_source_fingerprint_covers_runtime_dependencies(relative, monkeypatch):
    from pathlib import Path

    from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig

    module = generator()
    config = DatasetConfig(dataset_id="source-fixture")
    baseline = module._source_evidence(config)
    original = Path.read_bytes
    changed = Path(module.__file__).resolve().parents[2] / relative

    def altered_bytes(path):
        value = original(path)
        return value + b"\n# simulated runtime change\n" if path == changed else value

    monkeypatch.setattr(Path, "read_bytes", altered_bytes)
    modified = module._source_evidence(config)
    assert baseline["source_hash"] != modified["source_hash"]
    assert baseline["source_files"][relative] != modified["source_files"][relative]


@pytest.mark.parametrize("max_bytes", [1, 1024])
def test_tiny_budget_does_not_write_unbudgeted_metadata(cpu_factory, tmp_path, max_bytes):
    module, config, session, _, _ = cpu_factory
    result = module.generate_dataset(
        config.model_copy(update={"max_bytes": max_bytes}), tmp_path, lambda: False
    )
    assert result.status == "INCOMPLETE" and session.captures == 0
    assert result.resources["manifest_persisted"] is False
    assert sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file()) <= max_bytes
    assert not (tmp_path / "manifest.json").exists()


def test_rejection_journal_retains_terminal_metadata_within_budget(
    cpu_factory, tmp_path, monkeypatch
):
    module, config, _, scene, labels = cpu_factory
    session, adapter, _, _ = module._capture_dependencies()
    monkeypatch.setattr(
        module,
        "_capture_dependencies",
        lambda: (session, adapter, lambda cfg, seed: scene(cfg, 0), labels),
    )
    config = config.model_copy(update={"groups": 1000, "max_bytes": 190_000})
    result = module.generate_dataset(config, tmp_path, lambda: False)
    assert result.status == "INCOMPLETE" and result.completed_groups == 1
    assert result.attempts < 5000
    assert sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file()) <= config.max_bytes
    assert json.loads((tmp_path / "manifest.json").read_text())["status"] == "INCOMPLETE"
