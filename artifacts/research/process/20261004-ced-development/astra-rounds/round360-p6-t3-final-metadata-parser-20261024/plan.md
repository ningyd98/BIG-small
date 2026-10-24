# R360 Final Metadata Recipe Syntax Repair Plan

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Same `/root/p6_t3_sol` is the sole author and prospective metadata operator. ROOT performs metadata review; its independent complete runner review can continue.

Sol reported `python3 /tmp/r354-final-proof.py`, tool `f7d6a0`, exit 1, `SyntaxError: unmatched }` at line 121. The preserved script is 27,591 bytes, SHA256 `8042f8961a37e56b2940b272d0b7efa221b249d0834ac55def324d9f5983f89e`. Python failed before any module statement, so its binding/proof/lineage/report writes did not run. Original finding and script bytes remain unchanged; this planner did not replay the command.

The cause is the extra closing brace on **line 120**, at this unique literal:

```
Before: '}}},'AUTHOR':'initialHELD0/1
After:  '}},'AUTHOR':'initialHELD0/1
```

Delete only that one ASCII `}`. In-memory construction and stdlib AST/symtable parsing succeed, with `AUTHOR` and `transport_status` inside `reservation`, `terminal` inside `output_and_gate_contract`, and `normalization_and_scope` inside the outer proof. No second syntax defect is exposed by these static checks. The exact successor must be **27,590 bytes**, SHA256 **83ef01eefcd67751762253839837df90ceb0ca289ac6fb4f842d1669ea6610d6**.

## Permitted sequence

1. ROOT reviews this plan and verifies the twelve input pins in `plan.json`, exact HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`, branch `research/20261004-continuation`, and the output preconditions below. Activate the same Sol for this scope only.
2. Sol creates `R360/implementation/build-r354-final-metadata.py` from the frozen snapshot with exactly that deletion. Verify and retain ROOT’s existing exact snapshot `R360/author-binding-before.json`; do not make another copy. Do not modify or rerun the failed `/tmp` script or snapshot.
3. Before executing the new recipe, verify exact successor hash/one-byte diff, AST and symtable, intended dictionary nesting, unchanged imports and write callsites. Save inert `implementation/static-proof.json`. Do not import a candidate.
4. Sol runs the corrected recipe **once**, from the workspace root, solely to generate already authorized R354 metadata. Retain actual stdout, stderr and exit in R360 implementation evidence. The recipe reads candidate sources as bytes/text/AST; it does not execute them. Keep its assertions, counts and exclusive output writes unchanged.
5. Any non-syntax failure, unexpected output/input state or semantic discrepancy stops this attempt for ROOT and another Astra plan. Preserve partial outputs and actual binding state. No delete/rerun/overwrite/weakening to obtain success.
6. On success, read/hash the actual metadata, verify protected runner/observer/ledgers unchanged and binding changes limited to the existing intended fields. ROOT must independently validate claims; an exit 0 or parsing success is not evidence those claims are true. Record the step result without releasing runtime.

## Output preconditions and write boundary

At planning time, the following R354 `implementation/` paths are **absent**, including dangling symlinks: `source-proof.json`, `runner-after.diff`, `runner-lineage-adoption.json`, `author-step-report.md`. They may be created only through the recipe’s existing exclusive `x` mode. The new R360 recipe path is also absent. Recheck immediately before generation; do not overwrite newly appearing output.

The sole existing output intentionally updated is R354 `implementation/author-binding.json`: **2,235 bytes**, SHA256 `2ba4ace51671e33653fbab09a27631f9b923f0b2efdda1fc2d3321e3fc9f9d93`. ROOT already preserved its before bytes at `R360/author-binding-before.json`; that snapshot is now a twelfth plan input. Allow only recipe line 37’s already authorized reference/preparation update. The old current-path binding pin is a preparation precondition only; the future final gate must bind the actual successor hash without recursively requiring the old hash at the updated path. This is not reservation or runtime activation. Other files written by this round are its static proof, raw metadata-generation stdout/stderr/result, and step report.

Runner remains 105,341 bytes / `cec15badf5279a4a7c6811bef32dde504391fec8877e37dc289045bb1b638540`; observer remains 64,609 bytes / `397b36c31b8dd8ce03e0328586489b500cdfe25070d8510bf443c3a080a60e3d`. No candidate, product, test, helper or prerequisite edits/imports/execution; no DB engine, collection, help, probes, new tests or agents. No recipe semantic/schema/assertion edits are authorized by this syntax plan.

## Evidence and limits

`source-readout.json` records exact input pins, the in-memory parse result, structural nesting and current output states. All twelve input hashes match. Static parsing establishes syntax only: recipe claims such as 493 inputs, timer/definition counts and lineage preservation remain to be checked by the unchanged metadata assertions and ROOT review. Any discrepancy is a new issue, not permission to fix unrelated logic.

R354 remains HELD 0/1 on both ledgers; R350 three SPENT and six HELD are unchanged and unreleased. This plan adds **zero runtime allowances**. A single authorized metadata-generation operation is not a test or live diagnostic. Full R354 source acceptance, final gate and explicit reservation remain separate. Preserve original failure and later implementation outcome; do not claim runtime or behavior success.
