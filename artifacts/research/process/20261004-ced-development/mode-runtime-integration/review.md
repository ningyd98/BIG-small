# Root mode runtime integration independent review

Verdict: **PASS for the two scoped fixes**. Overall T11 remains REQUEST CHANGES for the separate repository/cache/selection findings in `../t11-module/review.md`. This verdict does not accept actual mode selection or physical runtime integration.

Reviewed the four-file `source-hashes.json`/`source/` snapshot and exact `review-package.diff` against root's initial snapshot. All four current sources match the saved hashes. Base/head remains `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. No production or test edits were made; this review report is the only write in this package.

- `RuntimeExperimentHarness.commit_mode_transition` delegates transition/status persistence to the repository transaction and removes the second status rewrite. It therefore preserves one switch increment, the first committed timestamp and the frozen policy on both initial commit and an idempotent retry. The remaining audit event records the facade call and does not commit another mode transition.
- The API prepare endpoint now supplies its existing repository directly to ModeTransitionService and returns that prepare result. It no longer creates a new ephemeral transition per request and then saves it separately. Repeated identical requests reuse the exact original UUID/payload; changed content under the same idempotency key returns the existing conflict response without modifying the original record.
- Neither change adds a research guard bypass or claims that the real checkpoint/selection adapters are implemented. Existing service/repository CAS behavior and its separate outstanding findings still apply.

Independent verification: `.venv/bin/python -m pytest -q tests/test_runtime_harness_mode_commit.py tests/test_phase7_api_config.py` produced **6 passed in 0.93s**, exit 0. These specifically cover one switch on first/repeated harness commit, preserved policy/time, identical repeated API prepare responses and conflicting prepare content. The shared T11/legacy CPU scope additionally passed **76 tests in 50.37s**. Ruff on the scoped integration and T11 files passed. Root's recorded 34-test regression log was inspected as supporting evidence; it was not falsely described as a new independent run.

No network, provider/model calls, GPU/rendering, physical execution, real selection, or broad project suite was performed. The tests are software fixtures only.
