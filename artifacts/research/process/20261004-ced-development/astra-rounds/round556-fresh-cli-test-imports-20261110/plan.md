# R556 Fresh CLI Test Imports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Parent implements inline; no additional permission round.

**Goal:** Resolve the single I001 finding without changing test behavior.

**Architecture:** Apply exactly the preserved Ruff import-order/grouping diff inside `same_session_fixture`; no other code changes.

**Tech Stack:** Python AST, pytest, Ruff.

**Spec:** Adjacent `request.json` and `original-ruff.diff`. Planner: actual `gpt-6-astra`.

## Evidence and scope

R554 CLI verification already passed **26 tests** (`task3-cli-green.log`). `original-ruff.log` records one I001 at `tests/test_molmo_grounded_cli.py:504`. The read-only Ruff diff places `import scripts.probe_molmo_grounded_planner as cli` before the cloud_edge imports with a separating blank line, and removes the blank line between cloud_edge imports and imports from tests. The cause is the existing configured import classification/grouping, not a runtime or feature defect.

All **four inputs** have verified byte lengths and SHA256 values; `plan.json` contains the exact inventory. Preserve the original source snapshot, failure log and diff byte-for-byte. Do not normalize original unified-diff whitespace for publication; use byte-preserving archival if needed.

## Task: Exact import-group repair

**Modify only:** `tests/test_molmo_grounded_cli.py`, the leading import block of `same_session_fixture`. Round-local reports/snapshots are permitted. No public interfaces, imported aliases, statements outside this block or production files change.

- [ ] Recheck all four input hashes; retain the pre-edit test file as an immutable local snapshot/archive with its original SHA256.
- [ ] Apply exactly `original-ruff.diff`: move the existing scripts import before the cloud_edge group, retaining a blank line after it; remove the blank line before imports from tests. Keep the datetime/types group and every import module/name/alias intact. Do not run broad automatic fixes.
- [ ] Compare ASTs after normalizing **only this function's contiguous leading import nodes** to a canonical order by their full `ast.dump(include_attributes=False)` representation. First assert the same multiset of complete import-node ASTs, then compare the complete module ASTs with only that block normalized. Require identical function signature, all import aliases and every sibling statement. A whole-file import sort or normalization of other nodes is forbidden. Also check textual diff equals the preserved intended import change.
- [ ] Run `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest tests/test_molmo_grounded_cli.py -q` in the managed worktree with explicit `PYTHONPATH=<worktree>/src`; require all **26 tests pass**. Run scoped Ruff on this test and the R554 applicable source set, then `git diff --check`; require success. Save fresh outputs separately from original logs.
- [ ] Record AST equality after the specified normalization, test/lint/diff results and final source hash in the R556 step report; resume R554 verification. Commit only explicitly verified paths via the parent workflow.

## Preconditions, review focus and acceptance

Use the frozen worktree input and existing app runtime; managed-worktree writes may require scoped escalation. No package installation, model/cloud/GPU/hardware calls, runtime changes, policy/TTL changes or budget changes. The moved imports stay inside the same fixture and before its first non-import statement; CPU tests check that their reordered import side effects remain compatible. If another issue or wider fix is needed, preserve its evidence for a new Astra plan.

Acceptance is limited to the exact Ruff change, preserved imports and other AST nodes, 26 CPU passes, scoped lint and diff checks. This turn is plan-only. R556 consumes **0 actual calls**; R554's unused additional 1 load / 4 generations / 1 paid attempt and prior cumulative 3 / 6 / 1 remain unchanged, subject to its independent review and real-run gates. No unresolved decisions.
