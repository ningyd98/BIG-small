from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.models import WorkerStatusView
from cloud_edge_robot_arm.simulation_runtime.repository import SimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.resource_limits import SimulationResourcePolicy
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

LOGGER = logging.getLogger(__name__)


class SimulationJobDispatcher:
    def __init__(
        self,
        *,
        repository: SimulationJobRepository,
        artifact_root: Path,
        resource_policy: SimulationResourcePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_root = artifact_root
        self.resource_policy = resource_policy or SimulationResourcePolicy()
        self._workers = [
            SimulationWorker(
                worker_id="mock-worker-1",
                backend="MOCK",
                repository=repository,
                artifact_root=artifact_root,
            ),
            SimulationWorker(
                worker_id="mujoco-worker-1",
                backend="MUJOCO",
                repository=repository,
                artifact_root=artifact_root,
            ),
            SimulationWorker(
                worker_id="isaac-blocked-worker-1",
                backend="ISAAC_SIM",
                repository=repository,
                artifact_root=artifact_root,
            ),
        ]
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="simulation-dispatcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def poll_once(self) -> bool:
        consumed = False
        for worker in self._workers:
            consumed = worker.poll_once() or consumed
        return consumed

    def workers(self) -> list[WorkerStatusView]:
        return [
            WorkerStatusView(
                worker_id=worker.worker_id,
                backend=worker.backend,
                status="BUSY" if worker.active_job_id else "IDLE",
                active_job_id=worker.active_job_id,
                heartbeat_at=None,
            )
            for worker in self._workers
        ]

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.repository.expire_leases()
                consumed = self.poll_once()
            except Exception:  # pragma: no cover - defensive dispatcher guard
                LOGGER.exception("simulation dispatcher iteration failed")
                consumed = False
            time.sleep(0.01 if consumed else 0.05)
