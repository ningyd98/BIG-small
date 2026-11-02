# R396 successor static review — R398 delta

Driver: 29323 bytes, SHA256 `3919f5ed871a8ff5d9ae000e7981856a6c5c5be86ff1f8e6f0ef6dc7deee3775`. Actual Astra R398 plan SHA256 `f1a95bffe2bace894b1920a09d6073ca1d415f1088d000de1abc639e5be239da`. Prior ready=false review and driver are preserved byte-exact in `round398-diagnostic-denial-reporting-20261102/inputs/`; the earlier R396 review remains frozen under R397 inputs.

## Strengths and resolutions

**R397-I1 resolved statically.** Immediately after cleanup, marker presence, exit78 or already observed AUDIT_DENIAL establishes a sticky denial before auxiliary decoding. Readers handle OSError, UTF-8/JSON errors, non-object values and consumed-field types. JSONL lines are independent, valid rows are retained, errors are identified by file/line and byte hash, and raw artifacts are never rewritten. Audit/boundary, marker, ready and child-outcome dependencies use these readers. Known denial retains highest classification precedence and nonzero return; absent known denial with corrupt observations yields UNKNOWN and nonzero. Poll entries are explicitly incomplete when reporting errors exist.

**R396-I1 remains resolved.** Exact delta confirms unconditional child exit78, defensive gates, parent ownership/cleanup, input derivation, profile/stack observation, permissions and budgets were not modified in R398.

Independent static checks: repaired driver and plan hashes, frozen prior review/driver hashes, exact recorded diff, AST parse, all 35 original input pins, and absence of run root/execution-start. No helper, driver, bad-log fixture, product import, tests, SQL, network or signal was executed.

## Issues

Critical: none. Important: none. Minor: none.

## Declined to judge

- Actual replay stack/identity, heartbeat, native completion/close and owned cleanup: required in final runtime evidence review.
- Unchanged driver paths: covered by original full review and R397 delta, with exact R398 delta verified.
- Product fixes, formal/browser acceptance and delivery: outside the static gate.

## Assessment

**Ready for the original single R396 attempt: Yes. C=0 / I=0 / M=0.** This gate binds only the above driver SHA. Original one-child/one-PCSC/one-ETEAC quotas, caps and final independent evidence review remain required. Static approval is not product PASS, ETEAC cause confirmation, historical stack proof or delivery approval.
