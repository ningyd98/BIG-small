"""T17a dataset endpoints reuse runtime authorization and committed artifacts."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

pytest_plugins = ("tests.test_rgbd_dataset_generation",)


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path))
    return TestClient(create_app(PlanningPipeline(planner=MockPlannerAdapter())))


def test_read_only_user_cannot_start_job(monkeypatch, tmp_path):
    response = client(monkeypatch, tmp_path).post("/api/v1/rgbd-datasets/jobs", json={
        "config_id": "SMOKE", "groups": 1, "seed": 1, "width": 320, "height": 240,
    })
    assert response.status_code == 403


@pytest.mark.parametrize("extra", [{"output": "/tmp/escape"}, {"model_path": "secret"},
                                  {"config_id": "../../file"}, {"groups": 10001}])
def test_dataset_create_rejects_arbitrary_paths_and_unbounded_groups(monkeypatch, tmp_path, extra):
    response = client(monkeypatch, tmp_path).post("/api/v1/rgbd-datasets/jobs", json={
        "config_id": "SMOKE", "groups": 1, "seed": 1, "width": 320, "height": 240, **extra,
    }, headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"})
    assert response.status_code == 422


def bind_dataset(monkeypatch, tmp_path, cpu_factory):
    from cloud_edge_robot_arm.cloud.api import rgbd_datasets
    generator, config, *_ = cpu_factory
    config = config.model_copy(update={"groups": 1})
    root = tmp_path / "run-1" / "dataset"
    generator.generate_dataset(config, root, lambda: False)
    job = SimpleNamespace(job_id="job-1", run_id="run-1", artifact_root="run-1",
        draft={"job_type": "DATASET_GENERATION", "dataset_config": config.model_dump(mode="json")},
        status="SUCCEEDED", cancel_requested=False, error_code="", error_message="")

    def lookup(value):
        if value not in {"run-1", "job-1"}:
            raise KeyError(value)
        return job

    repository = SimpleNamespace(get_job=lookup, get_job_by_run_id=lookup)
    service = SimpleNamespace(artifact_root=tmp_path,
                              runtime=SimpleNamespace(repository=repository))
    monkeypatch.setattr(rgbd_datasets, "_service", lambda _request: service)
    return root, job


def test_dataset_progress_comes_from_published_index(monkeypatch, tmp_path, cpu_factory):
    root, _job = bind_dataset(monkeypatch, tmp_path, cpu_factory)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["sample_count"] = 999
    (root / "manifest.json").write_text(json.dumps(manifest))
    response = client(monkeypatch, tmp_path).get("/api/v1/rgbd-datasets/jobs/job-1")
    assert response.status_code == 200
    result = response.json()
    assert result["published_groups"] == result["published_samples"] == 1
    assert result["task_success"] is False
    assert result["model_calls"] == 0
    assert len(result["sample_ids"]) == 1


def test_dataset_api_denies_path_traversal_and_cross_dataset_access(monkeypatch, tmp_path,
                                                                  cpu_factory):
    root, _job = bind_dataset(monkeypatch, tmp_path, cpu_factory)
    browser = client(monkeypatch, tmp_path)
    job = browser.get("/api/v1/rgbd-datasets/jobs/job-1").json()
    sample = job["sample_ids"][0]
    assert browser.get(f"/api/v1/rgbd-datasets/other/samples/{sample}").status_code == 404
    assert browser.get("/api/v1/rgbd-datasets/run-1/samples/other").status_code == 404
    response = browser.get(f"/api/v1/rgbd-datasets/run-1/samples/{sample}")
    assert response.status_code == 200
    assert response.json()["execution_verified"] is False
    assert response.json()["rgb_data_url"].startswith("data:image/png;base64,")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "episodes").rename(root / "saved-episodes")
    (root / "episodes").symlink_to(outside, target_is_directory=True)
    assert browser.get("/api/v1/rgbd-datasets/jobs/job-1").status_code == 409
