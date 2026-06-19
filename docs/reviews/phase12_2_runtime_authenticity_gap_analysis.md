# Phase 12.2 Runtime Authenticity Gap Analysis

## Baseline

- Baseline commit: `74f1b4b81bbc0ebb0d0772d6050c287d5a3b6d0c`
- Phase 12 smoke remains pipeline-only evidence.
- Phase 12.1 validation generated 540 rows, including Isaac and MoveIt environment blockers.
- Real hardware boundary remains unchanged: no controller contact, no hardware write operation, and no physical motion.

## Gaps Found

1. `actual_runner_invoked` mixed adapter attempts, environment checks, and real runtime execution.
2. Isaac and MoveIt environment blockers used actual-run execution sources even when runtime was never entered.
3. F20 projected Phase 11.1 runtime semantics from a Phase 8 runner instead of exercising repository, lease, worker, recovery, and duplicate competition behavior.
4. Paired MuJoCo/Isaac comparison reported structural pairing without distinguishing usable authoritative pairs from blocked pairs.
5. Metrics lacked per-field provenance, so adapter-derived and placeholder values could enter thesis statistics.
6. Planner comparison inferred provider behavior from control mode and used fixed latency values.

## Phase 12.2 Design Decisions

- Keep `actual_runner_invoked` as a compatibility field, but add authoritative runtime fields:
  `adapter_attempted`, `environment_check_completed`, `runtime_invoked`, `runtime_completed`, and `blocker_stage`.
- Treat environment blockers as environment-check evidence, not runtime evidence.
- Require F20 to produce Phase 11.1 runtime receipts from an isolated SQLite repository, worker lease, attempts, events, metrics, terminal artifacts, stale lease recovery, and duplicate worker competition.
- Add metric provenance and let statistics use only `MEASURED` and `EVENT_DERIVED` metrics by default.
- Keep blocked Isaac paired rows in the structure but mark `paired_backend_experiment_accepted=false` until both sides complete runtime.
- Keep full profile blocked until validation authenticity checks pass; do not run full profile in Phase 12.2.

## Full Profile Readiness

Validation can declare `PHASE12_FULL_PROFILE_READY` only when:

- Validation rows have zero synthetic samples.
- Blocked rows have `runtime_invoked=false`.
- F20 runtime receipts exist and hash-check.
- Worker lease and duplicate competition evidence exist.
- Metric provenance is complete.
- Placeholder metrics are excluded from statistics.
- Paired backend counts distinguish blocked and usable authoritative pairs.

This readiness is not full acceptance. Full profile still requires the larger sample policy and environment coverage.
