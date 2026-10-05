# Risk supervision workspace isolation correction

Software correction checks PASS; independent re-review PENDING. Actual RISK remains UNKNOWN and METHOD/execution remain NOT_RUN. No original frozen source or report was changed.

## Finding and narrow correction

The reviewed registration used `replace(raw.criteria)`, retaining caller-owned `workspace_min_m` and `workspace_max_m` lists inside CompletionCriteria. The auditor's later registration copy and concrete RAW copies shared those same lists. Changing a caller list could therefore change frozen task-label reconstruction while every original evidence file hash remained unchanged.

The supervision boundary now reconstructs concrete CompletionCriteria with two detached immutable three-element tuples. It validates each workspace item through the already reviewed strict finite-number helper, then retains the original number rather than its converted validation result. Legitimate list and tuple inputs remain supported; bool values and malformed workspace shapes reject. Every other criterion field is preserved by `replace`, and public dataclass fields/API remain unchanged. Auditor registration copies pass through the same corrected boundary; downstream shallow RAW copies receive immutable tuples. The original RAW reader was not edited.

Owned files only:

- `src/cloud_edge_robot_arm/research/risk_supervision.py`
- `tests/test_research_risk_supervision.py`

The change does not widen admission, alter risk fitting, or modify clock/calibration, allocation, history, terminal-label, INITIAL or actual-method rules.

## RED and GREEN evidence

The exact original `root-criteria-alias-probe.py` was replayed unchanged against the old frozen515 source and reproduced its assertion failure: SOFTWARE_ONLY diagnostic VALID/two rows changed to INVALID/zero rows after only `workspace_max_m[2]` changed. Original file hashes were unchanged. See `red-original-root-probe.log`.

Five new cases cover both min/max list mutations, both min/max boolean bounds, and a legitimate tuple/scalar policy control. Before correction, the new tests produced four qualified failures and the control passed. The final test assertions were also verified against unchanged frozen production: `red-criteria-isolation-final-tests.log` shows four failed/one passed/37 deselected. The first GREEN attempt detected a test-only error-message matcher (`number` versus the existing helper's `numeric`); that matcher was corrected without changing production behavior. Its failed log is preserved in `green-criteria-isolation.log`.

The fixed frozen overlay passes the original probe unchanged: before and after caller mutation, the diagnostic remains VALID with two rows, while actual source remains UNKNOWN. Both regression bounds preserve rows, counts and original inventory. The tuple control verifies every other criterion field and retains an integer zero as an integer. These are software reconstruction checks, not risk or physical acceptance.

## Verification

All checks ran from the exact frozen source copy, with an environment-only interpreter link and no moving live-production fallback:

- Original37 plus new5 owned tests: **42 passed in 15.46s**.
- Original178 plus new5 related cases: **183 passed / one compiled-dynamics test explicitly deselected in 32.47s**.
- Ruff2, format2 and cold mypy1: PASS.
- Original independent source script: exit0, unchanged original hashes, stable two-row diagnostic, actual UNKNOWN.
- All515 archived and isolated source hashes match; all387 Python files parse; live owned2 hashes match. Public dataclass fields are unchanged.

The first related run produced 182 passed/one failed/one deselected because the isolated directory lacked `.venv/bin/python`, used by `test_cli_missing_dataset_is_incomplete_and_never_enables`. The original reviewed setup had that environment-only symlink. Adding the same link made the focused test pass and the full183-case rerun pass. No production/test/source fixture changed for that environment correction. The failed run is retained in `frozen-cpu-first-environment-failure.log` and its result JSON.

The scope contains software numerical fixtures, recorded-file reads and static MjModel compilation for RAW controller constants. It creates no simulator state, steps, renderer/capture, provider/network request, actual learned-model inference or new controller action. The existing compiled-dynamics unit test is deselected, not claimed passed. Missing actual source/clock/calibration/risk commit/selection prerequisites remain named and fail closed.

## Immutable handoff

`source/` contains the exact reviewed515 dependency closure with only the two owned files changed; the other513 references are byte-identical. Basis manifest: `e7a13e97760d27eb15ecd321cd856f1726c1c58690d52156d13ff9cfe8d52a95`. Basis independent review: `9365244d2991e86651be0ac5c64a97abe00b56a4ab4becfd7bdfba5c24435c4d`. New manifest: `389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8`.

All554 files present in the old package at fix start retain their hashes, including its original515 source and existing release/review artifacts. Historical532 release artifacts are preserved within that inventory. New files are additive in this separate correction directory. No moving worker source was imported into the freeze. See `original-package-artifact-hashes.json` and `post-source-artifact-hash-check.json`.

Exact commands, cwd and environment are in `frozen-overlay-setup.json`; exit codes/log tails in `frozen-command-results.json`; the expanded test list in `frozen-collected-tests.log`; ownership and narrow source diff in `ownership.json` and `review-package.diff`. No full suite, actual collection, commit or admission toggle was run. Owned source is now quiet pending independent re-review.
