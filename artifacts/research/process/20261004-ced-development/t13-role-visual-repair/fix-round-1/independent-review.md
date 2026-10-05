# Independent fix1 review — PASS within the closed software scope

Date: 2026-10-04. Reviewer: `/root/ced_runtime_baselines`. No production files were edited. This review closes the original policy-relaxation P2; it does not accept an actual method, calibration source, B4 capability, execution or physical outcome.

## Snapshot and import scope

- Exact manifest SHA256: `25539ff80fa1b86db73910a083cec474ab0b835754e0bd164ef4515c4aebdacf`.
- All **29 listed frozen files** match SHA256 and parse with AST: three owned files plus 26 frozen references. The original 29-file archive is retained by the owner.
- Independent overlay: `/tmp/role-provider-fix1-independent-jyq16z_y`. Tests use explicit `PYTHONPATH=<overlay>/src:<overlay>` and run from that overlay.
- The release is not a complete transitive snapshot. **568 unlisted current Python dependencies/test support files** were copied before verification; their observed hashes and exact setup are recorded in `independent-review-setup.json`. Listed files were then overwritten from the immutable release. PASS is limited to this declared SOFTWARE_ONLY overlay; it is not a full transitive frozen-source acceptance.

## Original finding closed

Previously the actual provider with a software MockTransport accepted a local grounder's changed proof: the original error limit 0.01 m became 0.1 m, a 0.05 m bound became acceptable and required RGB-D sensors were removed. Independently reviewed frozen code now compares the grounded proof's allowed error, required sensors, ordinary TTL and action duration exactly with the original source policy. It also preserves the original step's skill, conditions, timing and retry requirements. A rewritten proof can satisfy canonical numeric validation and still cannot replace the original policy.

The original executable counterexample now returns `PLANNER_FAILED`, one software MockTransport attempt and **zero candidate steps**, with zero live model calls/controller commands (`independent-review-counterexample.log`). The preserved owner RED log shows all four regressions previously returned REPLANNED.

Additional independent probes (`independent-policy-probes.py/.log`) exercised all four changes separately: error tolerance, required sensors, TTL and expected duration. Each altered proof was explicitly checked by the canonical validator and was otherwise `VALID`; each provider call nevertheless returned `PLANNER_FAILED` with zero candidate steps. This establishes the frozen-policy boundary itself, rather than rejection caused by an unrelated malformed/failing proof. All calls used the same fake transport; no endpoint was contacted.

## Verification

Exact CPU command:

```text
PYTHONPATH=/tmp/role-provider-fix1-independent-jyq16z_y/src:/tmp/role-provider-fix1-independent-jyq16z_y <project>/.venv/bin/python -m pytest -q tests/test_role_visual_repair.py tests/test_visual_repair_builder.py tests/test_visual_local_repair.py tests/test_phase6_2_replan_resume.py
```

Result: **104 passed in 2.04s**, saved in `independent-review-tests.log`. The four regression cases are included; they are not added to that count. Scoped Ruff for the three owned files passes. Native mypy with `--no-incremental --follow-imports=silent` for the two owned production sources passes; its existing unused optional-module configuration note is retained in the log. Hash/AST checks precede these tests.

## Separate integration limit remains

The corrected-clock future-step probe was independently repeated from the same overlay (`independent-future-precondition-limit.log`). A coherent pending GRASP→LIFT sequence with an open, empty gripper gives the future LIFT `gripper_holding` condition canonical **FAIL** before GRASP. Current provider validation checks every future step's action preconditions immediately, so it returns `MORE_OBSERVATION_REQUIRED` before any wire attempt, with zero steps. The earlier owner log using NOW before capture yielded UNKNOWN; that log is historical, and the corrected NOW+0.2s result is the meaningful FAIL case.

This is a documented conditional-planning limitation, separate from fix1's policy bypass. Actual B4 capability is not established. A future design must preserve each original immutable canonical requirement and dependency, distinguish a conditional future candidate from current execution permission, and obtain a new current proof after earlier effects complete. It must retain fresh versions, deadlines, native bounds and SafetyShield at the actual submit boundary. No current gate should be weakened to label a future condition PASS or to give the whole plan immediate authority.

## Limits

The review accepts the narrow original-policy preservation correction and the observed software behavior. Actual source/current owner registration, genuine calibrated geometry/motion proof, INITIAL/selection prerequisites, live Max execution, candidate apply/activation and physical validation are outside this review. A typed source or candidate is not ACK, action start or success. No actual admission or motion claim follows from this PASS.
