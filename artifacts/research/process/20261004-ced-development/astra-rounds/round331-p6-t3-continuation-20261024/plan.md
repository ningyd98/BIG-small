# R331 P6 internal T3 continuation implementation plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` with one actual fresh GPT-6.1-sol implementer and an independent T3 reviewer. ROOT controls applicability, exact gates and evidence. The user's continue authorization already selects continuation; no extra user confirmation is needed for the steps below.

**Goal:** Complete original R158 internal T3 local runtime migration and public confirmed-publication distinction on current accepted T1/T2 sources, then obtain a fresh bounded T3 review.

**Architecture:** Extend the existing real worker/startup, job-first/event-second private publication chain and terminal commit/ack-confirm seam. Preserve historical SQL and files; expose confirmed publication separately. Reuse current resource instrumentation and a small R319-derived runner.

**Tech Stack:** Python, existing pytest, SQLite/Memory event repositories, strict detached models, current private operational clock/lease machinery. No new dependency.

**Spec:** Original R158 `plan.json` task T3, its nine test cases, migration targets and public-summary schema; current post-opening plan; AGENTS.md. JSON plan in this directory is the exact command/interface companion.

## Problem and evidence

Actual Astra author: `/root/astra_p6_t3_plan`, model `gpt-6-astra`. Current HEAD is `d66e258a1ebac178cce6c510347ed22117f24cb6`, branch `research/20261004-continuation`.

The old T3 plan refers to an obsolete input generation and retired Sol identities. No new product test/runtime failure has been executed. Current source inspection confirms the planned `remaining_app_seconds`, `get_publication_summary`, `PublicationStatusView`, confirmed counters and four T3 functions are absent. Existing T2 private publication and final terminal commit/confirm infrastructure is present.

`input-pins.json` contains actual SHA256 and byte length of all immediate evidence, all 24 owned paths and the finite original protected closure. `applicability-readout.json` records actual source observations and both original ledger states. All **211 protected inputs match** original R158 bytes; no recursive historical audit is necessary.

R196 bounded T1 and R319 bounded T2 acceptance are prerequisites. R319 supersedes status only: the seven T2 passes remain tied to their recorded source versions, with no final-generation seven-node replay. R311 writer-memory SIGSEGV remains **UNKNOWN**; the 35 historical database and 90 sidecar gaps remain unrepaired. Later success does not explain the crash.

## Global constraints

- Only original T3 scope within the 24 paths in `plan.json.scope.owned_paths`; new metadata only under R331.
- Preserve old A/T1/T2 test/helper bytes; append four T3 functions and helpers. No protected factory or OC1 edits.
- Original app/lease origins, independent domains, hard bounds, private registries, budget CAS and consumed costs remain intact. No decoded history creates live authority.
- Legacy external UTC and native safety/effect validators remain strict. No C executor/backend/recorder work, network/model/native/GPU/physics run or research qualification.
- One actual Sol writer; ROOT never edits product/tests. No concurrent writer during a run.
- Tests use real job SQLite and real Memory or SQLite event repository, actual poll/start_attempt/P5 handoff and owning-thread clocks.
- No retries, no spent budget reset, no historical evidence edits. Failure or uncertain launch spends its slot.

## Review focus

1. Post-COMMIT loss must retain SUCCEEDED/attempt/lease history but expose no confirmed artifacts/counts: the three terminal fault nodes cover actual close, delayed confirmation and prior-bound crossing.
2. Caller-crafted or replayed receipts/acks/manifests must not create positive proof: assertions in public-control nodes cover copied/serialized/mismatched joins without adding worker lifecycles.
3. Local UTC jumps must not refill budgets or change local authority, while external future >1000 ms and age >5000 ms still reject: both UTC provenance nodes cover these boundaries.
4. Reopened/missing/tampered receipt/file data must fail closed across all public projections: public-control nodes verify changed/missing files, old operational rows, attempt mismatch, legacy NOT_APPLICABLE and batch counters.
5. Source identity/cleanup must remain true across genuine heartbeat and terminal faults: startup nodes and all per-node resource sidecars cover immutable originals, actual broker clocks, connection/thread closure and full attempted denominator.

