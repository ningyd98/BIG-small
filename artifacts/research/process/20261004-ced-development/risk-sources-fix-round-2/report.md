# Risk RAW source numerical fix round 2 — immutable handoff

Fix1 independent review closed the original five source-consistency findings and reported the additional oversized-integer P2. This round changes only the owned `_number` conversion and adds four software regressions. It is an implementer-verified release for independent re-review, not an actual risk or method acceptance. Original545, fix1/511, both independent reports/probes and the separate self-audit remain unchanged.

The exact int/float type check still rejects booleans and strings. The helper then explicitly converts to float, converts only OverflowError into a reasoned ValueError, and applies the existing finite check to the converted value. There is no blanket exception handler or relaxed numeric threshold. The ordinary typed INVALID path retains the allocated attempt, unknown denominator, complete expected original hashes and false formal eligibility.

`red-overflow-typed-boundary.log` preserves four qualified RED failures before production edits: positive/negative10**500 in an actuator vector and in the registered physics_dt scalar. The same tests now assert INVALID, allocated=unknown=1, reconstructed=physical_success=0, exact expected original inventory retained and no fully verified case hash. Every original five-finding and full9-action/10-frame regression remains present.

Verification:

* Owned suite:56 passed17.08s (`green-owned-cpu.log`).
* Complete511-copy isolated overlay:113 passed/2 deselected17.65s (`frozen-overlay-all-cpu.log`). The two pre-existing dynamics-stepping tests remain outside the read-only run, as in fix1.57 related source/calibration/marker tests are included.
* Live and frozen scoped Ruff/format on two files and cold mypy on one production file pass. The existing unused mypy-section note is retained.
* All511 new source copies and both owned live hashes verified after tests. All545 original and511 fix1 archive source hashes remain unchanged.

The source manifest is `4ed1a5a571cfca7d43a77ca79c86964ec08da887e87663031df55078cbfac552`:2 owned and509 exact reviewed fix1 read-only references, with no moving helper dependency or whole-current-namespace claim. Owned source hashes are risk_sources.py `0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a` and test_research_risk_sources.py `941fec5d6b27a2cbe2a53f060c828d2fc93531816a25505523d6a0aa80d831d4`. `review-package.diff` contains only the narrow change against fix1. No more owned writes are planned during independent re-review.

`frozen-overlay-setup.json` contains exact argv/cwd/environment-link and all check results. From an overlay populated with `source/` contents and the declared interpreter environment:

```text
.venv/bin/python -m pytest -q -p no:cacheprovider -o pythonpath=src --confcutdir=. tests/test_research_risk_sources.py tests/test_rgbd_risk_calibration.py tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py -k 'not compiled'
.venv/bin/ruff check src/cloud_edge_robot_arm/research/risk_sources.py tests/test_research_risk_sources.py
.venv/bin/ruff format --check src/cloud_edge_robot_arm/research/risk_sources.py tests/test_research_risk_sources.py
.venv/bin/mypy --no-incremental src/cloud_edge_robot_arm/research/risk_sources.py
```

No renderer, simulator episode/step, action, model/provider/account call, capture, role collection, training/calibration, shared default change, full suite or commit occurred. RAW scope still verifies registered recorded constants/equations/joins, not full dynamics or generalized bias, original wall↔sim clocks, risk horizons/labels/calibration/finite selection. RISK_SUPERVISION remains UNKNOWN, formal_source_eligible remains false and actual INITIAL/METHOD remain NOT_RUN. The separately frozen26-reference supervision/replay design is the next bounded source scope, not a current positive.
