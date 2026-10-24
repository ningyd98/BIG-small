# R340 Cap Source Proof Convention Implementation Plan

> **For agentic workers:** Use the existing same-Sol execution workflow only after ROOT activation. No new agents or runtime actions.

**Goal:** Correct the metadata segment extraction and continue exactly the already approved R339 replacement.

**Architecture:** Preserve R339's AST segment hash convention and both expected hashes. Correct the new verification command, not the source policy or historical evidence.

**Tech Stack:** Standard-library AST, UTF-8 text, SHA256, optional symtable; source-only work.

**Spec:** `root-finding.json`, the pinned original R339 command/traceback/failure evidence, and R339 `plan.json`. Actual Astra: `gpt-6-astra`, `/root/astra_p6_t3_plan`. Same implementer: `/root/p6_t3_sol`, awaiting ROOT activation.

## Exact failure attribution

Actual tool chunk `7a40c0` exited 1 with `AssertionError` at stdin line 4, before any writes. That line has two assertions. The R338 frozen `operational_windows.py` has SHA `6e025a3d203d50640d65ee01c6fce3ea76cb36fdd7148a460e3a130b3f7a9b7c`, identical to the failure record's source input; it provides historical input reconstruction without treating the current whole file as frozen.

On those bytes, the first predicate `text.count(old)==1` is true. The second predicate fails: the command hashes all complete source lines, yielding 892 bytes and SHA `73e01450c5c53f7666536422909410b3f48575f53b5fbeecabfa5407d62c0898`. The prescribed AST segment is 887 bytes with the unchanged expected SHA `7fdd632f6bd6e93cb9d5a203cf245217f5bd27e5f336eced66be94d1491d2837`. The full-line representation is exactly four leading ASCII spaces plus the canonical segment plus one LF. This proves the specific failed predicate rather than guessing from the traceback line.

`source-convention-readout.json` records these source-only results. Original command text was parsed, never executed or rerun. All original evidence remains at its pinned R339 paths; `plan.json` lists complete input hashes.

## Constraints and scope

Create a distinct corrected metadata command/proof under R340. Select exactly one `OperationalWindowOwner` class and its direct `_remaining_app_seconds` method. Extract with `ast.get_source_segment(decoded_text, node).encode("utf-8")`, without stripping, dedenting or appending a newline. Place assertions on separate lines with named diagnostics.

Continue only R339's exact replacement of the rounded multiply condition with its `as_integer_ratio()` assignment and integer cross-product condition. Original target SHA remains `278da2ca8e6d25b1067a8cc0e7fde56ac1eb6c8b7f3ca5f16bbcf8e298e3e999`; successor SHA remains the value above. No algorithm, owner/thread, clock, hard-bound, positive check, other definition or expected hash changes.

No product imports/calls, tests, collection, numeric trials or runtime execution. RED remains SPENT; GREEN remains UNUSED/HELD, nine nodes and max15 worker polls. Do not rerun or overwrite the failed command, change old plans/evidence, restore an old whole source file, or reset any allowance. Independent R331/R338 work continues outside the selected definition.

## Execution sequence

- [ ] ROOT verifies original evidence hashes and current selected-definition applicability, then activates the same Sol. Surrounding-file drift is not a rollback condition. Target drift requires reconciliation before this repair continues.
- [ ] Sol saves a new corrected metadata command and reads the immediate live source. Verify the original canonical segment SHA and exact single target replacement. Construct the candidate text, parse AST and optionally symtable, and extract the canonical candidate using the same class-qualified selector.
- [ ] Require candidate equality with the frozen segment after exactly the R339 replacement and the original successor SHA. Check source diff contains only that replacement. Before writing, re-read the file to avoid overwriting concurrent edits; if surrounding bytes changed, recapture and rebuild from the latest source while requiring the unchanged target pin.
- [ ] Apply only the approved R339 edit, save immediate before/after and minimal diff in distinct R340 evidence, and record individually named static predicates. No product execution.
- [ ] ROOT independently checks the canonical final segment/hash and exact allowed diff, preserves the original failure, and writes R340 acceptance/step disposition linked to R339 before later GREEN source-gate preparation.

## Prerequisites and boundary

Only ROOT's review/activation and applicable source pins are needed for this source-only repair. No runtime is authorized here; original R331 actor/source/HEAD/resource gates, including applicable R337 disposition and other correction acceptances, remain required before future GREEN. Acceptance establishes the metadata convention and exact R339 source successor only, not a runtime pass, T3 completion, B final gate or C/native/model/physics result. A new cause/scope or unexpected validation failure pauses affected work for Astra; unrelated work may continue.