## Actor and budget binding

- [ ] Bind the already-spawned actual `/root/p6_t3_sol` (GPT-6.1-sol, high reasoning, fresh context). ROOT reported its current permission is read-only preparation. Save the original spawn request/result in `dispatch.json` and activate this same seat only after plan/pin review; do not spawn a duplicate or label it as an old Sol seat.
- [ ] Author acknowledges exact plan, pins, HEAD and scope in `implementation/author-binding.json`; ROOT writes `root-activation.json` and freezes current before sources.
- [ ] ROOT records `budget-transfer.json` binding both untouched R158 ledger SHA256s. Only unused `t3_red` and `t3_green` are transferred exclusively to `R331:t3_red` and `R331:t3_green`. Their original entries remain immutable historical held records; no other runner may spend them.
- [ ] Maintain R331 root and author ledgers: ROOT reserve before call, author consumes before spawn, actual result settles spent. No retry/refund on failure or uncertain launch.

R158 mypy baseline/T1/T2 RED/GREEN are spent. Import sorting, formatter, scope proof, Ruff, format check, final mypy/delta and final_new23 remain **held**. Original final_new23 contains accepted T2 reruns and its combined 600-second limit is incompatible with the recorded T2 sum (782.5699651249743 seconds); this is an applicability issue, not a new timeout. Do not silently extend it or rerun T2. After T3, make one concrete final-gate successor decision from the actual impact/readout.

## Task 1: Prepare nine-node T3 contract and runner

**Files:** append to `tests/test_operational_runtime_closure.py`; create R331 `implementation/run-evidence.py`, local relevant resource helpers, before-source snapshot, migration map, source gate and command ledgers. No product edits yet.

**Interfaces:** reuse `_b_t2_attempt(request)`, `_b_t2_observe(monkeypatch, value)`, real `software_factory`, `_b_t2_exercise` where its behavior suffices and existing adoption helpers unchanged. Add `_b_t3_*` wrappers for terminal success and public-service construction; use actual constructors. Do not patch old helpers to simplify new cases.

- [ ] Append the exact cases listed below, preserving every prior byte. Freeze node-to-assertion and fixture-to-resource maps before runtime.
- [ ] Construct the actual `SimulationRuntimeService` with declared `artifact_root`, `database_path`, `event_stream`; no invented repository keyword. Its real repository reads the same actual job DB. Before public methods invoke `start()`, suppress only this service instance's `dispatcher.start` with a fixture no-op, preventing a second background worker. Preserve actual public projections, repository reads, normal startup recovery and the tested worker poll/startup. Record any real recovery reconciliation. Do not patch successful authority or confirmation. Use the actual observer namespace fields `value`, `fault`, `clocks`, `objects`, `release_events`, `workers`, `sessions`, `wait_observer`, `add`; no guessed attributes.
- [ ] For the missing interfaces, use explicit assertions such as `assert callable(getattr(VisualWorkerRuntime, "remaining_app_seconds", None)), "R331 planned missing remaining_app_seconds"`; public cases similarly check `get_publication_summary` and exact model fields. An accidental AttributeError, unknown constructor argument, lock failure or collection error is not legal RED.
- [ ] Implement actual behavior assertions in the same nodes behind the API checks; no dummy all-pass controls, constant VALID or blanket exception catches.
- [ ] Reuse the pinned R319 compact runner's process-group cleanup, child env, reserve/consume semantics, snapshots and archival. Adapt only R331 identity, two commands, exact nine-node JUnit accounting and local T3 case/cap metadata. Do not import historical runners' main/authority/precondition functions or reconstruct every old round.
- [ ] Reuse current resource schema/observer and existing environment sink name; add only four T3 scenario names with caps 2/3/1/1 in the local helper. R319 nested-constructor completion handling stays intact. No new profiler/diagnostic plugin.
- [ ] ROOT full text/hash reviews new tests, runner, actual prerequisite plugin and source/fixture map. Metadata-only stdlib syntax/AST/hash checks are permitted; no smoke import or collection-only run.

