from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.models import RecoveryResponse
from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
from cloud_edge_robot_arm.simulation_runtime.repository import SimulationJobRepository


def recover_artifacts(
    *, repository: SimulationJobRepository, artifact_root: Path, dry_run: bool = True
) -> RecoveryResponse:
    if dry_run:
        return RecoveryResponse(rerun_started=False)
    return ArtifactRecoveryService(
        repository=repository,
        artifact_root=artifact_root,
    ).recover_interrupted_jobs()
