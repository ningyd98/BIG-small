# Phase 11.1 Design

Phase 11.1 adds runtime orchestration and persistence to the Phase 11 Simulation Workbench.

Design decisions:

- API calls create persistent jobs and return `QUEUED`.
- SQLite is the default persistent repository.
- State transitions use a strict state machine and CAS updates.
- Workers require leases and heartbeat.
- Runtime events and metrics are persisted for query and WebSocket replay.
- Cancel, timeout, retry, recovery, attempts, queue, and worker health are exposed through API.
- MuJoCo runtime acceptance is separate from MuJoCo readiness.

No real controller route, real robot adapter, MoveIt execute path, or hardware verifier is added.
