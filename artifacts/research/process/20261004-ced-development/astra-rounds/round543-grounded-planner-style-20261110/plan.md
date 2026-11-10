# Grounded Planner Style Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Existing user authorization covers this bounded repair; no further architecture approval is needed.

**Goal:** Remove exactly three scoped lint findings without changing runtime strings or test callable behavior.

**Architecture:** Split two Python string expressions across lines and replace one assigned lambda with a local def. Keep all model, geometry, security and validation interfaces unchanged.

**Tech Stack:** Existing Python >=3.12, pytest and Ruff environments.

**Spec:** R543 `request.json`; R542 `docs/superpowers/specs/2026-11-10-molmo-opencv-grounded-planner-design.md` remains the integration spec.

## Global Constraints

- Actual planner_model: `gpt-6-astra`; round `round543-grounded-planner-style-20261110`.
- Recheck all five input bytes/SHA256 before editing. They matched during planning.
- Only `src/cloud_edge_robot_arm/vision/grounded_planner.py` and `tests/test_molmo_grounded_planner.py` may change under this repair. R543 evidence reports may be added; never overwrite original failure files.
- No behavioral, dependency, security, coordinate, calibration, cloud identity, prompt-content or acceptance change; zero model loads, generation calls, paid calls or hardware dispatch.
- Parent reports five previous routine Ruff fixes already applied during R542. This plan begins at the currently hashed files and neither undoes nor expands those edits. R542 T1 commit `3a96a539`, T2 commit `cabbeacc`; T3 remains uncommitted.

## Review Focus

- Concatenated prompt bytes must remain identical, including spaces before `Schema:`; verify literal equality/AST equivalence for production file.
- Geometry status string must remain exactly `CALIBRATED_DEVELOPMENT_ESTIMATE_NOT_PHYSICAL_ACCEPTANCE`; same check.
- `advance()` must still mutate the captured list by six seconds and return None; run all four expiry-test cases.
- Newly added six edge cases were not in the parent-reported 54 passing cases; run the full current test file, not a saved old test selection.
- Concurrent independent Task4 work must not be staged or rewritten as part of this two-file repair; inspect explicit diff and stage only named paths.

---

## Failure evidence and root cause

Original Ruff command exited 1. `original-ruff.stdout` reports E501 at grounded_planner.py:220 (104 > 100) and :230 (101 > 100), plus E731 at test_molmo_grounded_planner.py:320. Stderr is empty. The first is a prompt literal, the second a geometry-status dictionary value, the third `advance = lambda: clock.__setitem__(0, clock[0] + timedelta(seconds=6))`. These are style violations; no functional defect is inferred. Parent reports 54 T3 functional tests already passing before six added edge cases, adjacent 119 and native-provider 33 passing. Those prior results are context, not post-repair evidence.

## Task 1: Apply exact style-only repair and verify

**Files:** Modify `src/cloud_edge_robot_arm/vision/grounded_planner.py:220` and `tests/test_molmo_grounded_planner.py:320` (line numbers refer to frozen R543 input).

**Interfaces:** Existing cloud prompt, `geometry_status` value and zero-argument callback `advance() -> None` remain behaviorally identical. No new public interface.

- [ ] **Step 1: Preserve RED and input identity.** Recheck request input hashes and retain original stdout/stderr. These recorded three Ruff findings are the RED evidence; do not add redundant tests for line wrapping. Save the production file's `ast.dump(ast.parse(source), include_attributes=False)` before editing for exact syntax-tree comparison afterward.
- [ ] **Step 2: Make only the three named replacements.** Split the prompt literal into adjacent string literals within the existing parentheses, preserving every resulting character. Wrap the geometry-status value in parentheses with its exact unchanged string (or concatenate two exact adjacent portions). Replace assigned lambda with:

```python
    def advance() -> None:
        clock[0] = clock[0] + timedelta(seconds=6)
```

  Preserve closure capture, invocation sites and surrounding clock logic. Do not run broad automatic or unsafe fixes.
- [ ] **Step 3: Verify style and semantic preservation.** Compare pre/post production AST dumps for equality. Inspect the test diff for only the local callback rewrite and confirm six-second mutation plus implicit None. Run the existing Ruff executable with `ruff check src/cloud_edge_robot_arm/vision/grounded_planner.py tests/test_molmo_grounded_planner.py` and `git diff --check`; expected zero exit codes and all checks passed.
- [ ] **Step 4: Run functional regression with the same existing explicit interpreter/environment as the R542 passing runs.** From the managed worktree, run `python -m pytest tests/test_molmo_grounded_planner.py -q -p no:cacheprovider` using that absolute interpreter path, then `python -m pytest tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py tests/test_molmo_pointing.py -q -p no:cacheprovider`. The current grounded file should cover the reported 54 plus six edge cases; adjacent baseline is 119 plus 33. Record actual collected/passed counts and reconcile any difference rather than assert a guessed number. All selected cases must pass. Use already authorized host/loopback permissions when required; do not fix unrelated environment or full-suite problems here.
- [ ] **Step 5: Record and commit explicit verified paths.** Create R543 implementation report recording old/new hashes, commands, interpreter, exits, actual test counts and raw log paths; link it from R542 phase report. Stage only the two scoped files plus the intended round reports as part of the applicable R542 T3 verified delivery. Follow existing development-branch push/SHA verification policy; no unreviewed independent Task4 files or local raw/assets.

## Preconditions, acceptance and stop boundary

The managed worktree requires approved write access; original-root existing runtimes supply dependencies. Verification needs the same test environment and host loopback access that passed R542. This plan permits no runtime installation or file changes outside scope. Expected final evidence: exact production AST equivalence, three findings removed, complete current grounded and adjacent suites passing, no new behavior. Software style acceptance only; REPLAY/model-runtime/cloud/physical/formal-research acceptance are NOT_PERFORMED by R543. Any different lint finding, hash drift, failed functional assertion or requested semantic change pauses affected repair for another actual Astra plan. Independent R542 Task4 work may continue.

## Exact verified inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/grounded_planner.py` — 13391 bytes — SHA256 `3a6a75d36bfc3fbc518d608f700025b74d85797a2c8372e34d049d910b63e892`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_grounded_planner.py` — 18289 bytes — SHA256 `8a1459fbfe5af0203340bba59b54e427d926f02285cfe804f45c979dc08f8ae7`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round543-grounded-planner-style-20261110/original-ruff.stdout` — 1753 bytes — SHA256 `710fd466eee4692625214fe48c71481f7adf2fb51b4a965c607dfeb483c9cc5c`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round543-grounded-planner-style-20261110/original-ruff.stderr` — 0 bytes — SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Request SHA256: `9ab121f4ededda978504cc8c5786a7c8f87f12e6c5e1dbd8f232bbf79a0554ff`.

Self-review: all three failures have exact bounded edits and verification; no unresolved design choice; this planner changed no production code.
