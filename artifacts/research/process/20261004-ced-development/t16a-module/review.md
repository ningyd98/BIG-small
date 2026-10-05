# T16a independent software review

Verdict: **REQUEST CHANGES**. Two reproducible P2 findings affect negative-result reporting and preregistered diagnostic denominators. No physical/research acceptance was enabled. Reviewer changed no production or test files.

## Released snapshot and validation

Reviewed the explicit immutable six-file release in `source-hashes.json`, `source/`, `ownership.json` and `review-package.diff`. All six owned working files and six saved copies matched the declared SHA256 at review start. Read the inherited Task16 plan and ced.research.v2 requirements, plus the original specification's G2/G3/G4 thresholds and fixed diagnostic denominators. Read-only dependencies were inspected as context, not modified.

Independent exact test command:

```bash
.venv/bin/python -m pytest -q tests/test_research_statistics.py tests/test_research_acceptance.py
```

**40 passed in 9.41s**, exit 0. Scoped Ruff passed all six files; mypy passed the four source/CLI files (unused ROS-config note only). Additionally verified the constrained q root against an independently evaluated multinomial likelihood grid for 25 count/null cases (maximum grid log-likelihood excess 1.42e-14), and checked five extreme/all-concordant interval endpoints. No broad suite, GPU/rendering/model/network, actual FINAL/selection, or real run was attempted.

## P2 — Definite G2 target failure and demonstrated inferiority are overwritten as insufficient evidence

Location: `research/acceptance.py:194–199` in the released snapshot.

`improvement_status(requests, .3)` correctly returns FAIL for a point below the 30% target. The next unconditional noninferiority failure assignment overwrites that FAIL as INSUFFICIENT_EVIDENCE. It also labels a success interval entirely below the allowed -3pp margin as merely undecided. This hides known negative results and can mislead the planned results API/UI.

Independent CPU reproductions used a valid synthetic FINAL protocol, explicit SOFTWARE_ONLY scope and full N=600 effect records:

- Requests .20, CI [.10,.25], success 0 with CI [-.031,.01], safety 0 with CI [-.001,.001]: request target is definitely failed under the point-target rule; emitted G2 status is INSUFFICIENT_EVIDENCE.
- Requests .50, CI [.40,.60], success -.50 with CI [-.55,-.45], safety 0 with CI [-.001,.001]: the entire one-sided success upper bound is below -.03; emitted G2 status is INSUFFICIENT_EVIDENCE.

Requested fix: preserve any definite target FAIL; distinguish confidently inferior success / unsafe risk from intervals crossing the NI boundary. Keep INSUFFICIENT_EVIDENCE for genuinely undecided NI or incomplete coverage. Holm failure must not erase an existing definite FAIL. Add request-failure+undecided-NI and wholly-inferior success/safety regressions. The default actual-source NOT_RUN boundary must remain unchanged.

## P2 — Preregistered UNKNOWN and fallback diagnostic denominators are missing or replaced by episode rates

Location: `research/metrics.py:67–99` in the released snapshot; original specification fixed denominators at line146.

The required UNKNOWN diagnostic is unknown condition judgments / all condition judgments; the required fallback diagnostic is fallback decisions / all decision rounds. Current code only emits UNKNOWN episodes / assigned episodes and `fallback_rate` from terminal run_status FALLBACK / episodes. The episode summaries are useful additional metrics, but they cannot stand in for the fixed diagnostics. No canonical condition or decision denominator/rate fields, or explicit unavailable status for those two required rates, are emitted.

Independent reproduction: two JOINT episodes, one containing a single UNKNOWN condition record and the other 99 PASS records, produces `unknown_episode_rate=.5` and no condition-rate keys. The declared fixed condition ratio for that synthetic complete fixture is 1/100=.01. The fallback numerator is explicitly taken from terminal episode status, not decision traces.

Requested fix: retain clearly named episode summaries separately. Emit canonical condition/decision counts and ratios only from sufficient typed source records; when full records are unavailable, use None with explicit NOT_RECORDED / not-source-verified status. Do not invent a condition/round count from the number of episodes. Rename or label the legacy fallback_rate alias with its episode basis, and add an unequal-condition-count regression plus missing-decision-source regression.

## Confirmed behavior and practical limits

- Matched binary inference retains concordance and finite positive all-concordant intervals; NI p values use their frozen -.03/+ .01 nulls rather than a zero-difference test. Zero-event group risk bounds stay positive.
- At least 10000 fixed-seed stratified paired scene-cluster bootstrap iterations; repeated seeds stay inside scene clusters and paired multiplicities are checked. Undefined relative gains/resamples remain N/A. Original intervals and full five-hypothesis Holm adjustment remain separate; missing hypotheses stay in the family with correction p=1.
- Fixed G3 opportunities retain complete snapshot IDs/hashes, UNKNOWN and VALID/INVALID denominators; replay does not add physical successes. Full FINAL analysis requires the fixed pools.json path and actual formal-pool digest, rebuilds all seven methods and full balanced ordered assignments, and retains blocked/failed/timeout records and Tcap penalties. Rehashed omitted failures fail coverage.
- Default analysis/goals always remain NOT_RUN with zero accepted physical success; caller source_verified/PHYSICS/formal_accepted flags or hashes cannot create research acceptance. SOFTWARE_ONLY numerical PASS is explicitly scoped. Actual raw physical/model/timeline verifier, accepted recovery and G0/G1/G5 evidence are not claimed.
- Machine-readable/CSV/chart outputs are deterministic and do not execute stored commands. Inputs remain unchanged.

Implementer acknowledged the findings and saved `fix-round-1-baseline/source`; fixes and a new immutable release will be reviewed separately. This report describes the original released snapshot.
