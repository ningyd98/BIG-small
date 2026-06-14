# Failure summary

A `FailureSummary` is the durable handoff from edge execution to cloud replanning.

## When it is created

`EventTriggeredModeController` creates a failure summary when local recovery cannot continue, including retry-budget exhaustion and replan-required decisions.

The summary is persisted before the outbox request is emitted.

## Contents

The model records at least:

- failed event identity;
- failed step ID and skill;
- completed step IDs;
- retry count and retry limit;
- requested replan scope;
- scene and robot context fields when available;
- deterministic summary hash.

## Repository operations

`EventAutonomyRepository` supports:

- `save_failure_summary`;
- `get_failure_summary`.

Both in-memory and SQLite implementations are available. SQLite stores the original payload in `failure_summaries.payload_json` and indexes by task.

## Verification

Behavior is covered by:

- `scripts/verify_phase6.py` check 12.
- `tests/test_phase6_recovery_replanning.py` failure-summary builder tests.
- `tests/test_phase6_e2e_executor.py` budget-exhaust/replan path checks.

The summary alone does not imply recovery success. Completion is evaluated separately by `CompletionEvaluator` and persisted as a `CompletionSummary` only after verification.
