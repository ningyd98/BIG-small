# Fresh independent T2 review

Reviewer: `/root/fresh_t2_review`. This is a fresh seat, separate from T1. Review only: no product/test edits, tests, probes, imports, AST, SQL or Git commands.

**Spec: Changes required. Quality: Incomplete. Bounded T2 software acceptance is not justified.**

## Finding T2-FR-01 — Important / P1

**A local outbox row disables unrelated legacy message claims in the same repository.**

The predicate at `src/cloud_edge_robot_arm/repositories/event_autonomy/protocol.py:186–189` answers “local target” for every `claim_outbox_message()` whenever any local outbox row exists. The dispatcher then raises at lines 220–224, before choosing a message. It ignores the row’s task and status.

This is reachable without forging authority:

1. A genuine private local runtime enqueues a message through the supported `enqueue_outbox` path (worker_runtime diff D02:608–643,666–668).
2. An unrelated unbound legacy task has an eligible message in the same repository. The legacy stores are separate: Memory uses `_outbox`, and SQLite uses `event_outbox`.
3. A normal public claim outside the local private scope fails because the local row exists. The repeated storage guard also fails before selecting the legacy candidate.
4. A retained local row continues blocking legacy delivery even when its status changes.

Backend locations: `memory.py:1784–1796` and `sqlite.py:2362–2387`. R158 T2 preserves existing legacy routes and fences mutations which can address operational tasks; the reviewed contract imposes no single-mode repository restriction.

The current writer test checks denial of the local outbox operations (`test_operational_runtime_closure.py:4998–5001,5012–5025`). It does not test unrelated legacy success in a shared repository. The seven passing nodes therefore do not cover this regression.

Astra should define a candidate-specific legacy claim path under the actual lock/transaction that retains the operational fence. Expected targeted regression cases: both backends with one retained local row and one eligible unrelated legacy message; repeat after the local status changes; verify unchanged local rows/receipts and continued public denial/private-scope requirements; cover binding changes under actual storage synchronization. No repair or runtime reproduction was performed by this reviewer.

## What the source review establishes

All 19 before-to-current diff entries were reviewed, including all 2,884 nonempty diff lines. Both backend writer diffs include all 36 guard insertions and source arguments. The SQLite checkpoint CAS controlling read now follows the actual BEGIN and guard. The public negative exception is exact positional CANCELLED; positive RUNNING/COMPLETED remains denied.

The coordinator takes the job scope before the event lock/BEGIN and checks both authorities afterward. The source seals original startup, task, binding, acquisition and policy descriptions. Private session opening checks genuine poll code/globals/self. Decoding does not register a live issuer or scope.

The four receipt stages and resume logic were read in the production diff. Pending semantics/debits commit before the first job receipt; completion commits event then job markers; lost acknowledgments are not converted to success, and resume does not repeat or refund the debit. Detailed seam fixtures and resource evidence remain outside completed coverage.

A possible later-event-BEGIN wait concern was considered. R158 expressly permits narrowly bound nonauthorizing completion-marker transactions and requires a fresh current check for later admission. Without the remaining seam/consumer review, this is a review question, **not a second proven defect**.

## Source generations and runtime evidence

The wait Memory/SQLite, dual, and budget Memory/SQLite passes used the old `local_temporal.py` SHA `8d41d767ea77a0a2a41e191a25d2e95d8e3cc6e4f6908faddbedbe13dcca6ad7`. The first three also predate the two read-only `contract_hash` accessors. The two current writer passes use codec SHA `5675220d5dc4f895d542151f5dfe7ab03c19a4d080e3bcf95ae6bb7e9d21eb9b`, with no current source deltas; recorded elapsed times are 189.959 s and 189.019 s.

The memo hunk preserves the existing strict validators and nested checks. It caches successful full canonical envelope/class keys only, returns fresh instances, and uses fixed 128-entry / conservative 8 MiB limits with ordinary-validation fallback. The current copied-context ownership handling catches foreign or consumed tokens and clears owned state in finally. The complete 329-line micro test was read, including mutation rejection, exact bytes/digest/projection, context and BaseException cleanup, copied contexts after both parent outcomes, and overflow fallback.

All seven actual JUnit documents were read: one passing node each, zero failures/errors/skips. The pinned current micro ROOT acceptance reports the six check groups and both copied-context cases passing. Seven actual-tool-return files were hash-checked, but the finite field selection missed their nested payloads; they were **not** semantically decoded. Resource totals of 15 completed polls, 5,708 allocation attempts / 5,693 initialized / 5,708 cleanup observations, and 30 database pairs are reported evidence, not an independently cleared denominator audit.

