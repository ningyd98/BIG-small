# Local recovery

Phase 6.1 local recovery is deterministic and repository-backed.

## Components

- `LocalRecoveryManager`: evaluates an `EdgeEvent` and returns a `LocalRecoveryDecision`. It does not execute robot actions and does not return fake success.
- `LocalRecoveryExecutor`: executes explicit local recovery actions when configured with a `SafetySkillExecutor`.
- `RetryBudgetService`: owns retry budget initialization, allowance checks, atomic consumption, result audit, and budget retrieval.
- `TaskExecutor`: executes the actual retry by re-running the same `TaskStep` after `EventTriggeredModeController` returns `RETRY_STEP`.

## Safety boundary

Every retry attempt is a normal `SafetySkillExecutor.execute_attempt` call. This means each retry re-reads telemetry and scene, rebuilds `SafetyContext`, runs SafetyShield pre-check, executes the skill, and then runs post-check after successful robot action.

Verified by:

- `scripts/verify_phase6.py` checks 4-8.
- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step`.

## Retry budget semantics

`RetryBudgetService` uses a task-level remaining pool and computes the effective allowance for a current retry as:

```text
min(current_step.retry_limit, skill_policy.limit, task_remaining_limit, safety_policy.limit)
```

The repositories consume retry budget with compare-and-swap semantics:

- In-memory: lock-protected compare of `retry_count_used`.
- SQLite: single transactional `UPDATE ... WHERE retry_count_used = ? AND remaining_retries > 0` plus `recovery_attempts` insert.

Verified by:

- `tests/test_phase6_e2e_executor.py::test_budget_cas_prevents_double_consume`.
- `scripts/verify_phase6.py` checks 8 and 9.

## Failure behavior

If budget is exhausted, local recovery does not continue to the next step. The controller creates and persists a failure summary and replan request, enqueues an outbox message, and transitions to `WAITING_CLOUD_REPLAN` / runtime `WAITING_CLOUD_UPDATE`.
