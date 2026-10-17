Spec Compliance

**Needs fixes.** Code quality: **Needs fixes**.

This report is newly composed from the existing same-seat review records under R198. It is not a restoration of the missing Markdown/full-report draft. No new source review, negative probe or test was performed to write it.

Strengths

The existing review records identify concrete improvements to request/operation/CAS/result history binding, diagnostic-independent local publication hashing, route hash recomputation, recursive local-envelope validation and the typed budget-history getter tests. Those improvements do not close the three remaining Important findings below.

Issues

Critical: none identified in the existing findings.

Important

### C1. Local promotion replay calls forbidden legacy UTC accessors

Severity: Important. Location: [local_temporal.py:854](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:854).

Trigger: Decode a four-field local bootstrap history through PROMOTE with request.payload.original tagged visual.owner.original.local.v1, matching contract/source/role/proposal/requirements and preceding capture/plan state.

Evidence: The exact tag dispatch in visual_owner.py:127–128 returns LocalVisualOriginalPlan. _history dispatches through _replay_bootstrap at 1288–1327; that replay decodes prior at 950 and passes it into _bootstrap_promotion_source at 990. With earlier source predicates satisfied, the helper evaluates prior.registered_at at 854–855 and prior.effective_deadline_at at 856. owner_registration.py:548–553 routes both properties to legacy_deadline(); local_temporal.py:1876–1877 always raises ValueError.

Consequence: A fully local promoted-original history cannot complete this validation path. It is forced through an archival UTC relation that the local type intentionally forbids. Separately decodable promotion requests do not prove full history restoration.

Remedy boundary: Use explicitly tagged local-versus-archival promotion source validation. Preserve external timestamp bytes and archival checks, but derive local relations from immutable descriptors/provenance without UTC authority getters. Validate a complete local-original capture/plan/promotion history and a separate preserved legacy-original control.

Scope: Residual I1/full-history replay defect. No live permission bypass claimed.

Verification limitation: Static call/type-path deduction only. Actual positive new-style history cases stop at bootstrap capture or supervision wait completion; no full local-original PROMOTE history was executed.

### C2. Embedded local original plans are not joined to the enclosing complete original_time

Severity: Important. Location: [local_temporal.py:614](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:614).

Trigger: Use a valid visual.owner.original.local.v1 child whose original_time differs only in a valid verification_reference.window_id. Keep lease identity, sources and contract content equal. Embed it as payload.original in a local route input, update the sibling publication original_plan_hash to the child digest and recompute publication_hash, but retain the enclosing original_time for publication and budgets. Supervision original edges use the same incomplete check.

Evidence: _join_audit_original at 614–625 compares lease/fence identity, sources and contract hash, never LocalVisualOriginalPlan.local_time. Route input calls it at 1538–1540 and supervision at 1435–1437. _audit_publication checks the publication own time at 475–480 and its identity/hash relation to prior at 556–557. Recursive validation at 433–445 validates child internal consistency but cannot replace the missing parent equality. The four R182 joins do not cover payload.original.

Consequence: A decoded request can combine a locally tagged original plan from one original-time history with a publication, budgets and outer history bound to another. Identity/source equality is weaker than exact original-obligation continuity.

Remedy boundary: For this declared semantic original-plan edge, compare local prior.local_time exactly with the enclosing original. Retain separate legacy archival checks and independently valid originals in descriptive JSON. Add an independently valid alternate-child negative case with refreshed sibling hashes.

Scope: Residual immutable-original causality gap adjacent to I4; the original four budget mismatch cases are fixed.

Verification limitation: Static counterexample construction, not executed. This concerns payload.original, not the deliberately permitted independent descriptive child parameter.

### C3. Route budget tasks are compared only with each other

Severity: Important. Location: [local_temporal.py:1589](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:1589).

Trigger: Starting from the accepted fully nested local route fixture, change both before_verification_budget.payload.task_id and after_verification_budget.payload.task_id to the same different nonempty task. Recompute each budget content_hash from its schema/task/state/revision. Leave original_time, revisions and counters unchanged, and leave route input and produced publication unchanged.

Evidence: _audit_pool at 598–611 checks envelope and enclosing original_time. Budget validation at 1608–1611 checks task/content hash without an original-plan task join. Route 1585–1598 checks before_task == after_task, revision +1 and nonincreasing counters/limits, not equality with input original task. Input/source hashes do not cover these separate before/after fields. Produced publication at 1599–1602 is validated independently and checked only against its declared publication hash.

Consequence: A route for task A can be accepted with a declared budget debit for task B, despite valid time envelopes. The history does not establish the task-bound transition it claims.

Remedy boundary: Join before/after task identities to the exact decoded input original and enforce the applicable input/publication-budget and produced-publication-budget relations. Add the paired task-id mutation with recomputed content hashes.

Scope: T1 detached route causal audit only, not evidence of actual CAS or live budget mutation.

Verification limitation: Static control-flow deduction from the accepted fixture structure; no probe was run.

Minor

No additional Minor finding is introduced by this report.

Assessment

**Task quality: Needs fixes. Spec compliance: Needs fixes. Code quality: Needs fixes.** C1, C2 and C3 are static findings from the already completed review. Their proposed negative cases were not executed by this reviewer. The report does not authorize or implement any repair.

Existing software evidence

The already reviewed R192 structured evidence and JUnit record 51 tests, 51 passes, zero failures, zero errors and zero skips. Existing resource evidence reports 204 successfully closed Memory instances. These observations remain valid bounded software evidence; they do not establish T1/T12/native/formal acceptance. There was no new execution or new per-object audit in R198. Continuation read 7 selected structured fields rather than independently inspecting embedded raw, before or base64 records.

Preservation, provenance and limits

The original continuationMarkdown, continuationReport and continuationReportWrite drafts were never successfully formed. The first report-writing functions.exec cell failed during JavaScript parsing with `SyntaxError: Invalid or unexpected token`; no nested interpreter process or numeric exit resulted. The complete failed JavaScript was not separately archived. The visible original error and its conversation-history location were preserved. Later extant issue and ledger objects are the basis for this newly organized report, not evidence that the failed cell stored its intended drafts.

The full three existing issue objects are copied without alteration into review.json. The continuation ledger is copied without alteration to continuation-read-ledger.json, including its original notes, selected read ranges, status and write-failure record. The original R175 review and ledger remain unchanged.

The same review seat used the original 9 batches plus 8 continuation batches: **17 authorized / 17 used / 0 remaining**. The original remaining 3 plus the explicitly authorized R179 extension of 5 supplied those 8 continuation batches; no budget reset or new reviewer seat occurred. The ledger retains all eight actual batch records and references their stored tool returns. Hashing does not imply full textual inspection.

No product code, test, AST, compilation, probe, Git operation or new source investigation was performed for this report. No T1/T12/native/formal completion is claimed. The original missing-draft state and prior failure evidence are not rewritten as success.

Basis: [original-existing-review-records.json](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round198-p6-t1-review-report-from-existing-records-20261014/original-existing-review-records.json). The JSON report identifies the exact issue, ledger and eight actual-read pointers.
