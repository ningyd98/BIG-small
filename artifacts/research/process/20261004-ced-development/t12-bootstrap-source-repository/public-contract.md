# Bootstrap source repository contract

Scope is fixed BOOTSTRAP_SOURCE_ONLY for bootstrap history and DURABLE_BINDING_ONLY for ordinary publication. No actual owner/lease authentication, effect/native permission, simulator/model/capture call or cross-database mode atomicity is provided. The root immutable pure producer supplies semantic compilation/promotion; repository code does not fabricate originals or verdict callbacks.

```python
initialize_visual_bootstrap_if_absent(definition: VisualBootstrapDefinition) -> VisualBootstrapRecord
get_visual_bootstrap(bootstrap_id: str) -> VisualBootstrapRecord | None
transition_visual_bootstrap_if_current(*, request: VisualBootstrapTransitionInput) -> VisualBootstrapTransitionResult | None
initialize_visual_owner_if_absent(
    original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint,
    verification_state: VerificationBudgetState,
    retry_budget: RecoveryBudget,
    *, bootstrap_promotion: VisualBootstrapPromotionInput | None = None,
) -> VisualOwnerPublicationRecord
```

Initialization is create-if-absent with the exact original definition. Bootstrap key is fixed by job/run, independently unique by episode. Changed attempt/lease/episode/registration/limits conflict. Existing ordinary source/group/history rows cannot receive a newly reset bootstrap. Initialization creates no ordinary active/checkpoint/retry/verification/publication rows.

Transitions reconstruct concrete detached typed inputs before lock; under memory lock / SQLite BEGIN IMMEDIATE they strictly decode/replay complete stored history and verify indexed identity/revision/definition/hash, then use repository-aware UTC and derive_bootstrap. State/history commit together, without an external effect callback. Same event key with changed or different-class source raises IdempotencyConflictError. Exact historical duplicates return HISTORICAL_DUPLICATE; they authorize no new effect. New invalid/stale requests return None, preserving previous spent/pending state. Hard-stop/deadline can persist terminal source history, not a control command. Get/init returning a pending claim cannot authorize replay; a lost response leaves it spent and requires stop/reconciliation.

Promotion is a separate typed input, never an ordinary ADOPT transition. Under the existing initializer's lock/transaction, lookup matches job/run OR episode and strictly validates source indexes. A matching bootstrap requires promotion; supplied promotion without a stored matching source conflicts. The supplied full original must equal the initializer original. promote_bootstrap recomputes canonical full proposal/original/requirements/camera/lease/deadline/retry consistency and exact complete spent verification state. Bootstrap adoption and original/active/contract-version/plan-version/checkpoint/ordinary verification/retry/publication rows commit together. Existing partial ordinary rows or an adopted bootstrap missing its initial publication fail closed. No nested public initializer is called.

Exact historical promotion can return a coherent current publication after subsequent ordinary SOURCE_ROUTE_ONLY pool consumption; it does not overwrite or refund the current pool. A historical record or expired getter is source history, never future capture/native authority. Original absolute limits, task/verification deadlines, remaining counts, rounds, no-progress and full best-condition history are inherited without restart reset. Retry is never consumed by this component.

Corrupt stored rows can raise ValueError instead of inventing a coherent snapshot; changed keys/definitions or unavailable adoption sources raise IdempotencyConflictError. Old no-bootstrap initialization remains supported. Separate runtime-job cancellation/live lease/mode source checks, registered source inventory/calibration, current backend acquisition, native/SafetyShield/PRE_SKILL checks and after-effect/hold/terminal conditions remain actual factory prerequisites before/after every effect. There is no automatic dispatch or actual runtime factory in this package.
