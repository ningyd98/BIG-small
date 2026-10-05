# Verified Recovery Lifecycle Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and TDD in this session; root arranges independent review. No subagents, commits or shared roadmap edits are authorized.

**Goal:** Persist recovery state and bounded task verification allowances so only current, canonical fresh evidence resolves the particular failure event.

**Architecture:** `edge/recovery/lifecycle.py` owns immutable recovery identity, typed provider inputs and canonical state/progress validation. EventAutonomyRepository owns memory/SQLite state and task verification-pool CAS, including consumption of the existing retry pool in the authorization transaction. Root retains real execution/evaluation/completion wiring; missing providers remain unavailable.

**Tech Stack:** Existing Python dataclasses/Pydantic contracts, canonical T10 condition/evidence validators, existing threading lock and SQLite BEGIN IMMEDIATE. No new dependencies.

**Spec:** Original roadmap `docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md` Task13; v2 `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md` T13; root's approved lifecycle/atomic-producer design messages.

## Global constraints

- Own only new lifecycle.py, repositories/event_autonomy/{protocol,memory,sqlite}.py and new tests/test_recovery_lifecycle_module.py. Root owns retry_budget.py and test_verified_recovery_lifecycle.py, all actual execution/evaluation integration.
- RecoveryRecord has exactly ten planned positional fields; additional source/versions/CAS bindings are keyword-only, with missing values unavailable rather than fabricated valid identities.
- Repository production edits wait for root's acceptance of the frozen activation temporal fix. Design and RED are authorized now.
- No model/network/GPU/render/full-suite/commit/dependency changes. No software fixture success becomes real recovery or physical acceptance; LOCAL_RECOVER remains disabled.
- One task verification pool persists reobservation quota, consecutive no-progress and absolute deadline across every event and restart. Retry quota authority stays in existing RecoveryBudget; remaining_retries in VerificationBudgetState is a read-only mirror, never independently consumed.
- Authorization proof/provider callbacks are frozen before the transaction. Any transaction callback must be pure and cannot read/write its locked repository. The transaction rechecks actual current state and canonical proof.

## Contracts

`RecoveryRecord(recovery_id, event_id, task_id, attempt_id, state, budget_state: VerificationBudgetState, progress_signature, last_verified_at, resolution_observation_id, reason)` uses DETECTED, RECOVERY_AUTHORIZED, RETRY_EXECUTED, VERIFIED_RESOLVED, EXHAUSTED, UNRECOVERABLE. Required current plan/command/episode/condition identities, actual execution receipt/times and CAS revision are additional keyword-only fields. Empty defaults remain unavailable; direct record overwrite/rehashing cannot promote state.

`VerificationBudgetRecord(task_id, state: VerificationBudgetState, revision, created_at, updated_at, content_hash)` is the persisted task envelope. Initialize once and return detached copies. Existing initialization returns the exact existing pool without timestamp/limit/deadline changes.

Repository producers:

- `initialize_verification_budget_if_absent(task_id: str, state: VerificationBudgetState) -> VerificationBudgetRecord`
- `get_verification_budget(task_id: str) -> VerificationBudgetRecord | None`
- `initialize_recovery_if_absent(record: RecoveryRecord) -> RecoveryRecord`
- `get_recovery(recovery_id: str) -> RecoveryRecord | None`
- `list_unresolved_recoveries(task_id: str) -> list[RecoveryRecord]` includes non-resolved exhausted/unrecoverable records; historical VERIFIED_RESOLVED records are excluded.
- `advance_recovery_if_current(record, *, expected_state, expected_revision, expected_budget_revision, verified_transition) -> RecoveryRecord | None` validates immutable identity, monotonic state and current source evidence, then updates recovery/task pool together.
- Approved root RetryBudgetService producer: `consume_retry_and_authorize_recovery_if_current(*, recovery_id: str, expected_recovery_revision: int, expected_verification_budget_revision: int, expected_retry_count: int, step_id: str, skill: str, authorization: RecoveryAuthorizationEvidence) -> RecoveryAuthorizationResult`. Result carries authorized, recovery, retry_budget, verification_budget and reasons; recovery identity supplies task/event. Same transaction reuses the existing retry-consumption rules, checks frozen actual step/skill/safety limits and commits retry counts + authorized recovery + task pool together. Failure consumes nothing; lost transport/authorization is never refunded automatically.

