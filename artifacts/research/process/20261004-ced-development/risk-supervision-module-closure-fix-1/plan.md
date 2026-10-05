# Registered Risk Supervision Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development for this bounded owner task. ROOT has already authorized inline implementation and independent review.

**Goal:** Reconstruct registered observation-level risk diagnostics and full missingness without granting actual source or execution authority.

**Architecture:** A concrete owner registry copies concrete RAW fix2 and INITIAL registrations, internally constructs their actual auditors, and rereads original frames/physics on every audit. Source-qualified status and diagnostic consistency are separate; current raw-v3 clock/calibration/label publishers and derived committed risk datasets do not exist and remain explicitly UNKNOWN.

**Tech Stack:** Python/dataclasses, strict JSON/SHA, existing RGBD, marker decoder, risk feature extractor and concrete source auditors; no simulation state/step/render/capture/provider/training.

**Spec:** `t9-risk-supervision-replay-design/report.md`, reference manifest310ed70b; ROOT's bounded raw-v3 publisher ruling. RAW dependency is independently reviewed fix2/511 manifest4ed1a5a5 and risk_sources.py0bf79e3e, never historical272595.

## Global constraints

Only create `src/cloud_edge_robot_arm/research/risk_supervision.py` and `tests/test_research_risk_supervision.py`. Preserve all prior packages/default CLI/fit/readers/collectors/workers/datasets. Caller probabilities, accepted flags, receipts, passed-in auditors and VALID callbacks confer no authority. Authorized development feedback may be explicitly train; used/viewed samples cannot become independent calibration/selection/test, and formal/power/G3/G4 exclusion remains. Missing observations/attempts remain in all original denominators.

## Concrete API

* `RiskObservationAllocation(sample_id, case_id, observation_id, split, previous_sample_id=None)` identifies an original scheduled frame. It has no supplied feature, label, probability, success or path field.
* `RiskComponentHistory(group_id, used_purposes)` records immutable application-owned history. Empty/unknown history remains UNKNOWN. Original group, physical-scene/asset, episode and image derivative connections are recomputed; history cannot split connected observations or shrink the RAW inventory.
* `RiskDiagnosticMeasurements(artifact_root, original_file_hashes, clock_path=None, calibration_path=None)` accepts only explicitly SOFTWARE_ONLY original measurement carriers, whose schema has no acceptance flag. Numeric consistency is diagnostic, never proof of an actual publisher. Original calibration reference pairs and source IDs must be separate from the target population; residuals are recomputed, not supplied risk-feature values.
* `RiskSupervisionRegistration(raw_registration, allocations, histories, initial_registration=None, diagnostic_measurements=None)` copies exact normal registries and data and fixes terminal-episode label scope. The only estimator scope is existing `MARKER_CENTER_TRANSLATION`; this is not extent/grasp/stability/whole-object calibration.
* `RiskSupervisionAuditor(registrations).audit(evidence_id) -> RiskSupervisionAudit`: opaque owner ID, immutable row diagnostics/counts/source hashes/missingness, diagnostic_status and actual_source_status separately. No method/execution admission fields or authority. Missing actual raw-v3 publishers/INITIAL/derived commits are returned by name.

Original allocations must exactly cover each case's registered frame count and reread deduplicated original frame identities. A missing attempt retains all its scheduled observations. Previous observation is the adjacent original earlier frame in the same case/split/component; caller-selected future/truth-derived previous inputs reject. Full source terminal task failure is recomputed through the concrete RAW auditor and original criterion; perception status is not the task label.

Diagnostic clock schema `risk.clock-diagnostic.v1` carries every raw step from reset through terminal with step/sim/monotonic/UTC identity. Complete coverage, finite increasing time, exact frame acquisition association and units are checked. No mapping/rate is invented. Diagnostic calibration schema `risk.calibration-diagnostic.v1` carries independent observation IDs, full camera domain, and estimated/reference3D pairs; residual norms are recomputed. Neither carrier is accepted as an actual collector by source_kind, SHA or boolean.

## Review focus and task steps

- [ ] Registry/authority RED: missing module, unregistered ID, passed auditor/callback/subclass receipt, source drift/copy mutation and original expected hashes.
- [ ] Registry GREEN: concrete copied registration, internally concrete RAW/INITIAL auditors, separate statuses and full attempt/observation counts.
- [ ] Frame/label RED: rehashed allocation omission, missing original frame/attempt, perception-label substitution, unsupported marker point geometry and complete endpoint/source joins.
- [ ] Frame/label GREEN: original decoded online-only input, offline terminal label, registered-asset marker-plane point truth and strictly scoped residual diagnostics.
- [ ] Feature/clock/split RED: labels/current true error in online calibration, future/cross-case previous frame, incomplete/malformed clock, bool/oversized numbers, camera drift, overlapping calibration IDs, used group holdout, connected source/viewpoint/duplicate-frame split and UNKNOWN history.
- [ ] Feature/clock/split GREEN: exact whitelist feature extraction, independent diagnostic norm replay, complete numeric clock checks and recomputed derivative/use-history closure. Actual qualification remains UNKNOWN with exact absent publishers.
- [ ] Scoped CPU/static checks, baseline/source hashes, failure logs, full test fixture/helper closure, immutable release and independent review. No full suite/commit or simulation/model work.

The second candidate replay module, actual raw-v3 publisher, calibration collector and new committed dataset materializer remain separate tasks. This module must report those missing capabilities rather than writing them as complete or enabling default calibration.
