# Dashboard User Guide

## Start Locally

```bash
scripts/start_dashboard_dev.sh
```

Open the Vite URL printed by the frontend server. By default the backend uses local-only auth, reads artifacts from `artifacts`, and disables software experiment writes.

To enable software experiment writes for local testing:

```bash
DASHBOARD_EXPERIMENT_WRITES_ENABLED=true scripts/start_dashboard_dev.sh
```

## Build And Test

```bash
scripts/build_dashboard.sh
```

For the Phase 10.2B acceptance verifier:

```bash
python scripts/verify_phase10_2b.py
```

Use `--skip-e2e` only when a browser runtime is unavailable.

## Pages

- Overview: authoritative project status, hardware boundary, blockers, and latest evidence.
- Simulation Lab: start and cancel allowlisted software experiments when writes are enabled.
- Task Execution: read-only runtime and active experiment status.
- Safety Acceptance: acceptance ladder and safety reviewer notes.
- Evidence: indexed evidence list, detail, download, and record comparison.
- Comparison: Phase 8 baseline metrics loaded from artifacts.
- Audit: dashboard event stream replay.

## Operator Expectations

The dashboard should be treated as a review console. It can show planning-only or simulation-only evidence, but it does not prove real hardware validation. Any hardware claim beyond planning must come from a later phase with real controller evidence and a separate acceptance process.
