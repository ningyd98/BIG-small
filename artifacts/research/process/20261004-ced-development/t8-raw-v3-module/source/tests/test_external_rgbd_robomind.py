"""synthetic_fixture：Franka 编码帧、状态语义与 worker 隔离读取。"""

from __future__ import annotations

import hashlib
import io
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import h5py
import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.external.robomind import (
    discover_robomind_samples,
    read_robomind_sample,
)


def _png(array: np.ndarray) -> np.ndarray:
    stream = io.BytesIO()
    Image.fromarray(array).save(stream, format="PNG")
    return np.frombuffer(stream.getvalue(), dtype=np.uint8)


def _trajectory(root: Path, *, raw: bool = False, episode: str = "1014_144602") -> Path:
    file = root / "h5_franka_1rgb" / "bread_in_basket" / "success_episodes"
    file = file / "train" / episode / "data" / "trajectory.hdf5"
    file.parent.mkdir(parents=True)
    rgb = np.array([[[255, 0, 0], [0, 0, 255]]], dtype=np.uint8)
    depth = np.array([[0, 65000]], dtype=np.uint16)
    with h5py.File(file, "w") as h5:
        h5.attrs["sim"] = False
        h5.attrs["compress"] = not raw
        h5.attrs["synthetic_fixture"] = True
        for kind, image in [("rgb_images", rgb), ("depth_images", depth)]:
            name = f"observations/{kind}/camera_top"
            if raw:
                data = image[..., ::-1] if kind == "rgb_images" else image
                h5.create_dataset(name, data=np.stack([data, data]))
            else:
                dataset = h5.create_dataset(name, (2,), dtype=h5py.vlen_dtype(np.uint8))
                dataset[0], dataset[1] = _png(image), _png(image)
        h5.create_dataset("master/joint_position", data=np.ones((2, 8)))
        h5.create_dataset("puppet/joint_position", data=np.full((2, 8), 2.0))
        h5.create_dataset("puppet/end_effector", data=np.zeros((2, 6)))
    return file


def _metadata() -> dict:
    return {"sample_provenance": "synthetic_fixture"}


def _worker_read(ref: dict) -> tuple:
    sample = read_robomind_sample(ref)
    return sample.rgb.shape, str(sample.depth_raw.dtype), sample.frame_index


def test_discovery_indexes_complete_episode_and_preserves_split(tmp_path):
    file = _trajectory(tmp_path)
    refs = discover_robomind_samples(tmp_path, "a" * 40, _metadata())
    assert len(refs) == 2
    assert {ref["episode_id"] for ref in refs} == {"1014_144602"}
    assert refs[0]["official_split"] == "train"
    assert refs[0]["task_id"] == "bread_in_basket"
    assert refs[0]["source_file"] == str(file.resolve())
    assert len(refs[0]["source_sha256"]) == 64
    assert refs[0]["metadata"]["sample_provenance"] == "synthetic_fixture"


@pytest.mark.parametrize("raw", [False, True])
def test_bgr_only_raw_arrays_swapped_once_and_sixteen_bit_depth(tmp_path, raw):
    _trajectory(tmp_path, raw=raw)
    refs = discover_robomind_samples(tmp_path, "a" * 40, _metadata())
    sample = read_robomind_sample(refs[0])
    assert sample.rgb.tolist() == [[[255, 0, 0], [0, 0, 255]]]
    assert sample.depth_raw.dtype == np.uint16
    assert sample.depth_raw.tolist() == [[0, 65000]]
    assert sample.depth_valid_mask.tolist() == [[False, True]]
    assert sample.depth_m is None


def test_units_require_explicit_source_evidence_not_maximum_heuristic(tmp_path):
    _trajectory(tmp_path)
    metadata = {
        **_metadata(),
        "source_depth_evidence": {
            "unit": "mm",
            "scale_m": 0.001,
            "evidence": "synthetic_fixture locked schema",
        },
    }
    ref = discover_robomind_samples(tmp_path, "a" * 40, metadata)[0]
    sample = read_robomind_sample(ref)
    assert sample.depth_m.dtype == np.float32
    np.testing.assert_allclose(sample.depth_m, [[0, 65]])
    assert sample.depth_scale_evidence == "synthetic_fixture locked schema"
    assert not sample.capabilities["camera_geometry"]


def test_unknown_units_calibration_time_and_action_remain_unknown(tmp_path):
    _trajectory(tmp_path)
    sample = read_robomind_sample(discover_robomind_samples(tmp_path, "a" * 40)[0])
    assert sample.K_rgb is None and sample.K_depth is None
    assert sample.rgb_depth_aligned is None
    assert sample.temporal_alignment is None
    assert sample.timestamp is None and sample.time_basis == "unknown"
    assert sample.transforms == {} and sample.action is None
    assert sample.robot_state["master"]["joint_position"][0] == 1
    assert sample.robot_state["puppet"]["joint_position"][0] == 2
    assert sample.robot_state["puppet"]["joint_position_semantics"][7] != "rotational_joint"
    assert "robot_state" not in sample.model_input()
    assert sample.metadata["sample_provenance"] == "synthetic_fixture"


