"""Run bounded offline dataset generation inside a runtime-owned artifact directory."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft


def run_dataset_job(
    draft: ExperimentDraft,
    run_dir: Path,
    *,
    cancelled: Callable[[], bool],
) -> dict[str, Any]:
    """Generate one dataset; the worker maps its terminal status to the job state.

    ``run_dir`` is supplied by the worker, never by the draft. Cancellation is
    forwarded to the existing generator so committed samples remain resumable.
    COMPLETE means data production completed, not that a robot task succeeded.
    """
    from cloud_edge_robot_arm.datasets.rgbd.generator import generate_dataset

    # model_copy can bypass Pydantic validation, including nested configuration.
    draft = ExperimentDraft.model_validate(draft.model_dump(mode="json"))
    if draft.job_type != "DATASET_GENERATION" or draft.dataset_config is None:
        raise ValueError("run_dataset_job requires a DATASET_GENERATION draft")
    output = Path(run_dir).absolute() / "dataset"
    for path in (output, *output.parents):
        if path.is_symlink():
            raise ValueError("symlink dataset job output is forbidden")
    manifest = generate_dataset(draft.dataset_config, output, cancelled)
    return {
        "job_type": "DATASET_GENERATION",
        "evaluation_scope": "CAPTURE_ONLY",
        "dataset_status": manifest.status,
        "dataset_path": "dataset",
        "dataset_manifest": manifest.model_dump(mode="json"),
        "job_completed": manifest.status == "COMPLETE",
        "task_success": False,
        "task_execution": "NOT_RUN",
        "model_calls": 0,
    }
