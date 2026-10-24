# R349 local grounding binding-scope repair plan

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**, acting as repair planner. Same actual `/root/p6_t3_sol` implements only after ROOT review and activation. This plan is source-only and allocates **zero runtime attempts**.

## Actual failure and preserved evidence

`R346:t3_01`, `test_private_startup_to_transaction_grounding[memory]`, failed with `ValueError: exact source binding scope required`. Session94189/chunkb06b43 recorded wrapper1/child1, outer129.54263916698983s and child-through-cleanup129.21119930999703s, **not a timeout**. The actual grounding body carried `DURABLE_BINDING_ONLY`.

All347 frozen source pins and exact HEAD remained stable. The539 HEAD observations had maximum completion gap0.2550562579999678s; cleanup succeeded. Actual JUnit contains one failure and zero errors/skips. The valid resource sidecar entered behavior, did not complete assertions, and records one poll, two constructed workers and402 initialized/cleaned allocations. The missing behavior case completion is not fabricated. ROOT verified40 original regular files /8,178,261bytes and two DB byte copies; this is not a transactional backup claim.

The24 ROOT inputs, original finding and source slices are hash-verified in `plan.json`. `owner-registration-before.py` preserves the full pre-repair product bytes. `source-readout.json` records the finite producer/consumer lineage. Original gates, raw files, DBs, result, completion and spent ledgers remain unchanged.

## Verified cause and exact repair

`StepGroundingBinding.binding_scope` is `SOURCE_BINDING_ONLY` (owner_registration.py:789). `LocalStepGroundingBinding` inherits that class and uses `visual.owner.grounding.local.v1` (line870). The local deterministic producer alone emits `DURABLE_BINDING_ONLY` at line1176. `_local_bind_grounding` passes this body to the local decoder before its branch's `_local_commit` call. The decoder deliberately requires SOURCE for nonpublication binding records and DURABLE only for `visual.owner.publication.local.v1`.

A genuine transaction recording grounding evidence does not turn it into the durable publication object. The source-side literal is wrong; the strict decoder is correct. Publication separately requires DURABLE with `mode_scope=NOT_INCLUDED`, and its actual producer already emits that value.

Change **exactly one literal**, inside `bind_step_grounding`'s local body passed to `runtime._local_bind_grounding`:

```diff
-            "binding_scope": "DURABLE_BINDING_ONLY", "original_plan_hash": original.digest(),
+            "binding_scope": "SOURCE_BINDING_ONLY", "original_plan_hash": original.digest(),
```

No other product byte changes. Preserve parser/FIELDS validation, publication and legacy semantics, actual owner/runtime/thread/source checks, TTL and original app/lease bounds, generation/revision joins, transaction ordering and COMPLETE receipts. No fixture change, hash override, DB migration or compatibility exception for malformed old grounding payloads. The corrected body will naturally yield its own real content/operation hashes only during a future authorized run.

Expected successor owner_registration.py: **49121 bytes**, SHA `bc3b8eab7d3059a40edc81453b15d37777f4d6c4f12ac59344c316636041ff80`. This hash was computed from a source-string replacement in memory; no product file was written or evaluated by the planner.

## Implementation and source proof

1. ROOT verifies input applicability, preserved snapshot and actual same Sol, then activates this exact repair. All remaining runtime slots stay HELD.
2. Sol makes the single literal substitution in `src/cloud_edge_robot_arm/vision/owner_registration.py`.
3. Sol saves `R349/implementation/source-proof.json`, `owner-registration.diff` and `author-step-report.md`. Prove complete after bytes equal the one planned before-byte replacement, the predicted hash matches, and source AST/symtable are valid. The function AST must differ only in the one string constant at the specified dictionary entry.
4. Verify unchanged class scope/inheritance, strict decoder, runtime private guards/transaction path, publication producer/guard and legacy constructor. Compare the other frozen sources and original artifacts with their existing pins; do not recursively reopen historical rounds.
5. ROOT independently reviews actual successor/proof and writes `R349/root-source-acceptance.json`. Report source correction separately from software behavior.

Verification is stdlib byte/hash/diff/AST and inert evidence inspection only. No candidate/helper/product import, test, collection, parser invocation, probe, database semantic read or extra test addition is authorized. Source reasoning retains the truth table grounding→SOURCE and publication→DURABLE; the old grounding DURABLE remains rejected by the untouched parser.

## Runtime and acceptance boundary

`t3_01` remains SPENT1/0 on ROOT and AUTHOR. The other eight slots remain HELD0/1. Original R331 RED/GREEN remain SPENT. No retry, refund, implicit carryover or continuation past the rejected predecessor occurs here.

After source acceptance, a **separate actual Astra finite execution plan** must explicitly allocate any replacement command, bind its new source generation and spend lineage, and decide how the eight unused commands may continue. It must preserve the current R346 gate, use a new versioned gate, and explicitly address predecessor/actor/runner mapping rather than rewriting the failed generation. Recheck exact HEAD/interpreter/source/test applicability, bind R349 acceptance and original failure evidence, complete ROOT gate review and individual reservation, then consume the specifically authorized slot before spawn. R349 supplies none of that runtime allowance.

This plan can accept only the exact source correction and preserved strict boundaries. It does not establish a passing failed node, behavior of the eight unlaunched nodes, absence of all earlier SQL effects, B9/fullB/C success or native/physical/formal evidence. New causes or unplanned failures return to actual Astra before repair; the current planner is not the later independent final reviewer.

## Finite full-path review

The source review also followed the complete constructor path: deterministic producer checks → private runtime grounding caller/publication/frame/TTL checks and real transaction scope → `_local_envelope` → domain-carrier `from_payload` → exact-tag local decoder → exact outer/body fields and decision/transaction joins → strict scope and grounding-specific identity/action/horizon/hash checks → original commit/result decode. The envelope copies the payload and immutable original-time descriptor; it does not rewrite scope.

A stdlib AST comparison confirms that the producer dictionary and grounding decoder field declaration have exactly the same 18 keys. No additional mismatch of this same scope contract was established in that finite path. Keep every later validator unchanged; this finding does not predict that all later runtime behavior will pass. ROOT's finalized R346 phase-step report is additionally pinned, preserving its false behavior/required-evidence booleans and successful retention observations separately.
