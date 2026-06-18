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

    def __init__(self, *, repository: SimulationJobRepository, artifact_root: Path) -> None:
        self.repository = repository
        self.artifact_root = artifact_root

    def recover_interrupted_jobs(self) -> RecoveryResponse:
        # 先让 repository 标记过期租约，再基于 artifact 完整性决定是否进入
        # RECOVERY_PENDING；这里不直接 requeue，避免重复执行。
        interrupted = self.repository.expire_leases()
        recovered: list[str] = []
        incomplete: list[str] = []
        for job in self.repository.find_recoverable_jobs():
            run_dir = self.artifact_root / job.artifact_root
            required = ["run_manifest.json", "events.jsonl", "metrics.json", "result.json"]
            if job.status == RuntimeJobStatus.INTERRUPTED and all(
                (run_dir / name).exists() for name in required
            ):
                updated = self.repository.update_status_cas(
                    job.job_id,
                    expected=RuntimeJobStatus.INTERRUPTED,
                    next_status=RuntimeJobStatus.RECOVERY_PENDING,
                    reason_code="artifact_review",
                    worker_id="recovery",
                    lease_id="",
                )
                if updated is not None:
                    recovered.append(job.job_id)
            elif job.status == RuntimeJobStatus.INTERRUPTED:
                incomplete.append(job.job_id)
        return RecoveryResponse(
            recovered_jobs=recovered,
            interrupted_jobs=interrupted,
            incomplete_artifacts=incomplete,
            rerun_started=False,
        )
