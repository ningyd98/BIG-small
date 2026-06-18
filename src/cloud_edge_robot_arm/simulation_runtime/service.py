"""仿真运行时门面。

本模块把 FastAPI 工作台请求转换为持久化 job，并负责把运行记录重新投影成
Phase 11 已有的 run/batch API 模型。它不直接执行任意命令，也不接触真实控制器；
所有实际运行都交给带 allowlist 的 dispatcher/worker。
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream
from cloud_edge_robot_arm.dashboard.models import DashboardEvent
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import git_sha
from cloud_edge_robot_arm.real_robot.provenance import current_source_tree_hash
from cloud_edge_robot_arm.simulation_runtime.dispatcher import SimulationJobDispatcher
from cloud_edge_robot_arm.simulation_runtime.models import (
    AttemptListResponse,
    AttemptView,
    QueueStatusResponse,
    RecoveryResponse,
    RuntimeHealthResponse,
    RuntimeJobStatus,
    WorkerListResponse,
)
from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
from cloud_edge_robot_arm.simulation_runtime.resource_limits import SimulationResourcePolicy
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_workbench.models import (
    BatchProgress,
    BatchRecord,
    ExperimentDraft,
    ExperimentManifest,
    ReproductionResponse,
    SimulationArtifactsResponse,
    SimulationBackend,
    SimulationEventsResponse,
    SimulationMetric,
    SimulationMetricsResponse,
    SimulationRunListResponse,
    SimulationRunRecord,
    SimulationRunStatus,
    SimulationRunType,
    TimelineEvent,
)


class SimulationRuntimeService:
    """仿真任务编排服务。

    该服务是 API 层唯一应该调用的运行时入口：创建任务立即返回 QUEUED，
    后台 worker 再推进状态。这里保留 Phase 11 API 兼容性，同时把真源放到
    SQLite repository，避免进程重启后丢失 run/history/event。
    """

    def __init__(
        self,
        *,
        artifact_root: Path,
        database_path: Path,
        event_stream: DashboardEventStream,
        runtime_root: Path | None = None,
        resource_policy: SimulationResourcePolicy | None = None,
    ) -> None:
        self.artifact_root = artifact_root
        self.runs_root = runtime_root or artifact_root / "phase11_1/runtime"
        self.batches_root = self.runs_root / "batches"
        self.repository = SQLiteSimulationJobRepository(database_path)
        self.resource_policy = resource_policy or SimulationResourcePolicy()
        self.dispatcher = SimulationJobDispatcher(
            repository=self.repository,
            artifact_root=artifact_root,
            resource_policy=self.resource_policy,
        )
        self.events = event_stream
        self._started = False

    def start(self) -> None:
        if not self._started:
            # 启动时先恢复遗留状态，再启动后台 dispatcher；顺序不能反过来，
            # 否则过期租约可能被新 worker 和恢复流程同时处理。
            ArtifactRecoveryService(
                repository=self.repository, artifact_root=self.artifact_root
            ).recover_interrupted_jobs()
            self.dispatcher.start()
            self._started = True

    def list_runs(self) -> SimulationRunListResponse:
        self.start()
        return SimulationRunListResponse(
            runs=[self._run_record(job) for job in self.repository.list_jobs()]
        )

    def get_run(self, run_id: str) -> SimulationRunRecord:
        self.start()
        return self._run_record(self.repository.get_job_by_run_id(run_id))

    def create_run(
        self,
        draft: ExperimentDraft,
        *,
        manifest: ExperimentManifest,
        blockers: list[str],
        batch_id: str = "",
    ) -> SimulationRunRecord:
        self.start()
        scenario_id = draft.scenarios[0]
        control_mode = draft.control_modes[0]
        seed = draft.seeds[0]
        run_id = (
            "sim-"
            + stable_hash(
                {
                    "manifest": manifest.reproducibility_hash,
                    "scenario_id": scenario_id,
                    "control_mode": control_mode,
                    "seed": seed,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )[:12]
        )
        timeout_seconds = int(
            draft.parameter_overrides.get(
                "timeout_seconds", int(draft.parameter_overrides.get("timeout_ms", 300_000)) // 1000
            )
        )
        timeout_seconds = max(1, min(timeout_seconds, self.resource_policy.max_runtime_seconds))
        job = self.repository.create_job(
            run_id=run_id,
            batch_id=batch_id,
            backend=draft.backend.value,
            scenario_id=scenario_id,
            control_mode=control_mode,
            seed=seed,
            manifest_id=manifest.manifest_id,
            reproducibility_hash=manifest.reproducibility_hash,
            draft=draft.model_dump(mode="json"),
            manifest=manifest.model_dump(mode="json"),
            timeout_seconds=timeout_seconds,
            max_attempts=2,
            artifact_root=(self.runs_root / run_id).relative_to(self.artifact_root).as_posix(),
            source_commit=manifest.source_commit,
            source_tree_hash=manifest.source_tree_hash,
            provenance=_provenance(manifest),
        )
        if blockers:
            # 被环境阻塞的后端仍会产生持久化 job，前端和审计才能看到真实
            # BLOCKED_BY_ENV 历史，而不是把 Isaac 等不可用环境静默吞掉。
            self.repository.update_status_cas(
                job.job_id,
                expected=RuntimeJobStatus.CREATED,
                next_status=RuntimeJobStatus.BLOCKED_BY_ENV,
                reason_code="backend_blocked",
                worker_id="",
                lease_id="",
                error_message="; ".join(blockers),
            )
            return self._run_record(self.repository.get_job(job.job_id))
        accepted_at = datetime.now(UTC)
        # HTTP 请求线程只负责入队，不等待 worker 执行；这是 Phase 11.1
        # 解决长时间 MuJoCo/Sweep 阻塞 API 的核心边界。
        self.repository.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="accepted",
            worker_id="",
            lease_id="",
        )
        queued = replace(
            job,
            status=RuntimeJobStatus.QUEUED,
            queued_at=accepted_at,
            updated_at=accepted_at,
        )
        record = self._run_record(queued)
        self._publish_job_events(queued.run_id)
        return record

    def cancel_run(self, run_id: str) -> SimulationRunRecord:
        self.start()
        job = self.repository.get_job_by_run_id(run_id)
        updated = self.repository.request_cancel(job.job_id)
        return self._run_record(updated)

    def retry_run(self, run_id: str) -> SimulationRunRecord:
        self.start()
        job = self.repository.get_job_by_run_id(run_id)
        updated = self.repository.retry_job(job.job_id)
        return self._run_record(updated)

    def attempts_for(self, run_id: str) -> AttemptListResponse:
        attempts = self.repository.list_attempts(run_id)
        return AttemptListResponse(
            attempts=[
                AttemptView(
                    attempt=attempt.attempt,
                    worker_id=attempt.worker_id,
                    started_at=attempt.started_at,
                    ended_at=attempt.ended_at,
                    result=attempt.result,
                    error=attempt.error,
                    artifact_paths=attempt.artifact_paths,
                )
                for attempt in attempts
            ]
        )

    def events_for(self, run_id: str) -> SimulationEventsResponse:
        events = [
            TimelineEvent(
                sequence=event.sequence,
                event_type=event.event_type,
                source=event.source,
                wall_time=event.timestamp,
                payload=event.payload,
            )
            for event in self.repository.list_events(run_id)
        ]
        return SimulationEventsResponse(events=events)

    def metrics_for(self, run_id: str) -> SimulationMetricsResponse:
        return SimulationMetricsResponse(
            metrics=[
                SimulationMetric.model_validate(metric)
                for metric in self.repository.get_metrics(run_id)
            ]
        )

    def artifacts_for(self, run_id: str) -> SimulationArtifactsResponse:
        return SimulationArtifactsResponse(artifacts=self.repository.get_artifacts(run_id))

    def clone_run(self, run_id: str) -> ReproductionResponse:
        job = self.repository.get_job_by_run_id(run_id)
        return ReproductionResponse(
            draft=ExperimentDraft.model_validate(job.draft),
            environment_match=True,
            warnings=[],
            reproducibility_hash=job.reproducibility_hash,
        )

    def reproduce_run(self, run_id: str) -> ReproductionResponse:
        job = self.repository.get_job_by_run_id(run_id)
        environment_match = job.source_tree_hash == _source_tree_hash()
        return ReproductionResponse(
            draft=ExperimentDraft.model_validate(job.draft),
            environment_match=environment_match,
            warnings=[]
            if environment_match
            else ["source tree hash differs from current checkout"],
            reproducibility_hash=job.reproducibility_hash,
        )

    def create_batch(
        self,
        draft: ExperimentDraft,
        *,
        manifest: ExperimentManifest,
        blockers: list[str],
    ) -> BatchRecord:
        self.start()
        batch_id = "batch-" + manifest.reproducibility_hash[:12]
        run_ids: list[str] = []
        for scenario_id in draft.scenarios:
            for control_mode in draft.control_modes:
                for seed in draft.seeds:
                    for _ in range(draft.repetitions):
                        run_draft = draft.model_copy(
                            update={
                                "run_type": SimulationRunType.SINGLE,
                                "scenarios": [scenario_id],
                                "control_modes": [control_mode],
                                "seeds": [seed],
                                "repetitions": 1,
                            },
                            deep=True,
                        )
                        run_ids.append(
                            self.create_run(
                                run_draft,
                                manifest=manifest,
                                blockers=blockers,
                                batch_id=batch_id,
                            ).run_id
                        )
        self.repository.create_batch(
            batch_id=batch_id,
            manifest=manifest.model_dump(mode="json"),
            run_ids=run_ids,
        )
        return self.get_batch(batch_id)

    def get_batch(self, batch_id: str) -> BatchRecord:
        batch = self.repository.get_batch(batch_id)
        runs = [self._run_record(job) for job in self.repository.list_batch_jobs(batch_id)]
        return BatchRecord(
            batch_id=batch.batch_id,
            manifest=ExperimentManifest.model_validate(batch.manifest),
            progress=_batch_progress(runs),
            run_ids=batch.run_ids,
            status=_batch_status(_batch_progress(runs)),
            artifact_paths={},
            hardware_write_operations=[],
        )

    def batch_runs(self, batch_id: str) -> SimulationRunListResponse:
        return SimulationRunListResponse(
            runs=[self._run_record(job) for job in self.repository.list_batch_jobs(batch_id)]
        )

    def cancel_batch(self, batch_id: str) -> BatchRecord:
        for job in self.repository.list_batch_jobs(batch_id):
            self.repository.request_cancel(job.job_id)
        return self.get_batch(batch_id)

    def retry_failed_batch(self, batch_id: str) -> BatchRecord:
        for job in self.repository.list_batch_jobs(batch_id):
            if job.status in {
                RuntimeJobStatus.FAILED,
                RuntimeJobStatus.TIMED_OUT,
                RuntimeJobStatus.CANCELLED,
                RuntimeJobStatus.INTERRUPTED,
                RuntimeJobStatus.RECOVERY_PENDING,
            }:
                self.repository.retry_job(job.job_id)
        return self.get_batch(batch_id)

    def health(self) -> RuntimeHealthResponse:
        self.start()
        return RuntimeHealthResponse(
            queued=self.repository.queued_count(),
            running=self.repository.running_count(),
            workers=len(self.dispatcher.workers()),
        )

    def workers(self) -> WorkerListResponse:
        return WorkerListResponse(workers=self.dispatcher.workers())

    def queue(self) -> QueueStatusResponse:
        return QueueStatusResponse(
            queued=self.repository.queued_count(),
            running=self.repository.running_count(),
            blocked=self.repository.blocked_count(),
            max_queued_jobs=self.resource_policy.max_queued_jobs,
            max_batch_runs=self.resource_policy.max_batch_runs,
        )

    def recover(self) -> RecoveryResponse:
        return ArtifactRecoveryService(
            repository=self.repository, artifact_root=self.artifact_root
        ).recover_interrupted_jobs()

    def replay_stream_after(self, sequence: int) -> list[Any]:
        dashboard_events = []
        for event in self.repository.list_stream_events_after(sequence):
            dashboard_event = DashboardEvent(
                event_id=event.event_id,
                sequence=event.stream_sequence,
                event_type=event.event_type,
                source=event.source,
                timestamp=event.timestamp,
                experiment_id=event.run_id,
                payload={
                    **event.payload,
                    "job_id": event.job_id,
                    "run_id": event.run_id,
                    "runtime_sequence": event.sequence,
                },
            )
            dashboard_events.append(self.events.append(dashboard_event))
        return dashboard_events

    def _run_record(self, job: Any) -> SimulationRunRecord:
        status = SimulationRunStatus(job.status.value)
        queue_position = (
            max(1, self.repository.queued_count()) if status == SimulationRunStatus.QUEUED else 0
        )
        return SimulationRunRecord(
            run_id=job.run_id,
            job_id=job.job_id,
            queue_position=queue_position,
            backend=SimulationBackend(job.backend),
            run_type=SimulationRunType.SINGLE,
            status=status,
            scenario_id=job.scenario_id,
            control_mode=job.control_mode,
            seed=job.seed,
            manifest=ExperimentManifest.model_validate(job.manifest),
            created_at=job.created_at,
            accepted_at=job.queued_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            timeout_seconds=job.timeout_seconds,
            cancel_requested=job.cancel_requested,
            worker_id=job.worker_id,
            lease_id=job.lease_id,
            runtime_reason=job.error_message,
            blockers=[job.error_message] if job.error_message else [],
            artifact_paths=job.artifact_paths,
            hardware_claim="PLANNING_ONLY"
            if job.backend == SimulationBackend.MOVEIT_DRY_RUN.value
            else "SIMULATION_ONLY",
            real_controller_contacted=False,
            hardware_motion_observed=False,
            hardware_write_operations=[],
            provenance=job.provenance,
        )

    def _publish_job_events(self, run_id: str) -> None:
        for event in self.repository.list_events(run_id):
            self.events.publish(
                event.event_type,
                event.source,
                event.payload,
                experiment_id=run_id,
            )


def _provenance(manifest: ExperimentManifest) -> dict[str, Any]:
    return {
        "source_commit": manifest.source_commit,
        "source_tree_hash": manifest.source_tree_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        "config_hash": stable_hash(manifest.normalized_config),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }


def _source_tree_hash() -> str:
    try:
        return current_source_tree_hash()
    except Exception:
        return hashlib.sha256(b"unknown-source-tree").hexdigest()


def build_manifest(draft: ExperimentDraft, *, run_count: int) -> ExperimentManifest:
    normalized = draft.model_dump(mode="json")
    normalized["scenarios"] = sorted(normalized["scenarios"])
    normalized["control_modes"] = sorted(normalized["control_modes"])
    normalized["seeds"] = sorted(normalized["seeds"])
    source_commit = git_sha()
    source_tree_hash = _source_tree_hash()
    reproducibility_hash = stable_hash(
        {
            "normalized_config": normalized,
            "source_commit": source_commit,
            "source_tree_hash": source_tree_hash,
        }
    )
    return ExperimentManifest(
        manifest_id="manifest-" + reproducibility_hash[:12],
        normalized_config=normalized,
        source_commit=source_commit,
        source_tree_hash=source_tree_hash,
        run_count=run_count,
        reproducibility_hash=reproducibility_hash,
    )


def _batch_progress(runs: list[SimulationRunRecord]) -> BatchProgress:
    total = len(runs)
    queued = sum(1 for run in runs if run.status == SimulationRunStatus.QUEUED)
    running = sum(
        1
        for run in runs
        if run.status
        in {
            SimulationRunStatus.VALIDATING,
            SimulationRunStatus.LEASED,
            SimulationRunStatus.STARTING,
            SimulationRunStatus.RUNNING,
            SimulationRunStatus.CANCEL_REQUESTED,
            SimulationRunStatus.CANCELLING,
            SimulationRunStatus.FINALIZING,
        }
    )
    succeeded = sum(1 for run in runs if run.status == SimulationRunStatus.SUCCEEDED)
    failed = sum(1 for run in runs if run.status == SimulationRunStatus.FAILED)
    blocked = sum(1 for run in runs if run.status == SimulationRunStatus.BLOCKED_BY_ENV)
    cancelled = sum(1 for run in runs if run.status == SimulationRunStatus.CANCELLED)
    timed_out = sum(1 for run in runs if run.status == SimulationRunStatus.TIMED_OUT)
    interrupted = sum(1 for run in runs if run.status == SimulationRunStatus.INTERRUPTED)
    done = succeeded + failed + blocked + cancelled + timed_out
    return BatchProgress(
        total=total,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        blocked=blocked,
        cancelled=cancelled,
        timed_out=timed_out,
        interrupted=interrupted,
        progress_ratio=done / total if total else 0.0,
    )


def _batch_status(progress: BatchProgress) -> SimulationRunStatus:
    if progress.running:
        return SimulationRunStatus.RUNNING
    if progress.queued:
        return SimulationRunStatus.QUEUED
    if progress.failed:
        return SimulationRunStatus.FAILED
    if progress.timed_out:
        return SimulationRunStatus.TIMED_OUT
    if progress.cancelled:
        return SimulationRunStatus.CANCELLED
    if progress.blocked:
        return SimulationRunStatus.BLOCKED_BY_ENV
    return SimulationRunStatus.SUCCEEDED
