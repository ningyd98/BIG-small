from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationResourcePolicy:
    mock_max_concurrency: int = 4
    mujoco_max_concurrency: int = 1
    isaac_max_concurrency: int = 1
    phase8_max_concurrency: int = 2
    max_queued_jobs: int = 500
    max_batch_runs: int = 120
    max_log_bytes: int = 2_000_000
    max_event_count: int = 20_000
    max_runtime_seconds: int = 900

    def concurrency_for(self, backend: str) -> int:
        if backend == "MOCK":
            return self.mock_max_concurrency
        if backend == "MUJOCO":
            return self.mujoco_max_concurrency
        if backend == "ISAAC_SIM":
            return self.isaac_max_concurrency
        return self.phase8_max_concurrency
