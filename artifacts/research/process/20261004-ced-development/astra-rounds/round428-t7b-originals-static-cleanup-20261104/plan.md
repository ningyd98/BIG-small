# R428 unused-import cleanup Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans, parent inline.

**Goal:** Clear Ruff F401 without changing tested behavior.
**Architecture:** Delete one unused test import; preserve production and R427 evidence.
**Tech Stack:** Python AST, Ruff.
**Spec:** intake/observation.json (8 SHA pins); plan.json pins that manifest.

### Task 1: Delete unused import

Failure: original R427 validation/static/ruff.stdout.log reports unused pathlib.Path at test line9. AST inspection confirms no Path Name usage. R427 functional GREEN59PASS remains valid; format/mypy already passed.

- [ ] Recheck all8 input pins. Preserve exact test preimage at R428/preimage/test_native_completion_originals_v2.py with original SHA before editing.
- [ ] Delete only `from pathlib import Path` from tests/test_native_completion_originals_v2.py.
- [ ] Run both exact Ruff commands in plan.json,60s each; require exit0. Compare AST with the preimage after removing exactly this ImportFrom, ignoring locations; assert production SHA unchanged and textual diff only this line.
- [ ] Preserve raw F401 and59PASS evidence; record result, then parent fresh review and explicit-path delivery.

No production edits, raw edits or pytest rerun for this unused import. All prior frozen boundaries remain. Unexpected failure or scope growth requires another actual Astra plan. Acceptance is static cleanup only: SOFTWARE_ONLY; actual/formal NOT_STARTED.

Evidence clarification: R427 omitted --junitxml; report JUnit **NOT_PRODUCED**. Existing raw pytest-events.jsonl phases, stdout59PASS, supervisor raw-exit/result and prerequisite records are authoritative execution evidence. Derive the summary from those actual events; do not fabricate JUnit or rerun59 solely for redundant output. No wrapper change/reuse in R428.
