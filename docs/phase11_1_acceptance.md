# Phase 11.1 Acceptance

Accepted only when these are true:

- Runtime API returns queued jobs immediately.
- Background worker completes Mock runs.
- SQLite repository persists jobs, events, metrics, attempts, leases, and artifact paths.
- Cancel, timeout, retry, and recovery paths are verified.
- WebSocket replay uses persisted event sequence.
- Dashboard shows queue, workers, attempts, cancellation, timeout, and recovery state.
- Playwright uses real FastAPI.
- MuJoCo M11-01 through M11-10 pass when `--mujoco` or `--full` is run.
- `real_controller_contacted=false`.
- `hardware_motion_observed=false`.
- `hardware_write_operations=[]`.

Verifier:

```bash
python scripts/verify_phase11_1_simulation_runtime.py --ci
python scripts/verify_phase11_1_simulation_runtime.py --mujoco
python scripts/verify_phase11_1_simulation_runtime.py --full
```

`--ci` does not claim real MuJoCo runtime acceptance. `--full` requires both CI and MuJoCo runtime evidence.
