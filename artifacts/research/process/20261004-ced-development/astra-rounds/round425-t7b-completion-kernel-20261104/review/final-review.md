# R425–R426 fresh final code review

Reviewer: actual `gpt-6-astra`, one fresh senior review. Scope: the four exact new product/test files and completed-run evidence named by `request.json`. BASE and current HEAD are `0a11393aba9e851b0e38fd469aba71ea1138307a`; these files remain untracked, so their full contents were reviewed directly. This is a precommit research-branch delivery assessment, not a main-branch merge or actual-research acceptance.

## Strengths

- `src/cloud_edge_robot_arm/vision/native_completion.py:85–120` computes the maximum of pointwise U+L+M sums, retains corresponding 3D points, validates finite inputs and derived arithmetic, and returns detached immutable results. It does not confuse endpoint error with continuous velocity or future wall-time support.
- `src/cloud_edge_robot_arm/vision/native_completion.py:165–181` uses exact integer arithmetic for ceil, tails and waits, including values beyond float precision. Explicit tail inclusion is correctly documented as a producer claim.
- `src/cloud_edge_robot_arm/research/native_completion_calibration.py:101–175` enforces all eight actions and validates malformed values even on failed rows. Lines 191–243 retain missing/failed groups and samples as infinity, merge dependency components using every assignment, and apply the fixed exact rank to components rather than actions or raw groups.
- The tests include missing observations, unavailable bridge groups, both shorter and longer terminal windows, rank 18 with 19 components, output detachment, and injected finite/VALID public facts that cannot upgrade legacy evidence. The rotation tests check all eight vertices despite identical centers.
- The source and reports consistently label the result SOFTWARE_ONLY / UNAVAILABLE. Existing runtime/configuration/controller and legacy evidence remain unchanged.

## Findings

### Critical

None found in the reviewed scope.

### Important

None found in the reviewed scope.

### Minor

None requiring an actionable review finding. No speculative or out-of-scope blocker was added.

## Evidence checked

- All 30 request pins match exact SHA256 and byte count. All 34 R425 input pins also match. All 14 R426 input pins match using the preserved preimage for the intentionally changed test.
- Rehashed the original 1311-file baseline, including 406 `src` files: no drift. Git shows only the pre-existing dirty nested gitlinks among tracked differences; no tracked product/configuration changes. Read both progress ledgers and their explicit execution rulings.
- R425 RED: 20 unique nodes, 20 expected absent-module call failures, all 20 setup and teardown passes, no duplicate node phases. Each failure is the explicit planned missing-kernel assertion; JUnit agrees.
- R425 first GREEN: 24 unique nodes, 23 call passes and one rotated-vertex oracle failure; all setup/teardown pass. The original failed test bytes match the R426 preserved preimage and R425 stage pin.
- R426 GREEN: 24 unique nodes, 24 setup/call/teardown passes, no duplicate phases or skips. The selection contains the 20 new nodes plus all four declared legacy nodes; JUnit and stdout agree. No fresh tests, product imports, runtime experiments, or subagents were used by this reviewer.
- All three recorded results report FINISHED with their expected exit codes, no source drift, signals, cancellation, remaining live descendants or abnormal adopted-child cleanup. Recorded invocation hashes match the corresponding frozen specs and unchanged R413 driver. R235 prerequisites are accepted with empty trace/profile channels before and after.
- Existing static evidence is consistent with current source pins: four-file Ruff/format and two-product-file mypy passed; R426's changed test has new Ruff/format passes. The mypy unused-configuration note is disclosed.
- Read both validation adapters. R426 reuses the frozen R425 stage specification and unchanged R413 supervisor, updates the single changed-test pin, and freezes its own adapter/plan inputs. The ledger explains why the immutable-input R425 wrapper was not reused directly. For these completed runs, source pins, stage paths, argv and result evidence support the reports; no broader fault-path certification is inferred.

## Rotation correction and plan alignment

For 90° about z, `(x,y,z) -> (-y,x,z)` and squared displacement is `(x+y)^2+(x-y)^2=2(x²+y²)=4` for x,y in {−1,1}; distance is 2. For 180°, squared displacement is `4x²+4y²=8`. This independently verifies the corrected oracle rather than using the production distance function as its own reference. The preimage/current diff changes only `test_pointwise_sum_and_rotated_vertices`; both product modules and the separate calibration test are SHA-identical to R426 intake. R425's incorrect planned sqrt8 oracle and its observed failure remain preserved, and R426 supersedes only that oracle.

The implementation matches the bounded arithmetic portions of R91 described in R425. Public scalar inputs are deliberately untrusted diagnostics; requiring the absent original-data adapter to be implemented here would expand the approved scope. No significant unrecorded deviation was found.

## Declined to judge

- **Authenticity/completeness of public point arrays, sample inventory, ancestry, fingerprints, and numeric scores; exchangeability and real-world coverage** — The reviewed pure arithmetic API explicitly makes these original-data producer proof obligations. No current result claims native authority.
- **Actual horizon execution, physical holds, unique owner, source/application registration, future wall-time D, and three native consumers** — Explicitly deferred R91 mainline work; no runtime/controller/source-index changes are part of these four new files.
- **Generic wrapper/supervisor timeout, failure-path, restart, and cross-environment reliability** — This review checks the two adapters against the three completed runs and their evidence, not an unrequested reusable runner certification.
- **R424 driver/lease behavior, prior formatting debt, full-suite health, and unrelated dirty/untracked artifacts or gitlinks** — Pre-existing material outside this change. Existing 1311-file baseline is unchanged; the four selected legacy nodes are the bounded compatibility evidence.
- **Hardware/research acceptance, success-rate or latency gains, full remote raw reproducibility, main-branch merge and eventual push success** — No such evidence or action is included in this precommit review. Software-only research-branch readiness does not establish these outcomes.

## Recommendation and assessment

**READY for scoped research-branch delivery.** No Critical or Important defect was found in the reviewed implementation or the truthfulness of these completed-run reports. The executor may proceed with the already-authorized exact-path delivery and commit-SHA checks; this review does not claim those Git actions have happened.

Continue the stated mainline next: independently reconstruct and validate original data before supplying these kernels. Native action admission remains HOLD; actual collection and formal research acceptance remain NOT_STARTED. No additional gate loop or test rerun is requested by this review.
