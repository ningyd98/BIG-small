"""仿真 job 仓库协议。

服务和 worker 只依赖这个 Protocol，因此 SQLite 可以作为默认真源，
InMemory/临时 SQLite 可以用于测试。状态更新必须由实现层保证 CAS 和事件序列。
"""

from __future__ import annotations

from typing import Protocol

from cloud_edge_robot_arm.simulation_runtime.models import (
    RuntimeJobStatus,
    SimulationBatchRecord,
    SimulationJobAttempt,
    SimulationJobEvent,
    SimulationJobLease,
    SimulationJobRecord,
)


class SimulationJobRepository(Protocol):
    """运行时持久化接口。"""

    def create_job(
        self,
        *,
        run_id: str,
        batch_id: str,
        backend: str,
        scenario_id: str,
        control_mode: str,
        seed: int,
        manifest_id: str,
        reproducibility_hash: str,
        draft: dict[str, object],
        timeout_seconds: int,
        max_attempts: int,
        artifact_root: str,
        source_commit: str,
        source_tree_hash: str,
        manifest: dict[str, object] | None = None,
        provenance: dict[str, object] | None = None,
    ) -> SimulationJobRecord: ...

    def get_job(self, job_id: str) -> SimulationJobRecord: ...

    def get_job_by_run_id(self, run_id: str) -> SimulationJobRecord: ...

    def list_jobs(self) -> list[SimulationJobRecord]: ...

    def update_status_cas(
        self,
        job_id: str,
        *,
        expected: RuntimeJobStatus,
        next_status: RuntimeJobStatus,
        reason_code: str,
        worker_id: str,
        lease_id: str,
        error_code: str = "",
        error_message: str = "",
    ) -> SimulationJobRecord | None: ...

    def request_cancel(self, job_id: str) -> SimulationJobRecord: ...

    def acquire_lease(
        self, *, worker_id: str, backend: str, lease_ttl_seconds: int
    ) -> SimulationJobLease | None: ...

    def heartbeat_lease(self, lease_id: str, *, lease_ttl_seconds: int) -> None: ...

    def release_lease(self, lease_id: str) -> None: ...

    def expire_leases(self) -> list[str]: ...

    def append_event(
        self,
        job_id: str,
        *,
        event_type: str,
        source: str,
        payload: dict[str, object],
        previous_status: str = "",
        next_status: str = "",
        reason_code: str = "",
    ) -> SimulationJobEvent: ...

    def list_events(self, run_id: str) -> list[SimulationJobEvent]: ...

    def list_stream_events_after(self, sequence: int) -> list[SimulationJobEvent]: ...

    def save_metrics(self, job_id: str, metrics: list[dict[str, object]]) -> None: ...

    def get_metrics(self, run_id: str) -> list[dict[str, object]]: ...

    def save_artifacts(self, job_id: str, artifact_paths: dict[str, str]) -> None: ...

    def get_artifacts(self, run_id: str) -> dict[str, str]: ...

    def create_batch(
        self, *, batch_id: str, manifest: dict[str, object], run_ids: list[str]
    ) -> SimulationBatchRecord: ...

    def get_batch(self, batch_id: str) -> SimulationBatchRecord: ...

    def list_batch_jobs(self, batch_id: str) -> list[SimulationJobRecord]: ...

    def list_attempts(self, run_id: str) -> list[SimulationJobAttempt]: ...

    def start_attempt(self, job_id: str, *, worker_id: str) -> SimulationJobAttempt: ...

    def finish_attempt(
        self,
        job_id: str,
        *,
        attempt: int,
        result: str,
        error: str,
        artifact_paths: dict[str, str],
    ) -> None: ...

    def find_queued_jobs(self) -> list[SimulationJobRecord]: ...

    def find_recoverable_jobs(self) -> list[SimulationJobRecord]: ...
