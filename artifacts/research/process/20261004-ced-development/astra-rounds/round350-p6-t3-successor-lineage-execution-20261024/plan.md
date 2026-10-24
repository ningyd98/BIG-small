# R350 T3 successor lineage and finite execution plan

> Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Same actual `/root/p6_t3_sol` prepares the successor after ROOT activation. This saved plan does not release runtime; the planner is not the later independent reviewer.

## Outcome and evidence

R349 has independently accepted the one local grounding scope correction: owner_registration.py SHA `bc3b8eab7d3059a40edc81453b15d37777f4d6c4f12ac59344c316636041ff80`. All16 ROOT checks passed;346 other historical gate pins remain unchanged. This is source acceptance only.

R346:t3_01 genuinely failed after129.54s with one JUnit failure, entered behavior and incomplete assertions; it did not time out. Its raw/result/completion/source/sidecar/DB bytes and absent case completion remain original. Both first-slot ledgers are SPENT. Eight original rows remain physically HELD. Existing gates, runners, acceptances and ledger bytes are never rewritten.

## One new allowance, eight exclusive transfers

Allocate **one fresh replacement attempt**, `R350:t3_01`. Transfer the eight unused `R346:t3_02..09` allowances one-to-one to `R350:t3_02..09`. They are not eight new attempts. A new ROOT-accepted `budget-disposition.json` records this exclusive mapping and disables old-path execution eligibility while keeping old ledger bytes intact. After adoption those old HELD rows are historical values, not additional executable entitlements.

New ROOT/AUTHOR ledgers each bind that immutable disposition and each slot origin. ROOT and the reserved runner check the old ledger pins and unique mapping before every launch. Any changed old ledger, duplicate origin, concurrent claim or old-path activation rejects. The failed first slot is excluded from transfer and never refunded. All new slots begin HELD; ROOT reserves only one after independently accepting its predecessor.

| New command | Source allowance | Node suffix | Poll cap |
|---|---|---|---:|
| R350:t3_01 | one fresh replacement | `test_private_startup_to_transaction_grounding[memory]` | 2 |
| R350:t3_02 | R346:t3_02 | `test_private_startup_to_transaction_grounding[sqlite]` | 2 |
| R350:t3_03 | R346:t3_03 | `test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]` | 3 |
| R350:t3_04 | R346:t3_04 | `test_local_new_schema_ignores_utc_jump_but_external_does_not[sqlite]` | 3 |
| R350:t3_05 | R346:t3_05 | `test_b_terminal_publication_confirmation_fault[commit_close]` | 1 |
| R350:t3_06 | R346:t3_06 | `test_b_terminal_publication_confirmation_fault[confirm_timeout]` | 1 |
| R350:t3_07 | R346:t3_07 | `test_b_terminal_publication_confirmation_fault[prior_bound]` | 1 |
| R350:t3_08 | R346:t3_08 | `test_b_public_confirmed_publication_control[memory]` | 1 |
| R350:t3_09 | R346:t3_09 | `test_b_public_confirmed_publication_control[sqlite]` | 1 |

Each child retains600s, cleanup15s/TERM grace5s, capture240s and outer900s/kill-after20s. Nine future attempts total **5,400 child seconds**,8,100 outer seconds plus180 maximum emergency grace, and **15 future polls**. Across original R346 plus R350, authorization is10 total attempts/6,000 child seconds: nine originally allocated plus one fresh replacement. The original actual poll remains counted; one observed prior poll plus15 future gives at most16 actual, within17 allocated across both generations. No spent duration is refunded. The failed129.54s gives no estimate for repaired or other nodes.

Exact absolute command argv, child environment, outputs and predecessor keys are in `plan.json.commands`. Change only round/command/output paths; preserve selected nodes, pytest/plugin flags and environment. Serial order, one real prerequisite import per actual child, no hidden smoke/collection/warm-up and stop on first unaccepted outcome remain mandatory.

## Minimal successor runner and truthful historical adoption

Base the new `R350/implementation/run-evidence.py` on the accepted57,557-byte R346 runner SHA `264ba312e849a44a93fba942015c539ce2b78568787352685530707eb1b0b9ef`. Copy the complete helper unchanged, SHA `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`. Do not import or execute either historical file.

Allowed runner changes are operational R350 identity/plan/path/CAS-suffix/helper-module strings, exact new predecessor identities, and finite lineage/budget/new-source-acceptance checks. Preserve all capture, monitor, cleanup, resource and error-retention algorithms. Keep the R348 terminal/error schema versions, original fixture case/resource schemas and R348 historical path/hash; schema version names are not command identities.

The old `verify_gate` requires R348 acceptance’s `runner == pin(__file__)`. **Do not carry that claim into a renamed clone.** R348 accepted the pinned old R346 runner. In the successor:

1. Verify R348 plan/acceptance and require its reviewed runner to equal the immutable historical R346 pin. Check the historical runner bytes. Keep historical R346 gate/acceptance and failed first disposition as history, not a successful predecessor.
2. Verify R349 plan/acceptance and exact current owner source. This proves only the accepted source change.
3. Create `implementation/runner-lineage-adoption.json` binding historical runner/R348 acceptance, actual successor runner, unchanged helper, narrow-diff proof, this plan, budget disposition, actual author and R349 acceptance. It explicitly states historical acceptance does not apply to the new runner.
4. Require a **new ROOT R350 source acceptance** binding the actual new gate, new runner/helper/proof/lineage, current actor, budget disposition and R349 source repair. The reserved runner validates these relationships; no historical acceptance substitutes for new review.

