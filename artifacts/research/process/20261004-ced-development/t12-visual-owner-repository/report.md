# Visual owner durable repository release

Released 2026-10-05 in the existing 20261004 stage directory. Ready for root's independent review; no further owned source writes while reviewing.

The four approved repository APIs now store exact immutable original requirements and coherent checkpoint/pool source publications under the existing event transaction domain. Every publication is fixed **DURABLE_BINDING_ONLY**, with independent mode database **NOT_INCLUDED**. This is source persistence and CAS software, not authenticated live ownership, a method capability, native admission or physical success.

## Exact ownership and source package

Only the five authorized files changed: event_autonomy protocol.py, memory.py, sqlite.py, new visual_owner.py and new test_visual_owner_repository.py. Initial baseline bytes/hashes are preserved in baseline/ and baseline-hashes.json; review-package.diff compares only those five against that baseline (new files against empty). source-isolation.json verifies all existing methods except the memory constructor and SQLite schema initializer remain AST-identical. Initialization additions allocate two memory dictionaries / two SQLite tables; no legacy callback or execution path changed.

Full runnable source/ freezes **772** files: immutable T8b fix3 768-file base plus exact final tested dependency/fixture overlay. Manifest SHA256: **e86e0a45330cfe5bf58f666628b7240ca0c80923f07e74d4d650a59d1b0db8e4**. scoped-source-hashes.json names 121 actually imported/tested source/fixture/config files, including five owned and 116 read-only references. freeze-setup.json records full base hash, overlay inventory and zero imported-source drift during the final CPU run. The complete closure contains historical unrelated base sources for imports; only the four listed tests are verified here, not the whole base inventory or full project suite. All archive hashes and the five live owned hashes match; The 121 scoped Python source/fixture ASTs parse successfully.

## Consumer interfaces

```python
initialize_visual_owner_if_absent(original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint, verification_state: VerificationBudgetState,
    retry_budget: RecoveryBudget) -> VisualOwnerPublicationRecord
get_visual_original_plan(task_id: str, plan_version: int) -> VisualOriginalPlan | None
get_visual_owner_publication(task_id: str) -> VisualOwnerPublicationRecord | None
publish_visual_boundary_if_current(*, task_id: str, owner_epoch: str,
    expected_owner_revision: int, expected_contract_hash: str,
    expected_checkpoint_hash: str, checkpoint: ExecutionCheckpoint,
    grounding: StepGroundingBinding | None, state_generation: int
) -> VisualOwnerPublicationRecord | None
```

VisualOwnerPublicationRecord has detached identity/checkpoint/verification_budget/retry_budget and revision/generation/original hash/deadline properties, digest(), detached(), to_payload()/from_payload(). Its canonical v1 envelope includes exact source scope, current checkpoint/pools, optional SOURCE_BINDING_ONLY grounding, source revision, operation key and actual persistence timestamp. Publication hash binds the full envelope. It intentionally has no execution/admission booleans or receipt token. Original plans and all nested reads are detached and revalidated. Stored hashes must be present; unsupported scope/schema, extras and foreign source/column/hash bindings reject.

Initialization is one memory lock / SQLite BEGIN IMMEDIATE. Active contract, checkpoint, verification pool and retry pool must be wholly absent, or wholly present with exact identities/hash/version/history/limit/deadline definitions. A partial group conflicts without allocating or resetting missing rows. Existing complete source groups are adopted without rewriting pools, counts, event history or deadlines. Same-version original/epoch/content cannot change; revision1/generation0 is frozen. Higher-version or new-epoch attachment remains an unimplemented explicit future CAS. Initialization retries return current coherent source only; stale source requires explicit publication rather than silently reconstructing a snapshot.

