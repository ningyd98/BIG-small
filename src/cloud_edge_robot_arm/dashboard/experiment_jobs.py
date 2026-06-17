from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.dashboard.models import (
    ExperimentCreateRequest,
    ExperimentJobRecord,
    ExperimentJobStatus,
    ExperimentKind,
    HardwareClaim,
)


class ExperimentJobManager:
    def __init__(self, *, artifact_root: Path, writes_enabled: bool = False) -> None:
        self.artifact_root = artifact_root
        self.writes_enabled = writes_enabled
        self._jobs: dict[str, ExperimentJobRecord] = {}

    def list_jobs(self) -> list[ExperimentJobRecord]:
        return list(self._jobs.values())

    def get(self, experiment_id: str) -> ExperimentJobRecord | None:
        return self._jobs.get(experiment_id)

    def start(self, request: ExperimentCreateRequest) -> ExperimentJobRecord:
        extras = set((request.model_extra or {}).keys())
        if extras:
            raise ValueError("forbidden experiment field")
        if not self.writes_enabled:
            raise PermissionError("dashboard experiment writes are disabled")
        now = datetime.now(UTC)
        experiment_id = _experiment_id(request)
        dry_run_kinds = {
            ExperimentKind.SYNTHETIC_DRY_RUN,
            ExperimentKind.MOVEIT_RUNTIME_DRY_RUN,
        }
        claim = (
            HardwareClaim.PLANNING_ONLY
            if request.kind in dry_run_kinds
            else HardwareClaim.SIMULATION_ONLY
        )
        job = ExperimentJobRecord(
            experiment_id=experiment_id,
            kind=request.kind,
            status=ExperimentJobStatus.SUCCEEDED,
            scenario_id=request.scenario_id,
            seed=request.seed,
            control_mode=request.control_mode,
            hardware_claim=claim,
            created_at=now,
            updated_at=now,
        )
        path = self.artifact_root / "dashboard_jobs" / f"{experiment_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": job.status,
            "experiment_id": experiment_id,
            "kind": request.kind,
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "control_mode": request.control_mode,
            "hardware_claim": claim,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
        }
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        evidence_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        job = job.model_copy(update={"evidence_id": evidence_id})
        self._jobs[experiment_id] = job
        return job

    def cancel(self, experiment_id: str) -> ExperimentJobRecord:
        job = self._jobs.get(experiment_id)
        if job is None:
            raise KeyError(experiment_id)
        updated = job.model_copy(
            update={
                "status": ExperimentJobStatus.CANCELLED,
                "updated_at": datetime.now(UTC),
            }
        )
        self._jobs[experiment_id] = updated
        return updated


def _experiment_id(request: ExperimentCreateRequest) -> str:
    raw = f"{request.kind}:{request.scenario_id}:{request.seed}:{request.control_mode}"
    return "exp-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
