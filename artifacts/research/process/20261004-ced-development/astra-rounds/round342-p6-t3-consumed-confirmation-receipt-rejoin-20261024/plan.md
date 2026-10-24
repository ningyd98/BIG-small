# R342 Consumed Confirmation Receipt Rejoin Implementation Plan

> **For agentic workers:** Use the existing same-Sol workflow after ROOT activation. No new agents or runtime actions.

**Goal:** Require actual current job/event COMPLETE receipt equality when writing the terminal CONFIRMED audit, after real confirmation has been consumed.

**Architecture:** Keep real terminal COMMIT/confirm semantics. Bind private source object identities, begin the separate audit transaction in job-before-event order, rejoin real receipts and check original D_app before its existing audit CAS.

**Tech Stack:** Existing SQLite/in-memory repositories, private TLS, actual registry/lock/connection identities; AST/source/hash verification only.

**Spec:** `root-finding.json`, four frozen snapshots, R331 and accepted R338 mode boundary. Actual Astra: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Same implementer: `/root/p6_t3_sol`, awaiting ROOT activation.

## Evidence and cause

`_final_publication_sources` joins current job/event COMPLETE receipts before terminal commit, then releases the event lock. `_dispatch_writer` commits the terminal proposal, performs real confirmation and consumes its one-use proof. `_record_final_confirmation` currently checks target, job snapshot and files but uses archived receipt context when writing CONFIRMED. Later summary denial cannot supply the missing write-time predicate.

The outer operational transaction still holds the genuine writer/view connection and job publication guard during the recorder, though the terminal COMMIT has ended its first SQL transaction. Existing local producer order is job guard/BEGIN before event lock/BEGIN. `_check_local_locked` calls broker evaluation, so it is unsuitable for rechecking an already-terminal lease: this audit must use consumed proof plus independent original app liveness.

This is a static candidate defect, not an executed failure. `source-slices.json`, `planner-readout.json` and `plan.json` preserve the finite evidence and input SHA256 values. Selected live definitions match their frozen inputs.

## Narrow implementation

Only three definitions in `simulation_runtime/sqlite_repository.py` may change: `_final_publication_sources` for private source-reference capture, `_record_final_confirmation` for the current rejoin, and `_dispatch_writer` finally for cleanup. No schema/public payload/summary, broker, mode gate, terminal SQL or R341 selector changes.

- [ ] ROOT verifies applicability and activates the same Sol. Preserve R338 dispatch, R340 exact cap successor and all historical evidence.
- [ ] In the genuine precommit source path, retain exact `(owner, runtime, events)` references in dedicated private TLS `final_publication_live_sources`; reject an unexpected existing slot. Never serialize these refs or include them in the pending context. Clear the slot on every dispatcher exit.
- [ ] In the recorder, keep existing consumed proof/caller/process/thread/view and LOCAL guards. Require the captured refs to match current owner/runtime registries, real worker/source repositories, session, startup/binding/thread and sealed original descriptors. Recorded kind/path must agree with the actual event source but cannot select authority or a connection.
- [ ] Start the separate audit job `BEGIN IMMEDIATE` using the genuine current view connection while the existing job publication guard remains held. Then acquire the actual event lock. For SQLite, reject an existing event transaction and open an owned `BEGIN IMMEDIATE` on the actual event connection; memory uses its actual lock. Hold event exclusion through the job audit COMMIT. Do not acquire event first or open a database named by archived JSON.
- [ ] Under both exclusions, recheck exact source refs and read the nonempty ordered actual job receipt list. Require full equality with pending payload receipts and its digest, all COMPLETE with original job/attempt/lease/epoch. Preserve each earlier receipt's stored generation/revision; do not require terminal generation. Read each counterpart by operation ID from the real event connection or actual memory map and require full dictionary equality. No archive-only memory confirmation, hash-only substitute, rewriting or reconciliation.
- [ ] Retain/recheck actual terminal target, committed job snapshot, manifest and exact pending row inside this exclusion. Record the existing proof fields with current original `_remaining_app_seconds`, and call `_check_app_live()` after receipt reads immediately before the existing CONFIRMED CAS. Preserve the existing audit UPDATE and COMMIT. Do not invoke lease evaluation/proposal/renewal, `_check_local_locked`, another confirm or a local publication scope.
- [ ] In finally, roll back only the owned SQLite event read transaction, after audit commit or failure, then release event lock. On failure roll back only the new audit job transaction; original terminal COMMIT/PENDING history stays intact. Track acquisition/transaction ownership and never commit or roll back foreign event work. Preserve primary failures through cleanup. No retry or success rewrite.
- [ ] Sol supplies exact diff, canonical source hashes and AST/symtable/text proof; ROOT independently reviews acquisition/release paths, case matrix and unchanged boundaries before static acceptance.

## Source-only verification and limits

Review unchanged SQLite and memory happy paths; missing/added/changed/partial receipts; private source swaps and forged serialized descriptions; app expiration during reads; already-terminal lease; and failures during lock/read/CAS/commit/cleanup. The invariant is real consume → genuine source binding → job audit BEGIN → event exclusion → real receipt equality → current original app/target/file/PENDING checks → audit CAS/COMMIT → cleanup.

No product imports/calls, tests, collection, probes or execution. Later memory summary remains explicitly archival; actual memory receipts are required at this write. No public summary behavior or FOUNDATION/legacy mode boundary changes. Whole-file snapshots are evidence, not rollback instructions; preserve all unrelated source work.

## Prerequisites and acceptance

ROOT activates only after plan/pin applicability review. RED stays SPENT and GREEN UNUSED/HELD; nine nodes, max15 polls and all allowances remain unchanged. This plan does not release GREEN or supersede original actor/source/HEAD/resource gates.

Acceptance establishes only the source-level post-consumption write predicate and its locking/source authority. It does not establish runtime GREEN, T3/B-final completion, real research or C/native/model/physics results. New causes or unexpected validation failures return affected work to Astra.