@pytest.mark.parametrize("change", ["empty_depth", "length_mismatch", "state_mismatch", "sim"])
def test_bad_trajectory_is_quarantined_and_never_silently_valid(tmp_path, change):
    file = _trajectory(tmp_path)
    with h5py.File(file, "a") as h5:
        if change == "empty_depth":
            del h5["observations/depth_images/camera_top"]
        elif change == "length_mismatch":
            del h5["observations/depth_images/camera_top"]
            h5.create_dataset("observations/depth_images/camera_top", data=np.ones((1, 1, 2)))
        elif change == "state_mismatch":
            del h5["puppet/joint_position"]
            h5.create_dataset("puppet/joint_position", data=np.ones((1, 8)))
        else:
            h5.attrs["sim"] = True
    metadata = _metadata()
    with pytest.raises(ValueError, match="valid.*trajectory|trajectory.*valid"):
        discover_robomind_samples(tmp_path, "a" * 40, metadata)
    assert len(metadata["quarantine"]) == 1


def test_discovery_retains_valid_episode_when_another_is_invalid(tmp_path):
    _trajectory(tmp_path)
    bad = _trajectory(tmp_path, episode="broken")
    bad.write_bytes(b"not hdf5")
    metadata = _metadata()
    refs = discover_robomind_samples(tmp_path, "a" * 40, metadata)
    assert len(refs) == 2 and len(metadata["quarantine"]) == 1


@pytest.mark.parametrize("bad_frame", [b"corrupt", None])
def test_broken_or_all_zero_depth_frame_is_not_a_valid_rgbd_sample(tmp_path, bad_frame):
    file = _trajectory(tmp_path)
    with h5py.File(file, "a") as h5:
        h5["observations/depth_images/camera_top"][0] = (
            np.frombuffer(bad_frame, dtype=np.uint8)
            if bad_frame
            else _png(np.zeros((1, 2), dtype=np.uint16))
        )
    ref = discover_robomind_samples(tmp_path, "a" * 40)[0]
    with pytest.raises(ValueError, match="decode|valid depth"):
        read_robomind_sample(ref)


def test_source_revision_and_checksum_mismatch_fail(tmp_path):
    _trajectory(tmp_path)
    with pytest.raises(ValueError, match="revision"):
        discover_robomind_samples(tmp_path, "main")
    ref = discover_robomind_samples(tmp_path, "a" * 40)[0]
    ref["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="checksum"):
        read_robomind_sample(ref)


def test_dataset_missing_is_an_error_without_generated_replacement(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError), match="trajectory|dataset"):
        discover_robomind_samples(tmp_path, "a" * 40)


def test_cpu_multiple_workers_open_hdf5_independently(tmp_path):
    _trajectory(tmp_path)
    refs = discover_robomind_samples(tmp_path, "a" * 40, _metadata())
    with ProcessPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(_worker_read, refs)) == [
            ((1, 2, 3), "uint16", 0),
            ((1, 2, 3), "uint16", 1),
        ]


@pytest.mark.parametrize("storage", ["external", "virtual"])
@pytest.mark.parametrize(
    "field",
    [
        "observations/rgb_images/camera_top",
        "observations/depth_images/camera_top",
        "master/joint_position",
        "puppet/joint_position",
        "puppet/end_effector",
        "observations/timestamp",
    ],
)
def test_hdf5_payload_cannot_escape_the_hashed_source_file(tmp_path, storage, field):
    file = _trajectory(tmp_path, raw=True)
    metadata = _metadata()
    if field == "observations/timestamp":
        metadata.update(
            {
                "timestamp_path": field,
                "timestamp_time_basis": "fixture clock",
                "timestamp_evidence": "synthetic_fixture",
            }
        )
        with h5py.File(file, "a") as h5:
            h5.create_dataset(field, data=np.array([1.0, 2.0]))
    ref = discover_robomind_samples(tmp_path, "a" * 40, metadata)[0]
    with h5py.File(file, "a") as h5:
        values = h5[field][:]
        del h5[field]
        if storage == "external":
            raw_payload = tmp_path / "external_payload.bin"
            dataset = h5.create_dataset(
                field,
                shape=values.shape,
                dtype=values.dtype,
                external=[(str(raw_payload), 0, values.nbytes)],
            )
            dataset[:] = values
        else:
            source_file = tmp_path / "external_payload.h5"
            with h5py.File(source_file, "w") as payload:
                payload.create_dataset("values", data=values)
            layout = h5py.VirtualLayout(shape=values.shape, dtype=values.dtype)
            layout[:] = h5py.VirtualSource(str(source_file), "values", shape=values.shape)
            h5.create_virtual_dataset(field, layout)
    # 外部数据的摘要未进入源HDF5摘要，故单靠wrapper摘要仍不能绑定观察。
    ref["source_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="external.*storage|virtual.*dataset"):
        read_robomind_sample(ref)


@pytest.mark.parametrize("storage", ["external", "virtual"])
def test_discovery_quarantines_unbound_hdf5_storage(tmp_path, storage):
    file = _trajectory(tmp_path, raw=True)
    with h5py.File(file, "a") as h5:
        name = "puppet/joint_position"
        values = h5[name][:]
        del h5[name]
        if storage == "external":
            h5.create_dataset(
                name,
                shape=values.shape,
                dtype=values.dtype,
                external=[(str(tmp_path / "state.bin"), 0, values.nbytes)],
            )
        else:
            layout = h5py.VirtualLayout(shape=values.shape, dtype=values.dtype)
            layout[:] = h5py.VirtualSource(str(tmp_path / "state.h5"), "values", shape=values.shape)
            h5.create_virtual_dataset(name, layout)
    metadata = _metadata()
    with pytest.raises(ValueError, match="no valid real Franka trajectory"):
        discover_robomind_samples(tmp_path, "a" * 40, metadata)
    assert len(metadata["quarantine"]) == 1
    assert storage in metadata["quarantine"][0]["reason"]
