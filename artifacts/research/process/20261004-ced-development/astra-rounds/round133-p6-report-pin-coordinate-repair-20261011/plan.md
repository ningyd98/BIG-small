# R133 Report-pin path-coordinate repair plan

Actual planner: gpt-6-astra /root/astra_status_plan. Status: pending ROOT activation. Same sole author /root/p6_stage_a_sol replacement GPT-6.1-sol. This round repairs the new metadata script only; it does not execute that script or any product/test validation.

## Verified source-only finding

ROOT's immutable pre-execution review is `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/script-review.json`, SHAce8dcb6f805376827c4d372311660f17f54d87f2e7a5865f2738e5719a81473f. Frozen305-line script is `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/implementation/stopped-script-review/generate-report.py`, SHA3465bccdfc648608dc7fb1c804eefd570dae7fb57ec4565eea3cf2993f566c19,22976 bytes; the current script matches it. No generator execution or traceback occurred. Report remains absent and the R131 metadata allowance remains0/1; this is a source-review finding, not an observed runtime failure.

Independent full-script reading confirms two expressions with one root cause: lines181–182 compare R129's exact relative `src/...` input key to an absolute current path, selecting zero records; lines183–184 then compare absolute receipt dictionaries to raw relative R129 dictionaries, which cannot be equal even if content is identical. R129 intentionally mixes some relative original-repository pins with absolute metadata pins, whereas R131's input receipts are absolute. Neither historical plan nor its records may be normalized in place.

The rest of the finite checks were reviewed without running the generator, importing it, evaluating its helpers/regex or parsing AST:

- Both before/after drafts have the15 top-level test functions and11 explicit variant decorators in the same order. The actual lists use double-quoted strings, no trailing commas inside JSON lists; current multiline whitespace and optional trailing decorator argument comma are supported by lines81–87. No demonstrated decorator-regex defect; do not rewrite it speculatively.
- TEXT_MANIFEST expands to original20 followed by new19, matching exact R127 order; RED order is new19 plus four corrected existing nodes. Do not sort, set-normalize or weaken ordered equality.
- Real ROOT ledger keys are commands, inherited_commands, inherited_consumed, final_gate and no_budget_reset. Values are respectively new5 at1/0/1, inherited3 at1/0/1, prior consumed5 at1/1/0, HELD and true. Script's existing key/argv checks match; do not rename keys or reset counters.
- Source-only finite tally distinguishes polls26/22/20 from full lifecycle bounds28/22/22 after adding the two legacy acquire/start-only controls where selected; all ≤64. No measured runtime/resource claim is permitted. Fixed call/loop source checks, byte/diff checks, four D1–D4 descriptions, exclusive-create output and no product import/subprocess design remain intact.

No further supported metadata problem was found in this bounded review. R132 completed independently and its state change is unrelated; do not read/write/restore the old state as part of R133.

## Sole editable script and exact repair

Only editable existing file:

`/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round131-p6-test-report-count-recovery-20261011/implementation/generate-report.py`

Retain PRODUCTION from exact R127 scope.owned_paths minus the single exact TEST_RELATIVE, preserving ordered five-name equality, uniqueness and the separate state_machine protection. Do not return to broad prefix selection.

For each selected relative path:

1. Select exactly one raw R129 input record by `pin['path'] == relative`. Require the recorded path to be that exact repository-relative owned name. No guessed suffix, fallback to an arbitrary basename or match against another coordinate system.
2. Independently resolve the raw record under WORKSPACE and the expected current owned path; require the same exact resolved absolute file identity within this fixed workspace. Retain the current absolute receipt path convention used by R131 (do not rewrite all R131 pins to resolved/relative strings).
3. Read the actual current file and compare its bytes and SHA256 with raw R129 bytes/SHA256 fields. Compare its complete absolute receipt with the exact R131 absolute pin separately. Do not compare the complete raw relative dictionary with the absolute receipt. Duplicates/missing records/hash mismatch stop; no silent deduplication or value coercion.
4. In report provenance preserve both the unmodified raw R129 record and the normalized absolute current receipt, with the explicit raw-record→resolved-absolute mapping. Existing unchanged_owned_production can remain a list of absolute receipts; a separate production_pin_mapping may hold raw and normalized representations. Label coordinate systems so a consumer never mistakes the derived receipt for an original pin. Preserve R131 absolute inputs and separate protected state-machine receipt exactly.

Bounded edits may add a small mapping helper, replace the production-loop selection/comparison, and add the corresponding report provenance fields. Report references may identify R133 as metadata-script repair while retaining R131 as the actual report-generation allowance. Do not add general schema migration, rewrite plan pins, change nodes/regex/tally/budget checks, product sources, tests, D1–D4, frozen before/after/diff, or output path. Original failed script/report-filter evidence and ROOT script-review.json stay immutable. Snapshot repaired script and limited diff separately under R133/implementation.

## Preconditions, review and inherited execution

ROOT first rechecks these plan/input pins and that the current script equals frozen pre-repair bytes, current test remains4a29c6792d0f4226d76f77572dbe63ee4b8d8be96936571739d3dd2b5e321908, five production/protected pins and product ledgers remain unchanged. During authorized editing only the sole script's before pin becomes expected authorized drift; retain the before receipt and pin after-script separately, never refresh the original before record to hide changes.

Author writes the bounded script change and R133/implementation/change-report.json (before/after SHA/bytes, mapping diff, raw/absolute coordinate examples, unchanged surrounding checks). ROOT text-reviews the entire revised script and limited diff; no AST/import/compile/probe or executing a fragment to test it. The fixed five schema records are inspected as metadata, not imported product code. Any new substantiated cause or expanded scope stops for actual Astra.

Only after that review may ROOT explicitly resume the **existing unused R131 single generator invocation**, with exactly its original argv/cwd/env, separate actual stdout/stderr/exit capture and exclusive-create target:

`/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round129-p6-root-read-and-test-draft-review-20261011/test-draft-repair.json`

R133 creates zero extra executions and resets none. It does not run the generator itself, authorize a retry, or consume RED/static commands. Output must still be absent; if it exists stop rather than overwrite. Keep R131 failure/receipt paths unchanged, and identify the reviewed new script SHA in its execution receipt. New stdout/stderr streams must be actual process streams, not reconstructed historic traces.

Allowed new ROOT metadata is confined to `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round133-p6-report-pin-coordinate-repair-20261011/`: input-check.json, root-activation.json, executor-brief.md, dispatch.json, script-review.json, validation.json, step-report.md/json, phase-summary.md, ledger.md/json and implementation/change report/before-after script/diff. Existing R131 script is the sole repair target. No active-t12-state update or R132 rollback. Established phase summary may append this metadata-only outcome without erasing history.

## Acceptance boundary

R133 source-only repair completes when relative selection plus explicit absolute identity/content comparison are correct under ROOT text review and all original evidence/scope/budgets remain. Actual successful report generation is still R131's separate single metadata outcome. ROOT must then review report and corrected test diff before R129 completion and R127 RED23 resume. Original39 nodes,23 RED,64 lifecycle cap and all four final holds remain unchanged. No software correctness, actual/native/paid execution or formal research acceptance is granted by this metadata repair.
