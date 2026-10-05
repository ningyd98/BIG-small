# Finite risk diagnostic replay implementation plan

> **For agentic workers:** implement this approved bounded block with superpowers:executing-plans and test-driven development, then freeze for independent review.

**Goal:** Reconstruct every preregistered candidate's fixed CPU logistic, isotonic, group-conformal, guarded prediction and Brier selection workflow, retaining original allocation and missingness denominators without actual risk or METHOD authority.

**Architecture:** Two new files only. A pure SOFTWARE_ONLY numerical kernel uses the existing fixed recipe helpers. A concrete application registry internally reconstructs its own RiskSupervisionAuditor from copied concrete registrations and passes the complete source view to that same kernel. Original config/model/calibration/selection bytes are read, compared and rehashed before/after; absent originals remain UNKNOWN comparison.

**Spec:** `t9-risk-supervision-replay-design/report.md` and its api-contract; ROOT follow-up explicitly permits diagnostic replay of the existing terminal failure target without fabricated SampleRecord/COMMIT/action labels.

**Dependencies:** exact reviewed supervision515 manifest `389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8`, review `336ff27096693abe4940c6946b62196ff04cd3f2a911a604adc62b5dfd98817c`, corrected RAW SHA `0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a`. Use a private frozen515 overlay plus only this block's new2; never overlay live RAW/event repository/worker dependencies.

**Owned new paths:**
- `src/cloud_edge_robot_arm/research/risk_replay.py`
- `tests/test_research_risk_replay.py`

## Exact API and output scope

- `required_replay_source_paths() -> tuple[str, ...]`: current validating source paths, including this module, correct supervision/RAW, risk fit/calibration/features/models and dataset model definitions.
- `risk_replay_environment() -> Mapping[str, str]`: exact local Python/Pydantic/Pillow/NumPy/OpenCV versions; no account/model/network operation.
- `supervision_registration_hash(registration: RiskSupervisionRegistration) -> str`: canonical digest of copied public original cases/counts/assignments/context/inventories, allocations, component histories, criteria, measured carriers and INITIAL/current role/source declarations. This is a consistency digest, never acceptance.
- `replay_diagnostic_candidates(allocations: Sequence[RiskObservationAllocation], reconstructed_rows: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]`: full deterministic numerical workflow. Its input/output are strictly SOFTWARE_ONLY; it cannot qualify raw, publisher, clock, source, risk, selection, METHOD, budget or execution.
- `RiskReplayArtifactRegistration(model_path: str, calibration_path: str)`: exact relative original diagnostic artifact paths.
- `RiskReplayRegistration(artifact_root: Path, original_file_hashes: Mapping[str,str], config_path: str, supervision_evidence_id: str, candidate_artifacts: Mapping[str,RiskReplayArtifactRegistration] = {}, selection_results_path: str | None = None)`: copied concrete immutable declarations.
- `RiskArtifactAuditor(registrations: Mapping[str,RiskReplayRegistration], supervision_registrations: Mapping[str,RiskSupervisionRegistration]).audit(evidence_id: str) -> RiskArtifactAudit`: accepts concrete registrations only and internally creates a concrete supervision auditor. No passed auditor, callback, private registrations, serialized eligible flag or supplied probability can provide authority.
- `RiskArtifactAudit`: schema `ced.risk-replay-audit.v1`, actual status UNKNOWN/INVALID, independent diagnostic/comparison statuses, complete counts and split counts, reasons, full candidate results, diagnostic winner only, exact original/current-source hashes and diagnostic source scope. No permission, execution, budget, METHOD or actual-positive accessor.

The frozen config has exact schema `ced.risk-replay-config.v1`, versioned finite inventory, fixed selection rule `minimum_brier_then_parameters_hash`, fixed population rule `all_allocated_observations_v1`, full candidate objects `{method, seed, settings}`, exact environment/current validating source hashes and supervision-registration hash. Fixed current SETTINGS are the only supported settings. Seeds must be explicit nonnegative bounded integers; multiple seeds require a declared versioned inventory, never a hidden CLI override. Empty/duplicate/added/incomplete objects, authority fields and schema/version/config/source mismatches fail closed.

Diagnostic model schema is `ced.risk-replay-model.v1`; calibration is `ced.risk-replay-calibration.v1`. These are not committed legacy SampleRecord/model packages. Preserve normalization/coefficient/regressor/feature schema/fingerprint/range recipes and exact canonical content hashes plus separate original raw-byte SHA. Calibration file names bind `calibration-{content_hash}.json`. Geometry is explicitly MARKER_CENTER_TRANSLATION; grouped point bounds cannot become whole-target/extent/grasp/native certificates. Current missing continuous motion and action labels remain None with counts/reasons. Original files absent means comparison UNKNOWN, never replay PASS from only a self-created hash.

