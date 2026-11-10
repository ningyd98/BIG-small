# R555 Revalidation Evidence State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Parent implements inline; no additional permission round. Steps use checkboxes.

**Goal:** Make returned refresh evidence reflect its completed success/rejection state, and correct one line-length finding without changing the cloud prompt.

**Architecture:** Keep the local `refresh` record authoritative and explicitly copy its final state into the currently active evidence dictionary at every existing success/rejection exit. Preserve the existing deep-copy boundaries and all planning behavior.

**Tech Stack:** Existing Python, pytest, Ruff and AST comparison.

**Spec:** This round's `request.json` and frozen R554 `plan.md`. Planner: actual `gpt-6-astra`.

## Problem and original evidence

R554 T2 first GREEN run produced **1 failed / 331 passed**. In `test_slow_cloud_uses_independently_grounded_fresh_frame_and_existing_pipeline`, the real CPU pipeline returned PLANNED, a non-null validated fresh contract and four queries, but `post_cloud_revalidation.status` was `STARTED` instead of `PASSED`. Preserve `round554-post-cloud-fresh-revalidation-20261110/task2-green.log` unchanged. `original-ruff.log` independently records E501 at `grounded_planner.py:359` (101 > 100).

Inspection confirms the evidence ownership error: shared `ground_observation` deep-copies its input evidence; `_ground` then calls `evidence.update(measured.evidence)`, replacing the nested refresh record. Subsequent updates to the local `refresh` dictionary no longer update the active evidence. Success and post-ground rejection paths therefore require final synchronization. This is diagnostic state correctness, not a geometry, TTL or cloud-response failure.

All **five frozen request inputs** were verified for exact size/SHA256; their full inventory is in `plan.json`. Before implementation retain the current source bytes as a round-local byte-preserving snapshot/archive or equivalent immutable artifact, recording its hash. Do not normalize either original failure log.

## Global constraints

Only `src/cloud_edge_robot_arm/vision/grounded_planner.py` and `tests/test_molmo_grounded_planner.py` may change under this repair, plus round-local derived evidence. Keep R554 policy/thresholds, acquisition/context bindings, default path, prompt bytes, TTL, shared geometry/tracker, pipeline, runtime and budgets frozen. No model, GPU, cloud or hardware calls in R555; R554's later independent review and actual-run gates remain in force.

## Review focus

The success snapshot, ValueError sentinel and native-perception-error draft must each contain the final local status even if nested evidence was replaced. Tests below cover success and rejection after grounding; existing native/capture failures retain their original outcome and error text. No returned completed attempt may still say STARTED.

### Task 1: Synchronize terminal evidence and apply a byte-equivalent string format

**Files:** Modify the two files named above; preserve all original inputs and write R555 RED/GREEN/lint/AST/diff evidence locally.

**Interface:** No public API changes. Immediately after updating `refresh` in each of the three existing terminal branches (success, `_NativePerceptionFailure`, `ValueError`), assign `evidence["post_cloud_revalidation"] = copy.deepcopy(refresh)` before constructing/copying/returning the draft. Keep `refresh is not None` guards so the default path is unchanged. Success remains PASSED with its existing completed timestamps; exceptions remain REJECTED with existing reason/error semantics. No early success or additional retries.

- [ ] Reverify the five hashes and preserve the source snapshot. Keep the existing failing success test; add `status == "REJECTED"` assertions to the existing support-mask mismatch, fresh-query TTL and post-candidate TTL negatives. Where the existing exception supplies a reason, assert the final nested reason matches the actual rejection. Also assert existing supplier/native-perception rejection evidence is REJECTED without changing outcome or error text; add a focused fresh-native failure case only if no existing case exercises that terminal branch.
- [ ] Run the focused success/mask/expiry cases before production edits and preserve RED. Expected failure is stale STARTED after a copied grounding record; some earlier rejection cases already pass because they precede replacement. Do not claim every new assertion failed or reclassify the original 331 passing tests.
- [ ] Add the explicit terminal synchronization described above in all three branches. Leave `_ground`, shared deep copies, geometric calculations and prompt creation unchanged except the formatting step below.
- [ ] Split only the `geometry_status` literal into parenthesized adjacent string literals, preserving the exact value `CALIBRATED_DEVELOPMENT_ESTIMATE_NOT_PHYSICAL_ACCEPTANCE`. Prove this formatting step separately: compare whole-file `ast.dump(..., include_attributes=False)` immediately before versus after the string-only edit, or compare the frozen original with an isolated formatting-only transformation. Do not require the behavioral synchronization patch itself to be AST-equivalent. Also assert the literal and serialized prompt value are unchanged.
- [ ] Rerun the focused tests, then the same R554 T2 scoped test command that produced 332 collected cases (plus any added cases). Preserve the exact command/output and expected all-pass result. Run scoped Ruff on the adapter/tests and the already applicable R554 source set; `git diff --check` must pass. Do not repair unrelated failures under R555.
- [ ] Record the three exits' coverage, source/output hashes, formatting-only AST equality and original failure references in a step report. Resume R554 T2/T3 without claiming any real native/cloud success from these CPU results. Commit only the explicit verified paths through the parent delivery workflow.

## Preconditions and acceptance

Use the original app interpreter `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`, worktree cwd and explicit `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src` for independent commands. Managed-worktree writes may require scoped escalation. Recheck input applicability before edits; concurrent T3 work must not alter the two frozen files. If a different root cause or expanded repair becomes necessary, preserve evidence and obtain the next actual Astra plan.

Acceptance: correct PASSED evidence on the already-valid pipeline positive; REJECTED evidence with unchanged failure behavior for the covered negatives; all scoped CPU tests and Ruff/diff checks pass; string-only AST and prompt bytes equal. Development-only result. This round performs **0 actual calls**. Prior totals remain **3 loads / 6 generations / 1 paid attempt**; R554's unused additional cap remains **1 / 4 / 1**, cumulative ceiling **4 / 10 / 2** after its software and independent-review gates, no retries and no hardware. No unresolved design decisions.
