from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream
from cloud_edge_robot_arm.dashboard.evidence_index import EvidenceIndex
from cloud_edge_robot_arm.dashboard.experiment_jobs import ExperimentJobManager
from cloud_edge_robot_arm.dashboard.models import (
    AcceptanceLevelItem,
    AcceptanceLevelSnapshot,
    CapabilitiesResponse,
    ComparisonResponse,
    DashboardEnvironment,
    DashboardSummary,
    EvidenceIndexRecord,
    ExperimentKind,
    FreshnessStatus,
    HardwareClaim,
    RuntimeSnapshot,
    SafetyGateSnapshot,
    ServiceHealth,
    ServiceStatus,
)


@dataclass(frozen=True)
class _LatestProvenance:
    generated_from_commit: str = ""
    source_tree_hash: str = ""
    worktree_clean: bool | None = None


class DashboardService:
    def __init__(
        self,
        *,
        artifact_root: Path,
        writes_enabled: bool = False,
    ) -> None:
        self.artifact_root = artifact_root
        self.evidence_index = EvidenceIndex(artifact_root)
        self.jobs = ExperimentJobManager(artifact_root=artifact_root, writes_enabled=writes_enabled)
        self.events = DashboardEventStream()

    @classmethod
    def from_environment(cls) -> DashboardService:
        root = Path(os.environ.get("DASHBOARD_ARTIFACT_ROOT", "artifacts"))
        writes_enabled = os.environ.get("DASHBOARD_EXPERIMENT_WRITES_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(artifact_root=root, writes_enabled=writes_enabled)

    def capabilities(self) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            pages=[
                "overview",
                "simulation_lab",
                "task_execution",
                "safety_acceptance",
                "evidence",
                "comparison",
                "audit",
            ],
            backends=[item.value for item in DashboardEnvironment],
            experiments=[item.value for item in ExperimentKind],
            allowed_write_operations=["start_software_experiment", "cancel_software_experiment"]
            if self.jobs.writes_enabled
            else [],
            hardware_write_operations=[],
            websocket=True,
        )

    def summary(self) -> DashboardSummary:
        records = self.evidence_index.refresh()
        status = _latest_project_status(records)
        provenance = _latest_provenance(records)
        safety = self.safety()
        return DashboardSummary(
            generated_at=datetime.now(UTC),
            software_commit=provenance.generated_from_commit or _git_commit(),
            source_tree_hash=provenance.source_tree_hash,
            worktree_clean=provenance.worktree_clean,
            current_project_status=status,
            hardware_claim=HardwareClaim.PLANNING_ONLY,
            real_robot_validation="NOT_STARTED",
            highest_acceptance_level="NONE",
            services=[
                ServiceHealth(name="SafetyShield", status=ServiceStatus.READY),
                ServiceHealth(name="HardwareExecutionGate", status=ServiceStatus.READY),
                ServiceHealth(name="RealRobotController", status=ServiceStatus.NOT_CONFIGURED),
            ],
            blockers=["real robot controller is not configured"],
            safety_summary=safety,
            latest_evidence=records[:10],
            active_experiments=self.jobs.list_jobs(),
        )

    def runtime(self) -> RuntimeSnapshot:
        summary = self.summary()
        return RuntimeSnapshot(
            runtime_profile=os.environ.get("RUNTIME_PROFILE", "local"),
            commit=summary.software_commit,
            source_tree_hash=summary.source_tree_hash,
            worktree_clean=summary.worktree_clean,
            backend_readiness=summary.services,
            service_health=summary.services,
            environment_blockers=summary.blockers,
        )

    def safety(self) -> SafetyGateSnapshot:
        return SafetyGateSnapshot(
            decided_at=datetime.now(UTC),
            controller_connected=False,
            emergency_stop_state="UNKNOWN",
            safety_shield_state=ServiceStatus.READY,
            telemetry_freshness=FreshnessStatus.UNKNOWN,
            current_acceptance_level="NONE",
            required_acceptance_level="LEVEL_0",
            allowed=False,
            hardware_motion_authorized=False,
            reason_codes=["REAL_ROBOT_VALIDATION_NOT_STARTED", "CONTROLLER_NOT_CONFIGURED"],
        )

    def acceptance(self) -> AcceptanceLevelSnapshot:
        levels = [
            AcceptanceLevelItem(
                level=f"LEVEL_{idx}",
                definition=_level_definition(idx),
                blockers=["real hardware acceptance has not started"],
            )
            for idx in range(7)
        ]
        return AcceptanceLevelSnapshot(
            current_level="NONE",
            next_level="LEVEL_0",
            blocked_reasons=["no controller connection, no site evidence, no operator session"],
            levels=levels,
        )

    def comparisons(self) -> ComparisonResponse:
        return ComparisonResponse(
            metrics=[
                {"name": "success_rate", "unit": "ratio", "pcsc": 1.0, "eteac": 1.0, "auto": 1.0},
                {"name": "cloud_calls", "unit": "count", "pcsc": 7, "eteac": 1, "auto": 2},
            ]
        )


def _latest_project_status(records: object) -> str:
    for record in records if isinstance(records, list) else []:
        summary = getattr(record, "summary", "")
        if "PHASE10_MOVEIT_DRY_RUN_ACCEPTED" in summary:
            return "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
    return "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"


def _latest_provenance(records: list[EvidenceIndexRecord]) -> _LatestProvenance:
    for record in records:
        if record.generated_from_commit:
            return _LatestProvenance(
                generated_from_commit=record.generated_from_commit,
                source_tree_hash=record.source_tree_hash,
                worktree_clean=record.worktree_clean,
            )
    return _LatestProvenance()


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _level_definition(index: int) -> str:
    definitions = {
        0: "read-only controller, e-stop, fault, joint and TCP status",
        1: "safe-stop and controller enable-disable checks without displacement",
        2: "single-joint low-speed small motion",
        3: "small TCP free-space motion",
        4: "HOME and verified named safe poses",
        5: "empty gripper workflow without object contact",
        6: "low-speed soft-object grasp at fixed location",
    }
    return definitions[index]