Construct artifacts without hash cycles: plan/binding/disposition → runner and source proof → lineage record → source gate → ROOT acceptance. The source gate cannot pin its own future acceptance. Runtime ledgers/results remain mutable and excluded from source pins; reservations bind gate and ROOT acceptance.

The new source inventory starts from the347 historical pins and changes only owner_registration to the R349 accepted hash. Keep the other346 historical paths byte-identical, including the old runner/helper as history, then append new R350 artifacts. Deduplicate current paths so old and new owner hashes are never simultaneously required. Exact HEAD remains `729bce11bbd55a4a869e25e52174da3d0db1825b`; no arbitrary descendant is applicable.

## Preserve accepted R348 execution and capture contract

- Keep measured successful HEAD completion gap≤1.0s, target0.25s, bounded git/storage and0.1s storage headroom, distinct subdeadline/wall reasons and final-tail check. Keep actual interpreter/path/link/binary/cfg validation without new interpreter startup.
- Keep preflight35s, owned process group cleanup15s, raw stdout/stderr files, sampled32MiB stream thresholds,1GiB persistent/10,000-entry threshold,3GiB minimum free and20GiB round output bound. Retain overshoot and truthful sampled observations; no deletion to meet caps.
- Preserve the seven independent receipts: raw-process-ledger15s, source-after-observed30s, persistent-inventory90s, resources30s, JUnit10s, cases10s and prerequisite-observation10s. Finalization15s plus30s bookkeeping keeps total capture240s. A rejected stage never prevents later retention.
- Preserve raw `prerequisite.json` separately from its observation receipt, strict postrun byte stability, live directory identity-only sampling, database/WAL/SHM/journal byte copies with no engine open, actual resource provenance and missingness. No coherent-database-backup claim.
- Keep precommit result/missingness/status, then completion written last and read back. Candidate acceptance requires actual outer wrapper exit0/no timeout/signal plus complete terminal references and behavior proof, then independent ROOT disposition. Receipt existence or result alone is insufficient.
- ROOT exclusively preopens fixed R350 wrapper streams; preserve descriptor/path checks and bounded stderr-first fallback for early rejection. Failed reserved prelaunch attempts spend without child/retry/refund. All stage and fallback bounds remain unchanged.

No product/test/plugin/helper edit, extra parser probe, DB semantic query, T2 rerun or numeric/timing experiment is part of this generation. The only helper execution is the same finite parsing/byte instrumentation inside each genuinely reserved new runner.

## Preparation, review and release sequence

1. ROOT checks this plan and31 intake pins, then activates same Sol for preparation only.
2. Bind the actual same Sol afresh; record the exclusive budget disposition and initialize new nine-slot ledgers with exact origins. Old ledgers stay unchanged.
3. Sol creates the minimal successor runner, whole helper copy, narrow diff and AST/symtable/hash/retained-definition proof. Do not run/import the runner, even for help or a dry run.
4. ROOT reviews complete successor source and proof, including every changed identity/lineage/gate branch. Freeze lineage and the new exact source gate; ROOT independently accepts the actual new implementation.
5. Before each individual reservation recheck source, exact HEAD, interpreter, shared-writer quiescence, old frozen ledger pins, origin uniqueness and previous R350 dispositions. Preopen wrapper streams. ROOT consumes the selected slot, then actual author consumes before child spawn.
6. Run only the one exact reserved command. Preserve process/capture and actual wrapper status. ROOT independently reviews raw, JUnit, sidecar/case/prerequisite, source, byte-retention and terminal receipts. Only full acceptance permits the next reservation.
7. On any failure or drift stop with all later slots HELD and return to actual Astra. No old-path fallback, automatic next-node diagnosis, refund or retry.
8. After nine accepted nodes, produce the aggregate and phase report. Request a fresh actual Astra independent reviewer under the inherited unused T3 review seat; neither current planner nor author occupies that seat. No B9/fullB/final-static/C/native/model/physics/formal gate is allocated.

## Verification and acceptance boundaries

Preparation verification is stdlib AST/symtable/JSON/hash/diff and finite Git metadata only. Prove exact nine-node order/caps/command mapping, whole helper bytes, one-fresh/eight-transfer conservation, no original edits, no historical-acceptance misbinding, acyclic artifacts and capture algorithms unchanged except declared operational literals. ROOT must read the actual changed validation code; a normalized-source report alone is insufficient.

A software candidate needs all nine genuine new-generation passes, zero errors/skips, correct worker/session/thread/poll relations and cleanup, original assertions complete, all same-gate predecessor receipts and total future polls≤15. Preserve the failed first generation, accepted T1/T2 version boundaries, R311 unknown SIGSEGV and historical DB gaps. R349 source acceptance is not a behavior pass. No runtime is released merely by saving or accepting this plan; actual new-source acceptance and per-command reservation are still required.

The budget disposition has explicit `ROOT_accepted=true`, `old_generation_launches_disabled=true`, the two original ledger pins, fresh author-binding pin and exact nine origin records; it is not a runtime release. Both new ledgers carry its pin, and each slot carries the exact planned `allowance_origin`. AUTHOR verifies that origin against the plan and selected ROOT reservation before CAS. Use separate `inherits_unused_allowance` and `resets_spent_allowance=false` fields so transferring an unused allowance is never confused with resetting a spent attempt.
