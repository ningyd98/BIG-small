# Risk source fix2 preparation — DESIGN_ONLY while fix1 is under review

ROOT approved the bounded numerical repair after the independent fix1 review reports its precise additional P2. Both owned files and all511 fix1 source copies remain frozen; this draft executes no tests and changes no production file.

The software counterexample is a rehashed original actuator row containing `pre_gravity_bias_nm[0] = 10**500`. The present `_number` calls `math.isfinite` on that integer, raising OverflowError instead of returning the registered attempt as INVALID with its expected original inventory and unknown denominator. This is an exception/typed-source boundary, not an admission bypass.

After the review handoff, append qualified regressions to the owned test file and run them against the unchanged fix1 implementation before editing production. Positive and negative oversized integers should each exercise an actuator vector and the registered physics_dt scalar. Assert INVALID, allocated=unknown=1, reconstructed=physical_success=0, exact expected original hash keys retained, no verified complete case hashes, and formal_source_eligible false.

Then `_number` must first require the exact int/float types, explicitly convert to float inside a small OverflowError handler that raises a reasoned ValueError, and run finite validation on the converted value. Booleans, strings and nonfinite floats continue to reject. Do not catch all audit exceptions or grant availability to a malformed source. No calibration/CLI/admission/runtime/collector changes are included.

Run the full owned/related read-only/frozen-overlay CPU commands and scoped static checks, preserve RED and setup failures, then publish a new immutable fix2 source manifest/report/diff. Original545, fix1/511, the independent reviews and oversized-int self-audit remain historical and untouched. Risk supervision, actual INITIAL/METHOD and formal acceptance remain UNKNOWN/NOT_RUN.
