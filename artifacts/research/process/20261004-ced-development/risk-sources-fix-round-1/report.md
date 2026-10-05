# Risk RAW source audit fix round 1 — frozen for independent re-review

The five independently reproduced RAW_EXECUTION consistency findings are repaired in the two owned files. This is an implementer verification report, **not an independent PASS or actual risk acceptance**. RISK_SUPERVISION stays UNKNOWN and formal_source_eligible stays false. No default risk fit/calibration/CLI/admission/runtime/collector file changed. Original release b8eedda6 and its independent REQUEST CHANGES report/probes remain untouched.

## Concrete repair and qualified RED

| Finding | Preserved counterexample | Result after repair |
|---|---|---|
| Hold target semantics | Complete derived SOFTWARE_ONLY 9-action/10-frame source changes a hold target by .01 at step745, then overwrites it at the same step | INVALID: every accepted hold's requested/applied target must exactly equal measured raw dispatch q; hold uses no generic joint clipping |
| Gain/range basis | Complete derived SOFTWARE_ONLY source changes gain20 to40 and coherently recomputes the equation, keeping the original asset | INVALID: registered inline XML is compiled read-only and every gain/range row must equal its original model constants |
| Empty action coverage | Derived source retains743 commands/4807 snapshots/10 frames but deletes all typed action ranges | UNKNOWN: missing required action ranges retains allocated/unknown denominator and grants no reconstruction/physical-success diagnostic |
| Fixed geometry | Derived source edits post-reset half-size and coherently recomputes its PhysicalSample | INVALID: object half-size must match the registered scene throughout the episode; region constants remain checked throughout |
| Strict typed rows | Unknown actuator field or boolean in a numeric slot; added command fields/boolean or string numeric targets | INVALID: exact ActuatorStepObservation field set, command-kind/acceptance-specific field set, and strict nonboolean finite elements are checked before numpy normalization |

`red-five-findings.log` preserves8 failures/5 passes from the first qualified regression run. That run independently exercises all three complete action sources, empty actions, unknown row field and zero-equivalent numeric coercions. `red-numeric-zero-bias.log` separately preserves the exact reviewer zero gravity-bias boolean counterexample (1 failure). Additional command schema cases have4 qualified RED failures against the untouched original source in `red-command-schema-original-frozen-source-corrected-path.log`.

The first additional command RED invocation accidentally used the live implementation because pytest's project pythonpath setting took precedence over PYTHONPATH. Its4 passes are retained and explicitly **not treated as RED evidence**; `red-command-import-setup.json` records the correction using pytest's `-o pythonpath=...` override. No original source was modified. `green-first-attempt.log` preserves47 passes/1 failure: an old controller-only fixture still expected VALID despite having commands with no typed action range. Its correct-clamp case now expects UNKNOWN with that missing-range reason; the bad-clamp case still expects INVALID. Initial Ruff E501 and a read-only missing scene key inspection are also retained as separate setup/static failures.

## Bounded controller reconstruction

The source registration must contain one exact XML payload whose original SHA matches SceneSpec.asset_family_hash. Missing/ambiguous assets, external include/file dependencies, unavailable compiler, unsupported actuator/transmission/table layouts remain UNKNOWN. Registered malformed XML or contradictory numeric constants are INVALID. The reader calls **MjModel.from_xml_string only**, reads its actuator gain/range and joint/finger ranges/static axis-aligned table height, and never creates MjData, steps, renders or dispatches.

Every raw actuator still joins the prior measured physical q, accepted command sequence, original initial targets, finger target and exact source time. The controller uses the original error clamp±.10, measured raw gravity/Coriolis bias divided by compiled gains, and compiled actuator ranges. Generalized bias, accelerations, contact forces, camera acquisition clocks and full MuJoCo dynamics are **not independently replayed** by this scope. Compiling fixed constants does not supply a physical motion certificate, risk label, wall↔simulation mapping or actual METHOD authority.

Fixed object half-size and region dimensions/position are scene-bound throughout; joint/finger ranges and static table height additionally match the registered compiled asset. Dynamic pose is not forced constant. Original actual excluded motion remains RAW-only:4806 physics steps,743 commands,9 actions,10 RGBD frames, nine UNKNOWN post-motion marker observations, original diagnostic task outcome. It remains excluded from formal/power/G3/G4 and is not a new risk population.

## Verification and immutable dependency closure

* Owned live CPU:52 passed16.74s, `green-owned-cpu.log`.
* Related risk/marker persisted-source CPU:57 passed/2 deselected1.33s, `related-read-only-cpu.log`. The two existing tests whose names contain `compiled` create MjData and perform dynamics steps; they are deliberately outside this read-only repair run. Their historical independent59-test result remains in the untouched original report.
* Completely separate immutable overlay:109 passed/2 deselected17.64s, `frozen-overlay-all-cpu.log`. It uses only511 registered source/fixture copies and an environment-only full venv directory link. `frozen-overlay-setup.json` has the exact argv/cwd/source manifest.
* Scoped Ruff and formatting checks on two files, cold mypy on the production file pass live and frozen. The existing unused mypy-section note is retained.
* Every511 source/fixture copy and both live owned hashes are checked after the overlay. All original545 archived hashes are checked separately and unchanged.

Source manifest SHA: `bb8cc8f658ebde7a8ec52d4702d8fc30d7470a4272c57ce8c5778fdd14270c1a`. It separates2 owned files from509 read-only references. The namespace basis is the historical b8eed373-file namespace with only this owned production replacement, not a claim that every subsequent live namespace edit is incorporated.68 irrelevant historical environment/cache conftests are omitted;33 exact previously independently frozen marker originals and the previously frozen calibration CLI are added to complete the scoped test closure. `source-origins.json` identifies every origin. The missing-dataset CLI test now executes its archived script from the overlay rather than relying on a moving live script.

Owned hashes: risk_sources.py `641dae4f3069186c44d955e88df4b823cee0aaa2a9849374a43e96952600cb61`; test_research_risk_sources.py `8302618524f75301b5c766b08ed59013311cdcdd9f76ede60c84bd4feabe2da4`. No more production writes are planned while independent re-review is active.

Reproduction command from an overlay containing `source/` contents and the declared interpreter environment:

```text
.venv/bin/python -m pytest -q -p no:cacheprovider -o pythonpath=src --confcutdir=. tests/test_research_risk_sources.py tests/test_rgbd_risk_calibration.py tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py -k 'not compiled'
.venv/bin/ruff check src/cloud_edge_robot_arm/research/risk_sources.py tests/test_research_risk_sources.py
.venv/bin/ruff format --check src/cloud_edge_robot_arm/research/risk_sources.py tests/test_research_risk_sources.py
.venv/bin/mypy --no-incremental src/cloud_edge_robot_arm/research/risk_sources.py
```

There are no new renderer/simulator episodes, action dispatches, model/provider/account calls, role collections, training/calibration runs, full suite or commit. Actual supervision/INITIAL/clock/calibration/finite-candidate replay/weight selection remain their own unavailable sources. The separately frozen `t9-risk-supervision-replay-design` defines the next two bounded owner modules and cannot upgrade this software verdict.
