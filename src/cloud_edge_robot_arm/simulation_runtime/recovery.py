"""运行时恢复服务。

恢复流程只检查租约和 artifact 完整性，不自动执行真实硬件，也不重复执行已经
完整落盘的仿真结果。
"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.models import RecoveryResponse, RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.repository import SimulationJobRepository


class ArtifactRecoveryService:
    """根据持久化状态和 artifact 完整性恢复 interrupted job。"""

    def __init__(
        self,
        *,
        repository: SimulationJobRepository,
        artifact_root: Path,
        requeue_recoverable: bool = False,
    ) -> None:
        self.repository = repository
        self.artifact_root = artifact_root
        self.requeue_recoverable = requeue_recoverable

    def recover_interrupted_jobs(self) -> RecoveryResponse:
        # 先让 repository 标记过期租约，再基于 artifact 完整性决定是否进入
        # RECOVERY_PENDING；只有显式允许时才重新入队，避免启动恢复无意中
        # 重复执行已经需要人工复核的任务。
        interrupted = self.repository.expire_leases()
        recovered: list[str] = []
        incomplete: list[str] = []
        for job in self.repository.find_recoverable_jobs():
            if job.status == RuntimeJobStatus.INTERRUPTED:
                self.repository.finish_open_attempts(
                    job.job_id,
                    result=RuntimeJobStatus.INTERRUPTED.value,
                    error="lease expired before worker released job",
                )
                updated = self.repository.update_status_cas(
                    job.job_id,
                    expected=RuntimeJobStatus.INTERRUPTED,
                    next_status=RuntimeJobStatus.RECOVERY_PENDING,
                    reason_code="lease_recovery",
                    worker_id="recovery",
                    lease_id="",
                )
                if updated is not None:
                    job = updated
                else:
                    job = self.repository.get_job(job.job_id)
            if job.status == RuntimeJobStatus.RECOVERY_PENDING and self.requeue_recoverable:
                updated = self.repository.update_status_cas(
                    job.job_id,
                    expected=RuntimeJobStatus.RECOVERY_PENDING,
                    next_status=RuntimeJobStatus.QUEUED,
                    reason_code="requeue_after_recovery",
                    worker_id="recovery",
                    lease_id="",
                )
                if updated is not None:
                    recovered.append(job.job_id)
            elif job.status == RuntimeJobStatus.RECOVERY_PENDING:
                recovered.append(job.job_id)
            else:
                run_dir = self.artifact_root / job.artifact_root
                if not run_dir.exists():
                    incomplete.append(job.job_id)
        return RecoveryResponse(
            recovered_jobs=recovered,
            interrupted_jobs=interrupted,
            incomplete_artifacts=incomplete,
            rerun_started=self.requeue_recoverable and bool(recovered),
        )
