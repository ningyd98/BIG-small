"""精选文件源发布与独立规模门禁，软件夹具不作为真实数据。"""

import hashlib
import json
from pathlib import Path

import pytest


def fixture_plan(root: Path):
    body = b"synthetic_fixture"
    source = root / "downloads/graspclutter6d_curated/modelscope" / ("a" * 40) / "samples.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    return {
        "dataset_id": "graspclutter6d_curated",
        "source": "modelscope",
        "revision": "a" * 40,
        "data_root": str(root),
        "minimum_free_bytes": 0,
        "storage_format": "fiftyone_curated",
        "variant": "synthetic_fixture",
        "files": [
            {"path": "samples.json", "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        ],
        "smoke_selection": {"scene_ids": ["000001"], "expected_rgbd_samples": 4},
    }


def test_curated_flat_files_are_atomically_published_with_derived_inventory(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.datasets.external import curated_deployment, fiftyone_curated

    plan = fixture_plan(tmp_path)

    def records(root, revision, scene_ids, metadata=None, minimum_free_bytes=0):
        path = root / ".curated-records/frame.json"
        path.parent.mkdir()
        path.write_text("{}")
        assert not (tmp_path / "raw/graspclutter6d_curated").exists()
        return {"files": [path.relative_to(root).as_posix()], "samples": 4}

    monkeypatch.setattr(fiftyone_curated, "materialize_curated_records", records)
    result = curated_deployment.extract_curated_dataset(plan)
    assert result["status"] == "COMPLETE"
    raw = tmp_path / "raw/graspclutter6d_curated"
    marker = json.loads((raw / "COMPLETE.json").read_text())
    assert {entry["path"] for entry in marker["extracted_files"]} == {
        "samples.json",
        ".curated-records/frame.json",
    }
    assert curated_deployment.extract_curated_dataset(plan)["status"] == "REUSED"


def test_curated_bad_source_digest_never_publishes_raw(tmp_path):
    from cloud_edge_robot_arm.datasets.external.curated_deployment import extract_curated_dataset

    plan = fixture_plan(tmp_path)
    plan["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="verified download"):
        extract_curated_dataset(plan)
    assert not (tmp_path / "raw/graspclutter6d_curated/COMPLETE.json").exists()


def test_curated_failed_materialization_retains_unpublished_stage(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.datasets.external import curated_deployment, fiftyone_curated

    plan = fixture_plan(tmp_path)
    monkeypatch.setattr(
        fiftyone_curated,
        "materialize_curated_records",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("missing selected RGB")),
    )
    with pytest.raises(ValueError, match="missing selected RGB"):
        curated_deployment.extract_curated_dataset(plan)
    assert not (tmp_path / "raw/graspclutter6d_curated").exists()
    assert list((tmp_path / "raw").glob("*.partial"))


def test_curated_gate_requires_exact_selected_count_and_only_curated_scope():
    from cloud_edge_robot_arm.datasets.external.curated_deployment import curated_scope_ready

    plan = {
        "smoke_selection": {"scene_ids": ["000001", "000002"], "expected_rgbd_samples": 8},
        "profile_config": {"preview_groups": 2},
    }
    current = {
        "samples": 8,
        "groups": 2,
        "quarantined": 0,
        "split_audit": {"valid": True},
        "preview_report": {"groups": 2},
        "annotation_status": "CURATED_2D_ANNOTATIONS_AVAILABLE",
    }
    assert curated_scope_ready(plan, current)
    assert not curated_scope_ready(plan, {**current, "samples": 7})
    assert not curated_scope_ready(plan, {**current, "quarantined": 1})
    assert not curated_scope_ready(plan, {**current, "annotation_status": "PARTIAL"})


def test_validation_preserves_curated_mask_failures(monkeypatch, tmp_path):
    """损坏 GT 不妨碍读取 RGB-D，但必须阻止精选标注验收。"""
    import numpy as np

    from cloud_edge_robot_arm.datasets.external import deployment
    from cloud_edge_robot_arm.datasets.external.models import DatasetSample

    ref = {
        "dataset_id": "graspclutter6d_curated",
        "source_revision": "a" * 40,
        "scene_id": "000001",
        "camera_id": "top",
        "frame_index": 0,
        "official_split": None,
    }
    sample = DatasetSample(
        dataset_id="graspclutter6d_curated",
        source_revision="a" * 40,
        sample_kind="static_multiview_scene",
        source_file="synthetic_fixture.png",
        relative_path="synthetic_fixture.png",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split=None,
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.ones((2, 2), dtype=np.float32),
        annotations={
            "instances": [{"visible_mask": {"available": False}}],
            "issues": ["instance 0: crop dimensions differ"],
        },
    )
    monkeypatch.setattr(deployment, "discover", lambda _: [ref])
    monkeypatch.setattr(deployment, "read_sample", lambda _: sample)
    result = deployment.validate_dataset(
        {
            "dataset_id": "graspclutter6d_curated",
            "data_root": str(tmp_path),
            "profile_config": {"validation_fraction": 0.2},
        }
    )
    assert "instance 0: crop dimensions differ" in result["rows"][0]["quality"]["annotation_issues"]


def test_curated_reuse_identity_binds_depth_interpretation(tmp_path):
    from cloud_edge_robot_arm.datasets.external.deployment import _plan_identity

    plan = fixture_plan(tmp_path)
    assert _plan_identity(plan) != _plan_identity(
        {**plan, "reader_metadata": {"source_depth_evidence": "pinned millimetre evidence"}}
    )