## Full workflow and population rules

1. Reconstruct concrete supervision, source/hash before/after, exact case/allocation/history closure and all assigned attempts, including blocked/failed/missing sources. Registration copies detach aliases and reject subclasses/receipts.
2. Kernel validates original allocation identities/splits, duplicate/extra rows, original terminal failure horizon, full exact online feature schema, strict finite/nonboolean numbers, offline marker/motion residual scope and component/history isolation. Missing rows produce explicit placeholders with the original denominator.
3. For every candidate, train only on the full preregistered train allocation. Any missing required feature/terminal label makes training UNAVAILABLE, never silently drops a favorable subset. Use existing `logistic_fit` and fixed seed/order/SETTINGS, preserve schema/normalization/coefficients/ranges/fingerprints/provenance. Missing both failure classes is UNAVAILABLE. Do not fit action models without actual matched executed feedback; action models/coverage remain None.
4. Calibrate only on the full isolated calibration allocation, applying existing `predict`/`isotonic_fit`; one-class calibration probabilities remain unavailable. Preserve exact support, grouped maximum point/fresh-motion residuals and rank `ceil((g+1)*0.9)`. Fewer than nine groups cannot yield the corresponding finite bound. Report full allocation versus available groups/labels separately.
5. Predict each selection and test allocation using exact observable guards (invalid depth, calibration validity/fingerprint, fresh pair/interval, support), calibrated probabilities and point/motion bounds. Probability/action/bound missingness is explicit. Missing any required selection prediction makes that candidate NO_FEASIBLE; retain all sample rows and scores as None, not a survivor-only Brier.
6. Only complete feasible candidate selection populations get Brier means. Choose minimum score then canonical parameters hash deterministically. No feasible candidate yields NO_FEASIBLE; insufficient source/features/labels yields UNAVAILABLE. Test rows report frozen-result diagnostics only and never affect fit/calibration/support/winner. Keep every candidate, all failed denominators and action/motion/point missingness.
7. Registered wrapper independently compares complete stored candidate model/calibration mappings and complete selection results/winner against reconstructed diagnostic outputs. Exact deterministic comparison under pinned environment; changed raw bytes, rehashed forged probabilities/coefficients/calibration/flags, incorrect filenames or incomplete candidate inventory are INVALID. Absent originals remain UNKNOWN comparison. Recheck original and current source inventories after numerical processing.

## TDD tasks and review focus

- [x] Write missing-module tests with unregistered and subclass/receipt/API negatives, deterministic complete numerical workflow and full denominators; save exact RED source/log before production implementation.
- [x] Add independent hand-derived controls: constant balanced features give sigmoid/isotonic 0.5, Brier0.25, hash tie-break; 9 distinct groups use maximum-group rank9; 8 groups and repeated frames do not grant finite bounds; raw sigmoid differs from independently isotonic-calibrated probabilities.
- [x] Implement registration parsing and the complete kernel; run all new tests against the private frozen overlay. Hard errors require strict shape/type/overflow/schema validation rather than blanket catch.
- [x] Add qualified algorithm/source RED for missing selection rows, test-driven winner, train/calibration leakage, used holdouts, unseen fingerprint/support, raw probability forgery and rehashed original artifacts, mutable registration inputs and source drift; implement minimal fixes after each observed failure.
- [x] Run relevant CPU supervision/RAW/risk/admission tests from the reviewed515 only, explicitly deselect its known compiled-dynamics test; no full suite, simulation, renderer, model/provider/GPU/network/action. User-authorized scope overrides a skill's generic full-suite/commit suggestions.
- [x] Scoped Ruff/format on2 new files, cold mypy on1 new module, complete archive/import/test/fixture closure, isolated final replay, before/after hashes, report/diff/source manifest and independent-review handoff. Preserve every RED/setup failure and original515 package.

Likely regressions: missing frames accidentally shrink Brier denominator; invented/one-class action labels become estimates; first-frame/no-motion or fewer-than-nine point groups obtain bounds; seen/tuned components move into holdouts; mutable aliases/subclass auditors or source_accepted flags bypass source reconstruction. Each is pinned by the dedicated tests. Actual RISK/INITIAL/selection/METHOD remain UNKNOWN; materializer and actual fresh-motion/raw-v3 publishers stay distinct future responsibilities.

Final denominator supplement: distinct terminal-labelled/failure/unknown attempt counts use original task inventory, while task_labels/failed_task_observations remain frame counts. Action outcomes None and missing counts include test. Three saved qualified REDs preceded these additions.
