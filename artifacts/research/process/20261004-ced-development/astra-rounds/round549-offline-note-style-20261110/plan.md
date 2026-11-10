# R549 Offline Note Style Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this single bounded edit. Existing authorization applies; no further review or sub-agents.

**Goal:** Clear one E501 without changing any runtime value.
**Architecture:** Split one literal into adjacent literals in parentheses.
**Tech Stack:** Existing Python/Ruff.
**Spec:** R549 request.json; actual planner_model `gpt-6-astra`.

## Problem and scope

Original final-ruff.stdout reports exactly one E501 (108>100) at R547 implementation/replay_association.py:129, the `note` literal. Root cause is line length only. Both input bytes/SHA256 matched. Change only that literal's source layout; production, tests, geometry, runtime and historical evidence remain untouched. No public push.

## One task and verification

- [ ] Recheck both input hashes; preserve original lint output. Save pre-edit `ast.dump(ast.parse(source), include_attributes=False)` and the note's evaluated string.
- [ ] Replace only the note value with:

```python
"note": (
    "Static-only calculations bypass no production gate; "
    "archived frame remains stale."
),
```

- [ ] Require exact pre/post whole-file AST equality and exact note string equality, including the space after semicolon.
- [ ] Rerun the identical existing 13-file Ruff scope and `git diff --check`; both must exit0. Inspect diff for only the literal wrap. Reuse the prior321 scoped regression PASS, focused28 PASS, offline diagnostic PASS and runtime preflight PASS; no test rerun is needed because source semantics and production/tests are unchanged.
- [ ] Record original/new file hashes, AST/string equality and lint/diff exits in a short R549 implementation report. Preserve old log bytes and locally stage only the scoped diagnostic edit and intended reports.

## Preconditions and acceptance

Existing app Python/Ruff and approved managed-worktree access suffice; no installs. Acceptance is byte-equivalent evaluated note, identical AST and clean lint/diff. Unexpected AST change or any other failure requires a new Astra plan before broader repair. This round performs zero model/cloud/hardware calls; cumulative1load/2generations stays unchanged and R547 optional remaining1load/2generations remains unspent. No real-local/cloud/physical/formal acceptance is created.

## Verified inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round547-molmo-point-component-association-20261110/implementation/replay_association.py` — 5789 bytes — SHA256 `3dcb63c59f742f8801067d7541ca9332bb74f72d1baed6f4b7d93d17ca94fb17`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round548-association-test-contracts-20261110/final-ruff.stdout` — 607 bytes — SHA256 `36bfc08c6bbe1058a170388589fa71bdb14c1b36ac152981eacbde45e1400148`
