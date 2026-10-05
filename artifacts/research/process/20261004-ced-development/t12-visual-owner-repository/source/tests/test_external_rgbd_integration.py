"""synthetic_fixture：索引、CPU批读取和离线来源边界，不替代真实下载验收。"""

import numpy as np
import pytest

from cloud_edge_robot_arm.datasets.external.index import audit_splits, build_index, load_index
from cloud_edge_robot_arm.datasets.external.loaders import collate_samples, time_windows
from cloud_edge_robot_arm.datasets.external.models import DatasetSample
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider


def ref(group="e1", frame=0, split="train", digest="b" * 64):
    return {
        "dataset_id": "synthetic_fixture",
        "source_revision": "a" * 40,
        "episode_id": group,
        "frame_index": frame,
        "camera_id": "top",
        "official_split": split,
        "source_file": "/unused/fixture.h5",
        "source_sha256": digest,
        "sample_kind": "trajectory_observation",
    }


def item(height=2, timestamp=None):
    return DatasetSample(
        dataset_id="synthetic_fixture",
        source_revision="a" * 40,
        sample_kind="trajectory_observation",
        source_file="fixture.h5",
        relative_path="fixture.h5",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split="train",
        rgb=np.zeros((height, 3, 3), dtype=np.uint8),
        depth_raw=np.ones((height, 3), dtype=np.uint16),
        timestamp=timestamp,
        annotations={"oracle": 42},
    )


def test_index_preserves_official_split_and_groups(tmp_path):
    refs = [ref("e1", i) for i in range(3)] + [ref("e2", 0, "val", "c" * 64)]
    path = tmp_path / "index.jsonl"
    build_index(refs, path, validation_fraction=0.5)
    rows = load_index(path)
    assert len({r["split"] for r in rows if r["episode_id"] == "e1"}) == 1
    assert rows[-1]["official_split"] == "val" and rows[-1]["split"] == "val"


def test_original_scene_split_conflict_is_reported():
    report = audit_splits([ref(split="train"), ref(frame=1, split="test")])
    assert not report["valid"]
    assert report["group_conflicts"]


def test_cross_split_content_duplicates_reported():
    rows = [ref("e1", split="train"), ref("e2", split="test")]
    assert audit_splits(rows)["content_conflicts"]


def test_time_windows_do_not_cross_episode_camera_or_split():
    rows = [ref("e1", i) for i in range(3)] + [ref("e2", i) for i in range(3)]
    windows = time_windows(rows, length=2)
    assert len(windows) == 4
    assert all(len({r["episode_id"] for r in w}) == 1 for w in windows)


def test_collate_heterogeneous_sizes_and_nullable_fields():
    batch = collate_samples([item(), item(3)])
    assert isinstance(batch["rgb"], list)
    assert batch["depth_m"] == [None, None]
    assert "annotations" not in batch
    homogeneous = collate_samples([item(), item()])
    assert homogeneous["rgb"].shape == (2, 2, 3, 3)


def test_provider_offline_only_pause_seek_clock_and_gt_separate():
    samples = [item(timestamp=None), item(timestamp="original-time")]
    provider = DatasetObservationProvider([ref(), ref(frame=1)], reader=lambda _: samples.pop(0))
    first = provider.next_observation()
    assert first["timestamp"] is None and first["source"] == "dataset_replay"
    assert "oracle" not in first and "annotations" not in first
    provider.pause()
    with pytest.raises(RuntimeError, match="paused"):
        provider.next_observation()
    provider.seek(1)
    provider.resume()
    assert provider.next_observation()["timestamp"] == "original-time"
    assert provider.oracle_annotations()["oracle"] == 42
    with pytest.raises(ValueError, match="offline"):
        DatasetObservationProvider([ref()], mode="hardware")


def test_missing_index_is_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_index(tmp_path / "missing.jsonl")


def test_same_episode_name_in_two_tasks_does_not_merge():
    rows = [
        {**ref("same", frame), "task_id": task, "source_file": f"/{task}.h5"}
        for task in ("task_a", "task_b")
        for frame in range(3)
    ]
    windows = time_windows(rows, length=2)
    assert len(windows) == 4
    assert all(len({row["task_id"] for row in window}) == 1 for window in windows)


def test_cpu_loader_zero_and_two_workers_read_same_encoded_hdf5(tmp_path):
    import h5py

    from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader
    from cloud_edge_robot_arm.datasets.external.robomind import discover_robomind_samples

    path = tmp_path / "h5_franka_1rgb/task/success_episodes/train/e1/data/trajectory.hdf5"
    path.parent.mkdir(parents=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["sim"] = False
        h5.attrs["synthetic_fixture"] = True
        h5.create_dataset(
            "observations/rgb_images/camera_top", data=np.zeros((2, 2, 3, 3), dtype=np.uint8)
        )
        h5.create_dataset(
            "observations/depth_images/camera_top", data=np.ones((2, 2, 3), dtype=np.uint16)
        )
        for name, width in (
            ("master/joint_position", 8),
            ("puppet/joint_position", 8),
            ("puppet/end_effector", 6),
        ):
            h5.create_dataset(name, data=np.zeros((2, width)))
    rows = discover_robomind_samples(tmp_path, "a" * 40)
    serial = next(iter(DatasetLoader(rows, batch_size=2, num_workers=0)))
    parallel = next(iter(DatasetLoader(rows, batch_size=2, num_workers=2)))
    np.testing.assert_array_equal(serial["rgb"], parallel["rgb"])
    assert parallel["rgb"].shape == (2, 2, 3, 3)
    assert parallel["depth_raw"].dtype == np.uint16
