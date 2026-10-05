# Independent review: risk RAW numerical fix round 2

Verdict: **PASS for the bounded RAW source-consistency software scope.** The fix1 oversized-integer finding is closed. No actual risk, calibration, INITIAL, METHOD or execution admission is claimed.

The reviewed immutable release manifest is `4ed1a5a571cfca7d43a77ca79c86964ec08da887e87663031df55078cbfac552`, 511 files: two owned sources and 509 unchanged fix1 references. Independent reconstruction used the independently reviewed T8 fix3 immutable768 base plus all exact511 released copies. The merged899-file overlay has zero differing-byte overwrites and131 new paths. `independent-review-setup.json` records the actual path and `independent-merged-source-hashes.json` every imported source/fixture byte. No moving live source or helper was used; the environment-only `.venv` directory link supplies the already installed interpreter/packages.

The narrow change preserves strict int/float rejection of booleans/strings, converts a numeric input to float with a specific OverflowError→ValueError diagnostic, then rejects nonfinite values. It does not catch arbitrary exceptions around the whole auditor or change thresholds. The original public10**500 actuator-vector probe now returns INVALID, allocated=unknown=1 and reconstructed=physical_success=0; it does not raise uncaught OverflowError. Four dedicated tests cover positive/negative oversized values in the vector and registered physics_dt. They retain the exact original file inventory and withhold fully verified hashes/formal eligibility.

The original full9-action/10-frame copied-source probes independently close the hold-current-q, asset-gain, absent typed action interval and post-reset geometry findings: altered controls/geometry return INVALID and commands without action ranges return UNKNOWN. The strict unknown-field and numeric-boolean regressions remain in the56 owned tests. A baseline copied historical RAW episode still reconstructs its diagnostic physical trace, with formal_source_eligible=false; that diagnostic is neither a risk supervision result nor a method/physical acceptance badge.

## Fresh verification

* Independent frozen CPU command:113 passed,2 deselected in18.61s (`independent-cpu.log`), including56 owned and57 related source/calibration/marker tests.
* Scoped Ruff check/format of two owned files and cold mypy of the production source pass (`independent-ruff.log`, `independent-format.log`, `independent-mypy.log`).
* Original public overflow and full-source probes exit0 against the frozen overlay (`independent-original-overflow-counterexample.log`, `independent-original-full-counterexample-check.log`).
* Post-test all511 new archive hashes, all899 overlay hashes/AST and both live-owned hashes match. Original545 and fix1/511 archives and both original review reports remain byte-identical (`independent-post-hash-check.json`).

Exact scoped command, run from the declared overlay:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q -p no:cacheprovider -o pythonpath=src --confcutdir=. tests/test_research_risk_sources.py tests/test_rgbd_risk_calibration.py tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py -k 'not compiled'
```

The two deselected pre-existing tests instantiate simulator state and perform passive stepping; they are outside this read-only review. The historical original review's broader wording is corrected in `../risk-sources-module/scope-erratum.md` and `.json`; neither the original report nor its source manifest was rewritten. This run may compile registered MuJoCo model constants, but creates no simulator episode/state, performs no physics step, capture/render/controller action/provider inference/account call, and changes no production source, dataset, defaults or admission flags.

RAW scope still checks recorded source constants/equations/joins rather than generalized bias or full dynamics. Complete original wall↔simulation clocks, supervision horizons, actual calibration/INITIAL/billing/source acceptance and finite method selection remain unavailable. RISK_SUPERVISION remains UNKNOWN, formal eligibility false and actual INITIAL/METHOD NOT_RUN. No new finding remains open in this narrow numerical fix.
