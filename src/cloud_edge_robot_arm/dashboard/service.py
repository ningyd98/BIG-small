from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    EvidenceStatus,
    ExperimentKind,
    FreshnessStatus,
    HardwareClaim,
    RuntimeSnapshot,
    SafetyGateSnapshot,
    SafetyReviewNoteRequest,
    SafetyReviewNoteResponse,
    ServiceHealth,
    ServiceStatus,
    UserRole,
)
from cloud_edge_robot_arm.dashboard.redaction import redact
from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
from cloud_edge_robot_arm.real_robot.gate import HardwareExecutionGate, HardwareGateInput


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
        self.events = DashboardEventStream()
        self.jobs = ExperimentJobManager(
            artifact_root=artifact_root,
            writes_enabled=writes_enabled,
            event_stream=self.events,
        )

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
        services = _service_health_from_safety(safety)
        hardware_claim = _highest_hardware_claim(records)
        return DashboardSummary(
            generated_at=datetime.now(UTC),
            software_commit=provenance.generated_from_commit or _git_commit(),
            source_tree_hash=provenance.source_tree_hash,
            worktree_clean=provenance.worktree_clean,
            current_project_status=status,
            hardware_claim=hardware_claim,
            real_robot_validation="NOT_STARTED",
            highest_acceptance_level="NONE",
            services=services,
            blockers=_summary_blockers(records, safety),
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
        settings = RealRobotRuntimeSettings(
            runtime_profile=os.environ.get("RUNTIME_PROFILE", "local"),
            execution_mode=ExecutionMode.DRY_RUN,
            enable_real_robot=False,
            config=None,
        )
        gate = HardwareExecutionGate(settings=settings)
        decision = gate.evaluate(
            HardwareGateInput(
                controller_connected=False,
                emergency_stop_active=False,
                safety_shield_healthy=False,
                telemetry=None,
                requested_velocity_scale=0.0,
                requested_acceleration_scale=0.0,
                acceptance_level="NONE",
                required_acceptance_level="LEVEL_0",
            )
        )
        return SafetyGateSnapshot(
            decided_at=datetime.now(UTC),
            controller_connected=False,
            emergency_stop_state="UNKNOWN",
            safety_shield_state=ServiceStatus.UNKNOWN,
            telemetry_freshness=FreshnessStatus.MISSING,
            current_acceptance_level="NONE",
            required_acceptance_level="LEVEL_0",
            allowed=decision.allowed,
            hardware_motion_authorized=decision.hardware_motion_authorized,
            reason_codes=decision.reason_codes,
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
        return ComparisonResponse(metrics=_comparison_metrics(self.artifact_root))

    def record_safety_review_note(
        self, request: SafetyReviewNoteRequest, *, role: UserRole
    ) -> SafetyReviewNoteResponse:
        note = str(redact(request.note))
        response = SafetyReviewNoteResponse(
            note_id=str(uuid4()),
            role=role,
            note=note,
            related_evidence_id=request.related_evidence_id,
            hardware_motion_authorized=False,
            created_at=datetime.now(UTC),
        )
        self.events.publish(
            "safety_review_note",
            "dashboard",
            {
                "note_id": response.note_id,
                "role": role.value,
                "related_evidence_id": response.related_evidence_id,
                "hardware_motion_authorized": False,
            },
        )
        return response


def _latest_project_status(records: object) -> str:
    accepted_statuses = {
        "PHASE10_MOVEIT_DRY_RUN_ACCEPTED",
        "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED_WITH_MOVEIT_ENV_BLOCK",
        "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED",
        "PHASE10_DRY_RUN_ACCEPTED",
    }
    fallback_blocked = ""
    for record in records if isinstance(records, list) else []:
        if getattr(record, "status", None) not in {
            EvidenceStatus.ACCEPTED,
            EvidenceStatus.BLOCKED_BY_ENV,
        }:
            continue
        summary = str(getattr(record, "summary", ""))
        if summary in accepted_statuses:
            return summary
        if "PHASE10_MOVEIT_DRY_RUN_ACCEPTED" in summary:
            return "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
        if (
            getattr(record, "status", None) == EvidenceStatus.BLOCKED_BY_ENV
            and not fallback_blocked
        ):
            fallback_blocked = summary or "BLOCKED_BY_ENV"
    return fallback_blocked or "UNKNOWN"


def _highest_hardware_claim(records: list[EvidenceIndexRecord]) -> HardwareClaim:
    order = {
        HardwareClaim.NONE: 0,
        HardwareClaim.SIMULATION_ONLY: 1,
        HardwareClaim.PLANNING_ONLY: 2,
        HardwareClaim.HARDWARE_READ_ONLY: 3,
        HardwareClaim.HARDWARE_MOTION: 4,
    }
    highest = HardwareClaim.NONE
    for record in records:
        if order[record.hardware_claim] > order[highest]:
            highest = record.hardware_claim
    return highest


def _service_health_from_safety(safety: SafetyGateSnapshot) -> list[ServiceHealth]:
    gate_status = (
        ServiceStatus.NOT_CONFIGURED
        if "CONTROLLER_NOT_CONNECTED" in safety.reason_codes
        or "REAL_ROBOT_CONFIG_MISSING" in safety.reason_codes
        else ServiceStatus.UNKNOWN
    )
    return [
        ServiceHealth(name="SafetyShield", status=safety.safety_shield_state),
        ServiceHealth(name="HardwareExecutionGate", status=gate_status),
        ServiceHealth(name="RealRobotController", status=ServiceStatus.NOT_CONFIGURED),
    ]


def _summary_blockers(records: list[EvidenceIndexRecord], safety: SafetyGateSnapshot) -> list[str]:
    blockers: list[str] = []
    if not records:
        blockers.append("no indexed authoritative dashboard evidence")
    blockers.extend(safety.reason_codes)
    return blockers


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


def _comparison_metrics(artifact_root: Path) -> list[dict[str, Any]]:
    candidates = [
        artifact_root / "baselines" / "phase8_2" / "full" / "summary.json",
        artifact_root / "baselines" / "phase8_2" / "validation" / "summary.json",
        Path("experiments/baselines/phase8_2/full/summary.json"),
        Path("experiments/baselines/phase8_2/validation/summary.json"),
    ]
    summary = next((_load_json(path) for path in candidates if path.exists()), {})
    by_mode = summary.get("by_mode") if isinstance(summary, dict) else None
    if not isinstance(by_mode, dict):
        return []
    metrics: list[dict[str, Any]] = []
    for metric_name, unit in (
        ("success_rate", "ratio"),
        ("cloud_invocation_count", "count"),
        ("retry_count", "count"),
        ("mode_switch_count", "count"),
    ):
        row: dict[str, Any] = {"name": metric_name, "unit": unit}
        for mode, key in (("PCSC", "pcsc"), ("ETEAC", "eteac"), ("AUTO", "auto")):
            mode_payload = by_mode.get(mode)
            if not isinstance(mode_payload, dict):
                row[key] = None
                continue
            value = mode_payload.get(metric_name)
            if isinstance(value, dict):
                row[key] = value.get("mean", value.get("point_estimate"))
            else:
                row[key] = value
        metrics.append(row)
    return metrics


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
