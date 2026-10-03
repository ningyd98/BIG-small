"""Dataset production is a bounded artifact job, never a physical task success."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig
from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft

pytest_plugins = ("tests.test_rgbd_dataset_generation",)


def _payload(**changes: Any) -> dict[str, Any]:
    return {
        "backend": "MUJOCO",
        "job_type": "DATASET_GENERATION",
        "input_mode": "RGBD",
        "execution_scope": "CAPTURE_ONLY",
        "scenarios": ["S01_NORMAL_STATIC"],
        "control_modes": ["PCSC"],
        "seeds": [0],
        "dataset_config": {"dataset_id": "runtime-data", "groups": 1},
        **changes,
    }


def test_simulation_job_type_remains_default() -> None:
    payload = _payload()
    del payload["job_type"]
    del payload["dataset_config"]
    assert ExperimentDraft.model_validate(payload).job_type == "SIMULATION"


def test_dataset_config_survives_runtime_manifest_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.simulation_runtime import service

    monkeypatch.setattr(service, "git_sha", lambda: "source-commit")
    monkeypatch.setattr(service, "_source_tree_hash", lambda: "source-tree")
    draft = ExperimentDraft.model_validate(_payload())
    manifest = service.build_manifest(draft, run_count=1)
    restored = ExperimentDraft.model_validate(manifest.normalized_config)
    assert restored.job_type == "DATASET_GENERATION"
    assert restored.dataset_config is not None
    assert restored.dataset_config.dataset_id == "runtime-data"
    assert restored.dataset_config.groups == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"dataset_config": None},
        {"backend": "MOCK"},
        {"backend": "ISAAC_SIM"},
        {"input_mode": "LEGACY_PIPELINE"},
        {"execution_scope": "VISUAL_PLANNING"},
        {"execution_scope": "VISION_CLOSED_LOOP"},
        {"job_type": "SIMULATION"},
        {"run_type": "BATCH"},
        {"seeds": [0, 1]},
        {"repetitions": 2},
        {"dataset_config": {"dataset_id": "runtime-data", "model_path": "/tmp/scene.xml"}},
        {"dataset_config": {"dataset_id": "runtime-data", "output": "/tmp/escape"}},
    ],
)
def test_dataset_job_rejects_mixed_scope_or_unbounded_paths(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ExperimentDraft.model_validate(_payload(**changes))


@pytest.mark.parametrize("case", ["complete", "cancelled", "blocked", "incomplete"])
def test_dataset_helper_preserves_generator_status_without_claiming_task_success(
    cpu_factory: Any, tmp_path: Path, case: str
) -> None:
    from cloud_edge_robot_arm.simulation_runtime.dataset_job import run_dataset_job

    generator, config, session, *_ = cpu_factory
    config = config.model_copy(update={"groups": 1})
    if case == "blocked":
        session.fail_enter = True
    elif case == "incomplete":
        config = config.model_copy(update={"max_bytes": 1})
    draft = ExperimentDraft.model_validate(_payload(dataset_config=config.model_dump(mode="json")))
    run_dir = tmp_path / "job-artifacts"
    result = run_dataset_job(draft, run_dir, cancelled=lambda: case == "cancelled")
    expected_status = {
        "complete": "COMPLETE", "cancelled": "CANCELLED",
        "blocked": "BLOCKED", "incomplete": "INCOMPLETE",
    }[case]
    assert result["job_type"] == "DATASET_GENERATION"
    assert result["dataset_status"] == expected_status
    assert result["job_completed"] is (case == "complete")
    assert result["task_success"] is False
    assert result["task_execution"] == "NOT_RUN"
    assert result["model_calls"] == 0
    assert result["dataset_path"] == "dataset"
    assert result["dataset_manifest"]["status"] == expected_status
    if case == "complete":
        records = generator.load_records(run_dir / "dataset")
        assert len(records) == result["dataset_manifest"]["sample_count"] == 1
        assert (run_dir / "dataset" / "reports" / "quality.json").is_file()
    assert not (tmp_path / "dataset").exists()


def test_dataset_helper_revalidates_bypassed_scope_before_writing(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.simulation_runtime.dataset_job import run_dataset_job

    draft = ExperimentDraft.model_validate(_payload()).model_copy(
        update={"execution_scope": "VISION_CLOSED_LOOP"}
    )
    run_dir = tmp_path / "job"
    with pytest.raises(ValidationError):
        run_dataset_job(draft, run_dir, cancelled=lambda: False)
    assert not run_dir.exists()


@pytest.mark.parametrize("symlink_run", [False, True])
def test_dataset_helper_rejects_symlink_output_escape(tmp_path: Path, symlink_run: bool) -> None:
    from cloud_edge_robot_arm.simulation_runtime.dataset_job import run_dataset_job

    run_dir = tmp_path / "job"
    outside = tmp_path / "outside"
    outside.mkdir()
    if symlink_run:
        run_dir.symlink_to(outside, target_is_directory=True)
    else:
        run_dir.mkdir()
        (run_dir / "dataset").symlink_to(outside, target_is_directory=True)
    draft = ExperimentDraft.model_validate(_payload())
    with pytest.raises(ValueError, match="symlink"):
        run_dataset_job(draft, run_dir, cancelled=lambda: False)
    assert not list(outside.iterdir())


def test_dataset_job_uses_existing_bounded_config() -> None:
    draft = ExperimentDraft.model_validate(_payload())
    assert isinstance(draft.dataset_config, DatasetConfig)
