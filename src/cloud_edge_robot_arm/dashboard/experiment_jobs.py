"""Dashboard 实验 job 管理器。

这里的 runner 通过固定 allowlist 映射到安全实验入口，不接受浏览器提交的任意
shell、脚本路径、模块名或环境变量。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import threading
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream
from cloud_edge_robot_arm.dashboard.evidence_index import EvidenceIndex
from cloud_edge_robot_arm.dashboard.models import (
    ExperimentCreateRequest,
    ExperimentJobRecord,
    ExperimentJobStatus,
    ExperimentKind,
    HardwareClaim,
)
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService
from cloud_edge_robot_arm.real_robot.planners import SyntheticDryRunPlanner
from cloud_edge_robot_arm.real_robot.verification import _phase10_dry_run_contract
from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial

TERMINAL_STATUSES = {
    ExperimentJobStatus.SUCCEEDED,
    ExperimentJobStatus.FAILED,
    ExperimentJobStatus.CANCELLED,
    ExperimentJobStatus.BLOCKED_BY_ENV,
}


@dataclass(frozen=True)
class RunnerResult:
    status: ExperimentJobStatus
    exit_code: int
    stdout: str
    stderr: str
    payload: dict[str, Any]
    blockers: list[str]


class RunnerAdapter(ABC):
    hardware_claim: HardwareClaim

    @abstractmethod
    def run(self, request: ExperimentCreateRequest, run_dir: Path) -> RunnerResult:
        raise NotImplementedError

    def cancel(self) -> None:
        return


class MockSoftwareRunnerAdapter(RunnerAdapter):
    hardware_claim = HardwareClaim.SIMULATION_ONLY

    def run(self, request: ExperimentCreateRequest, run_dir: Path) -> RunnerResult:
        config = _experiment_config(request, artifact_dir=run_dir)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            execution = ExperimentRunner(config).run()
        result = execution.result
        payload = {
            "runner_kind": request.kind.value,
            "status": "SUCCEEDED" if result.task_success else "FAILED",
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "control_mode": request.control_mode,
            "hardware_claim": self.hardware_claim.value,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
            "result": result.model_dump(mode="json"),
            "event_count": len(execution.events),
        }
        status = (
            ExperimentJobStatus.SUCCEEDED if result.task_success else ExperimentJobStatus.FAILED
        )
        return RunnerResult(
            status=status,
            exit_code=0 if status == ExperimentJobStatus.SUCCEEDED else 1,
            stdout=buffer.getvalue(),
            stderr="",
            payload=payload,
            blockers=[] if status == ExperimentJobStatus.SUCCEEDED else ["mock experiment failed"],
        )


class MuJoCoSmokeRunnerAdapter(RunnerAdapter):
    hardware_claim = HardwareClaim.SIMULATION_ONLY

    def run(self, request: ExperimentCreateRequest, run_dir: Path) -> RunnerResult:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            trial = run_mujoco_physical_trial(request.scenario_id, seed=request.seed)
        payload = {
            "runner_kind": request.kind.value,
            "status": "SUCCEEDED",
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "control_mode": request.control_mode,
            "hardware_claim": self.hardware_claim.value,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
            "trial": asdict(trial),
        }
        return RunnerResult(
            status=ExperimentJobStatus.SUCCEEDED,
            exit_code=0,
            stdout=buffer.getvalue(),
            stderr="",
            payload=payload,
            blockers=[],
        )


class SyntheticDryRunRunnerAdapter(RunnerAdapter):
    hardware_claim = HardwareClaim.PLANNING_ONLY

    def run(self, request: ExperimentCreateRequest, run_dir: Path) -> RunnerResult:
        service = DryRunValidationService(
            shield=SafetyShield(),
            runtime_settings=RealRobotRuntimeSettings(
                runtime_profile="dashboard",
                execution_mode=ExecutionMode.DRY_RUN,
                enable_real_robot=False,
                config=None,
            ),
            telemetry_sample=TelemetrySample(
                timestamp=datetime.now(UTC),
                tcp_velocity=0.0,
                joint_velocities=[0.0] * 7,
                acceleration=0.0,
            ),
            planner=SyntheticDryRunPlanner(),
        )
        result = service.validate(_phase10_dry_run_contract().model_dump(mode="json"))
        dry_run = result.model_dump(mode="json")
        succeeded = result.status == "DRY_RUN_VALIDATED" and result.validation_claimed
        payload = {
            "runner_kind": request.kind.value,
            "status": "SUCCEEDED" if succeeded else "FAILED",
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "control_mode": request.control_mode,
            "hardware_claim": self.hardware_claim.value,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
            "dry_run": dry_run,
        }
        return RunnerResult(
            status=ExperimentJobStatus.SUCCEEDED if succeeded else ExperimentJobStatus.FAILED,
            exit_code=0 if succeeded else 1,
            stdout=json.dumps(dry_run, sort_keys=True) + "\n",
            stderr="",
            payload=payload,
            blockers=[] if succeeded else [result.status],
        )


class MoveItRuntimeDryRunRunnerAdapter(RunnerAdapter):
    hardware_claim = HardwareClaim.PLANNING_ONLY

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None

    def run(self, request: ExperimentCreateRequest, run_dir: Path) -> RunnerResult:
        output_dir = run_dir / "moveit_runtime"
        argv = [
            sys.executable,
            "scripts/phase10/run_moveit_dry_run_runtime.py",
            "--output",
            str(output_dir),
        ]
        self._process = subprocess.Popen(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        stdout, stderr = self._process.communicate(timeout=120)
        exit_code = self._process.returncode
        evidence_path = output_dir / "moveit_dry_run_evidence.json"
        payload: dict[str, Any]
        if evidence_path.exists():
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        else:
            payload = {}
        if exit_code == 0 and payload.get("validation_claimed") is True:
            status = ExperimentJobStatus.SUCCEEDED
            blockers: list[str] = []
            payload_status = "SUCCEEDED"
        else:
            status = ExperimentJobStatus.BLOCKED_BY_ENV
            blockers = [_short_blocker(stderr) or "MoveIt runtime dry-run environment unavailable"]
            payload_status = "BLOCKED_BY_ENV"
        payload = {
            "runner_kind": request.kind.value,
            "status": payload_status,
            "scenario_id": request.scenario_id,
            "seed": request.seed,
            "control_mode": request.control_mode,
            "hardware_claim": self.hardware_claim.value,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
            "moveit_runtime": payload,
        }
        return RunnerResult(
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            payload=payload,
            blockers=blockers,
        )

    def cancel(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()


class ExperimentJobManager:
    def __init__(
        self,
        *,
        artifact_root: Path,
        writes_enabled: bool = False,
        event_stream: DashboardEventStream | None = None,
    ) -> None:
        self.artifact_root = artifact_root
        self.writes_enabled = writes_enabled
        self.evidence_index = EvidenceIndex(artifact_root)
        self.events = event_stream or DashboardEventStream()
        self._jobs: dict[str, ExperimentJobRecord] = {}
        self._adapters: dict[str, RunnerAdapter] = {}
        self._lock = threading.RLock()

    def list_jobs(self) -> list[ExperimentJobRecord]:
        with self._lock:
            return list(self._jobs.values())

    def get(self, experiment_id: str) -> ExperimentJobRecord | None:
        with self._lock:
            return self._jobs.get(experiment_id)

    def start(self, request: ExperimentCreateRequest) -> ExperimentJobRecord:
        extras = set((request.model_extra or {}).keys())
        if extras:
            raise ValueError("forbidden experiment field")
        if not self.writes_enabled:
            raise PermissionError("dashboard experiment writes are disabled")

        experiment_id = _experiment_id(request)
        now = datetime.now(UTC)
        adapter = _adapter_for(request.kind)
        job = ExperimentJobRecord(
            experiment_id=experiment_id,
            kind=request.kind,
            status=ExperimentJobStatus.QUEUED,
            scenario_id=request.scenario_id,
            seed=request.seed,
            control_mode=request.control_mode,
            hardware_claim=adapter.hardware_claim,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            existing = self._jobs.get(experiment_id)
            if existing is not None and existing.status not in TERMINAL_STATUSES:
                return existing
            self._jobs[experiment_id] = job
            self._adapters[experiment_id] = adapter
        self._publish_state_event("experiment", job)
        thread = threading.Thread(
            target=self._run_job,
            args=(experiment_id, request, adapter),
            name=f"dashboard-job-{experiment_id}",
            daemon=True,
        )
        thread.start()
        return job

    def cancel(self, experiment_id: str) -> ExperimentJobRecord:
        with self._lock:
            job = self._jobs.get(experiment_id)
            adapter = self._adapters.get(experiment_id)
        if job is None:
            raise KeyError(experiment_id)
        if job.status in TERMINAL_STATUSES:
            self.events.publish(
                "audit",
                "dashboard",
                {
                    "experiment_id": job.experiment_id,
                    "status": job.status.value,
                    "cancel_ignored": True,
                    "reason": "job already terminal",
                },
                experiment_id=job.experiment_id,
            )
            return job
        if adapter is not None:
            adapter.cancel()
        updated = self._update(
            experiment_id,
            status=ExperimentJobStatus.CANCELLED,
            blockers=["cancelled by operator"],
            completed_at=datetime.now(UTC),
        )
        self._publish_state_event("audit", updated)
        return updated

    def _run_job(
        self,
        experiment_id: str,
        request: ExperimentCreateRequest,
        adapter: RunnerAdapter,
    ) -> None:
        run_dir = self.artifact_root / "dashboard_jobs" / experiment_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._update(experiment_id, status=ExperimentJobStatus.STARTING)
        started_at = datetime.now(UTC)
        self._update(experiment_id, status=ExperimentJobStatus.RUNNING, started_at=started_at)
        time.sleep(0.05)
        try:
            result = adapter.run(request, run_dir)
        except Exception as exc:  # pragma: no cover - defensive job evidence
            result = RunnerResult(
                status=ExperimentJobStatus.FAILED,
                exit_code=1,
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                payload={
                    "runner_kind": request.kind.value,
                    "status": "FAILED",
                    "hardware_motion_observed": False,
                    "sent_to_hardware": False,
                },
                blockers=[f"{type(exc).__name__}: {exc}"],
            )
        with self._lock:
            current = self._jobs.get(experiment_id)
        if current is not None and current.status == ExperimentJobStatus.CANCELLED:
            return
        completed_at = datetime.now(UTC)
        evidence_path = self._write_evidence(
            experiment_id=experiment_id,
            request=request,
            run_dir=run_dir,
            result=result,
            started_at=started_at,
            completed_at=completed_at,
        )
        evidence_id = _evidence_id(self.artifact_root, evidence_path)
        updated = self._update(
            experiment_id,
            status=result.status,
            evidence_id=evidence_id,
            evidence_path=evidence_path.relative_to(self.artifact_root).as_posix(),
            completed_at=completed_at,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            blockers=result.blockers,
        )
        self._publish_state_event("evidence", updated)
        self._publish_state_event("summary", updated)
        self._publish_state_event("safety", updated)

    def _write_evidence(
        self,
        *,
        experiment_id: str,
        request: ExperimentCreateRequest,
        run_dir: Path,
        result: RunnerResult,
        started_at: datetime,
        completed_at: datetime,
    ) -> Path:
        payload = {
            **result.payload,
            "experiment_id": experiment_id,
            "kind": request.kind.value,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "blockers": result.blockers,
            "validation_claimed": result.status == ExperimentJobStatus.SUCCEEDED,
        }
        evidence_path = run_dir / "job_evidence.json"
        evidence_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return evidence_path

    def _update(self, experiment_id: str, **updates: object) -> ExperimentJobRecord:
        with self._lock:
            job = self._jobs[experiment_id]
            updated = job.model_copy(update={"updated_at": datetime.now(UTC), **updates})
            self._jobs[experiment_id] = updated
            self._publish_state_event("experiment", updated)
            return updated

    def _publish_state_event(self, event_type: str, job: ExperimentJobRecord) -> None:
        self.events.publish(
            event_type,
            "dashboard",
            {
                "experiment_id": job.experiment_id,
                "status": job.status.value,
                "hardware_claim": job.hardware_claim.value,
                "evidence_id": job.evidence_id,
                "evidence_path": job.evidence_path,
                "exit_code": job.exit_code,
            },
            experiment_id=job.experiment_id,
        )


def _adapter_for(kind: ExperimentKind) -> RunnerAdapter:
    allowlist: dict[ExperimentKind, type[RunnerAdapter]] = {
        ExperimentKind.MOCK_SOFTWARE: MockSoftwareRunnerAdapter,
        ExperimentKind.MUJOCO_SMOKE: MuJoCoSmokeRunnerAdapter,
        ExperimentKind.SYNTHETIC_DRY_RUN: SyntheticDryRunRunnerAdapter,
        ExperimentKind.MOVEIT_RUNTIME_DRY_RUN: MoveItRuntimeDryRunRunnerAdapter,
    }
    return allowlist[kind]()


def _experiment_config(request: ExperimentCreateRequest, *, artifact_dir: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=_experiment_id(request),
        scenario_id=request.scenario_id,
        mode=ExperimentMode(request.control_mode),
        seed=request.seed,
        repetitions=request.repetitions,
        network_profile=NetworkProfileName(request.network_profile),
        fault_profile=FaultProfile(name=request.fault_profile),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=300,
        timeout_ms=30_000,
        artifact_dir=artifact_dir,
    )


def _experiment_id(request: ExperimentCreateRequest) -> str:
    raw = (
        f"{request.kind}:{request.scenario_id}:{request.seed}:{request.control_mode}:"
        f"{request.network_profile}:{request.fault_profile}:{request.repetitions}"
    )
    return "exp-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _evidence_id(root: Path, path: Path) -> str:
    relative_path = path.relative_to(root).as_posix()
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


def _short_blocker(stderr: str) -> str:
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:300]
    return ""
