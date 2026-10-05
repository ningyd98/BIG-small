# T9 independent software review

Date: 2026-10-04. Reviewed all eight files listed in `software-readiness.json`, `checks.json`, the current and inherited Task 9 specification/plan, and reused dataset, observation, trajectory, and INITIAL-loading contracts. All eight current source SHA-256 values match the handoff.

**Specification and quality verdict: REQUEST CHANGES.** The feature/model/calibration preparation is coherent and remains disabled, but the acceptance command can use an unverified alternative split and does not establish its claimed source-backed selection freeze. The coverage chart is also quantitatively misleading.

Independent scoped command: `.venv/bin/python -m pytest -q tests/test_rgbd_risk_calibration.py` — **27 passed in 0.69s**. These are CPU software fixtures, including test-only source acceptance; they establish no genuine dataset/calibration acceptance. No GPU, renderer, network, model service, or full suite ran.

## P1 — the fitted partition can differ from the official payload-validated split

Location: `scripts/calibrate_rgbd_risk.py:55-66`, `:72-84`; reused validator at `datasets/rgbd/quality.py:333-363`.

`accepted_records` constructs train/calibration/selection/test from `config['split_manifest']`. `validate_dataset(root)` always verifies `reports/split_audit.json` and the corresponding committed split files. The two split objects are never compared, and the CLI does not constrain the configurable path to that official file. Consequently a second manifest may reassign an entire official test group to train while keeping all four new partitions internally disjoint. If risk supervision and the acceptance references use that second manifest, the official dataset quality check still passes but fitting consumes official held-out test sources. The later disjointness check only compares the newly chosen partitions, so it cannot detect this reassignment.

Use the exact officially verified split or independently validate the configured split against the canonical dataset assignment and committed split payloads, requiring equality before source acceptance/fitting. Add a rejection case with a valid official audit and a different configured audit; keep test/selection groups out of training and calibration.

## P2 — FROZEN selection is a YAML assertion, not a bound selection artifact

Location: `scripts/calibrate_rgbd_risk.py:172-186`, `:129-132`.

The command compares hyperparameters to hard-coded defaults and then requires only the literal `selection_status == 'FROZEN'`. It does not read/hash a selection result, verify which isolated selection groups chose those settings, bind an accepted parameter snapshot, or retain a config/selection digest in `source_bindings`. Merely changing NOT_RUN to FROZEN satisfies this gate once source labels are accepted, despite the error message promising “source-backed freezing required.” The resulting model is marked `source_accepted=True` and can produce VALID estimates. The current disabled default prevents an actual handoff claim, but the implemented acceptance path does not enforce the promised selection prerequisite.

Require a separately verified selection/parameter snapshot with its dataset split, group IDs, method/settings/source hashes and INITIAL link, and persist its digest in the model bindings. Until that evidence exists, preserve INCOMPLETE rather than using the YAML status as proof.

## P2 — the empirical coverage chart is independent of the residual values

Location: `scripts/calibrate_rgbd_risk.py:224-230`.

`coverage_points` uses only `index / len(residuals)` and `(index + 1) / len(residuals)`. Nine errors around a millimetre and nine errors around a metre produce the same line. The axes are labeled 0–1, without an error threshold or requested-coverage meaning. This is an index-rank diagonal, not an error-bound coverage curve, and cannot show whether a usable geometric bound is narrow or broad.

Plot actual error threshold in metres against the empirical fraction of independent group maxima below it, or plot requested conformal coverage against the resulting bound with clear units. Keep calibration-set and independent holdout coverage explicitly distinguished, as the reliability chart already does.

## Positive contracts / interpretation

- `RiskFeatures` has a closed observable feature/source whitelist, immutable copied values, finite numeric values, and observation identity. Revalidation rejects extra truth fields; raw true error/fault labels are not online regressor fields. Calibration fingerprint is a guard rather than a numerical regressor.
- Frame-pair motion requires fresh frame/time progression, same scene/episode/calibration and dimensions; old crops do not refresh evidence. The depth-change quantity is correctly described as a scene-motion proxy, with separate measured residual calibration required.
- Logistic regression estimates failure from dedicated offline boolean supervision, not candidate probability, perception POSITIVE status, or reported confidence. Both failure classes are required; independent calibration partitions fit an isotonic map.
- Grouped bounds use a maximum residual per physical group and the finite-sample order statistic `ceil((n+1)*coverage)`. At coverage 0.9 fewer than nine labeled groups cannot yield a finite bound. These are marginal bounds under the intended exchangeable-group assumptions, not per-action guarantees or universal OOD coverage.
- Action models require referenced checksummed feedback, a trajectory, a bound independent action result, and independent calibration. Missing/one-class action outcomes remain `None`; a VALID global estimate may still have an unknown action entry, which downstream capability filtering must reject. No LOCAL_RECOVER capability was enabled.
- Model/calibration hashes, pinned calibration filename, train/calibration provenance isolation, depth/calibration support guards, absent calibration/source acceptance, and required motion/geometry residuals prevent the tested software paths from silently becoming calibrated online evidence.
- The command separately loads an INITIAL protocol and binds its content hash, and checks exact label coverage/equality plus checksummed raw evaluator-output references and source observations. The unchanged dataset smoke run correctly remains INCOMPLETE for missing dedicated risk supervision.

## Cannot verify / deferred research acceptance

The package contains no genuine risk supervision/source acceptance, independently chosen selection freeze, real calibration quality, holdout probability/error coverage, or online policy integration. Matching a checksummed evaluator-output file to a label proves record consistency; it does not independently recompute the physical failure or geometric/motion residual from lower-level physical/geometry data, nor authenticate an arbitrary caller's `INDEPENDENT_EVALUATOR` declaration. A trusted collector/evaluator and accepted source snapshot must supply that evidence. INITIAL loading currently verifies its content hash and required binding fields; full re-audit of the new role/opportunity/fault freezer remains separate root work.

The source report honestly marks research NOT_RUN and enabled=false. Software fixtures, calibration-set isotonic reliability, and the CPU test result must not be reported as actual calibration acceptance. No production/test code was edited by this review.
