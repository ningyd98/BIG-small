# T8 raw hooks independent fix-round-1 review

Review date: 2026-10-04. Scope: original `review.md`, refreshed `fix-round-1.diff`, `fix-round-1-hashes.json`, appended `report.md`, and the exact backend/teacher/test sources. All three frozen hashes match current files, including the refreshed import ordering. Only this review was written; no production code was edited.

**Scoped specification verdict: PASS (software only).**

**Code-quality verdict: PASS.** Both prior findings are resolved; no remaining P1, P2 or Minor finding identified in this narrowly scoped patch.

## Resolved findings

- Original P1, teacher reentry clearing an outer read-only flag: `run_teacher_episode` now calls `backend._require_not_in_observer_callback()` immediately on entry (`teacher.py:107`), before recorder/config/scene checks or any snapshot/callback work. An outer physics, actuator or action callback cannot enter the teacher and reach the old flag assignment/finally path. A dummy backend CPU check independently confirmed the nested call raises `observer callback cannot mutate or step the backend`, the existing flag stays true, and a subsequent joint command is blocked. The backend model remained uninitialized throughout.
- Original P2, actuator observer surviving reset: `backend.reset` clears `_actuator_observer` beside `_step_observer` (`backend.py:252`) before reset/episode state initialization. Existing observer-context cleanup checks callback identity, so exiting an old context does not remove a different subsequently installed callback. Initialize already clears both observers.

The patch changes guard/cleanup behavior only. It preserves the existing teacher/executor actions and driver rules, exact commands and terminal hold metadata, per-step measured controls and timestamps, and original successful/failed ActionResult reporting. No new executor or actuator behavior was introduced.

## Verification and limits

- Independently verified all three frozen file hashes and ran the non-simulation dummy callback check described above.
- Inspected the two failing pre-fix regression cases and the supplied fix-round-1 green log (**26 passed in 3.41s**), plus the reported clean static checks. Did not rerun physical/rendering tests, any GPU/network operation or the full suite.
- Historical development data/source hashes remain historical diagnostics: 5368 raw states, 5367 actual controls and nine successful teacher actions with a separate zero-error/one-proven audit. This does not prove the fixed source version experimentally or satisfy 200 formal recovery groups or G4.
- Trusted collector/freezer integration, all formal sources and independent physical acceptance remain pending root work; this PASS applies only to the scoped passive-hook repair.
