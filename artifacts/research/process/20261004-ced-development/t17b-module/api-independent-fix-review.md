# T17 API corrected independent review

Verdict: **PASS** for the corrected API software scope. The original P2 null-assignment HTTP500 finding is closed. The reviewer changed no production or test files, and did not review their own frontend as an independent reviewer.

All15 saved source copies matched manifest SHA256 `ff22d4801aa1fd366a73c43a2afe09bec1de5c49f2c9f9865d3b62ac54ddb869`. The original release remains in `fix-round-1-baseline/`; the original independent finding/report/probes remain preserved. Because parallel T8 development changes protocol dependencies, runtime verification used a temporary source overlay with all released reference files restored exactly. Overlay path: `api-fix-independent-overlay.txt`.

Independent scoped command against the frozen test copy:

```bash
env PYTHONPATH=/tmp/t17-api-fix-review-zxbce3rf/src:. .venv/bin/python -m pytest -q /tmp/t17-api-fix-review-zxbce3rf/tests/test_research_results_api.py
```

**25 passed in15.49s**, exit0, with the existing Starlette BlockingPortal deprecation warning. The API now explicitly validates assignment manifest/row shapes, formal-pool/row shapes and record-line assignment objects before mutation/indexing. There is no blanket catch of unrelated programming exceptions. Ten coherently rehashed malformed raw-source regressions pass. An additional independent warm-cache replay of the original null-assignment source and its updated report source hash now returns409 with `research_artifact_invalid`; the earlier complete4200-record view is not returned from cache.

The previous independent seven-file cache invalidation, registration change, failed-assignment omission and export/view equivalence checks remain relevant; the correction changes only raw-table shape rejection. Read-only allowlist/auth, complete failure denominators, source recomputation, same-view export and literal actual NOT_RUN/false/0 boundaries remain intact. No source declaration or typed VALID has gained actual physical authority.

Native-layout scoped Ruff passed the API/test/app, and native mypy passed the three jointly checked API/reproduction sources; their six native target files were rehashed against the reviewed snapshots. Temporary overlay-wide Ruff initially had two test import-classification warnings; a full-import overlay mypy run also exposed an unrelated `cloud/planning/pipeline.py:487` str|None assignment diagnostic. These are recorded as verification limitations, not hidden as source passes. Frozen reviewed-file mypy with `--follow-imports=silent` passed all three files; the native project-layout gate passed. No full-source typecheck or unrelated pipeline fix is asserted.

Actual research/T16b/physical acceptance remain NOT_RUN. This review closes the API software finding only; frontend independent review and real browser smoke are root-owned, and missing B0/G3/G4/risk/decision source integration is not claimed.