`RecoveryLifecycleService.advance_recovery(recovery_id: str, expected_state: str, next_state: str, verification: Sequence[ConditionVerdict]) -> RecoveryRecord` retains the planned public call. Injected typed evidence/execution providers acquire actual inputs; supplied PASS/VALID labels alone cannot authorize or resolve. `RecoveryAuthorizationEvidence` holds the canonical DecisionEnvelope, actual current CommitContext, ActionEvidenceContract and OnlineEvidenceSnapshot plus immutable recovery/current checkpoint bindings. Repository pure recomputation checks canonical T10 validity and transaction-current task/cancel/versions/checkpoint.

Execution receipts reuse canonical `ReplanExecutionReceipt`; missing provider/receipt remains unavailable. A start receipt proves start, not completion. Root's execution provider must additionally supply actual completed-action/checkpoint time to enter RETRY_EXECUTED and bound a post-execution verification frame; absence must not be filled from wall-clock now or an ACK. Evidence provider supplies the frozen required conditions and actual current OnlineEvidenceSnapshot. Canonical `evaluate_conditions` is recomputed, and supplied verdicts must match; only full nonempty PASS on this event/current versions and a distinct frame acquired after actual execution can resolve.

Progress uses best verified condition/target/spec states and comparable observable residual improvements. Event/attempt/frame/time/confidence/log IDs are excluded. UNKNOWN→valid and FAIL→PASS count; repeated or oscillating previously best states do not. No evidence/old frames remain unresolved and cannot replenish quota; the third consecutive non-progress verification attempt reaches EXHAUSTED with max_no_progress=3. A task exhausted/deadline pool cannot revive under a new event.

## Review focus

- Two SQLite connections race authorization: one successful state/retry/pool transaction, no duplicate quota use.
- A new event or restart proposes new limits/timestamps: preserve complete existing pool and absolute deadline.
- Caller PASS labels, old/wrong-episode/current-version frames and missing execution capability: no VERIFIED_RESOLVED or physical admission.
- Two conditions share a name but differ in target/spec: no forged cross-target residual improvement; no progress from frame IDs or status oscillation.
- Mutation/model_copy/rehashed records or a failed transaction: immutable identity/state/pool preserved, no partial retry/authorization write.

### Task 1: Durable task pool and record boundaries

- [ ] Write pool initialization/deep-copy/two-connection restart and recovery identity tests in test_recovery_lifecycle_module.py.
- [ ] Run scoped RED and retain exact failures before source edits.
- [ ] After root activation acceptance, preserve current repository baseline. Implement strict records/serializers and atomic initialize/get methods under existing locks/BEGIN IMMEDIATE, without updating existing rows.
- [ ] Run scoped GREEN, independent import smoke and root budget regression; record exact commands/results.

### Task 2: Atomic authorization with existing retry quota

- [ ] Write tests for missing/caller-invalid proof, stale state/pool/retry versions, step/skill/task/event/safety/deadline exhaustion, same-event duplicate and two SQLite connections.
- [ ] Verify RED before implementing the typed producer. Factor/reuse current locked retry-consumption calculation without committing a helper transaction early.
- [ ] Recompute proof inside the transaction against current event/active/checkpoint/cancel state; commit all three durable rows together. Missing provider is unavailable and not authorized.
- [ ] Run GREEN and fault-injected restart tests; publish exact producer to root for its consumer without editing retry_budget.py.

### Task 3: Execution and verified event resolution

- [ ] Write tests for authorization/ACK not resolved, missing/start-only completion source, exact receipt identity/ordering, fresh all-PASS resolving only its event, FAIL/UNKNOWN/stale/foreign/empty verdicts remaining unresolved.
- [ ] Verify RED then implement planned advance_recovery with typed providers, canonical recomputation and CAS. Unknown conflicting duplicates/old versions reject; exact transition retries preserve original content.
- [ ] Add restart/list_unresolved assertions: completion may query unresolved records, not every historical failure. Do not wire completion/execution in this ownership.

### Task 4: Monotonic progress and bounded verification

- [ ] Write tests for max_no_progress=3 terminating on third non-progress verification, true UNKNOWN→valid/FAIL→PASS/residual progress, cross-event best-state preservation, repeated old frame/candidate and status oscillation not progress.
- [ ] Verify RED then implement progress signature/task-pool advancement atomically; retries only mirror the authoritative retry pool. Preserve original deadline and spent allowances under restart/new event and rejected/stale concurrent writes.
- [ ] Run targeted lifecycle/retry/activation/canonical regression CPU tests plus scoped Ruff/mypy/import smoke. Preserve logs, exact owned/dependency source snapshots/hashes and review diff; request root's independent scoped review. Report actual capability acceptance NOT_RUN.
