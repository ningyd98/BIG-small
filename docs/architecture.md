# BIG-small Architecture

BIG-small uses a cloud-edge architecture with deterministic edge execution and cloud-side planning/supervision services.

## Components

- `contracts`: Pydantic models, enums, traceable messages, and JSON Schema exports.
- `edge.runtime`: contract validation, command replay defense, task state machine, skill execution, retry policy, restart recovery, and `TaskExecutor`.
- `edge.safety`: SafetyShield, safety context builder, runtime telemetry/scene providers, stop controller, and 21 safety rules.
- `edge.event_mode`: event-triggered autonomy controller and state machine.
- `edge.recovery`: deterministic local recovery evaluation, local recovery executor, and repository-backed retry budget service.
- `edge.outbox`: pending-message repository protocol and dispatcher.
- `cloud.planning`: initial planning pipeline and planner adapters.
- `cloud.supervision`: periodic cloud supervisory control and supervision repositories.
- `cloud.replanning`: local replanning service and replanner adapters.
- `cloud.api`: FastAPI API for planning, supervision, event autonomy, summaries, replanning, and completion reports.
- `skill_cache`: Phase 7 high-level skill template cache, statistics, promotion/quarantine/invalidation, and InMemory/SQLite persistence.
- `risk`: Phase 7 deterministic risk evaluator and versioned risk policy.
- `auto_mode`: Phase 7 AUTO selector, persisted decisions/status/transitions, and mode transition lifecycle.
- `experiments`: Phase 8 experiment models, deterministic runner, batch suite, metrics, statistics, artifacts, and reproducibility hashing.
- `repositories`: runtime repositories and event-autonomy repositories with in-memory and SQLite implementations.
- `simulation`: deterministic mock robot adapter, virtual clock, network simulator, world state, and fault injection for CI and local tests.

## Phase 6.1 event autonomy layer

The Phase 6.1 layer adds a durable event-triggered loop without implementing Phase 7 AUTO features.

Stable interfaces:

- `EventAutonomyRepository`: persistence boundary for events, retry budgets, state, summaries, replan requests/results, outbox, plan-version CAS, and audit events.
- `EventTriggeredModeController`: event-mode orchestration and state persistence.
- `RetryBudgetService`: repository-backed retry allowance and atomic consumption.
- `LocalReplanningService`: cloud-side request validation, adapter call, result validation, CAS update, and persistence.
- `CompletionEvaluator`: deterministic completion verification.

## Runtime data flow

```text
TaskContract
  -> TaskExecutor
  -> SafetySkillExecutor pre-check
  -> RobotAdapter action
  -> SafetySkillExecutor post-check
  -> CompositeEventDetector
  -> EventTriggeredModeController
  -> RetryBudgetService or FailureSummary/LocalReplanningRequest
  -> EventAutonomyRepository
  -> OutboxDispatcher/API retrieval
```

`RETRY_STEP` keeps the same step index and re-enters the same SafetyShield-protected execution path.

## Phase 7 Skill Cache, Risk, and AUTO

Phase 7 adds decision-support services around the two existing execution modes. AUTO is not a third execution engine. It only selects between `PERIODIC_CLOUD_SUPERVISION` and `EVENT_TRIGGERED_EDGE_AUTONOMY`, or chooses keep current, request observation, pause, or safe stop.

`SkillCacheRepository` persists high-level `SkillTemplate` records and `SkillExecutionRecord` statistics. It never stores joint-angle sequences, PWM, motor commands, servo pulses, or unverified low-level trajectories. Cache hits still require fresh contract generation/validation, current-scene parameter resolution, and `SafetyShield`.

`RiskEvaluator` produces versioned `RiskSnapshot` records with task, scene dynamics, perception, network, execution, and safety risk components. Missing inputs fail closed and SafetyShield emergency stop hard-overrides to CRITICAL.

`AutoModeSelector` uses risk snapshots, cache lookup results, contract/checkpoint readiness, supervision availability, event autonomy readiness, and switch history. It enforces dwell time, cooldown, switch limits, and atomic-step safe boundaries.

`ModeTransitionService` models prepare/commit/abort transitions with idempotency keys and expected mode versions. `AutoModeRepository` persists risk snapshots, decisions, statuses, switch history, and prepared transitions through restart.

## SQLite event-autonomy tables

The SQLite event-autonomy repository creates:

- `edge_events`
- `recovery_budgets`
- `recovery_attempts`
- `event_mode_states`
- `event_mode_transitions`
- `failure_summaries`
- `completion_summaries`
- `replan_requests`
- `replan_results`
- `event_outbox`
- `event_audit_events`
- `plan_versions`

The tested CAS paths are retry-budget consumption, plan-version advance, and outbox claim.

## Phase 8 experiment layer

Phase 8 is an evidence layer around the stable Phase 3-7 architecture. It adds
`ExperimentConfig`, `ScenarioDefinition`, `FaultEvent`, `ExperimentRun`,
`ExperimentResult`, `MetricSummary`, a virtual clock, network simulator, scenario
registry, runner, batch runner, statistics, artifact writer, and reproducibility
hashing.

The runner exposes a unified PCSC/ETEAC/AUTO interface. AUTO remains a selector:
formal `initial_mode` and `final_mode` are only
`PERIODIC_CLOUD_SUPERVISION` or `EVENT_TRIGGERED_EDGE_AUTONOMY`. Safety
counterfactuals are shadow metrics only and do not enter `TaskExecutor`.

## Production boundary

Production mode must explicitly configure durable and real integrations. Test defaults may use mock adapters, fake clocks, and in-memory repositories, but production constructors reject missing durable dependencies where production mode is enforced.

When `AUTO_MODE_ENABLED=true` in production, `SKILL_CACHE_BACKEND`, `SKILL_CACHE_DB_PATH`, `AUTO_MODE_REPOSITORY`, `AUTO_MODE_DB_PATH`, `RISK_POLICY_VERSION`, `RISK_COMPONENT_WEIGHTS`, and `RISK_LEVEL_THRESHOLDS` must be explicit. Production AUTO rejects InMemory repositories, fake/mock providers, static network data, and missing risk policy.

## Verification references

- Phase 3 safety: `scripts/verify_phase3.py`, `scripts/verify_phase3_1.py`, `scripts/verify_phase3_2.py`.
- Phase 4 planning: `scripts/verify_phase4.py`.
- Phase 5 supervision: `scripts/verify_phase5.py`.
- Phase 6.1 event autonomy: `scripts/verify_phase6.py` and `tests/test_phase6_e2e_executor.py`.
- Phase 6.2 checkpoint/replan closure: `scripts/verify_phase6_2.py`.
- Phase 7 skill cache, risk, AUTO, and transition closure: `scripts/verify_phase7.py`.
- Phase 8 reproducible experiments: `scripts/verify_phase8.py`.
