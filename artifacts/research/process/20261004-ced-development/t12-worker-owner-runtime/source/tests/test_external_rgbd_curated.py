"""synthetic_fixture：精选导出契约与安全边界，不代替真实源验收。"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

MODULE = "cloud_edge_robot_arm.datasets.external.fiftyone_curated"
REVISION = "f6d801ce94dbeaf1a40c19006b741cba7675a101"


def reader() -> Any:
    return importlib.import_module(MODULE)


def encoded(array: np.ndarray) -> dict[str, Any]:
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=array.dtype.hasobject)
    return {
        "$binary": {
            "base64": base64.b64encode(zlib.compress(stream.getvalue())).decode(),
            "subType": "00",
        }
    }


def fixture(root: Path, *, evidence: bool = True) -> dict[str, Any]:
    # 保持真实 schema：Depth Heatmap、裁剪 mask、重复 object instance、export clock。
    (root / "data").mkdir()
    rgb = np.zeros((3, 4, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    Image.fromarray(rgb).save(root / "data/000001.png")
    depth = np.array(
        [[0, 1000, 1100, 1000], [1000, 1000, np.nan, 1000], [1000, 1000, 1000, 1000]],
        dtype=np.float32,
    )
    detections = [
        {
            "obj_id": 60,
            "instance_idx": i,
            "label": "obj_060",
            "bounding_box": [0.25, 0.0, 0.5, 2 / 3],
            "mask": encoded(np.array([[True, False], [False, True]])),
        }
        for i in range(2)
    ]
    record = {
        "_id": {"$oid": "6a0f715680e82071ad51ad52"},
        "_media_type": "image",
        "filepath": "data/000001.png",
        "scene_id": "000000",
        "camera": "realsense_d415",
        "viewpoint": 0,
        "metadata": {"width": 4, "height": 3, "num_channels": 3},
        "depth": {"map": encoded(depth), "range": [1000, 1100]},
        "detections": {"detections": detections},
        "grasp_lines": {
            "polylines": [{"label": "grasp_obj_060", "points": [[[0.1, 0.1], [0.2, 0.2]]]}]
        },
        "created_at": {"$date": "2026-05-21T20:55:50.286Z"},
    }
    (root / "samples.json").write_text(
        json.dumps(
            {
                "samples": [
                    record,
                    {"_media_type": "3d", "scene_id": "000000", "filepath": "data/000001.fo3d"},
                ]
            }
        )
    )
    (root / "metadata.json").write_text(
        json.dumps({"camera_intrinsics": {}, "created_at": {"$date": "2026-05-21T20:52:25.475Z"}})
    )
    options: dict[str, Any] = {"sample_provenance": "synthetic_fixture"}
    if evidence:
        options["source_depth_evidence"] = "pinned-source-README: depth map values are millimetres"
    return {"record": record, "options": options}


def save_records(root: Path, records: list[dict[str, Any]]) -> None:
    (root / "samples.json").write_text(json.dumps({"samples": records}))


def prepared(root: Path, *, evidence: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = fixture(root, evidence=evidence)
    result = reader().materialize_curated_records(root, REVISION, ["000000"], data["options"])
    return result, reader().discover_curated_grasp_samples(root, REVISION, ["000000"])


def test_curated_reader_module_exists() -> None:
    assert importlib.util.find_spec(MODULE) is not None


def test_materialization_selects_only_image_records_and_binds_original_blob(tmp_path: Path) -> None:
    result, refs = prepared(tmp_path)
    assert result["samples"] == 1 and result["scenes"] == ["000000"]
    assert len(result["records"]) == len(refs) == 1
    assert all(not Path(path).is_absolute() for path in result["files"])
    envelope = json.loads((tmp_path / result["records"][0]).read_text())
    original = json.loads((tmp_path / "samples.json").read_text())["samples"][0]
    assert envelope["record"] == original
    assert set(envelope["source_hashes"]) == {"samples.json", "metadata.json"}
    assert refs[0]["dataset_id"] == "graspclutter6d_curated"
    assert refs[0]["camera_id"] == "realsense_d415"
    assert refs[0]["frame_index"] == 0 and refs[0]["official_split"] is None


def test_depth_preserves_float_millimetres_scales_once_and_separates_gt(tmp_path: Path) -> None:
    _, refs = prepared(tmp_path)
    sample = reader().read_curated_grasp_sample(refs[0])
    assert sample.depth_raw.dtype == np.float32
    assert sample.depth_raw[0, 1] == 1000 and sample.depth_m[0, 1] == pytest.approx(1)
    assert not sample.depth_valid_mask[0, 0] and not sample.depth_valid_mask[1, 2]
    assert sample.rgb[0, 0].tolist() == [255, 0, 0]
    assert sample.timestamp is None and sample.time_basis == "static_multiview_index"
    assert sample.K_rgb is None and sample.K_depth is None
    assert sample.action is None and sample.robot_state is None
    assert (
        not sample.capabilities["camera_geometry"]
        and not sample.capabilities["robot_base_geometry"]
    )
    assert "annotations" not in sample.model_input() and "instances" not in sample.model_input()
    assert [(v["instance_id"], v["obj_id"]) for v in sample.annotations["instances"]] == [
        (0, 60),
        (1, 60),
    ]
    assert sample.metadata["export_created_at"] == {"$date": "2026-05-21T20:55:50.286Z"}
    assert sample.metadata["sample_provenance"] == "synthetic_fixture"
    assert sample.annotations["grasp_annotation_kind"] == "exported_2d_visualization"


def test_missing_unit_evidence_keeps_raw_depth_and_unknown_units(tmp_path: Path) -> None:
    _, refs = prepared(tmp_path, evidence=False)
    sample = reader().read_curated_grasp_sample(refs[0])
    assert sample.depth_m is None and sample.depth_scale_m is None
    assert sample.capabilities["rgbd_decodable"] and not sample.capabilities["depth_metric"]


def test_bbox_cropped_mask_is_placed_at_exact_pixel_bounds(tmp_path: Path) -> None:
    _, refs = prepared(tmp_path)
    sample = reader().read_curated_grasp_sample(refs[0])
    mask = sample.annotations["instances"][0]["visible_mask"]
    assert mask["available"]
    with Image.open(mask["path"]) as image:
        pixels = np.asarray(image)
    assert pixels.shape == (3, 4)
    assert np.argwhere(pixels > 0).tolist() == [[0, 1], [1, 2]]


@pytest.mark.parametrize(
    "bbox",
    [
        [0.25, 0, 0.25, 2 / 3],
        [-0.25, 0, 0.5, 2 / 3],
        [0.75, 0, 0.5, 2 / 3],
        [0.3, 0, 0.5, 2 / 3],
        [float("nan"), 0, 0.5, 2 / 3],
    ],
)
def test_invalid_or_inexact_mask_bounds_are_flagged_without_fake_geometry(
    tmp_path: Path, bbox: list[float]
) -> None:
    data = fixture(tmp_path)
    data["record"]["detections"]["detections"][0]["bounding_box"] = bbox
    save_records(tmp_path, [data["record"]])
    reader().materialize_curated_records(tmp_path, REVISION, ["000000"], data["options"])
    sample = reader().read_curated_grasp_sample(
        reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])[0]
    )
    assert not sample.annotations["instances"][0]["visible_mask"]["available"]
    assert sample.annotations["issues"]


@pytest.mark.parametrize(
    "relative", ["../outside.png", "/tmp/evil.png", "data/../../outside.png", "data\\000001.png"]
)
def test_source_image_paths_cannot_escape_or_use_platform_ambiguous_separator(
    tmp_path: Path, relative: str
) -> None:
    data = fixture(tmp_path)
    data["record"]["filepath"] = relative
    save_records(tmp_path, [data["record"]])
    with pytest.raises(ValueError, match="path"):
        reader().materialize_curated_records(tmp_path, REVISION, ["000000"])


@pytest.mark.parametrize("name", ["samples.json", "metadata.json", "data/000001.png", "record"])
def test_source_rgb_and_record_digest_mutations_are_rejected(tmp_path: Path, name: str) -> None:
    result, refs = prepared(tmp_path)
    relative = result["records"][0] if name == "record" else name
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest"):
        reader().read_curated_grasp_sample(refs[0])


def test_wrong_revision_and_missing_selected_scene_are_rejected(tmp_path: Path) -> None:
    prepared(tmp_path)
    with pytest.raises(ValueError, match="revision"):
        reader().discover_curated_grasp_samples(tmp_path, "0" * 40, ["000000"])
    with pytest.raises(FileNotFoundError, match="scene"):
        reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000009"])


@pytest.mark.parametrize(
    "array",
    [
        np.array([[object()]], dtype=object),
        np.ones((2, 2, 2), dtype=np.float32),
        np.ones((2, 2), dtype=np.complex64),
    ],
)
def test_pickle_complex_and_non_image_depth_are_rejected(tmp_path: Path, array: np.ndarray) -> None:
    data = fixture(tmp_path)
    data["record"]["depth"]["map"] = encoded(array)
    save_records(tmp_path, [data["record"]])
    reader().materialize_curated_records(tmp_path, REVISION, ["000000"])
    ref = reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])[0]
    with pytest.raises(ValueError, match="array|dtype|pickle"):
        reader().read_curated_grasp_sample(ref)


@pytest.mark.parametrize("kind", ["bomb", "truncated", "trailing", "invalid_base64"])
def test_binary_decode_is_bounded_and_checks_complete_compressed_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = fixture(tmp_path)
    raw = zlib.compress(b"x" * 100000)
    if kind == "truncated":
        raw = raw[:-1]
    elif kind == "trailing":
        raw += b"trailing"
    binary = {
        "$binary": {
            "base64": "!invalid!" if kind == "invalid_base64" else base64.b64encode(raw).decode(),
            "subType": "00",
        }
    }
    data["record"]["depth"]["map"] = binary
    save_records(tmp_path, [data["record"]])
    reader().materialize_curated_records(tmp_path, REVISION, ["000000"])
    ref = reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])[0]
    if kind == "bomb":
        monkeypatch.setattr(reader(), "MAX_ARRAY_BYTES", 1024)
    with pytest.raises(ValueError, match="binary|compressed|array"):
        reader().read_curated_grasp_sample(ref)


def test_different_depth_shape_does_not_fabricate_alignment(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data["record"]["depth"]["map"] = encoded(np.ones((2, 2), dtype=np.float32))
    save_records(tmp_path, [data["record"]])
    reader().materialize_curated_records(
        tmp_path,
        REVISION,
        ["000000"],
        {**data["options"], "source_alignment_evidence": "source grid declaration"},
    )
    sample = reader().read_curated_grasp_sample(
        reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])[0]
    )
    assert sample.rgb_depth_aligned is False and not sample.capabilities["rgb_depth_alignment"]


def test_symlink_to_external_rgb_is_rejected(tmp_path: Path) -> None:
    fixture(tmp_path)
    rgb = tmp_path / "data/000001.png"
    rgb.unlink()
    rgb.symlink_to(tmp_path.parent / "outside.png")
    with pytest.raises(ValueError, match="path"):
        reader().materialize_curated_records(tmp_path, REVISION, ["000000"])


def test_duplicate_camera_view_records_are_rejected(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    save_records(tmp_path, [data["record"], dict(data["record"])])
    with pytest.raises(ValueError, match="duplicate"):
        reader().materialize_curated_records(tmp_path, REVISION, ["000000"])


def test_discovery_reuses_source_digest_until_stat_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared(tmp_path)
    called: list[str] = []
    original = reader()._digest_uncached

    def tracked(path: Path) -> str:
        called.append(path.name)
        return original(path)

    monkeypatch.setattr(reader(), "_digest_uncached", tracked)
    reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])
    reader().discover_curated_grasp_samples(tmp_path, REVISION, ["000000"])
    assert "samples.json" not in called and "metadata.json" not in called


def test_materialization_requires_all_selected_scenes_and_source_metadata(tmp_path: Path) -> None:
    fixture(tmp_path)
    with pytest.raises(FileNotFoundError, match="scene"):
        reader().materialize_curated_records(tmp_path, REVISION, ["000001"])
    (tmp_path / "metadata.json").unlink()
    with pytest.raises(FileNotFoundError):
        reader().materialize_curated_records(tmp_path, REVISION, ["000000"])


@pytest.mark.parametrize("missing", ["record", "rgb", "mask", "source"])
def test_read_reference_requires_complete_immutable_digest_inventory(
    tmp_path: Path, missing: str
) -> None:
    result, refs = prepared(tmp_path)
    ref = refs[0]
    key = {
        "record": result["records"][0],
        "rgb": "data/000001.png",
        "mask": next(path for path in result["files"] if path.endswith(".png")),
        "source": "samples.json",
    }[missing]
    del ref["source_hashes"][key]
    with pytest.raises(ValueError, match="digest inventory"):
        reader().read_curated_grasp_sample(ref)


@pytest.mark.parametrize("kind", ["mask", "json"])
def test_materialization_preserves_partial_and_existing_output_before_storage_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = fixture(tmp_path)
    if kind == "json":
        data["record"]["detections"] = {"detections": []}
        save_records(tmp_path, [data["record"]])
    result = reader().materialize_curated_records(tmp_path, REVISION, ["000000"], data["options"])
    relative = next(
        path for path in result["files"] if path.endswith(".png" if kind == "mask" else ".json")
    )
    existing = tmp_path / relative
    original = existing.read_bytes()
    partial = tmp_path / (relative + ".partial")
    partial.write_bytes(b"existing interrupted write")
    monkeypatch.setattr(reader().shutil, "disk_usage", lambda path: SimpleNamespace(free=1000))
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        reader().materialize_curated_records(
            tmp_path, REVISION, ["000000"], data["options"], minimum_free_bytes=1000
        )
    assert existing.read_bytes() == original
    assert partial.read_bytes() == b"existing interrupted write"


def test_materialization_checks_storage_again_during_chunked_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    capacity = iter([10**9, 0])
    monkeypatch.setattr(
        reader().shutil, "disk_usage", lambda path: SimpleNamespace(free=next(capacity))
    )
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        reader().materialize_curated_records(
            tmp_path, REVISION, ["000000"], data["options"], minimum_free_bytes=1000
        )
    assert not list((tmp_path / ".curated-records").glob("*.png"))
    assert len(list((tmp_path / ".curated-records").glob("*.partial"))) == 1


def test_materialization_reserve_parameter_requires_nonnegative_integer(tmp_path: Path) -> None:
    fixture(tmp_path)
    with pytest.raises(ValueError, match="minimum_free_bytes"):
        reader().materialize_curated_records(tmp_path, REVISION, ["000000"], minimum_free_bytes=-1)
