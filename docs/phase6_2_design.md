# Phase 6.2 Design

Phase 6.2 closes the event-triggered edge autonomy loop without starting Phase 7.
The scope is validation, hardening, tests, documentation, and CI only.

## Authoritative State

The authoritative checkpoint source is `EventAutonomyRepository`. The edge writes
`ExecutionCheckpoint` records when a task starts, a step starts, a step succeeds,
a step fails, cloud replanning is requested, resume starts, and completion is
verified. Cloud replanning must read active contract, triggering event,
`FailureSummary`, and latest checkpoint from the same repository. Request IDs are
identifiers only; the system must not infer `task_id` by slicing request strings.

`InMemoryEventAutonomyRepository` is only for tests and simulation. Durable
restart acceptance uses `SQLiteEventAutonomyRepository`.

## Replan Merge Rules

`ReplanMergeValidator` validates partial replans before a new contract is
assembled.

- Completed step IDs must exactly match the checkpoint.
- Completed steps must remain present, byte-for-byte unchanged, and in the same
  order.
- Replacement steps cannot reuse a completed `step_id`.
- The merged contract cannot contain duplicate step IDs.
- Completed non-repeatable skills such as `GRASP`, `PLACE`, and `RELEASE` cannot
  be regenerated.
- Low-level actuator fields and safety bypass fields are rejected.

`ReplanContractAssembler` creates the new trusted contract only after validator
approval. The new contract carries strictly higher `plan_version` and
`command_seq`, points `current_step_id` at the first pending step, and preserves
the completed prefix from the previous active contract.

Time-sensitive replanning components accept injectable clocks. `LocalReplanningService`,
`ReplanApplyService`, `ReplanContractAssembler`, and replanner adapters must use
their configured clock for response timestamps, contract assembly, validation,
acknowledgement, and rejection records.

## CAS And Idempotency

`ReplanApplyService` is the single writer for active contract updates. It uses
`advance_active_contract_if_current()` with expected `plan_version` and
`command_seq`. A stale result based on an older active contract returns
`VERSION_CONFLICT`; it cannot overwrite the newer active contract.

Repository idempotency is hash based:

- Same idempotency key and same payload returns the stored object.
- Same idempotency key with different payload raises `IdempotencyConflictError`.
- Duplicate completion evidence uses deterministic `cs-{task_id}` summary IDs
  and semantic `summary_hash`; the same evidence returns the original summary,
  while conflicting evidence is rejected.

## Crash Recovery

Crash recovery flow:

1. Edge executes until a retry budget is exhausted.
2. Edge persists event, `FailureSummary`, replan request, outbox message, and
   checkpoint.
3. Process objects may be destroyed.
4. Cloud or a restarted process reopens the same SQLite database.
5. The cloud reads active contract, event, summary, and checkpoint from SQLite.
6. Replanning is generated and applied through CAS.
7. A restarted `TaskExecutor` resumes from the persisted checkpoint and the new
   active contract.
8. Completed steps are skipped; the failed step is re-executed under the new
   contract; later steps continue normally.

## Completion Evidence

Task success is not declared by callers. `TaskExecutor._complete_task()` invokes
`CompletionEvaluator`, which checks step completion, terminal state,
completion criteria, final safety decision, robot state, target state, scene
freshness, critical events, and `VERIFY_RESULT`.

The cloud completion API also evaluates evidence before persisting a summary.
Forged or incomplete completion requests return 422 and do not create
`CompletionSummary` records.

## Boundaries

Still not implemented in Phase 6.2:

- Phase 7 skill cache.
- AUTO mode selection or dual-mode automatic switching.
- Risk-based scheduling.
- Real robot, real telemetry, and real scene providers.
- External planner production adapter execution in CI.

Phase 7 has not started.
