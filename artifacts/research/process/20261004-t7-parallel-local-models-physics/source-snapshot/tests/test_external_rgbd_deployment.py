"""小型离线部署门禁；夹具只用于软件验证，不计真实部署。"""

import json

import numpy as np
import pytest

from cloud_edge_robot_arm.datasets.external.deployment import data_root, prepare_plan, status
from cloud_edge_robot_arm.datasets.external.models import DatasetSample
from cloud_edge_robot_arm.datasets.external.preview import save_preview


def test_data_root_respects_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("BIGSMALL_DATA_ROOT", str(tmp_path))
    assert data_root(None) == tmp_path.resolve()


def test_grasp_plan_requires_all_five_volumes(tmp_path):
    plan = prepare_plan("graspclutter6d", "smoke", tmp_path)
    parts = [f["path"] for f in plan["files"] if f["path"].startswith("scenes.")]
    assert len(parts) == 5
    assert len(plan["revision"]) == 40
    assert plan["budget_bytes"] == 250 * 1024**3
    assert len(plan["smoke_selection"]["scene_ids"]) == 10
    assert plan["network"]["mode"] == "direct"
    assert plan["network"]["hf_endpoint"] is None


def test_robomind_plan_records_actual_budget_block(tmp_path):
    plan = prepare_plan("robomind", "smoke", tmp_path)
    assert plan["dataset_budget_bytes"] == 10 * 1024**3
    assert sum(f["size"] for f in plan["files"]) > plan["dataset_budget_bytes"]
    assert plan["target_subset"].endswith("h5_franka_1rgb")


def test_status_does_not_claim_unstarted_data(tmp_path):
    result = status("graspclutter6d", tmp_path)
    assert result["verified_scope"] == "NOT_VERIFIED"
    assert result["download_status"] == "NOT_STARTED"


def test_preview_preserves_raw_depth_and_marks_unknown_units(tmp_path):
    sample = DatasetSample(
        dataset_id="synthetic_fixture",
        source_revision="a" * 40,
        sample_kind="trajectory_observation",
        source_file="test.h5",
        relative_path="test.h5",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split="train",
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[0, 1250], [65000, 1000]], dtype=np.uint16),
    )
    report = save_preview(sample, tmp_path)
    assert report["depth_unit"] == "raw_unit_unknown"
    raw = np.load(tmp_path / "depth_raw.npy", allow_pickle=False)
    assert raw.dtype == np.uint16 and raw.max() == 65000
    assert not (tmp_path / "pointcloud.npy").exists()
    assert json.loads((tmp_path / "metadata.json").read_text())["timestamp"] is None


def test_unknown_dataset_is_error(tmp_path):
    with pytest.raises(ValueError):
        prepare_plan("random", "smoke", tmp_path)


