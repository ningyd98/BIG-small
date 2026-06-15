# Phase 8.1 Design

Phase 8.1 closes the experimental-validity gap left by Phase 8. The goal is not
new robot behavior. The goal is to make the experiment layer drive the existing
Phase 3-7 runtime chain and record evidence from real repositories, ACKs,
safety decisions, execution records, and mode-transition records.

## Scope

- Keep the Phase 8 models, CLI, batch runner, artifacts, and reproducibility
  surface.
- Replace synthetic runner-side outcomes with a `RuntimeExperimentHarness`.
- Preserve production semantics for `TaskExecutor`, `SafetyShield`,
  `PeriodicSupervisorService`, `EventTriggeredModeController`,
  `LocalReplanningService`, `ReplanApplyService`, and `ModeTransitionService`.
- Record metrics only from formal events and repositories.

## Architecture

- `RuntimeExperimentHarness` assembles the real runtime graph with injected
  `VirtualClock`, `MockRobotAdapter`, SQLite/in-memory repositories, safety
  providers, risk evaluation, AUTO selection, and transition services.
- `ExperimentRunner` only schedules faults, advances virtual time, delivers
  commands, and collects results.
- `ExperimentMetricsCollector` rebuilds metrics from audit events, execution
  records, ACK records, supervisor decisions, replanning records, mode
  transitions, safety evaluations, network events, and cache records.

## Evidence Sources

- Contract validation: validator calls and accepted command records.
- Execution: `TaskExecutor` step records, checkpoint state, completion evidence.
- Safety: safety decisions, rejects, emergency-stop records.
- PCSC: supervisor decisions and cloud invocation events.
- ETEAC: retry-budget consumption, failure summaries, replans, CAS apply.
- AUTO: persisted decision, prepared transition, commit, abort, dwell, cooldown,
  and switch-limit records.
- Crash recovery: repository reopen and restart verification.

## Compatibility

- No Phase 3-7 data model changes are required for consumers.
- Optional observer and clock injections default to existing behavior.
- AUTO remains a selector between the two existing execution modes.
