# Event-triggered edge autonomy

This document describes the Phase 6.1 event-triggered edge autonomy path as implemented and verified in this repository.

## Scope

Implemented scope:

- `EVENT_TRIGGERED_EDGE_AUTONOMY` is advertised together with `PERIODIC_CLOUD_SUPERVISION`.
- `AUTO` control mode remains out of scope and is not advertised by the API.
- Edge events are persisted through `EventAutonomyRepository`.
- Local retry decisions are budgeted through `RetryBudgetService`.
- Budget exhaustion creates a `FailureSummary`, a `LocalReplanningRequest`, and an outbox message, then leaves execution waiting for cloud update.
- Task completion is evaluated by `CompletionEvaluator`; step exhaustion alone is not sufficient.

Out of scope:

- Skill caching.
- AUTO mode selection.
- Dual-mode automatic switching.
- Risk scheduling.

## Runtime flow

The verified local retry path is:

```text
TaskExecutor
→ SafetySkillExecutor pre-check
→ robot action
→ SafetySkillExecutor post-check
→ CompositeEventDetector
→ EventTriggeredModeController
→ LocalRecoveryManager.evaluate
→ RetryBudgetService.consume_if_available
→ RETRY_STEP
→ re-run same TaskStep through SafetySkillExecutor
```

The regression test `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step` verifies the robot action sequence:

```text
APPROACH, GRASP, GRASP, LIFT, MOVE_TO_REGION, PLACE, RELEASE, VERIFY_RESULT
```

The required shorter invariant is therefore also true:

```text
APPROACH, GRASP, GRASP, PLACE
```

## Persistent state

The controller stores event-mode state through the configured `EventAutonomyRepository`, not process-local dictionaries. The SQLite implementation creates tables for events, retry budgets, attempts, state transitions, summaries, replan requests/results, outbox, audit events, and plan versions.

Verified by:

- `scripts/verify_phase6.py` checks 10-15.
- `tests/test_phase6_e2e_executor.py::test_sqlite_restart_preserves_state`.
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims`.

## Production configuration

`EventTriggeredModeController(runtime_profile="production")` rejects missing repository configuration. Production must explicitly provide SQLite or another durable repository implementation. In-memory repositories are for tests and CI only.
