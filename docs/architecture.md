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
- `experiments`: Phase 8 and Phase 8.1 experiment models, deterministic runner, runtime harness, batch suite, metrics, statistics, artifacts, and reproducibility hashing.
- `repositories`: runtime repositories and event-autonomy repositories with in-memory and SQLite implementations.
- `simulation`: deterministic mock robot adapter, virtual clock, network simulator, world state, MuJoCo physics backend, physics robot adapter, domain randomization, ROS 2 conversion/QoS guards, Isaac independent-process client guards, and fault injection for CI and local tests.

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

## Phase 8.1 validity layer

Phase 8.1 keeps the Phase 8 surface but replaces synthetic runner-side outcomes
with a `RuntimeExperimentHarness` that drives the real execution chain:
`TaskContract -> ContractValidator -> SafetyShield -> TaskExecutor ->
SkillRegistry -> MockRobotAdapter -> repositories / audit`.

This layer also connects PCSC supervision ticks, ETEAC event/replan handling,
AUTO prepare/commit/abort transitions, SQLite restart recovery, and
event-sourced metric recomputation from formal events.

## Phase 9 physical simulation layer

Phase 9 adds a physical backend below the existing safety and task execution
boundaries:

```text
TaskContract
  -> EdgeContractValidator
  -> SafetyShield
  -> TaskExecutor
  -> SkillExecutor
  -> PhysicsRobotAdapter
  -> SimulatorBackend
  -> MuJoCo physics state / contacts / sensor frames
```

`MuJoCoPhysicsBackend` is the core backend for CI and benchmark execution. It
loads an MJCF scene, owns `mujoco.MjModel` and `mujoco.MjData`, advances
simulation with `mj_step`, reads the TCP pose from a site, classifies contacts,
and emits sensor frames. `PhysicsRobotAdapter` maps the 13 high-level skills to
physics-backed actions while keeping MuJoCo types out of the upper runtime.

Isaac Sim, ROS 2, and MoveIt 2 are decoupled. Core imports never require Isaac
private modules or `rclpy`; environment verifiers mark those paths
`BLOCKED_BY_ENV` unless the host is actually ready. Ground truth is evaluation
data only and is not formal control input.

## Phase 9.2 Isaac and paired-backend layer

Phase 9.2 keeps the same boundary but adds a real Isaac runtime acceptance path:

```text
Core Python
  -> IsaacSimBackend / IsaacSimProcessClient
  -> JSONL protocol
  -> ISAAC_SIM_ROOT/python.sh, ISAAC_SIM_ROOT/bin/python, or Isaac Sim 6.0 container
  -> SimulationApp / USD stage / Franka articulation / RGB-D / contacts
```

The standalone Isaac process owns all Isaac imports and writes smoke evidence
under `artifacts/phase9_2/isaac`. Core Python only validates protocol messages,
artifact provenance, sensor presence, forbidden log markers, and process
identity. Source guards and protocol fixtures do not count as runtime
validation.

Cross-backend validation pairs MuJoCo and Isaac artifacts by scenario and seed.
It checks backend identity, run id uniqueness, commit SHA, config hash, result
hash, process/environment provenance, required metric completeness, and metric
deltas. Isaac failures are rejected; MuJoCo fallback is never accepted as Isaac
evidence.

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
- Phase 8.1 experimental validity: `scripts/verify_phase8_1.py`.
- Phase 8.2 sensitivity and closed-loop validity: `scripts/verify_phase8_2.py`.
- Phase 9 MuJoCo readiness and guarded Isaac/ROS checks: `scripts/verify_phase9.py`.
- Phase 9.1 ROS 2 / MoveIt runtime acceptance: `scripts/verify_phase9_1.py`.
- Phase 9.2 Isaac and MuJoCo-Isaac acceptance: `scripts/verify_phase9_2_environment.py`, `scripts/verify_phase9_2_isaac_smoke.py`, `scripts/run_phase9_2_cross_backend.py`, and `scripts/verify_phase9_2.py`.