def test_smoke_rejects_synthetic_index_as_real_data(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.datasets.external import deployment

    sample = DatasetSample(
        dataset_id="robomind",
        source_revision="a" * 40,
        sample_kind="trajectory_observation",
        source_file="test.h5",
        relative_path="test.h5",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split="train",
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.ones((2, 2), dtype=np.uint16),
        metadata={"sample_provenance": "synthetic_fixture"},
    )
    path = deployment.index_path(tmp_path, "robomind")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dataset_id": "robomind"}) + "\n")
    monkeypatch.setattr(deployment, "read_sample", lambda _: sample)
    monkeypatch.setattr(deployment, "_verify_raw_marker", lambda _: {})
    with pytest.raises(ValueError, match="synthetic_fixture"):
        deployment.smoke_dataset(
            {
                "dataset_id": "robomind",
                "data_root": str(tmp_path),
                "profile_config": {"batch_size": 1},
            }
        )
    assert not (tmp_path / "reports/robomind/smoke-workers-0.json").exists()


def test_discovery_preserves_file_quarantine_even_when_all_invalid(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.datasets.external import deployment, robomind

    raw = tmp_path / "raw/robomind"
    raw.mkdir(parents=True)
    (raw / "COMPLETE.json").write_text("{}")

    def fail_discovery(root, revision, metadata):
        metadata["quarantine"] = [{"source_file": "broken.h5", "reason": "empty depth"}]
        raise ValueError("no valid trajectories")

    monkeypatch.setattr(robomind, "discover_robomind_samples", fail_discovery)
    monkeypatch.setattr(deployment, "_verify_raw_marker", lambda _: {})
    with pytest.raises(ValueError):
        deployment.discover(
            {"dataset_id": "robomind", "data_root": str(tmp_path), "revision": "a" * 40}
        )
    report = json.loads((tmp_path / "reports/robomind/discovery-quarantine.json").read_text())
    assert report["quarantine"][0]["source_file"] == "broken.h5"


def test_half_deployed_directory_cannot_be_indexed(tmp_path):
    from cloud_edge_robot_arm.datasets.external.deployment import discover

    (tmp_path / "raw/graspclutter6d/scenes").mkdir(parents=True)
    with pytest.raises(ValueError, match="marker"):
        discover({"dataset_id": "graspclutter6d", "data_root": str(tmp_path)})


def test_wrong_raw_revision_cannot_be_relabelled_by_plan(tmp_path):
    from cloud_edge_robot_arm.datasets.external.deployment import discover

    raw = tmp_path / "raw/robomind"
    raw.mkdir(parents=True)
    (raw / "COMPLETE.json").write_text(json.dumps({"identity": {"revision": "a" * 40}}))
    with pytest.raises(ValueError, match="identity"):
        discover(
            {
                "dataset_id": "robomind",
                "data_root": str(tmp_path),
                "revision": "b" * 40,
                "source": "modelscope",
                "files": [],
            }
        )


def test_interrupted_bundle_assembly_rolls_forward_without_reextract(monkeypatch, tmp_path):
    import hashlib
    import io
    import tarfile
    from pathlib import Path

    from cloud_edge_robot_arm.datasets.external.deployment import extract_dataset

    directory = tmp_path / "downloads/robomind/modelscope" / ("a" * 40)
    directory.mkdir(parents=True)
    archive = directory / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in ("data/a.txt", "data/b.txt"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    plan = {
        "data_root": str(tmp_path),
        "dataset_id": "robomind",
        "source": "modelscope",
        "revision": "a" * 40,
        "minimum_free_bytes": 0,
        "sample_provenance": "synthetic_fixture",
        "files": [
            {
                "path": archive.name,
                "size": archive.stat().st_size,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ],
    }
    original = Path.replace
    moved = []

    def interrupt(path, target):
        if path.name == "b.txt" and ".bundles" in str(path):
            raise OSError("synthetic interruption during assembly")
        result = original(path, target)
        if path.name == "a.txt":
            moved.append(str(target))
        return result

    monkeypatch.setattr(Path, "replace", interrupt)
    with pytest.raises(OSError, match="interruption"):
        extract_dataset(plan)
    assert len(moved) == 1
    assert not (tmp_path / "raw/robomind/COMPLETE.json").exists()
    monkeypatch.setattr(Path, "replace", original)
    result = extract_dataset(plan)
    assert result["status"] == "COMPLETE"
    assert (tmp_path / "raw/robomind/data/a.txt").read_bytes() == b"x"
    assert (tmp_path / "raw/robomind/data/b.txt").read_bytes() == b"x"
    assert extract_dataset(plan)["status"] == "REUSED"


def test_oracle_preview_is_separate_from_original_rgb(tmp_path):
    from PIL import Image

    mask_path = tmp_path / "visible.png"
    Image.fromarray(np.array([[255, 0], [0, 0]], dtype=np.uint8)).save(mask_path)
    sample = DatasetSample(
        dataset_id="synthetic_fixture",
        source_revision="a" * 40,
        sample_kind="static_multiview_scene",
        source_file="test.png",
        relative_path="test.png",
        source_sha256="b" * 64,
        frame_index=0,
        camera_id="top",
        official_split="train",
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.ones((2, 2), dtype=np.uint16),
        annotations={
            "instances": [
                {
                    "instance_id": 0,
                    "obj_id": 1,
                    "visible_mask": {"available": True, "path": str(mask_path)},
                }
            ]
        },
    )
    report = save_preview(sample, tmp_path / "preview")
    assert report["oracle_overlay"]
    assert (tmp_path / "preview/oracle_overlay.png").is_file()
    assert np.array(Image.open(tmp_path / "preview/rgb.png")).max() == 0


def test_complete_task_coverage_excludes_partial_second_task():
    from cloud_edge_robot_arm.datasets.external.deployment import trajectory_completeness

    rows = [
        {
            "dataset_id": "robomind",
            "task_id": task,
            "episode_id": "same_episode",
            "camera_id": "top",
            "frame_index": frame,
            "episode_length": 2,
        }
        for task, frames in (("task_a", (0, 1)), ("task_b", (0,)))
        for frame in frames
    ]
    summary = trajectory_completeness(rows)
    assert summary["complete_episodes"] == 1
    assert summary["complete_tasks"] == 1
    assert summary["incomplete_episodes"] == 1


def test_doctor_never_uses_system_network_or_unverified_mirror(monkeypatch, tmp_path):
    import httpx

    from cloud_edge_robot_arm.datasets.external import deployment, network

    observed = []
    original_client = httpx.Client

    def serve(request):
        observed.append(request.url.host)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("unbound system HTTP"))
    monkeypatch.setattr(network, "create_direct_transport", lambda _: httpx.MockTransport(serve))

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    result = deployment.doctor(tmp_path)
    assert observed == ["modelscope.cn"]
    assert result["source_checks"]["huggingface"]["status"] == "BLOCKED_NETWORK"
    assert result["source_checks"]["modelscope"]["network_mode"] == "direct"
