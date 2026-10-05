# T10 module independent review

**REQUEST CHANGES.** Spec compliance: FAIL for clock consistency and fixed-replay evidence integrity. Code quality: CHANGES REQUIRED. Scope is the five new files in `review-package.diff`, not unimplemented runtime integration.

All five current files match `source-hashes.json` (independently recomputed SHA-256). Reviewed the local report, diff, current source, canonical `conditions.py`, T10 interfaces and G3 denominator definitions. No suite rerun, GPU, network, live capture or production/test edits. Three small CPU-only probes below exited 0 and reproduced the findings.

## F1 — P1: preconditions and action age use different clocks

Location: `src/cloud_edge_robot_arm/edge/evidence/validator.py:58, 98–100`; called canonical implementation `edge/evidence/conditions.py:91–97, 116–121`.

The action TTL/completion bound uses the caller's `now`, but `evaluate_conditions` independently reads `datetime.now(UTC)`. Thus a condition can pass even when it is already stale at the purported submission time, or a historical fixed replay can become UNKNOWN merely because it is replayed later. The same contract/input/explicit clock is not a deterministic evaluation.

**Probe:** use a fresh `target_visible` fact, `max_age_s=0.5`, motion bound zero and supplied `now` one second ahead of the fixture's NOW. Acquisition age at the supplied clock is 1.1 seconds. Both JOINT and B3 return `VALID`; the precondition should be stale/UNKNOWN at that clock. Ordinary TTL remains 5 seconds, so it does not catch this narrower condition expiry.

**Required:** route one explicit evaluation time through the existing canonical condition evaluator (with a backward-compatible default for ordinary callers). Do not implement a parallel evaluator or merely change the RGB-D timestamp. Apply the same clock to replay and both validators. Tests must cover a narrower per-condition max age and historical replay, not only action-bound/ordinary-TTL expiry.

## F2 — P1: fixed opportunity hashes omit live inputs that change the verdict

Location: `src/cloud_edge_robot_arm/edge/evidence/opportunities.py:33–68, 90–117, 121–133`; partial online binding in `validator.py:81–95`.

An Opportunity freezes/hashes its observation, contract and label, but replay takes a separate arbitrary `OnlineEvidenceSnapshot` mapping, `now` and calibration argument. Robot state, visual facts and their actual observation payload are not included in the fixed opportunity or record input hash. The validator compares only frame ID/time/calibration (plus contract versions/context), not the external snapshot's checksum/episode against the Opportunity observation. Methods can therefore evaluate different substantive precondition evidence while claiming the same fixed snapshot/candidate hash. Replaying at a different age/configuration is likewise unrecorded.

**Probe:** replay one unchanged, valid-labeled Opportunity with precondition `gripper_open`. Supply an open versus closed RobotState in its external snapshot. Verdicts are `VALID` and `INVALID`; `opportunity_hash` is identical; both summaries are accepted and report false-rejection counts 0 and 1 respectively. This is not a method difference: the evaluated evidence changed outside the hash.

**Required:** freeze/copy and hash all decision-relevant online inputs and the prescribed evaluation clock/configuration as part of the fixed replay identity, or require an immutable independently versioned replay context whose hash is checked/recorded. Bind the supplied online observation to the exact fixed observation checksum/episode. Compare methods against the same sealed inputs; reject mismatches instead of accepting alternate robot states/facts as the same opportunity. Oracle labels must remain outside online validator inputs. Add changed robot state, changed visual fact, same-ID changed observation payload/episode, and changed replay time/configuration regressions.

## F3 — P2: malformed verdict/method categories silently publish perfect rates

Location: `src/cloud_edge_robot_arm/edge/evidence/opportunities.py:127–159`; `EvidenceVerdict` and `GateReplayRecord` constructors do not validate their category fields.

The summarizer checks that all method IDs are equal, but not that the method is registered or each verdict status is VALID/INVALID/UNKNOWN. Python dataclass Literal annotations do not enforce values. An unrecognized status falls through all counters, producing zero false acceptance/rejection and zero UNKNOWN instead of rejecting corrupted evidence.

**Probe:** replace all three replay records' status with `CORRUPT` and method with `UNREGISTERED`, retaining valid opportunity hashes. Summary is accepted with total 3, eligible-valid/invalid/unknown labels each 1, both error rates 0.0, and both method-UNKNOWN counts 0.

**Required:** validate category membership at construction and/or at the summary trust boundary. Unknown schema values must fail closed as malformed records, never disappear from error/UNKNOWN accounting. Add exact rejection tests for invalid status and unsupported method.

## Verified design strengths and remaining scope

- The numerical completion rule matches the planned `error + motion * (age + duration)` calculation; missing/nonfinite/negative bounds are rejected or UNKNOWN, and integer versions reject bool aliases.
- Exact ConditionSpec objects are recomputed via the single evaluator, rather than trusting external verdicts. Nested mapping/list tolerances and sensor sequences are copied/frozen for the supported data shapes.
- B3 shares base identity, context, sensors, preconditions and ordinary TTL; it removes the calibrated completion-bound calculation. F1 affects both and must be fixed for a fair comparison.
- Commit validation checks task/episode/observation/context/candidate equality, plan/command/mode versions, cancellation, creation/expiry and nonempty provider/policy identities. Candidate generation/membership and actual dispatch remain downstream integration responsibilities.
- For well-formed records and genuinely fixed inputs, G3 denominator arithmetic matches the design: false acceptance over oracle-INVALID opportunities, false rejection over oracle-VALID safe opportunities, oracle-UNKNOWN separate; method UNKNOWN on valid/invalid opportunities is separately counted. Duplicate/missing opportunity records and changed hashed fields are rejected. F2/F3 prevent treating the current hash/counter checks as sufficient integrity.
- Labels are not passed into either online validator. Reported 74 software passes and lint/mypy results were read, not independently rerun. Existing replay tests use empty preconditions, so they do not expose F1/F2; the oracle-isolation test remains useful.

Actual frozen opportunity generation, source-backed risk calibration, paired research replay, episode-clustered inference, runtime double-check boundaries, SafetyShield and executor integration remain **cannot verify runtime/research**. These are acknowledged pending work, not reasons to claim a second engine or existing dispatch regression. The canonical `object_placed` path currently composes region/release without T7b stability; preserving T7b UNKNOWN there remains root-owned integration work outside these five files.