| T3 exact function | Variants | Worker cap per case | Required behavior |
|---|---|---:|---|
| `test_private_startup_to_transaction_grounding` | memory, sqlite | 2 | Real poll/startup -> bootstrap capture/plan -> adoption -> private event publication -> grounding/verifier input; original identity stable across genuine heartbeat. |
| `test_local_new_schema_ignores_utc_jump_but_external_does_not` | memory, sqlite | 3 | Local +/-1-day UTC immunity under original D bounds, exact-bound rejection, external UTC validation, four P5 adapter entries and B execution timing. |
| `test_b_terminal_publication_confirmation_fault` | commit_close, confirm_timeout, prior_bound | 1 | Real terminal SQL commit then actual close/late RPC/original prior bound failure; truthful unconfirmed public outputs and cleanup. |
| `test_b_public_confirmed_publication_control` | memory, sqlite | 1 | Actual commits/files/confirm produce coherent public readouts; CPU success flags explicit, model/actions/physical quantities zero; false proof and malformed joins rejected. |

The JSON preserves the original detailed assertions. Total maximum T3 lifecycles is 15. No extra test nodes.

## Task 2: Run legal RED, then implement T3

- [ ] ROOT reserve `R331:t3_red`, invoke exact `commands.t3_red.launcher_argv` once, and retain raw stdout/stderr/JUnit/prerequisite/source/resource/DB evidence. Accept only the exact planned missing interface/behavior assertions, nine collected nodes, zero collection errors/skips.
- [ ] After ROOT accepts RED, implement `VisualWorkerRuntime.remaining_app_seconds() -> float`: actual owning-thread original app obligations, minimum positive remaining bound; reject <=0, never renew/rebase. Use it for local timeout/model-return/startup and B source-time checks in worker/execution; preserve legacy/external UTC and native checks.
- [ ] Complete all T3 local producer/consumer callsites in the inherited migration matrix. Already migrated T1/T2 rows are classified unchanged; do not duplicate their algorithms. Use after-both-lock private decisions for positive publication; late cost remains charged.
- [ ] Extend existing SQLite `finalize_operational_publication` and `_writer_call` actual ack/confirm seam. Add `simulation_publication_confirmations_v1` final receipt storage without changing old SQL status/history. Bind PENDING to exact run/attempt/epoch/operation, job/event receipts and manifest. Confirm only after actual committed ack is consumed, broker confirmation returns, original app check remains valid and exact joins hold.
- [ ] Use a private one-use proof bound to actual owner/process/thread/finalizer; no public mapping, bool, replayed ack or durable receipt may call a successful audit writer. Audit cannot renew lease or alter budgets/status.
- [ ] Preserve existing staging/promote/withdraw code. Post-COMMIT failure retains terminal history; promoted previews are withdrawn and rejection bytes retained. Missing/PENDING/mismatched proof gives UNKNOWN/UNCONFIRMED and empty confirmed paths.
- [ ] Add immutable detached `PublicationSummary` with `to_payload()` producing the exact original fourteen fields, and repository `get_publication_summary(run_id: str, *, attempt: int | None = None) -> PublicationSummary`. Add strict `PublicationStatusView` and fields on the existing public response models. See JSON for compatible artifact-root plumbing if needed; absence of a trustworthy root/file join must fail closed.
- [ ] Update service run/attempt/artifacts/events/metrics/batch projections. Preserve `status`, attempt `result`, metrics and historical paths/payloads. Operational public artifact references require accepted proof; add `confirmed_succeeded`, `unconfirmed_terminal`, `publication_state`. Legacy rows remain NOT_APPLICABLE with old semantics.
- [ ] Produce a finite migration/impact map: exact changed definitions, local/external/diagnostic/C-only classification, unchanged original budget/authority protections and T3 tests that exercise them. No blanket claim that all T2 evidence is current-generation.

