"""派生记录仍保留来源、未知能力和原生数据，禁止变成合成观察。"""

import json

import numpy as np
import pytest

from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader, read_sample
from cloud_edge_robot_arm.datasets.external.models import DatasetSample


def sample_fields():
    return dict(
        dataset_id="industryshapes_real",
        source_revision="pinned",
        sample_kind="static_multiview_scene",
        source_file="original.png",
        relative_path="data/original.png",
        source_sha256="a" * 64,
        scene_id="000001",
        camera_id="native",
        frame_index=4,
        official_split="test",
        annotations={"instances": [{"obj_id": 1}]},
        depth_scale_m=0.001,
        depth_scale_evidence="source depth_scale=1 mm",
        depth_excluded_values=[65535],
        depth_validity_evidence="conservative saturation exclusion",
    )


def make_record(tmp_path):
    from cloud_edge_robot_arm.datasets.external.prepared import write_observation

    return write_observation(
        tmp_path,
        sample_fields(),
        np.full((2, 3, 3), [240, 20, 3], np.uint8),
        np.array([[0, 1234, 65535], [100, 2500, 4000]], np.uint16),
    )


def test_explicit_depth_exclusion_requires_evidence():
    fields = sample_fields()
    fields["depth_validity_evidence"] = None
    with pytest.raises(ValueError, match="exclusion.*evidence"):
        DatasetSample(
            **fields, rgb=np.ones((1, 1, 3), np.uint8), depth_raw=np.full((1, 1), 65535, np.uint16)
        )


def test_prepared_preserves_uint16_split_unknown_geometry_and_gt_isolation(tmp_path):
    ref = make_record(tmp_path)
    sample = read_sample(ref)
    assert sample.depth_raw.dtype == np.uint16
    assert sample.depth_raw[0, 2] == 65535
    assert not sample.depth_valid_mask[0, 2] and sample.depth_m[0, 2] == 0
    assert sample.depth_m[0, 1] == pytest.approx(1.234)
    assert sample.official_split == "test" and sample.timestamp is None
    assert sample.K_depth is None and not sample.capabilities["camera_geometry"]
    assert sample.annotations["instances"][0]["obj_id"] == 1
    assert "annotations" not in sample.model_input()
    assert next(iter(DatasetLoader([ref], num_workers=0)))["rgb"].shape == (1, 2, 3, 3)


@pytest.mark.parametrize("change", ["record", "image", "frame", "split", "escape", "symlink"])
def test_prepared_rejects_tampering(tmp_path, change):
    ref = make_record(tmp_path)
    record = tmp_path / ref["record_relative_path"]
    envelope = json.loads(record.read_text())
    if change == "record":
        record.write_text(record.read_text() + " ")
    elif change in {"image", "symlink"}:
        target = tmp_path / envelope["images"]["depth"]["path"]
        if change == "image":
            target.write_bytes(b"corrupt")
        else:
            outside = tmp_path.parent / "outside.png"
            outside.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(outside)
    elif change == "frame":
        ref["frame_index"] = 5
    elif change == "split":
        ref["official_split"] = "train"
    else:
        ref["record_relative_path"] = "../outside.json"
    with pytest.raises(
        (ValueError, FileNotFoundError), match="digest|identity|relative|symlink|escape"
    ):
        read_sample(ref)


def test_unknown_depth_unit_keeps_raw_without_metric_depth(tmp_path):
    from cloud_edge_robot_arm.datasets.external.prepared import write_observation

    fields = sample_fields()
    fields.update(dataset_id="vins_rgbd_small", depth_scale_m=None, depth_scale_evidence=None)
    ref = write_observation(
        tmp_path, fields, np.ones((2, 3, 3), np.uint8), np.ones((2, 3), np.uint16)
    )
    assert read_sample(ref).depth_m is None


def test_timestamp_pairs_are_one_to_one_and_report_missing():
    from cloud_edge_robot_arm.datasets.external.prepared import pair_timestamps

    rgb = [{"timestamp_ns": t, "frame_index": i} for i, t in enumerate([100, 200, 300])]
    depth = [{"timestamp_ns": t, "frame_index": i} for i, t in enumerate([102, 302])]
    pairs, report = pair_timestamps(rgb, depth, tolerance_ns=5)
    assert [(a["frame_index"], b["frame_index"]) for a, b in pairs] == [(0, 0), (2, 1)]
    assert report["unpaired_rgb"] == [1] and report["unpaired_depth"] == []
    assert report["max_delta_ns"] == 2
    assert not pair_timestamps(rgb, depth, tolerance_ns=0)[0]


def test_duplicate_or_noninteger_timestamps_are_not_silently_paired():
    from cloud_edge_robot_arm.datasets.external.prepared import pair_timestamps

    with pytest.raises(ValueError, match="timestamp"):
        pair_timestamps(
            [{"timestamp_ns": 100, "frame_index": i} for i in range(2)], [], tolerance_ns=0
        )
