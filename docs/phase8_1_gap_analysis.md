# Phase 8.1 Gap Analysis

Phase 8 added a deterministic experiment framework, but its runner still mixes
formal production services with synthetic experiment-side outcomes. Phase 8.1
keeps the Phase 8 models, CLI, scenarios, artifacts, and reproducibility
surface, and replaces those synthetic outcomes with a runtime harness that
drives the Phase 3-7 control chain.

## Synthetic Behavior Found

- `ExperimentRunner._run_network_warmup()` schedules network deliveries and then
  calls `VirtualClock.run_until_idle()` before task execution. Because scenario
  faults are already scheduled on the same clock, dynamic faults fire before any
  atomic step starts.
- `ExperimentRunner._execute_step()` advances virtual time, records telemetry and
  commands, records `SafetyDecision.ALLOW`, marks completed steps, and recursively
  simulates grasp retry. It does not call `TaskExecutor`.
- Scenario branches in `_execute_scenario()` directly set safety, replan, cache,
  SQLite restart, and command rejection counters.
- S10 currently records stale, duplicate, and reordered command counters without
  delivering malformed or stale commands to the edge command validation path.
- `_cloud_invocations()` derives cloud calls from completed step counts and mode
  formulas instead of supervisor, planner, or replanning service records.
- Fault detection and recovery latency are assigned constants in `_apply_fault()`
  rather than derived from fault, detection, ACK, and recovery events.
- `_switch_mode()` calls `ModeTransitionService.prepare()` and then immediately
  mutates `current_mode`; no persisted status commit/abort boundary is exercised.
- `_simulate_sqlite_restart()` only reopens auto-mode and event-autonomy
  repositories after a minimal write; it does not continue through crash points
  involving risk snapshots, decisions, transitions, replans, checkpoints, outbox,
  command ACKs, or skill execution statistics.

## Existing Production Entrypoints

- Contract validation and command acceptance:
  `edge.contract_validator.EdgeContractValidator.accept_payload()` and
  `TaskRepository.accept_command()` in `repositories.memory` and
  `repositories.sqlite`.
- Execution:
  `edge.runtime.task_executor.TaskExecutor.submit_contract()` already performs
  `TaskContract -> EdgeContractValidator -> TaskStateMachine -> SafetyShield ->
  SafetySkillExecutor -> SkillRegistry -> MockRobotAdapter -> repositories`.
- Safety:
  `edge.safety.shield.SafetyShield` and `edge.safety.safety_skill_executor`
  emit safety audit events into the runtime repository.
- PCSC:
  `cloud.supervision.service.PeriodicSupervisorService.evaluate_snapshot()` and
  `cloud.supervision.repository.*SupervisionRepository` persist snapshots,
  supervisor decisions, planner invocation flags, version CAS, and audit events.
- ETEAC:
  `edge.event_mode.controller.EventTriggeredModeController`,
  `edge.recovery.retry_budget.RetryBudgetService`,
  `cloud.replanning.service.LocalReplanningService`, and
  `cloud.replanning.apply_service.ReplanApplyService` cover event detection,
  retry budget consumption, failure summaries, outbox, cloud replan, CAS apply,
  ACK persistence, checkpoint merge, and resume.
- Mode switching:
  `auto_mode.selector.AutoModeSelector`, `auto_mode.transition_service`, and
  `auto_mode.repository.*AutoModeRepository` support persisted risk snapshots,
  decisions, prepared transitions, statuses, commit, abort, idempotency, and
  restart lookup.
- Skill cache:
  `skill_cache.repository.*SkillCacheRepository` supports trusted lookup,
  execution records, promotion, quarantine, invalidation, CAS, idempotency, and
  SQLite restart.
- SQLite recovery:
  Runtime, supervision, event autonomy, auto-mode, and skill-cache repositories
  already have persistent implementations; Phase 8.1 needs an experiment-level
  restart harness that closes and reconstructs services around the same files.

## Integration Strategy

- Add `RuntimeExperimentHarness` as the only experiment assembly layer. It will
  construct real contracts, repositories, `TaskExecutor`, `SafetyShield`,
  `MockRobotAdapter`, `PeriodicSupervisorService`,
  `EventTriggeredModeController`, `LocalReplanningService`,
  `ReplanApplyService`, `RiskEvaluator`, `AutoModeSelector`,
  `ModeTransitionService`, and cache repositories.
- Add optional observer hooks to production execution components with no default
  behavior change. The hooks will mirror repository/audit facts into experiment
  events and advance `VirtualClock` during mock action execution.
- Remove pre-task `run_until_idle()`. Faults use absolute virtual time and run
  only when task execution or explicit network delivery advances the clock.
- Make command consistency experiments call a harness command-ingress method that
  uses `EdgeContractValidator`, repository command acceptance, scene-version
  checks, and persisted `CommandAck` records.
- Make AUTO transitions persist decision and prepared transition first, then
  commit or abort only through harness methods at a step boundary. The current
  mode is read from committed `AutoModeStatus`.
- Add `ExperimentMetricsCollector` to rebuild metrics from formal events,
  runtime repositories, command ACKs, supervisor decisions, replan/apply records,
  mode transition records, safety audit events, network events, and cache records.

## Required Adapters And Fixtures

- `VirtualClockAdapter`: exposes `now()` and `monotonic()` for services that use
  clock protocols.
- `ExperimentTelemetryProvider` and `ExperimentSceneProvider`: deterministic
  safety providers backed by virtual time, `MockRobotAdapter`, and
  `SimulatedWorld`.
- `ExperimentExecutionObserver`: records step start/completion/failure, safety
  evaluations, and task terminal evidence without deciding outcomes.
- `ObservableMockRobotAdapter`: or optional `MockRobotAdapter` callbacks for
  action start/finish and virtual action duration advancement.
- `CountingPlannerAdapter` and `CountingReplannerAdapter`: deterministic mock
  adapters that emit formal cloud invocation events while keeping planner output
  high level.
- Temporary SQLite fixture directories for S15 crash points C1-C9. The fixture
  must close and recreate repositories/services rather than reusing old objects.

## Compatibility Notes

- Phase 3-7 data models do not need incompatible field changes.
- Optional observer/clock parameters must default to current behavior so existing
  constructors, serialization, SQLite payloads, and tests remain compatible.
- `AUTO` remains an experiment mode selector only; committed runtime states are
  still `PERIODIC_CLOUD_SUPERVISION` or `EVENT_TRIGGERED_EDGE_AUTONOMY`.
- Safety counterfactual metrics stay shadow-only and must never feed unchecked
  actions into `TaskExecutor`.
