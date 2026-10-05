# BOOTSTRAP_SOURCE_ONLY repository contract (in progress)

Owned producer is the root pure `visual_bootstrap.py`; this repository does not manufacture proposals, leases, source proofs or native/effect permissions. The pure module is a read-only dependency and awaits root stable promotion release before final archive.

```python
initialize_visual_bootstrap_if_absent(definition: VisualBootstrapDefinition) -> VisualBootstrapRecord
get_visual_bootstrap(bootstrap_id: str) -> VisualBootstrapRecord | None
transition_visual_bootstrap_if_current(*, request: VisualBootstrapTransitionInput) -> VisualBootstrapTransitionResult | None
```

Initialization is create-if-absent, exact original definition only. Bootstrap keys are fixed by job/run, independently unique by episode. Changed attempt/lease/episode/registration/limits conflict. Existing ordinary source/group/history rows cannot be converted into a new bootstrap pool. Bootstrap initialization makes no ordinary active/checkpoint/retry/verification/publication rows.

Transitions reconstruct concrete detached typed input before lock; under memory lock / SQLite BEGIN IMMEDIATE they strictly decode the stored record and indexed identity/revision/hash, use repository-aware UTC and the single pure derive_bootstrap producer, and commit source history/state together. Same event key + changed source raises IdempotencyConflictError. Exact historical duplicates return HISTORICAL_DUPLICATE and authorize no effect. New invalid/stale requests return None, leaving prior spent/pending state intact. Hard-stop/deadline source stop may commit a terminal source history record; it is not a control command. No recovery retry debit or external callbacks occur here.

Get/init returning a pending record does not authorize replay; lost replies remain spent and require stop/reconciliation. Original absolute deadlines and full verification state remain fixed, and exhausted source cannot be refilled through initialization. Read-only getters can raise ValueError for corrupt current rows rather than fabricate coherent source.

Owner initializer currently rejects any matching bootstrap without promotion (lookup matches job/run OR episode and validates complete matching source). Upcoming keyword-only VisualBootstrapPromotionInput and promote_bootstrap integration will adopt bootstrap plus all ordinary rows inside the existing initializer transaction. No generic ordinary transition ADOPT kind is accepted. Promotion is pending, not complete.

No cross-database mode/runtime lease atomicity, native safety certificate, METHOD acceptance, actual capture/request or execution receipt is provided. Worker actual source/lease/backend/role checks before and after every effect remain separate prerequisites.
