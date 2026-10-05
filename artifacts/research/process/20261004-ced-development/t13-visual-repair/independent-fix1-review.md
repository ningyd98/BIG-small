# Independent corrected visual-builder re-review

PASS for the corrected software candidate scope. The full thirteen-file manifest SHA-256 is `b6ae32c4bfedd8481d78ba10f543b1cd0ea5fbc436b435a3f1ce9cc0fddc6edf`. All thirteen source copies match their declared hashes and parse as Python. The original bad snapshot and first review remain preserved; the corrected immutable memory/protocol references now permit a strict import without the earlier read-only-reference exception.

Independent overlay: `/tmp/visual-repair-fix1-independent-x3cp_pkx`. Every released file was hash-compared against this overlay, and all commands set its root and `src` explicitly on `PYTHONPATH`. The builder import was printed and points into the frozen overlay, not the editable live package.

All four original direct observation, context observation, window and dependency mutations now produce `PLANNER_FAILED` while the caller's original inputs remain unchanged. A separate provider exception probe mutates every input category and throws `TimeoutError`; the caller request, contract, observations, window and physical-effect identities remain unchanged, and there are no candidate steps. The original final-clock sequence `.2`, `.3`, `7` now returns `MORE_OBSERVATION_REQUIRED` with `evidence_expired_at_publication`, timestamp 7 and no candidate steps. `independent-fix1-counterexamples.log` preserves the exact outputs.

The strict frozen scoped command passed **66 tests in 0.91s**: `tests/test_visual_repair_builder.py`, `tests/test_phase6_2_replan_resume.py` and `tests/test_visual_evidence_contract.py`. This is the same prior 62-test scope plus four new regressions, rather than the author's separate 72-test scope. Provider-copy, publication-clock, canonical target/evidence and ordinary merge checks were reviewed together.

Scoped Ruff passed for both frozen owned files. No-incremental mypy with imported modules treated silently passed for the one frozen owned source; this is not a whole-project or dependency typing claim.

No command dispatch, plan activation, gateway ACK, compensation, recovery resolution, actual calibration, model endpoint, GPU work or physical acceptance occurred. The builder remains a candidate generator for the existing `ReplanApplyService`; submit-time T10 and SafetyShield revalidation remain required. LOCAL_RECOVER and actual admission remain closed.