The historical five are separate source-specific passes, not a synthetic current GREEN7. No blanket rerun of all five is indicated solely by the scoped memo/read-only accessor changes. The legacy regression needs targeted validation after an actual Astra repair plan; remaining review gaps need a defined continuation. Earlier writer SIGSEGV cause remains unresolved. Current success and repeated-decode observations do not establish its cause.

## Original read budget and receipts

All **12 attempts are consumed**, with no reset or extension. Nine displayed bounded payloads. Attempts 7, 9 and 11 stopped before printing source/evidence because the computed payload exceeded the byte cap; all three count. The 9-token outer display loss in batch 2 was explicitly recovered in batch 3; its raw exec result was retained.

| Batch | Displayed source lines | Display UTF-8 bytes | Coverage/outcome |
|---|---:|---:|---|
| 1 | 160 | 24215 | read; Both skill files in full; finite release, source manifest, coverage and R315 plan fields. |
| 2 | 449 | 38910 | read_with_outer_display_recovery; 32 frozen source SHA/size pins; 19 diff inventory; R315 implementation/micro/root-cause fields; global diff lines 1–449. |
| 3 | 477 | 38945 | read; Global diff lines 450–925 plus D00:139 recovery. |
| 4 | 541 | 38950 | read; Global diff lines 926–1466. |
| 5 | 600 | 38897 | read; Global diff lines 1467–2066. |
| 6 | 559 | 38966 | read; Global diff lines 2067–2625. |
| 7 | 0 | 0 | pre_output_bound_refusal; No source/evidence payload displayed; traceback only. Attempt counted. |
| 8 | 588 | 39129 | read; Global diff lines 2626–2884; tests/test_local_temporal_decode_memo.py:1–329. |
| 9 | 0 | 0 | pre_output_bound_refusal; No source/evidence payload displayed; traceback only. Attempt counted. |
| 10 | 38 | 31492 | read; Finite seven-run coverage/generation/resource fields; all seven full JUnit documents; actual-tool-return hashes; ROOT status fields; complete current micro acceptance JSON; 38 test declaration locators. |
| 11 | 0 | 0 | pre_output_bound_refusal; Final coverage-list serialization exceeded cap before print. No source/evidence payload displayed; traceback only. Attempt counted. |
| 12 | 386 | 38983 | read; R158 dual_database_protocol, public_publication, tasks[1], four matched legacy migration dispositions; protocol.py:170–245; memory.py:1780–1805; sqlite.py:2355–2392; test_operational_runtime_closure.py:4914–5055,3517–3576,3833–3876. |

Total displayed source lines including declarations/recovery: **3,798**. All 32 frozen file hashes were checked. Equivalence to current live paths relies on the pinned release and ROOT freeze statement; live paths were not independently rehashed. Full exact pins/ranges are in the JSON report and raw receipts.

Each `batch-01-receipt.json` through `batch-12-receipt.json` contains the exact read invocation and actual raw return. The failed pre-output reads are preserved, not erased. Report/receipt writes are administrative outputs, not new source/evidence reads.

## Exact remaining quality coverage

- Observer `test_operational_runtime_closure.py:3577–3832` and `3877–3952`: connection/partial-init handling, full poll/thread/clock observation, cleanup denominator, final restoration.
- Attempt helper 3479–3516, exercise 4081–4142, event-wait helper 4143–4233, detached-read helper 4303–4349.
- Wait fixture 4350–4434, dual seam fixture 4435–4590, budget fixture 4591–4662. Only their declaration locators and JUnit documents were covered.
- Writer adoption/input/authorization builders 4698–4913. The complete writer inventory and denial/cancellation body at 4914–5055 was covered.
- The 195-line `test_t2_observer_lifecycle.py` was hash-pinned only.
- Full unchanged private lease/view/operational transaction and original app CPU provenance implementations beyond changed diff context.
- Detailed accepted seam/resource cases and nested actual-tool-return execution payloads. Large raw cases were not dumped.

These gaps prevent Quality approval even apart from the concrete Spec finding.

ROOT should obtain an actual **gpt-6-astra** plan for T2-FR-01 before repair. This report grants no T2 acceptance, whole P6B/P6C promotion, T3 permission, native/physical/physics qualification, formal research acceptance, or full remote reproducibility claim.

