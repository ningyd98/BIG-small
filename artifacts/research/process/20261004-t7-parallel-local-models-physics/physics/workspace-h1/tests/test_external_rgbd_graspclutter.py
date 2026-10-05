"""synthetic_fixture：验证 BOP 读取边界，不代替真实数据验收。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.external.graspclutter import (
    discover_grasp_samples,
    read_grasp_sample,
)
from cloud_edge_robot_arm.datasets.external.models import backproject_depth

REVISION = "973a567efa2f8047e5a40c9113a672e8215bcc1b"


def fixture_scene(root: Path, *, image_id: int = 1, scale: float | None = 1.0) -> Path:
    """手工构造毫米位姿和原位深深度的 synthetic_fixture。"""
    scene = root / "scenes" / "000005"
    for folder in ["rgb", "depth", "label", "mask", "visible_mask"]:
        (scene / folder).mkdir(parents=True, exist_ok=True)
    rgb = np.zeros((3, 4, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    Image.fromarray(rgb).save(scene / "rgb" / f"{image_id:06d}.png")
    depth = np.full((3, 4), 1000, dtype=np.uint16)
    depth[0, 0] = 0
    depth[0, 1] = 60000
    Image.fromarray(depth).save(scene / "depth" / f"{image_id:06d}.png")
    Image.fromarray(np.full((3, 4), 69, dtype=np.uint8)).save(
        scene / "label" / f"{image_id:06d}.png"
    )
    camera = {
        "cam_K": [100, 0, 2, 0, 100, 1, 0, 0, 1],
        "cam_R_w2c": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "cam_t_w2c": [0, 0, 200],
    }
    if scale is not None:
        camera["depth_scale"] = scale
    (scene / "scene_camera.json").write_text(json.dumps({str(image_id): camera}))
    pose = {
        "obj_id": 69,
        "cam_R_m2c": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "cam_t_m2c": [100, 200, 800],
    }
    (scene / "scene_gt.json").write_text(json.dumps({str(image_id): [pose, dict(pose)]}))
    (scene / "scene_gt_info.json").write_text(
        json.dumps({str(image_id): [{"bbox_visib": [0, 0, 2, 2]}, {"visib_fract": 0.5}]})
    )
    for instance_id in range(2):
        mask = np.zeros((3, 4), dtype=np.uint8)
        mask[:, instance_id : instance_id + 1] = 255
        for folder in ["mask", "visible_mask"]:
            Image.fromarray(mask).save(scene / folder / f"{image_id:06d}_{instance_id:06d}.png")
    return scene


def refs(root: Path, *, splits: dict | None = None) -> list[dict]:
    return discover_grasp_samples(
        root,
        REVISION,
        {"train": ["000005"], "test": []} if splits is None else splits,
        ["000005"],
    )


def test_discovery_preserves_official_split_camera_and_view_index(tmp_path: Path) -> None:
    # 若把52编号当时序或错置相机，则该测试失败。
    fixture_scene(tmp_path, image_id=4, scale=0.1)
    fixture_scene(tmp_path, image_id=5)
    found = refs(tmp_path)
    assert [(r["image_id"], r["frame_index"], r["camera_id"]) for r in found] == [
        (4, 0, "zivid"),
        (5, 1, "realsense-d415"),
    ]
    assert all(r["official_split"] == "train" and r["protocol"] == "grasp" for r in found)


@pytest.mark.parametrize(("image_id", "scale", "want"), [(1, 1.0, 1.0), (4, 0.1, 0.1)])
def test_depth_preserves_uint16_and_applies_scale_once(
    tmp_path: Path, image_id: int, scale: float, want: float
) -> None:
    fixture_scene(tmp_path, image_id=image_id, scale=scale)
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.depth_raw.dtype == np.uint16
    assert sample.depth_raw[0, 1] == 60000
    assert sample.depth_m.dtype == np.float32
    assert sample.depth_m[1, 1] == pytest.approx(want)
    assert not sample.depth_valid_mask[0, 0]
    assert sample.rgb[0, 0].tolist() == [255, 0, 0]


def test_camera_geometry_has_source_evidence_and_correct_units(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.depth_semantics == "optical_z"
    assert sample.capabilities["camera_geometry"]
    assert sample.capabilities["rgb_depth_alignment"]
    assert sample.transforms["world_to_camera"]["from_frame"] == "dataset_world"
    assert sample.transforms["world_to_camera"]["to_frame"] == "camera"
    assert sample.transforms["world_to_camera"]["matrix"][2][3] == pytest.approx(0.2)
    points = backproject_depth(sample)
    assert np.any(np.all(np.isclose(points, [-0.01, 0.0, 1.0]), axis=1))
    assert not sample.capabilities["robot_base_geometry"]
    assert sample.robot_state is None and sample.action is None and sample.timestamp is None
    assert sample.time_basis == "static_multiview_index"


def test_repeated_object_instances_and_both_mask_channels_are_retained(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    sample = read_grasp_sample(refs(tmp_path)[0])
    instances = sample.annotations["instances"]
    assert [(i["instance_id"], i["obj_id"]) for i in instances] == [(0, 69), (1, 69)]
    assert instances[0]["model_to_camera"]["matrix"][0][3] == pytest.approx(0.1)
    assert instances[0]["visible_mask"]["available"]
    assert instances[0]["amodal_mask"]["available"]
    assert sample.annotations["semantic_label"].shape == (3, 4)
    assert "annotations" not in sample.model_input()
    assert "instances" not in sample.model_input()


def test_upstream_mask_visib_directory_is_supported(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    (scene / "visible_mask").rename(scene / "mask_visib")
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert "mask_visib" in sample.annotations["instances"][0]["visible_mask"]["path"]


def test_missing_depth_scale_preserves_readable_rgbd_without_metric_geometry(
    tmp_path: Path,
) -> None:
    fixture_scene(tmp_path, scale=None)
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.capabilities["rgbd_decodable"]
    assert sample.depth_m is None
    assert not sample.capabilities["camera_geometry"]
    with pytest.raises(ValueError, match="verified units"):
        backproject_depth(sample)


def test_missing_camera_intrinsics_does_not_fabricate_calibration(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    value = json.loads((scene / "scene_camera.json").read_text())
    value["1"].pop("cam_K")
    (scene / "scene_camera.json").write_text(json.dumps(value))
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.K_rgb is None and sample.K_depth is None
    assert sample.rgb_depth_aligned is None
    assert not sample.capabilities["camera_geometry"]


def test_different_rgb_depth_size_disables_alignment(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    Image.fromarray(np.ones((2, 2), dtype=np.uint16)).save(scene / "depth" / "000001.png")
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.rgb_depth_aligned is False
    assert sample.K_rgb is not None
    assert sample.K_depth is None
    assert sample.capabilities["rgbd_decodable"]
    assert not sample.capabilities["camera_geometry"]
    with pytest.raises(ValueError, match="depth camera intrinsics"):
        backproject_depth(sample)
    with pytest.raises(ValueError, match="depth camera intrinsics"):
        backproject_depth(sample, with_rgb=True)


@pytest.mark.parametrize("scale", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_depth_scale_is_rejected(tmp_path: Path, scale: float) -> None:
    fixture_scene(tmp_path, scale=scale)
    with pytest.raises(ValueError, match="depth scale"):
        read_grasp_sample(refs(tmp_path)[0])


def test_wrong_rotation_is_rejected(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    value = json.loads((scene / "scene_camera.json").read_text())
    value["1"]["cam_R_w2c"] = [-1, 0, 0, 0, 1, 0, 0, 0, 1]
    (scene / "scene_camera.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="right-handed"):
        read_grasp_sample(refs(tmp_path)[0])


def test_missing_depth_and_missing_dataset_are_explicit_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        refs(tmp_path)
    scene = fixture_scene(tmp_path)
    (scene / "depth" / "000001.png").unlink()
    with pytest.raises(FileNotFoundError):
        refs(tmp_path)


def test_official_cross_split_overlap_is_reported(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    with pytest.raises(ValueError, match="more than one"):
        refs(tmp_path, splits={"train": ["000005"], "test": ["000005"]})


def test_source_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    ref = refs(tmp_path)[0]
    Image.fromarray(np.ones((3, 4, 3), dtype=np.uint8)).save(scene / "rgb" / "000001.png")
    with pytest.raises(ValueError, match="digest"):
        read_grasp_sample(ref)


def test_scene_path_escape_is_rejected(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    with pytest.raises(ValueError, match="scene"):
        discover_grasp_samples(tmp_path, REVISION, {}, ["../000005"])


def test_npz_annotations_are_lazy_and_missing_dependencies_are_reported(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    labels = tmp_path / "grasp_label"
    labels.mkdir()
    np.savez(
        labels / "obj_000069_labels.npz",
        points=np.zeros((1, 3), dtype=np.float32),
        offsets=np.zeros((1, 300, 12, 4, 3), dtype=np.float32),
        scores=np.zeros((1, 300, 12, 4), dtype=np.float32),
    )
    sample = read_grasp_sample(refs(tmp_path)[0])
    annotation = sample.annotations["grasp_labels"]["69"]
    assert annotation["available"]
    assert annotation["arrays"]["points"]["shape"] == [1, 3]
    assert "values" not in annotation["arrays"]["offsets"]
    assert not sample.annotations["collision_labels"]["available"]
    assert sample.metadata["annotation_issues"]


def test_object_dtype_npz_is_never_deserialized(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    labels = tmp_path / "grasp_label"
    labels.mkdir()
    np.savez(labels / "obj_000069_labels.npz", points=np.array([{"unsafe": 1}], dtype=object))
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert not sample.annotations["grasp_labels"]["69"]["available"]
    assert "object" in sample.annotations["grasp_labels"]["69"]["error"]


def test_all_zero_depth_is_readable_but_not_a_valid_rgbd_sample(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    Image.fromarray(np.zeros((3, 4), dtype=np.uint16)).save(scene / "depth" / "000001.png")
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert not sample.capabilities["rgbd_decodable"]
    assert not sample.depth_valid_mask.any()


def test_descriptor_cannot_pair_image_with_another_camera_metadata(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    ref = refs(tmp_path)[0]
    ref["image_id"] = 4
    with pytest.raises(ValueError, match="identifier"):
        read_grasp_sample(ref)


def test_collision_grid_must_match_instance_object_grasp_grid(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    (tmp_path / "grasp_label").mkdir()
    (tmp_path / "collision_label").mkdir()
    np.savez(
        tmp_path / "grasp_label" / "obj_000069_labels.npz",
        points=np.zeros((1, 3), dtype=np.float32),
        offsets=np.zeros((1, 300, 12, 4, 3), dtype=np.float32),
        scores=np.zeros((1, 300, 12, 4), dtype=np.float32),
    )
    np.savez(
        tmp_path / "collision_label" / "000005.npz",
        arr_0=np.zeros((2, 300, 12, 4), dtype=bool),
        arr_1=np.zeros((1, 300, 12, 4), dtype=bool),
    )
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert not sample.annotations["collision_labels"]["available"]
    assert "grid" in sample.annotations["collision_labels"]["error"]


def test_collision_labels_reject_numeric_nonboolean_arrays(tmp_path: Path) -> None:
    fixture_scene(tmp_path)
    (tmp_path / "collision_label").mkdir()
    np.savez(
        tmp_path / "collision_label" / "000005.npz",
        arr_0=np.zeros((1, 300, 12, 4), dtype=np.float32),
        arr_1=np.zeros((1, 300, 12, 4), dtype=np.float32),
    )
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert not sample.annotations["collision_labels"]["available"]
    assert "boolean" in sample.annotations["collision_labels"]["error"]


def test_absent_camera_metadata_remains_readable_without_geometry(tmp_path: Path) -> None:
    scene = fixture_scene(tmp_path)
    (scene / "scene_camera.json").unlink()
    sample = read_grasp_sample(refs(tmp_path)[0])
    assert sample.capabilities["rgbd_decodable"]
    assert sample.depth_m is None and sample.K_depth is None
    assert sample.transforms == {}
