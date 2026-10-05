# Role visual repair: preserve the frozen action policy

Scope: SOFTWARE_ONLY. [Independent review](independent-review.md) passed: 29 frozen hashes/AST and unchanged post-test overlay; 104 CPU tests in 2.04 s, Ruff and mypy passed. Original immutable 29-file release and its root 100-test review are preserved.

Root reproduced an admitted-candidate defect with the real provider and a boundary MockTransport. The original contract allowed 0.01 m error and required RGB-D. A grounder supplied a 0.05 m bound, raised the allowance to 0.1 m and removed required sensors; the provider returned REPLANNED. This did not dispatch an action. The original independent executor gates still apply.

Four qualified RED regressions additionally isolate error tolerance, required sensors, ordinary TTL and the full action horizon. The candidate now must preserve all four fields exactly alongside the complete original pre/postcondition specifications, timing, retry and source bindings. Fresh grounded geometric measurements remain independently validated; a fresh proof cannot rewrite the frozen policy.

Final scoped command: `pytest -q tests/test_role_visual_repair.py tests/test_visual_repair_builder.py tests/test_visual_local_repair.py tests/test_phase6_2_replan_resume.py`: 104 passed in 1.81 s. Ruff checks the three owned files; mypy checks the two source files. Original combined counterexample now returns PLANNER_FAILED with no steps and one mock transport attempt. The earlier style-check failure was corrected before this freeze. These test counts overlap with the original suite and are not additive.

Manifest SHA256: `25539ff80fa1b86db73910a083cec474ab0b835754e0bd164ef4515c4aebdacf`, 29 files, three owned and 26 unchanged frozen references. This is a scoped software release; unlisted current dependencies used by test overlays are not a full transitive release declaration. All source/AST checks pass; review diff is against the preserved original release.

There were zero live cloud calls, controller commands or physical task actions. Actual Max credentials/profile, calibrated geometry/motion, source grounding and stage/resume/start gateway remain unavailable. A candidate is neither admission nor execution; LOCAL_RECOVER and INITIAL/FINAL are not accepted.

The separate `root-future-precondition-probe-clock-corrected.log` confirms another integration limit: a GRASP→LIFT candidate whose future holding precondition is currently FAIL cannot be produced by this provider. Future conditional planning, stepwise fresh grounding and apply/activation eligibility need a coordinated design; no future condition is treated as a current PASS and no submit gate was weakened. B4 actual capability remains unavailable. The first probe's pre-frame clock produced UNKNOWN and is retained separately rather than counted as defect evidence.
