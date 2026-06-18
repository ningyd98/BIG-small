# Simulation Workers And Leases

`SimulationJobDispatcher` owns allowlisted workers:

- `MockWorker` through the `MOCK` backend.
- `MuJoCoWorker` through the `MUJOCO` backend.
- `BlockedBackendWorker` behavior for environment-blocked backends such as Isaac when unavailable.

Workers acquire a SQLite lease before execution. The lease has a TTL and heartbeat; expired leases are marked `INTERRUPTED` for recovery. This prevents two service instances from consuming the same queued job.

Default concurrency policy:

- Mock: up to 4 logical jobs.
- MuJoCo: 1 logical job.
- Isaac: 1 logical job when available, otherwise blocked.
- Global queue limit: 500.
- Batch run limit: 120.

Workers run only fixed code paths and never execute arbitrary shell commands.