Publish checks epoch/revision, current active version/history and full contract/checkpoint identities, strictly increasing generation, full completed prefix/pending suffix and unchanged original requirements. Checkpoint plus revision publication commit together. Exact operation key/content retry returns the detached historic publication under the same transaction; changed stale requests return None. Historical idempotency is a software source record, not an action receipt or freshness guarantee. A current getter rechecks real repository rows and pool snapshots; legitimate external debit makes the older publication unavailable until a fresh publication, while definitions/deadlines remain unchanged and remaining quotas/history cannot refill/regress.

Optional grounding binds the actual original requirement digest, prior checkpoint, next generation/current step/versions, source inventory and checkpoint safety references. It is only a structural source carrier: repository persistence does not establish that caller-provided frame/source hashes came from a real capture, calibrated geometry or a current worker. Historical grounding is validated at its recorded publication timestamp; current reads/new submission require its current freshness. Expired grounding cannot permanently prevent a fresh ungrounded boundary from being published. Native evidence and worker authentication must be independently supplied later.

## TDD and verification

Initial collection failure in red.log was a wrong test import namespace, not qualified RED. red-qualified.log then reproduced 33 absent-API failures, and red-fresh-software-clocks.log repeated with fresh synthetic clocks. Subsequent qualified RED logs cover global checkpoint collision, subclass scope envelope, fabricated declared checkpoint alias, rehashed original/publication link, missing active version history and rehashed grounding requirement weakening. The first expired-grounding regression clock substitution caused a setup/isinstance failure (red-expired-grounding-refresh.log); corrected red-qualified-expired-grounding-refresh.log reached the actual fresh publication assertion and failed both backends. All authentic setup failures and REDs remain preserved.

Final green-final-freeze.log: **219 passed, 3 skipped in 24.51s**, the new repository cases plus registration, standalone verified recovery lifecycle and replan activation. Three skips explicitly cover storage-backend-only cases. No full suite, renderer, GPU, model or controller runs occurred. Separate green-isolated-recovery.log: **4 passed in 0.50s** in a cold process. cold-imports.log: all five individually launched memory/protocol/visual_owner/sqlite/owner_registration imports passed. Final Ruff check all five owned files passed; cold mypy checked four source files successfully (only existing unused ROS config notes).

New files and newly inserted method groups pass Ruff format (format-scoped.log). All three original baseline legacy files fail whole-file Ruff format too (format-baseline.log); this release preserves their old formatting rather than introducing unrelated changes. ruff-current/mypy-first/format-current logs preserve earlier lint/type/format findings and corrections.

Meaningful software tests include detached nested inputs/outputs, exact original conflicts, checkpoint prefixes/no replay, partial group rollback, SQLite trigger-induced rollback after provisional writes, two-connection conflicting initialization and concurrent publish/restart, legitimate pool debit/limits/deadline/refill, scope/envelope/hash/source alias tampering, positive source-only grounding and fresh refresh after historical expiry. All fixtures are **SOFTWARE_ONLY**; no saved real frame timestamp was rewritten and no actual evidence accepted.

## Remaining integration prerequisites

Root must later attach registration to the existing genuine worker owner thread with current job/attempt/lease/backend/capture and cancellation authentication; map source-only publications to actual worker liveness; supply genuine current frame/calibration/grounding/native evidence; preserve original full requirements during derivation; and coordinate mode through its separate database without claiming cross-database atomicity. Decision reserve, stage/resume, command/effect receipts, executor attachment, recovery authority and any worker/default/profile edits are absent here. No movement is inferred from an observer or a persisted completed-ID field. Existing admission gates remain unchanged and unavailable capabilities remain unavailable.

Actual model/network/capture/render/controller/task actions: **0**. No credentials accessed, no new physical acceptance, no commits.

Frozen-only assembly check (green-frozen-owned.log): launched from source/ with its own src/tests namespace; **64 passed, 3 backend-only skips in 10.48s**. This confirms the new scoped closure runs independently of moving live modules. Reproducible freeze-source.py/check-scoped-format.py/check-cold-imports.py are preserved as artifact tools; freeze-source.py refuses to overwrite an existing source release.
