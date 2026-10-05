"""Holdout separation follows source and image evidence, never random seeds."""

from __future__ import annotations

import base64
import importlib
import io
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import SampleRecord, SceneSpec
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def module(name):
    try:
        return importlib.import_module(f"cloud_edge_robot_arm.datasets.rgbd.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"RGB-D {name} is not implemented")


def record(index, *, scene=None, **changes):
    scene = scene or SceneSpec.from_parameters(
        {"target": {"position": [float(index), 0, 0.04]}, "camera": {"fovy": 45}},
        "asset-a",
        index,
    )
    return SampleRecord(
        **{
            "sample_id": f"s-{index}",
            "group_id": scene.group_id,
            "episode_id": f"e-{index}",
            "frame_id": f"f-{index}",
            "scene": scene,
            "observation_metadata": {},
            "labels": {"positive": True},
            "physics_state_hash": "a" * 64,
            "status": "POSITIVE",
            **changes,
        }
    )


def observation(*, offset=0, brightness=0):
    rgb = np.full((48, 64, 3), 90 + brightness, dtype=np.uint8)
    rgb[15:25, 20 + offset : 30 + offset] = [190 + brightness, 25 + brightness, 25 + brightness]
    depth = np.full((48, 64), 2, dtype="<f4")
    depth[15:25, 20 + offset : 30 + offset] = 1
    image = io.BytesIO()
    Image.fromarray(rgb).save(image, format="PNG")
    return RGBDObservation(
        frame_id="test-frame",
        captured_at=datetime(2020, 1, 1, tzinfo=UTC),
        sim_time_s=0,
        width=64,
        height=48,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        intrinsics=(60, 60, 32, 24),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        source="mujoco_camera",
    )


def test_group_split_80_5_5_10():
    records = [record(i) for i in range(100)]
    splits = module("splitter").assign_splits(records, seed=17)
    assert splits.counts == {"train": 80, "calibration": 5, "selection": 5, "test": 10}
    assert len(splits.sample_assignments) == 100
    assert splits == module("splitter").assign_splits(list(reversed(records)), seed=17)


def test_same_scene_different_seed_is_duplicate():
    first = record(0)
    forged = first.scene.model_copy(update={"seed": 1234, "group_id": "forged-group"})
    second = record(1, scene=forged)
    splits = module("splitter").assign_splits([first, second], seed=4)
    assert sum(splits.counts.values()) == 1
    assert splits.sample_assignments[first.sample_id] == splits.sample_assignments[second.sample_id]
    assert splits.duplicates
    assert module("quality").find_duplicate(second, [first]) == first.sample_id


def test_episode_augmentations_keep_split():
    first = record(0)
    variant = first.scene.model_copy(
        update={"scene_parameters": {**first.scene.scene_parameters, "camera": {"fovy": 55}}}
    )
    second = record(1, scene=variant)
    records = [first, second, *[record(i) for i in range(2, 101)]]
    splits = module("splitter").assign_splits(records, seed=3)
    assert splits.counts == {"train": 80, "calibration": 5, "selection": 5, "test": 10}
    assert splits.sample_assignments[first.sample_id] == splits.sample_assignments[second.sample_id]


def test_content_duplicates_cannot_cross_splits():
    records = [record(i) for i in range(101)]
    records[0].content_hash = records[-1].content_hash = "f" * 64
    splits = module("splitter").assign_splits(records, seed=21)
    assert sum(splits.counts.values()) == 100
    assert splits.sample_assignments["s-0"] == splits.sample_assignments["s-100"]


def test_near_duplicate_brightness_change_is_detected_without_collapsing_layouts():
    quality = module("quality")
    first = record(0, perceptual_hash=quality.perceptual_signature(observation()))
    near = record(1, perceptual_hash=quality.perceptual_signature(observation(brightness=4)))
    moved = record(2, perceptual_hash=quality.perceptual_signature(observation(offset=12)))
    assert quality.find_duplicate(near, [first]) == first.sample_id
    assert quality.find_duplicate(moved, [first]) is None
    splits = module("splitter").assign_splits([first, near, moved], seed=0)
    assert sum(splits.counts.values()) == 2
    assert any(item["reason"] == "near_duplicate" for item in splits.duplicates)


def test_duplicate_sample_identity_is_rejected():
    with pytest.raises(ValueError, match="sample"):
        module("splitter").assign_splits([record(0), record(0)], seed=0)


def test_malformed_perceptual_signature_is_rejected():
    with pytest.raises(ValueError, match="signature"):
        module("quality").find_duplicate(record(1, perceptual_hash="junk"), [record(0)])