Public schema is exactly `simulation.publication-status.v1` with fields:
`schema_version`, `recorded_sql_status`, `confirmation_state`, `accepted`, `operation_id`, `attempt`, `epoch`, `generation`, `job_receipt_hash`, `event_receipt_hash`, `artifact_manifest_sha256`, `confirmed_artifact_paths`, `historical_artifact_paths`, `reasons`.
States: NOT_APPLICABLE, PENDING, CONFIRMED, UNCONFIRMED, UNKNOWN. CONFIRMED is archival proof, never live authority.

## Task 3: Exact GREEN and fresh review

- [ ] ROOT freezes and reviews actual GREEN source/fixture/runner hashes; no concurrent writer.
- [ ] ROOT reserve `R331:t3_green`, invoke exact `commands.t3_green.launcher_argv` once. Required: exit 0, exactly nine passes, no errors/skips; full actual SQL/file/receipt/public and resource evidence, no runtime source mutation.
- [ ] Spawn a fresh read-only actual Astra reviewer distinct from planner/author. Transfer only the unused original T3 review seat: <=12 read-only batches, <=600 source lines per source batch, zero product commands. Review current diff and evidence, no recursive audit and no T2 rerun.
- [ ] ROOT records the bounded T3 decision, step report and phase summary. Findings/new root causes stop affected repair and return to actual Astra before changing code.
- [ ] Prepare the next B9/static/final gate decision using this review, the actual impact map and unchanged original mypy baseline. Do not spend held gates under this plan.

## Exact runtime prerequisites and commands

`plan.json.commands` contains full literal child argv/env/cwd/output and launcher argv for both runs. ROOT may execute them only after the above source gates. Both use:

```text
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python
  <R331>/implementation/run-evidence.py t3_red
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python
  <R331>/implementation/run-evidence.py t3_green
```

`<R331>` abbreviates this plan directory only in this prose; JSON paths are absolute. Child commands preserve original exact nine-node order, `-q -p no:cacheprovider`, and explicitly add existing `-p r235_startup_prerequisite`. They disable plugin autoload and use a clean finite env. No network/model/GPU/native/physics call.

Per child: 600 seconds, original <=64 lifecycles (T3-specific 15), <=2 concurrent workers, <=1 broker and heartbeat per worker. Cleanup: 15 seconds, TERM grace 5 seconds; outer transport 900 seconds with 20-second kill grace does not extend child/product deadlines. Output directories must be new. Existing R235 prerequisite runs once in child with empty trace/profile channels before observers. All independent SQL reader connections exist before tested locks. Close every owned connection; transaction exit is not close. Preserve actual DBs/sidecars and rejected bytes under current workspace outputs.

RED's missing API guard may allocate zero workers; report that truthfully. GREEN must execute declared behavior. Retain attempted/failed resources in denominator, actual observed cleanup and unknown measurements as unknown. Source review establishes zero external invocation scope; do not fabricate measured OS/network totals.

## Acceptance, stop and delivery boundaries

This plan authorizes concrete T3 preparation, expected RED, implementation, GREEN and fresh review. It does **not** declare B complete, rerun accepted T2, release final_new23, permit C/native/model/physics work or grant formal research acceptance. All old failures, gaps and version-specific passes remain.

Unexpected failures, unrelated RED errors, missing evidence, new root causes, outside-scope pin drift or required scope expansion stop affected changes and require a new actual Astra plan. Read-only metadata verification and ordinary preparation within this scope do not require repeated planning rounds.

AGENTS.md requires each verified delivery to be committed/pushed with selective paths and local/upstream/remote SHA agreement. ROOT should prepare that concrete delivery gate once review accepts the deliverable; this plan never reuses old spent Git budgets. The final B gate must follow, then fresh final B review and ROOT decision, before separate C authorization.

## Planner self-review

Original T3 assertions, public fields, real resource prerequisites and migration responsibilities are preserved. Scope is limited to current T3 deltas and new R331 evidence. Two original unused slots are transferred exclusively, never reset. Exact child commands are materialized. Existing protected source hashes match; status evidence is not relabeled as same-generation runtime proof. No product/test import, test execution, product edit, historical artifact modification or agent spawn was performed by this planner.
