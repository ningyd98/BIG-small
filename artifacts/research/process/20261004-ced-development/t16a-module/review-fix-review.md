# T16a independent corrected software review

Verdict: **PASS** for the corrected six-file SOFTWARE_ONLY snapshot. Both P2 findings from `review.md` are closed. No production or test files were edited by the reviewer; no actual research, physical execution, selection or acceptance was performed.

The corrected `source-hashes.json` SHA256 is `6460a3b03c8fa1bd76023779b8c663122dc4b11cf20756fcb836695d2190e9f2`. All six declared live files and saved `source/` copies matched that manifest before and after review. The original released snapshot remains in `fix-round-1-baseline/`; the original independent review remains in `review.md`. Reviewed the new scoped correction diff and the original findings, rather than replacing the original review history.

Independent verification:

```bash
.venv/bin/python -m pytest -q tests/test_research_statistics.py tests/test_research_acceptance.py
```

**43 passed in 9.54s**, exit 0. Scoped Ruff passed the six files. Mypy passed the four source/CLI files, with only the existing unused ROS configuration note. The statistical implementation and original independent constrained-likelihood/interval checks remain unchanged by this correction.

The original request-target failure with undecided NI now remains FAIL. An entire success interval below the -3pp margin and an entire safety interval above the +1pp margin independently return FAIL. Intervals crossing those boundaries remain INSUFFICIENT_EVIDENCE. Default actual-source evaluation still returns NOT_RUN in all five independent reproductions; software numerical results retain their explicit SOFTWARE_ONLY scope. Holm adjustment cannot erase an existing definite target or NI FAIL.

For two episodes with one UNKNOWN condition judgment and 99 PASS judgments in the other episode, canonical `unknown_condition_count`, `condition_evaluation_denominator`, `unknown_condition_rate`, `fallback_decision_count`, `decision_round_denominator`, `fallback_decision_rate` and `fallback_rate` are all None. Both canonical diagnostic statuses explicitly say NOT_RECORDED and identify the required source-qualified record basis. Additional `unknown_episode_rate` and `fallback_episode_rate` remain .5 with names that state their episode denominator. Missing typed condition/decision sources are therefore visible; the episode summaries no longer substitute for the preregistered condition and decision ratios.

The review establishes corrected software reporting behavior only. Typed raw condition/decision source integration and actual model/physics/timeline acceptance remain unavailable and cannot be inferred from flags or hashes. No new findings were identified within this six-file correction scope.
