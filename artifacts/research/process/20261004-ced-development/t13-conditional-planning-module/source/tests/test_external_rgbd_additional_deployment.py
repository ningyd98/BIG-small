"""新增源完整离线部署门禁与批读取；不连接网络或硬件。"""

import json
import socket
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.external.deployment import (
    DATASETS,
    index_path,
    prepare_plan,
    run_operation,
)
from cloud_edge_robot_arm.datasets.external.index import load_index
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider
from tests.test_external_rgbd_native import bag_fixture, simple_plan


def local_plan(tmp_path):
    folder = tmp_path / "downloads/vins_rgbd_small/public_https/fixture-pinned"
    folder.mkdir(parents=True)
    bag = folder / "Normal.bag"
    bag_fixture(bag)
    plan = simple_plan("vins_rgbd_small", bag)
    plan.update(
        data_root=str(tmp_path),
        source="public_https",
        storage_format="prepared_rgbd",
        source_mode="existing_downloads",
        profile="curated",
        decode_workers=2,
        download_workers=4,
        retries=0,
        budget_bytes=10**9,
        extraction_estimated_bytes=10**7,
        smoke_selection={"expected_rgbd_samples": 1, "expected_groups": 1},
        profile_config={"validation_fraction": 0.2, "batch_size": 1, "preview_groups": 5},
    )
    return plan


def test_registered_manifests_pin_existing_files(tmp_path):
    for dataset in ("industryshapes_real", "microagi01_small", "vins_rgbd_small"):
        assert dataset in DATASETS
        plan = prepare_plan(dataset, "curated", tmp_path)
        assert plan["source_mode"] == "existing_downloads"
        assert plan["storage_format"] == "prepared_rgbd"
        assert all(len(file["sha256"]) == 64 for file in plan["files"])


def test_deploy_is_offline_idempotent_and_keeps_incomplete_sequence(tmp_path, monkeypatch):
    plan = local_plan(tmp_path)

    def no_network(*args, **kwargs):
        raise AssertionError("offline deployment attempted network")

    monkeypatch.setattr(socket, "socket", no_network)
    first = run_operation("deploy", plan, num_workers=0)
    assert first["verified_scope"] == "SELECTED_RGBD_VERIFIED"
    assert first["original_full_target_verified"] is False
    assert first["complete_episodes"] == 0 and first["incomplete_episodes"] == 1
    assert first["annotation_status"] == "UNAVAILABLE"
    rows = load_index(index_path(tmp_path, plan["dataset_id"]))
    assert rows[0]["split"] == "unknown"
    provider = DatasetObservationProvider(rows)
    provider.pause()
    with pytest.raises(RuntimeError, match="paused"):
        provider.next_observation()
    provider.resume()
    observation = provider.next_observation()
    assert observation["timestamp"] == 1000000010
    assert observation["execution_verified"] is False and "annotations" not in observation
    assert run_operation("extract", plan)["status"] == "REUSED"
    assert run_operation("deploy", plan, num_workers=0)["verified_scope"] == first["verified_scope"]


@pytest.mark.parametrize("change", ["missing", "corrupt", "traversal", "symlink"])
def test_download_command_only_verifies_local_source_and_fails_closed(tmp_path, change):
    plan = local_plan(tmp_path)
    source = tmp_path / "downloads/vins_rgbd_small/public_https/fixture-pinned/Normal.bag"
    if change == "missing":
        source.unlink()
    elif change == "corrupt":
        source.write_bytes(b"bad source")
    elif change == "traversal":
        plan["files"][0]["path"] = "../Normal.bag"
    else:
        outside = tmp_path / "outside.bag"
        source.rename(outside)
        source.symlink_to(outside)
    with pytest.raises((ValueError, FileNotFoundError), match="source|digest|escape|symlink"):
        run_operation("download", plan)
    assert not (tmp_path / "raw/vins_rgbd_small/COMPLETE.json").exists()


def test_partial_and_modified_prepared_publication_not_reused(tmp_path):
    plan = local_plan(tmp_path)
    result = run_operation("extract", plan)
    raw = Path(result["raw_path"])
    marker = json.loads((raw / "COMPLETE.json").read_text())
    target = raw / marker["extracted_files"][0]["path"]
    target.write_text("tampered")
    with pytest.raises(ValueError, match="inventory"):
        run_operation("extract", plan)


def test_single_sequence_preview_reports_frames_separately_from_groups(tmp_path):
    plan = local_plan(tmp_path)
    run_operation("extract", plan)
    run_operation("validate", plan)
    result = run_operation("preview", plan)
    assert result["groups"] == 1 and result["frames"] == 1
    assert run_operation("smoke", plan, num_workers=2)["num_workers"] == 2


def test_incomplete_conversion_never_publishes_complete_marker_and_can_retry(tmp_path):
    plan = local_plan(tmp_path)
    plan["smoke_selection"]["expected_rgbd_samples"] = 2
    with pytest.raises(ValueError, match="pair count"):
        run_operation("extract", plan)
    assert not (tmp_path / "raw/vins_rgbd_small").exists()
    # 不修改选择身份：缺失帧不能被再次运行伪造出来。
    with pytest.raises(ValueError, match="pair count"):
        run_operation("extract", plan)


def test_storage_reserve_blocks_before_preparation(tmp_path):
    plan = local_plan(tmp_path)
    plan["minimum_free_bytes"] = 10**18
    assert run_operation("plan", plan)["budget"]["status"] == "BLOCKED_STORAGE"
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        run_operation("extract", plan)
    assert not (tmp_path / "raw").exists()


def test_reused_raw_does_not_reserve_conversion_space_again(tmp_path, monkeypatch):
    from collections import namedtuple

    from cloud_edge_robot_arm.datasets.external import prepared_deployment

    plan = local_plan(tmp_path)
    run_operation("extract", plan)
    plan["minimum_free_bytes"] = 100_000
    disk = namedtuple("Disk", "total used free")
    monkeypatch.setattr(
        prepared_deployment.shutil, "disk_usage", lambda _: disk(500_000, 300_000, 200_000)
    )
    budget = run_operation("plan", plan)["budget"]
    assert budget["status"] == "READY"
    assert budget["estimated_conversion_peak_bytes"] == 0
    assert budget["raw_reusable"] is True
    assert run_operation("deploy", plan)["verified_scope"] == "SELECTED_RGBD_VERIFIED"
    plan["minimum_free_bytes"] = 200_001
    assert run_operation("plan", plan)["budget"]["status"] == "BLOCKED_STORAGE"


def test_reuse_plan_does_not_trust_corrupted_raw_to_skip_space_gate(tmp_path):
    plan = local_plan(tmp_path)
    run_operation("extract", plan)
    raw = tmp_path / "raw/vins_rgbd_small"
    (raw / "samples.jsonl").write_text("corrupt")
    with pytest.raises(ValueError, match="inventory"):
        run_operation("plan", plan)
