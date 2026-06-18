# Phase 11.1 Runtime Orchestration Gap Analysis

Baseline `9ca80f89ae606a3811a162d11d213981e37ba883` completed the Phase 11 Simulation Workbench, but the runtime path still had orchestration gaps:

- `create_run()` could execute the run synchronously inside the request path.
- Batch creation could serially call run creation and wait on individual work.
- Runtime state was primarily process memory plus artifacts, so service restart could lose queryable state.
- WebSocket replay depended on in-memory event history and could miss persisted state changes.
- Cancel requests were best-effort and did not model `CANCEL_REQUESTED -> CANCELLING -> CANCELLED`.
- Timeout, retry, lease expiry, duplicate consumption prevention, and orphan recovery were not first-class runtime concepts.
- Artifacts could be produced, but a fresh service could not rebuild queryable history from them.
- MuJoCo was reported as ready, but Phase 11 evidence did not include runtime acceptance runs.

Phase 11.1 adopts an asynchronous runtime:

FastAPI accepts a draft, writes a persistent job, returns `QUEUED`, and lets a dispatcher lease jobs to allowlisted workers. SQLite is the default repository, with CAS state transitions, per-run sequences, global stream sequences, leases, attempts, metrics, and artifact references. Existing `/api/v1/simulation/*` paths stay compatible; new `/runtime/*`, attempts, retry, batch cancel, and recovery endpoints expose the orchestration layer.

The work remains simulation-only. It does not add real robot adapters, does not contact controllers, and preserves `real_controller_contacted=false`, `hardware_motion_observed=false`, and `hardware_write_operations=[]`.
