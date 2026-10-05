# Independent bounded motion residual review

Verdict: REQUEST_FIX for one P2 immutable-input issue. The 13 new CPU tests passed independently in 7.03 seconds (exit 0). This review is restricted to CALIBRATION_INPUT and makes no actual-source, calibration, continuous-motion or native certificate claim. Production files were not edited and no broader suite, renderer, physical step or provider call ran.

## Finding

P2 — `_registered_point` reads `case.marker_registration` without requiring the concrete immutable `PoseMarkerRegistration`. The containing concrete `RiskSourceRegistration` retains a `RawCaseRegistration` whose marker can be a mutable caller-owned `SimpleNamespace`. A COMPLETE existing software raw graph and hash-matched immutable XML yielded AVAILABLE with residual 2.1908204622631042 m/s. Mutating the retained marker-size alias from 0.045 to 0.0525 then made the same registration, raw source digest and XML bytes yield UNAVAILABLE. This contradicts the immutable registration input contract. The existing supervision registration already requires the exact marker type, but this module does not pass through that validator.

The counterexample is saved in `independent-review-counterexample.json`; no fake measurement authenticity or execution authority is claimed. Require the exact marker registration type and detach/reconstruct it before field use in this module, with a qualified software regression. This can remain a one-module change without editing shared risk source code. The result's UNKNOWN actual-source status and NOT_CERTIFIED continuous-motion status stayed intact throughout the counterexample.

## Reviewed behavior

The lower wall-time elapsed bracket is next PHYSICS_STEP start mono-before minus prior endpoint interval end mono-after; the upper bracket is next interval end mono-after minus prior interval start mono-before. Nanoseconds are divided by 1e9, displacement is metres, and speed bounds use displacement/upper and displacement/lower respectively. The first endpoint is the original BEFORE_SUBMIT acquisition with its exact joined physics state; subsequent endpoints use the recorded physical intervals. Nonpositive/overlapping brackets produce unavailable input. The max_sample_gap_s criterion is explicitly enforced against simulation-time sample gaps, while residual speeds and the reused depth observable use wall time. Raw UTC mapping must be BRACKETED.

The function freshly replays the entire supplied raw-v3 graph. Missing/invalid graph or mapping produces no numeric residual and keeps every allocated action row. Original action endpoints, half-open command range, expected duration and requirement hash remain present even for unavailable inputs. The exact BEFORE_SUBMIT ONLINE input and immediately prior completed ONLINE acquisition feed the existing observation-only depth temporal maximum. The raw source digest binds the replayed graph. Asset selection requires a unique registered XML digest equal to the raw identity asset hash and the provided bytes; the point is reconstructed from XML geometry and recorded proper rotations, without an arbitrary caller point or simulation velocity substitution.

Concrete CompletionCriteria is required; all scalar fields reject boolean coercion, nested workspace bounds are detached into tuples, original criteria are preserved and hashed, and wrong object/region criteria do not produce a numeric row. Produced points, segments, reasons and rows are tuples/frozen dataclasses. Sampled secants may miss between-step excursions and are not continuous motion bounds. The scene-wide depth temporal maximum is not target-specific marker tracking. Registered inventory/live disk authenticity and risk activation are explicitly outside this pure CALIBRATION_INPUT scope; their absence is not a finding here.

## Evidence and scope

Independent command: `PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_motion_residuals.py`; result `13 passed in 7.03s`, exit 0, saved in `independent-review-tests.log`.

Reviewed module SHA256: `74fb8e7a53d52d6aff793a2264018fb4c6a4d4c7179eae8781050f1ea61cfa35`.

Reviewed test SHA256: `0ced3fe25d394699c6b44db4385e237b6ddcf37e277b02f248a1a30b154dba36`.

Both hashes matched readiness.json and were rechecked after the independent run and counterexample. Scope stays CALIBRATION_INPUT / actual-source UNKNOWN / continuous motion NOT_CERTIFIED. This review neither accepts actual calibration data nor admits METHOD/INITIAL/FINAL or native execution. The finding applies to this exact pre-fix source; any owner fix requires a separate bounded follow-up check.


## Post-fix independent re-review — 2026-10-05

Final bounded verdict: PASS / original P2 finding CLOSED for this exact fixed source. This supersedes the historical REQUEST_FIX verdict only for the fixed hashes below; the original review, 13-test result and initial counterexample above remain preserved.

The fix requires `type(marker) is PoseMarkerRegistration`, then reconstructs it with `replace(marker)` to rerun registration validation before any geometry field is used. The additional regressions reject mutable carriers and subclasses, and reject a forged dictionary on an otherwise genuine frozen marker instance. The original COMPLETE raw graph and mutable caller alias counterexample was replayed independently: both before and after external marker-size mutation yield UNAVAILABLE with identical `concrete_pose_marker_registration_required` reasons. Observed motion, sampled secant and residual fields remain null, segments are empty, and original action range (120,124) / command range [1,2) are retained. No numeric label is produced for this mismatch. Evidence is `independent-review-fix1-counterexample.json`; the original `independent-review-counterexample.json` is unchanged.

Independent command: `PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_motion_residuals.py`. The original 13 plus three new cases passed: **16 passed in 9.25s**, exit 0, saved in `independent-review-fix1-tests.log`. Only this assigned suite and the exact software counterexample replay ran in this follow-up. Production source was not edited, no wider source audit was required, and no actual capture, renderer, provider call or physical step occurred.

Fixed module SHA256: `7412d44d0a821b44064302008fec08950c2e8898be44e3a4ac4cd325628374f4`.

Fixed test SHA256: `3cff610cd152f4447c58a24baf70e51868c6cbce09e9af4032f0083f5573fa2e`.

Both final hashes were independently rechecked after tests and the counterexample. Scope remains CALIBRATION_INPUT; actual-source status stays UNKNOWN and continuous motion remains NOT_CERTIFIED. This PASS accepts only the bounded software preparation/type fix. It is not an actual calibration, continuous-motion, native geometry/motion, INITIAL/METHOD/FINAL or execution certificate.
