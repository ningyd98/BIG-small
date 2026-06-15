# Phase 8 Gap Analysis

Phase 8 builds an experiment system on top of the stable Phase 3-7 control
surface. It does not redesign `TaskContract`, `SafetyShield`, `TaskExecutor`,
event autonomy, replanning, Skill Cache, RiskEvaluator, AutoModeSelector, or
ModeTransitionService.

## Reusable Modules

- `contracts.models`: `TaskContract`, `CloudCommand`, `CommandAck`, `EdgeEvent`,
  `CompletionSummary`, `RiskSnapshot`, `AutoModeDecision`, transition enums, and
  shared control modes.
- `edge.runtime.TaskExecutor`: canonical TaskContract execution path protected
  by `SafetyShield`.
- `edge.safety`: SafetyShield, safety decisions, safety providers, and stop
  semantics.
- `cloud.supervision`: PCSC concepts, periodic supervisor service, decisions,
  and supervision persistence.
- `edge.event_mode`, `edge.recovery`, `cloud.replanning`: ETEAC events, retry
  budgets, failure summaries, local replanning, CAS apply, and restart recovery.
- `skill_cache`: high-level template cache, execution records, promotion,
  quarantine, invalidation, idempotency, and SQLite restart recovery.
- `risk`: versioned deterministic `RiskEvaluator` and fail-closed
  `RiskPolicy`.
- `auto_mode`: AUTO selector over PCSC/ETEAC and persisted mode transitions.
- `repositories`: InMemory/SQLite task, event-autonomy, skill-cache, and
  auto-mode repositories.
- `simulation.mock_robot`: deterministic MockRobotAdapter and fault injection
  hooks for CI.

## Missing Experiment Infrastructure

- No Phase 8 experiment domain models or schema versioning.
- No deterministic discrete-event virtual clock with priority and insertion
  ordering.
- No seed-driven network simulator for latency, jitter, loss, duplication,
  reordering, outage, bandwidth accounting, timeout, and cloud unavailability.
- No canonical scenario registry for the 15 required scenarios.
- No unified runner for PCSC, ETEAC, and AUTO experiments.
- No batch runner, smoke/full suite matrix, or command-line entry point.
- No metrics/statistics layer for raw run metrics, Wilson confidence intervals,
  deterministic bootstrap, CSV/JSON summaries, or Markdown reports.
- No reproducibility hashing that ignores wall-clock fields.
- No artifact writer for manifest, JSONL events/runs, summary files, and
  generated report.

## Data Model Extensions

Phase 8 should add experiment-local models rather than changing Phase 3-7
persistent models:

- `ExperimentConfig`, `ScenarioDefinition`, `FaultEvent`, `ExperimentRun`,
  `ExperimentResult`, `MetricSummary`, and artifact manifests.
- Explicit experiment enums for mode aliases, scenario ids, network profiles,
  fault types, cache policies, ablations, result status, event types, and
  metric units.
- `ExperimentResult` should include observed metrics, derived metrics,
  counterfactual metrics, reproducibility hashes, and metadata.

No existing serialized Phase 3-7 models need modification for Phase 8.

## Required Tests

- Config validation, duplicate scenario ids, mode validation, seed boundaries,
  and units.
- Virtual clock ordering, same-timestamp priority ordering, maximum duration,
  and no real sleep.
- Network profiles and deterministic fault behavior.
- One key behavior per required scenario.
- PCSC/ETEAC/AUTO runner smoke tests and AUTO-as-selector checks.
- Risk/mode switching dwell, cooldown, switch limit, emergency stop, and
  insufficient evidence through the experimental path.
- Skill Cache hit/miss/promotion/quarantine/invalidation and cache ablations.
- Stale, duplicate, reordered, idempotency, and CAS command handling metrics.
- SQLite restart during experiment state writes.
- Reproducibility hash equality for same config+seed and controlled variation
  for different seeds.
- Artifact parseability and stable summary columns.
- Phase 3-7 acceptance regressions via `scripts/verify_phase8.py`.

## Compatibility Risks

- Existing Phase 7 docs and tests assume AUTO is not an execution engine; Phase 8
  must preserve that and record AUTO decisions as mode selections only.
- Experiment timestamps must separate virtual time from wall-clock metadata so
  reproducibility hashes remain stable.
- Safety counterfactuals must be computed as shadow metrics only; unsafe actions
  must not enter `TaskExecutor`.
- SQLite restart tests must use existing repositories and idempotency semantics
  rather than inventing replacement persistence.
- The experiment framework must not add a mandatory plotting dependency or
  require network access, ROS 2, real hardware, a real camera, or production LLM.
