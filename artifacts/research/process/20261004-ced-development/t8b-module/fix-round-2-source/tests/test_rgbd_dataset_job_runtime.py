"""Data generation uses its own worker route and cannot claim robot success."""

import pytest

from tests.test_phase11_1_simulation_runtime import _draft
from tests.test_rgbd_runtime_control import _queued_closed_loop_worker, _terminal_artifacts


@pytest.mark.parametrize(
    ("dataset_status", "expected"),
    [
        ("COMPLETE", "SUCCEEDED"),
        ("INCOMPLETE", "FAILED"),
        ("FAILED", "FAILED"),
        ("BLOCKED", "BLOCKED_BY_ENV"),
    ],
)
def test_dataset_job_has_separate_route_and_truthful_terminal(
    tmp_path,
    monkeypatch,
    dataset_status,
    expected,
):
    from cloud_edge_robot_arm.simulation_runtime import dataset_job

    draft = _draft(
        backend="MUJOCO",
        input_mode="RGBD",
        execution_scope="CAPTURE_ONLY",
        job_type="DATASET_GENERATION",
        dataset_config={"dataset_id": "test", "groups": 1},
    )
    repo, job, worker = _queued_closed_loop_worker(tmp_path, draft)
    calls = []

    def generate(draft, directory, *, cancelled):
        calls.append(directory)
        assert not cancelled()
        output = directory / "dataset"
        output.mkdir(parents=True)
        (output / "manifest.json").write_text('{"status":"' + dataset_status + '"}')
        return {
            "job_type": "DATASET_GENERATION",
            "dataset_status": dataset_status,
            "job_completed": dataset_status == "COMPLETE",
            "task_success": False,
            "task_execution": "NOT_RUN",
            "model_calls": 0,
        }

    monkeypatch.setattr(dataset_job, "run_dataset_job", generate)
    worker._run_rgbd = lambda *args, **kwargs: pytest.fail("data job entered visual model route")
    assert worker.poll_once()
    current, result, consistency = _terminal_artifacts(tmp_path, repo, job)
    assert calls == [tmp_path / job.artifact_root]
    assert current.status == expected
    assert result["status"] == expected
    assert result["task_success"] is False
    assert result["task_execution"] == "NOT_RUN"
    assert result["runner"] == "DATASET_GENERATION"
    assert result["model_calls"] == 0
    assert "dataset_manifest" in current.artifact_paths
    assert consistency["consistent"]
